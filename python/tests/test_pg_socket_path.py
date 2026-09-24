"""The socket-path guard and the argument validation around the cluster.

None of these tests need PostgreSQL: they cover the refusals that must happen
before a single binary is executed.
"""

from __future__ import annotations

import pytest

from testisolation import pgcluster
from testisolation.pgcluster import (
    SUN_PATH_MAX,
    EphemeralCluster,
    PostgresUnavailable,
    SocketPathTooLong,
    check_socket_dir,
    find_binaries,
    socket_path_for,
)


def test_socket_path_is_the_postgres_socket_file():
    assert socket_path_for("/dev/shm/stpg-abc", 5432) == "/dev/shm/stpg-abc/.s.PGSQL.5432"


def test_a_short_socket_dir_passes_and_returns_the_socket_path():
    path = check_socket_dir("/dev/shm/stpg-abc", 5432)
    assert path == "/dev/shm/stpg-abc/.s.PGSQL.5432"


def _dir_of_socket_path_length(length: int, port: int) -> str:
    """A directory whose socket path is exactly ``length`` bytes."""
    suffix = f"/.s.PGSQL.{port}"
    directory = "/d" + "x" * (length - len(suffix) - 2)
    assert len(directory + suffix) == length
    return directory


def test_the_limit_is_exact_at_the_boundary():
    at_limit = _dir_of_socket_path_length(SUN_PATH_MAX, 5432)
    assert len(check_socket_dir(at_limit, 5432).encode()) == SUN_PATH_MAX

    one_over = _dir_of_socket_path_length(SUN_PATH_MAX + 1, 5432)
    with pytest.raises(SocketPathTooLong) as excinfo:
        check_socket_dir(one_over, 5432)
    message = str(excinfo.value)
    assert str(SUN_PATH_MAX) in message
    assert str(SUN_PATH_MAX + 1) in message
    # The remediation must name the escape route, not just the problem.
    assert "socket_parent" in message
    assert "/dev/shm" in message


def test_the_port_counts_toward_the_limit():
    """The socket file name carries the port, so a longer port shortens the dir."""
    directory = _dir_of_socket_path_length(SUN_PATH_MAX, 5432)
    with pytest.raises(SocketPathTooLong):
        check_socket_dir(directory, 54321)


def test_a_socket_dir_with_whitespace_is_refused():
    with pytest.raises(ValueError, match="whitespace"):
        check_socket_dir("/dev/shm/stpg abc", 5432)


def test_an_explicit_socket_parent_that_is_too_long_is_an_error_not_a_fallback():
    """An explicit choice is never silently replaced by a working one."""
    too_long = "/" + "x" * (SUN_PATH_MAX + 10)
    cluster = EphemeralCluster("TEST_DSN", socket_parent=too_long)
    with pytest.raises((SocketPathTooLong, PostgresUnavailable)):
        cluster.start()


def test_dsn_env_has_no_default():
    with pytest.raises(ValueError, match="no default name"):
        EphemeralCluster("")


@pytest.mark.parametrize(
    "name",
    [
        'evil"; DROP DATABASE postgres; --',
        "has space",
        "1leading_digit",
        "has-dash",
        "",
        "x" * 64,
    ],
)
def test_database_names_outside_the_closed_character_set_are_refused(name):
    with pytest.raises(ValueError, match="not accepted"):
        EphemeralCluster._check_name(name)


@pytest.mark.parametrize("name", ["test_a", "_x", "T1", "x" * 63])
def test_ordinary_database_names_are_accepted(name):
    EphemeralCluster._check_name(name)


def test_generated_names_are_unique_and_acceptable():
    names = {EphemeralCluster.generate_name() for _ in range(50)}
    assert len(names) == 50
    for name in names:
        EphemeralCluster._check_name(name)


def test_missing_binaries_report_precisely_what_is_missing(monkeypatch):
    monkeypatch.setattr(pgcluster.shutil, "which", lambda name: None)
    monkeypatch.setattr(pgcluster, "BINARY_SEARCH_DIRS", ())
    with pytest.raises(PostgresUnavailable) as excinfo:
        find_binaries()
    message = str(excinfo.value)
    for binary in ("initdb", "pg_ctl", "psql"):
        assert binary in message
    assert "server package" in message


def test_binary_discovery_finds_a_fedora_style_usr_bin_layout(tmp_path, monkeypatch):
    """No PATH entry, no versioned directory, no pg_ctlcluster wrapper."""
    bindir = tmp_path / "usr" / "bin"
    bindir.mkdir(parents=True)
    for name in ("initdb", "pg_ctl", "psql"):
        binary = bindir / name
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)
    monkeypatch.setattr(pgcluster.shutil, "which", lambda name: None)
    monkeypatch.setattr(pgcluster, "BINARY_SEARCH_DIRS", (str(bindir),))

    binaries = find_binaries()
    assert binaries.initdb == bindir / "initdb"
    assert binaries.pg_ctl == bindir / "pg_ctl"
    assert binaries.psql == bindir / "psql"
    assert binaries.bindir == bindir
