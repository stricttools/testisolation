"""An ephemeral PostgreSQL cluster for test suites.

This is a cluster *launcher*, one layer below the per-test database managers
that consumers already have: it boots a real postmaster on a private tmpfs
directory with fsync off, hands back a base libpq URL, and shuts the cluster
down again. Creating and dropping a database per test is then an ordinary
``CREATE DATABASE`` against that URL.

The model is one shared cluster per session, many ephemeral databases inside
it. Booting a cluster costs roughly a second; creating a database inside a
running one costs milliseconds. A per-test cluster would be neither.

A consumer writes its own fixtures -- the plugin deliberately ships none, so
that a suite with no database pays nothing::

    import pytest
    from stricttest.pgcluster import ephemeral_cluster

    @pytest.fixture(scope="session")
    def pg():
        with ephemeral_cluster(dsn_env="MYAPP_DATABASE_URL") as cluster:
            yield cluster

    @pytest.fixture
    def db_url(pg):
        with pg.database(export=True) as url:
            yield url

There is no default name for ``dsn_env``: the variable an application reads its
connection string from is the application's decision, and guessing it would
either do nothing or silently point production configuration at a test cluster.

Nothing here is imported by the plugin itself. The module depends only on the
standard library and the PostgreSQL binaries it launches -- ``initdb``,
``pg_ctl`` and ``psql`` -- so the plugin keeps its "pytest and the standard
library, nothing else" rule.

**Interaction with the socket guard.** The cluster listens on a unix socket
only. What that means for the socket guard depends entirely on how the driver
is implemented, and the answer is not the one an allowlist key suggests.

``asyncpg`` speaks the wire protocol from Python and opens its connection
through ``socket``, so the audit hook fires and the guard refuses the connect
unless it is allowlisted. A suite that reaches the cluster through asyncpg must
allowlist the socket directory's parent as a prefix::

    stricttest_unix_socket_allowlist = ["/dev/shm/"]

``psycopg`` -- and anything else built on libpq -- is a C extension. The
connect happens inside libpq, never through Python's ``socket`` module, so no
audit event is ever raised. The guard does not see the connection, cannot
refuse it, and cannot be made to allow it: there is no event to allow. Adding
the socket directory to ``stricttest_unix_socket_allowlist`` changes nothing
for a libpq consumer, in either direction, and no stance this plugin offers
protects one. The same is true of ``psql``, which is a subprocess.

The protection that does work for every driver is this module. Point the
application's DSN at the ephemeral cluster and a connection the guard never
saw still lands in a throwaway database on a private socket rather than on a
real server. That is structural rather than a policy, which is why it holds for
the drivers the guard is blind to.
"""

from __future__ import annotations

import atexit
import glob
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

# ---------------------------------------------------------------------------
# The socket-path limit
# ---------------------------------------------------------------------------

# A unix socket address is a fixed-size ``sockaddr_un.sun_path`` char array.
# Linux gives it 108 bytes INCLUDING the NUL terminator, so 107 usable bytes;
# the BSDs are smaller still (104). The limit is enforced by the kernel, not by
# PostgreSQL, and it applies to the full socket FILE path -- the directory plus
# PostgreSQL's own ``.s.PGSQL.<port>`` name. Exceeding it fails at bind() time
# with a message that names neither the limit nor the path, which is why this
# module refuses up front instead.
SUN_PATH_MAX = 107

# The socket file PostgreSQL creates inside the socket directory.
SOCKET_FILE_TEMPLATE = ".s.PGSQL.{port}"

# Candidate parents for the socket directory, in order. Short paths first: the
# whole point is to stay far below SUN_PATH_MAX, and a session TMPDIR (which
# under a sandbox runner can be deeply nested) is the last resort.
DEFAULT_SOCKET_PARENTS = ("/dev/shm", "/tmp")

# Candidate parents for the data directory, in order. tmpfs first -- the data
# directory of a throwaway cluster should never touch a disk.
DEFAULT_DATA_PARENTS = ("/dev/shm",)

# Directories searched for the PostgreSQL binaries when PATH does not carry
# them. Fedora installs the server binaries straight into /usr/bin (no
# per-version directory, no pg_ctlcluster wrapper); Debian and the PGDG
# packages use versioned directories.
BINARY_SEARCH_DIRS = (
    "/usr/bin",
    "/usr/local/bin",
    "/usr/lib/postgresql/*/bin",
    "/usr/pgsql-*/bin",
    "/usr/local/pgsql/bin",
    "/opt/homebrew/opt/postgresql*/bin",
)

REQUIRED_BINARIES = ("initdb", "pg_ctl", "psql")

# A database name this module will create or drop. Deliberately narrower than
# what PostgreSQL accepts: the name is interpolated into SQL, and a closed
# character set is a stronger guarantee than a quoting routine.
_SAFE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


class PostgresUnavailable(RuntimeError):
    """No usable PostgreSQL installation was found on this machine.

    Raised by :func:`find_binaries` and by :meth:`EphemeralCluster.start`. It
    carries a precise reason so a test can skip with it verbatim::

        try:
            binaries = find_binaries()
        except PostgresUnavailable as exc:
            pytest.skip(str(exc))
    """


class SocketPathTooLong(ValueError):
    """A socket directory would produce a path past the kernel's sun_path limit."""


class PostgresClusterError(RuntimeError):
    """A PostgreSQL program this module ran failed.

    The message carries the command, its output, and the server log when one
    exists -- a bind() failure or a refused start says nothing useful on its
    own.
    """


# ---------------------------------------------------------------------------
# Binary discovery
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Binaries:
    """Resolved paths to the PostgreSQL programs this module runs."""

    initdb: Path
    pg_ctl: Path
    psql: Path

    @property
    def bindir(self) -> Path:
        return self.initdb.parent


def _search_dirs(extra_dirs: Sequence[str | Path]) -> list[Path]:
    """Expand the search-dir globs into existing directories, newest first."""
    found: list[Path] = [Path(d) for d in extra_dirs]
    for pattern in BINARY_SEARCH_DIRS:
        if "*" in pattern:
            # Descending so a newer major version wins over an older one, and
            # so the choice never depends on directory order.
            found.extend(sorted((Path(p) for p in glob.glob(pattern)), reverse=True))
        else:
            found.append(Path(pattern))
    return [d for d in found if d.is_dir()]


def find_binaries(extra_dirs: Sequence[str | Path] = ()) -> Binaries:
    """Locate ``initdb``, ``pg_ctl`` and ``psql``.

    PATH wins; otherwise the layouts in :data:`BINARY_SEARCH_DIRS` are searched
    in order. ``extra_dirs`` is searched before either. Raises
    :class:`PostgresUnavailable` naming exactly what was missing and where it
    was looked for.
    """
    dirs = _search_dirs(extra_dirs)
    resolved: dict[str, Path] = {}
    missing: list[str] = []
    for name in REQUIRED_BINARIES:
        on_path = shutil.which(name)
        if on_path:
            resolved[name] = Path(on_path)
            continue
        for directory in dirs:
            candidate = directory / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                resolved[name] = candidate
                break
        else:
            missing.append(name)
    if missing:
        raise PostgresUnavailable(
            "PostgreSQL is not usable on this machine: "
            f"{', '.join(missing)} not found on PATH nor in "
            f"{', '.join(str(d) for d in dirs) or '(no candidate directory exists)'}. "
            "Install the PostgreSQL server package (the client package alone is "
            "not enough -- initdb and pg_ctl ship with the server)."
        )
    return Binaries(
        initdb=resolved["initdb"], pg_ctl=resolved["pg_ctl"], psql=resolved["psql"]
    )


# ---------------------------------------------------------------------------
# The socket-path guard
# ---------------------------------------------------------------------------


def socket_path_for(directory: str | Path, port: int) -> str:
    """The socket file PostgreSQL will create for ``port`` in ``directory``."""
    return str(Path(directory) / SOCKET_FILE_TEMPLATE.format(port=port))


def check_socket_dir(directory: str | Path, port: int) -> str:
    """Validate a socket directory, returning the socket path it would produce.

    Raises :class:`SocketPathTooLong` when the resulting socket path would not
    fit in ``sockaddr_un.sun_path``, and :class:`ValueError` when the path
    contains whitespace (the directory is passed to the postmaster inside a
    space-separated options string, where a space would silently split it).
    """
    path = socket_path_for(directory, port)
    if any(char.isspace() for char in path):
        raise ValueError(
            f"socket directory {directory!r} contains whitespace. The path is "
            "passed to the postmaster in a space-separated options string, "
            "where it would be split apart. Choose a directory without spaces."
        )
    length = len(path.encode())
    if length > SUN_PATH_MAX:
        raise SocketPathTooLong(
            f"the unix socket path would be {length} bytes, past the kernel's "
            f"{SUN_PATH_MAX}-byte sun_path limit:\n\n    {path}\n\n"
            "This is a hard kernel limit, not a PostgreSQL setting, and it "
            "applies to the whole path including PostgreSQL's "
            f"'{SOCKET_FILE_TEMPLATE.format(port=port)}' file name. Point the "
            "cluster's socket directory at a shorter parent -- '/dev/shm' or "
            "'/tmp' -- with the socket_parent argument."
        )
    return path


def _pick_parent(
    explicit: str | Path | None,
    candidates: Sequence[str],
    *,
    port: int,
    check_socket: bool,
    what: str,
) -> Path:
    """Choose a parent directory, explicitly or from the candidate list.

    An explicit choice is never second-guessed: if it is unusable, that is an
    error, not a reason to quietly use something else. Without one, the
    candidates are tried in their fixed order and the first usable one wins.
    """
    if explicit is not None:
        parent = Path(explicit)
        if not parent.is_dir():
            raise PostgresUnavailable(
                f"the {what} parent {parent} does not exist or is not a directory."
            )
        if check_socket:
            # Probe with the longest name mkdtemp can produce below it.
            check_socket_dir(parent / ("stpg-" + "x" * 8), port)
        return parent

    tried: list[str] = []
    for candidate in candidates:
        parent = Path(candidate)
        if not parent.is_dir() or not os.access(parent, os.W_OK):
            tried.append(f"{parent} (missing or not writable)")
            continue
        if check_socket:
            try:
                check_socket_dir(parent / ("stpg-" + "x" * 8), port)
            except (SocketPathTooLong, ValueError) as exc:
                tried.append(f"{parent} ({exc.__class__.__name__})")
                continue
        return parent

    fallback = Path(tempfile.gettempdir())
    if fallback.is_dir() and os.access(fallback, os.W_OK):
        if check_socket:
            check_socket_dir(fallback / ("stpg-" + "x" * 8), port)
        return fallback
    tried.append(f"{fallback} (missing or not writable)")
    raise PostgresUnavailable(
        f"no usable {what} directory. Tried: {'; '.join(tried)}. Pass an "
        f"explicit {what} parent."
    )


# ---------------------------------------------------------------------------
# The cluster
# ---------------------------------------------------------------------------

# Server settings that make a throwaway cluster fast. Every one of them trades
# crash safety for speed, which is the correct trade for a cluster whose data
# directory is deleted at the end of the session and lives on a tmpfs anyway.
FAST_SETTINGS = (
    "fsync=off",
    "full_page_writes=off",
    "synchronous_commit=off",
    "wal_level=minimal",
    "max_wal_senders=0",
    "autovacuum=off",
)


class EphemeralCluster:
    """A throwaway PostgreSQL cluster on a private tmpfs directory.

    Use :func:`ephemeral_cluster` rather than constructing and starting this
    directly unless the start and stop must be separated.
    """

    def __init__(
        self,
        dsn_env: str,
        *,
        port: int = 5432,
        superuser: str = "postgres",
        maintenance_db: str = "postgres",
        data_parent: str | Path | None = None,
        socket_parent: str | Path | None = None,
        binaries: Binaries | None = None,
        start_timeout: int = 60,
    ) -> None:
        if not dsn_env:
            raise ValueError(
                "dsn_env is required: the cluster's DSN is exported under the "
                "environment variable the consuming application reads its "
                "connection string from. There is no default name."
            )
        self.dsn_env = dsn_env
        self.port = port
        self.superuser = superuser
        self.maintenance_db = maintenance_db
        self.start_timeout = start_timeout
        self._data_parent = data_parent
        self._socket_parent = socket_parent
        self._binaries = binaries
        self._data_dir: Path | None = None
        self._socket_dir: Path | None = None
        self._logfile: Path | None = None
        self._previous_dsn: str | None = None
        self._dsn_was_set = False
        self._running = False

    # -- state ------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._running

    @property
    def socket_dir(self) -> Path:
        """The directory holding the cluster's unix socket."""
        if self._socket_dir is None:
            raise RuntimeError("the cluster is not started")
        return self._socket_dir

    @property
    def data_dir(self) -> Path:
        if self._data_dir is None:
            raise RuntimeError("the cluster is not started")
        return self._data_dir

    @property
    def socket_path(self) -> str:
        """The full path of the cluster's unix socket file."""
        return socket_path_for(self.socket_dir, self.port)

    @property
    def base_url(self) -> str:
        """The libpq URL of the maintenance database.

        This is what gets exported under ``dsn_env``, and what a per-test
        database manager connects to in order to ``CREATE DATABASE``.
        """
        return self.url_for(self.maintenance_db)

    def url_for(self, dbname: str) -> str:
        """The libpq URL of ``dbname`` in this cluster."""
        host = quote(str(self.socket_dir), safe="")
        return (
            f"postgresql://{quote(self.superuser)}@/{quote(dbname)}"
            f"?host={host}&port={self.port}"
        )

    # -- lifecycle --------------------------------------------------------

    def start(self) -> EphemeralCluster:
        """initdb into tmpfs, start the postmaster, export the DSN."""
        if self._running:
            return self
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            raise PostgresUnavailable(
                "PostgreSQL refuses to run as root, so an ephemeral cluster "
                "cannot be started by a root process. Run the suite as an "
                "unprivileged user."
            )
        binaries = self._binaries or find_binaries()
        self._binaries = binaries

        data_parent = _pick_parent(
            self._data_parent,
            DEFAULT_DATA_PARENTS,
            port=self.port,
            check_socket=False,
            what="data",
        )
        socket_parent = _pick_parent(
            self._socket_parent,
            DEFAULT_SOCKET_PARENTS,
            port=self.port,
            check_socket=True,
            what="socket",
        )
        self._data_dir = Path(tempfile.mkdtemp(prefix="stpg-data-", dir=data_parent))
        self._socket_dir = Path(tempfile.mkdtemp(prefix="stpg-", dir=socket_parent))
        # The real directory exists now; re-check the real path rather than the
        # probe used to choose the parent.
        check_socket_dir(self._socket_dir, self.port)
        self._logfile = self._data_dir.parent / (self._data_dir.name + ".log")

        atexit.register(self.stop)
        try:
            self._initdb()
            self._pg_ctl_start()
        except BaseException:
            self.stop()
            raise

        self._running = True
        self._export_dsn()
        return self

    def stop(self) -> None:
        """Stop the postmaster and delete everything it wrote (idempotent)."""
        atexit.unregister(self.stop)
        if self._running:
            self._running = False
            self._restore_dsn()
        if self._data_dir is not None and (self._data_dir / "postmaster.pid").exists():
            # -m immediate: no checkpoint, no clean shutdown bookkeeping. The
            # data directory is about to be deleted, so durability is pointless
            # and the shutdown should be as fast as the boot was.
            self._run(
                [
                    str(self._binaries.pg_ctl),  # type: ignore[union-attr]
                    "-D",
                    str(self._data_dir),
                    "-m",
                    "immediate",
                    "-w",
                    "-t",
                    str(self.start_timeout),
                    "stop",
                ],
                check=False,
            )
        for path in (self._data_dir, self._socket_dir, self._logfile):
            if path is not None:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    try:
                        path.unlink()
                    except OSError:
                        pass
        self._data_dir = None
        self._socket_dir = None
        self._logfile = None

    # -- databases --------------------------------------------------------

    @staticmethod
    def generate_name() -> str:
        """A fresh, unique, always-acceptable database name."""
        return "test_" + uuid.uuid4().hex[:16]

    def create_database(self, name: str | None = None) -> str:
        """Create a database in this cluster and return its libpq URL.

        Without a name, a fresh unique one is generated -- the ordinary
        per-test case.
        """
        name = name or self.generate_name()
        self._check_name(name)
        self.sql(f'CREATE DATABASE "{name}"')
        return self.url_for(name)

    def drop_database(self, name: str) -> None:
        """Drop a database, disconnecting anything still attached to it."""
        self._check_name(name)
        # WITH (FORCE) terminates leftover connections instead of failing on
        # them: a test that leaked a connection should not break teardown.
        self.sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')

    @contextmanager
    def database(
        self, name: str | None = None, *, export: bool = False
    ) -> Iterator[str]:
        """Create a database for the block's duration and drop it afterwards.

        With ``export=True`` the database's URL replaces the cluster's base URL
        under ``dsn_env`` for the duration, so an application that reads its
        connection string from the environment lands in the per-test database.
        """
        dbname = name or self.generate_name()
        url = self.create_database(dbname)
        previous = os.environ.get(self.dsn_env)
        if export:
            os.environ[self.dsn_env] = url
        try:
            yield url
        finally:
            if export:
                if previous is None:
                    os.environ.pop(self.dsn_env, None)
                else:
                    os.environ[self.dsn_env] = previous
            self.drop_database(dbname)

    # -- queries ----------------------------------------------------------

    def sql(self, statement: str, *, dbname: str | None = None) -> str:
        """Run one SQL statement through ``psql`` and return its output.

        A subprocess rather than a driver on purpose: the plugin depends on
        pytest and the standard library only, and a database driver would be a
        third dependency every consumer inherits.
        """
        url = self.url_for(dbname) if dbname else self.base_url
        result = self._run(
            [
                str(self._binaries.psql),  # type: ignore[union-attr]
                "--no-psqlrc",
                "--quiet",
                "--no-align",
                "--tuples-only",
                "--set=ON_ERROR_STOP=1",
                "--dbname",
                url,
                "--command",
                statement,
            ]
        )
        return result.stdout.strip()

    # -- internals --------------------------------------------------------

    @staticmethod
    def _check_name(name: str) -> None:
        if not _SAFE_NAME.match(name):
            raise ValueError(
                f"database name {name!r} is not accepted. Names created or "
                "dropped through this helper must match "
                f"{_SAFE_NAME.pattern} -- the name is interpolated into SQL, "
                "and a closed character set is a stronger guarantee than a "
                "quoting routine."
            )

    def _env(self) -> dict[str, str]:
        """A clean environment for the PostgreSQL programs.

        Every ``PG*`` variable is dropped: an ambient PGHOST, PGDATABASE,
        PGSERVICE or PGPASSFILE would silently redirect these commands at the
        developer's real cluster. The locale is pinned so error messages are
        the ones this module's callers expect to match on.
        """
        env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
        env["LC_ALL"] = "C"
        env["LANG"] = "C"
        return env

    def _run(
        self, argv: list[str], *, check: bool = True
    ) -> subprocess.CompletedProcess:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            env=self._env(),
            check=False,
        )
        if check and result.returncode != 0:
            raise PostgresClusterError(self._failure_message(argv, result))
        return result

    def _failure_message(
        self, argv: list[str], result: subprocess.CompletedProcess
    ) -> str:
        message = (
            f"{Path(argv[0]).name} failed with exit status {result.returncode}.\n"
            f"command: {' '.join(argv)}\n"
        )
        if result.stdout.strip():
            message += f"stdout:\n{result.stdout.strip()}\n"
        if result.stderr.strip():
            message += f"stderr:\n{result.stderr.strip()}\n"
        if self._logfile is not None and self._logfile.exists():
            log = self._logfile.read_text(errors="replace").strip()
            if log:
                message += f"server log:\n{log}\n"
        return message

    def _initdb(self) -> None:
        self._run(
            [
                str(self._binaries.initdb),  # type: ignore[union-attr]
                "--pgdata",
                str(self._data_dir),
                # The cluster is deleted at the end of the session, so paying
                # for durable initialization would be pure waste.
                "--no-sync",
                "--username",
                self.superuser,
                "--auth-local=trust",
                "--auth-host=reject",
                "--encoding=UTF8",
                "--locale=C",
            ]
        )

    def _pg_ctl_start(self) -> None:
        options = [
            # No TCP at all: the cluster is reachable through its unix socket
            # and nothing else, so it cannot collide with a real local server
            # and cannot be reached from off the machine.
            "-c listen_addresses=",
            f"-c unix_socket_directories={self._socket_dir}",
            f"-p {self.port}",
        ]
        options.extend(f"-c {setting}" for setting in FAST_SETTINGS)
        self._run(
            [
                str(self._binaries.pg_ctl),  # type: ignore[union-attr]
                "-D",
                str(self._data_dir),
                "-l",
                str(self._logfile),
                "-o",
                " ".join(options),
                "-w",
                "-t",
                str(self.start_timeout),
                "start",
            ]
        )

    def _export_dsn(self) -> None:
        self._previous_dsn = os.environ.get(self.dsn_env)
        self._dsn_was_set = self.dsn_env in os.environ
        os.environ[self.dsn_env] = self.base_url

    def _restore_dsn(self) -> None:
        if self._dsn_was_set and self._previous_dsn is not None:
            os.environ[self.dsn_env] = self._previous_dsn
        else:
            os.environ.pop(self.dsn_env, None)
        self._previous_dsn = None
        self._dsn_was_set = False


@contextmanager
def ephemeral_cluster(dsn_env: str, **kwargs) -> Iterator[EphemeralCluster]:
    """Start a throwaway cluster for the block's duration.

    ``dsn_env`` names the environment variable the base URL is exported under;
    every other argument is :class:`EphemeralCluster`'s. The cluster is stopped
    and its directories removed on the way out, including when the block raises.
    """
    cluster = EphemeralCluster(dsn_env, **kwargs)
    cluster.start()
    try:
        yield cluster
    finally:
        cluster.stop()
