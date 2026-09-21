+++
title = "README.md"
+++
# stricttest

Uncompromising test isolation: your tests structurally cannot touch your real files, secrets, or git identity -- First-class support for Go, Python with pytest, and TypeScript with Node

| Component | Install | Location |
|-----------|---------|----------|
| **Pytest plugin** | `pip install stricttest` | [python/](python/) |
| **Go env-hygiene module** | `go get github.com/smm-h/stricttest/go` | [go/](go/) |
| **Node env-hygiene package** | `npm install --save-dev stricttest` | [typescript/](typescript/) |

The three ship from one repository and a cross-language test holds their
credential lists and preserve enums in lockstep, so a polyglot repo gets the
same guarantee in every language it tests in.

## What the isolation does

Installing the pytest plugin IS adoption -- there is no opt-in switch. Once
installed, every session binds:

- **Environment overrides.** A throwaway `HOME`, `USERPROFILE` and XDG directory set,
  created before any conftest module is imported.
- **Throwaway git identity and config.** `GIT_CONFIG_GLOBAL` / `GIT_CONFIG_SYSTEM`
  point at a session-local file carrying `protocol.ssh.allow=never` and a
  throwaway commit identity; `GIT_AUTHOR_*` / `GIT_COMMITTER_*` are pinned to it.
- **Transport lockdown.** `GIT_ALLOW_PROTOCOL=file`; ssh, proxy, terminal prompt
  and askpass are wired to hard-fail.
- **Credential stripping.** GitHub, npm, PyPI, cargo, AWS, Cloudflare and model
  API tokens plus the SSH agent socket are removed from the environment.
- **Socket guard.** A `sys.addaudithook` guard that refuses network connects,
  datagram sends and name resolution, with host:port and unix-socket-path
  allowlists. Default is network-off.
- **Push guard.** A real `git push` to a non-local remote fails the test at the
  `subprocess.Popen` boundary.
- **Cwd isolation.** Every test runs chdir-ed into its own `tmp_path`, so an
  unanchored git command cannot operate on the development repo. Opt out per
  test with `@pytest.mark.repo_cwd`.
- **TMPDIR refusal.** A `TMPDIR` or `--basetemp` inside the repository aborts the
  session, because fixture temp dirs inside a repo let unanchored git commands
  walk up and commit junk.
- **Bare-run refusal.** A run collecting more than the threshold outside the
  sandbox runner is refused; small targeted runs stay bare-runnable.

## Configuration

Everything lives in `[tool.pytest.ini_options]`. Five safety keys are
**required**; a missing one aborts at configure time. There are no defaults for
them, on purpose.

```toml
[tool.pytest.ini_options]
stricttest_sockets = "deny"              # "deny" | "allowlist"
stricttest_socket_allowlist = []         # ["example.com:443", "[::1]:5432"]
stricttest_unix_socket_allowlist = []    # ["/run/pg/.s.PGSQL.5432"]
stricttest_loopback = "deny"             # "deny" | "allow"
stricttest_sandbox_required = "false"    # "true" once a sandbox runner exists
```

Optional keys, with their defaults:

| Key | Default | Meaning |
|-----|---------|---------|
| `stricttest_threshold` | `50` | Bare-run refusal threshold |
| `stricttest_sandbox_env` | `STRICTTEST_SANDBOX` | Env var the sandbox runner sets to `1` |
| `stricttest_runner_command` | `scripts/test.sh` | Command named in the refusal message |
| `stricttest_tmp_prefix` | `stricttest-env-` | Prefix of the throwaway env directory |
| `stricttest_git_user_name` | `stricttest` | Throwaway commit identity |
| `stricttest_git_user_email` | `stricttest@example.invalid` | Throwaway commit identity |
| `stricttest_preserve` | *(empty)* | Toolchain caches preserved across the HOME repoint |

`stricttest_preserve` accepts only a closed enum of known-safe toolchain
variables -- `go_path`, `go_mod_cache`, `go_cache`, `python_user_base`,
`cargo_home`, `rustup_home`, `npm_cache`, `uv_cache`, `pip_cache`,
`gradle_user_home`. Arbitrary environment variable names are rejected so a
credential vector can never become preservable by typo.

## Ephemeral PostgreSQL

`stricttest.pgcluster` boots a throwaway cluster for suites that need a real
database. It is a cluster *launcher*, one layer below the per-test database
managers consumers already have: `initdb --no-sync` into tmpfs, a postmaster on
a short dedicated unix socket with `fsync=off`, and a base libpq URL exported
under the environment variable **you** name. One shared cluster per session,
one ephemeral database per test.

```python
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
```

There is no default for `dsn_env`: the variable an application reads its
connection string from is the application's decision. The kernel's 107-byte
`sun_path` limit is checked before anything is executed, so a long temp path
fails with a precise message instead of an unexplained `bind()` error.

The cluster listens on a unix socket only, and what the socket guard makes of
that depends on the driver. `asyncpg` connects through Python's `socket`
module, so the guard sees it and the socket directory's parent has to be in
`stricttest_unix_socket_allowlist` (e.g. `/dev/shm/`). `psycopg` and everything
else built on libpq connect inside a C extension, where no audit event is ever
raised -- the guard cannot see those connections, cannot refuse them, and
cannot be made to allow them, so an allowlist entry changes nothing for them in
either direction. Pointing the application's DSN at this cluster is what
protects a libpq consumer, and it is structural rather than a stance: a
connection the guard never saw still lands in a throwaway database on a private
socket. `psql` subprocesses are outside the guard for the same reason and need
nothing.

Go suites get the same launcher as [`go/pgcluster`](go/pgcluster/): `Start` and
`Stop` for `TestMain`, `Ephemeral` and `Database(t)` for a test, sentinel
errors so a machine without PostgreSQL skips instead of failing, and the same
zero-dependency rule -- `initdb`, `pg_ctl` and `psql` are subprocesses, never a
linked driver. One difference is documented rather than solved: Go has no
`atexit`, so a test binary killed outright (SIGKILL, a cancelled CI job) leaves
its postmaster running where the Python launcher would have reaped it.

## The Go module

Go suites get the same environment isolation as a package of explicit helpers, since
Go has no plugin mechanism to bind one automatically:

```go
func TestSomething(t *testing.T) {
	hygiene.Isolate(t)
}
```

One call gives the test a throwaway `HOME` and XDG directory set, an empty git
config with a throwaway identity, `GIT_ALLOW_PROTOCOL=file` with git's ssh and
proxy helpers pinned to `/bin/false`, and an environment stripped of every
ambient credential -- all restored when the test ends. `ThrowawayHome`,
`IsolateGitConfig`, `LockdownTransports`, `StripCredentials` and `Chdir` are
exported individually, and `Preserve(hygiene.GoModCache, ...)` keeps the named
toolchain caches pointing at the real home. Every helper mutates the environment
through `TB.Setenv`, which panics under `t.Parallel` -- intended, since a
parallel test cannot own a process-wide variable like `HOME`. See
[go/](go/) for details.

## The npm package

Node suites get the same environment isolation, in the shape Node's runner allows:

```ts
import { test } from "node:test";
import { isolate } from "stricttest";

test("something", (t) => {
	isolate(t);
});
```

`node:test`'s `TestContext` is the cleanup registry the helpers bind to, so no
adapter is needed; other runners need a one-line literal (`{ after:
onTestFinished }` for vitest). The same pieces are exported individually --
`throwawayHome`, `isolateGitConfig`, `lockdownTransports`, `stripCredentials`,
`chdir` -- and `isolate(t, { preserve: ["goCache", ...] })` keeps the named
toolchain caches pointing at the real home. Node offers no `TB.Setenv`
equivalent, so the package detects the conflict directly: a test that finishes
its isolation while another's is still open fails with an explanatory error
rather than letting one test's `HOME` leak into another's.

Bare-run refusal is a function the consumer calls, `requireSandbox`, because
`node --test` runs each test file in its own child process and an `--import`ed
setup module is loaded in those children, never in the parent that owns the run
-- so a setup module can never learn how large the run is. The honest call sites
are a programmatic runner entry (`policy: "threshold"`, with the file count it
already has) or a setup module (`policy: "always"`, refusing every bare run).
See [typescript/](typescript/) for details.

## Scope

The socket guard sees the connects, datagram sends and name resolution made
through Python's `socket` module -- resolution included, because a DNS query for
a forbidden host has already left the machine by the time a connect could be
refused. Network performed by a spawned subprocess (git, gh, psql) is invisible
to it;
whole-process network isolation is the sandbox runner's job. The guard is the
in-process guard beneath it, not a replacement for it.

A C extension that calls `connect()` itself is invisible to the guard too. The
audit events are raised by Python's `socket` module, so a libpq-backed driver
(`psycopg`) or any other native client connects at a level the hook never runs
at. No allowlist entry helps -- there is no event to allow or deny -- and no
stance offered here protects such a consumer. Clients written in Python
(`asyncpg`, `httpx`, `requests`, `urllib`) go through `socket` and are covered.
For the rest the protection has to be structural: an ephemeral database at the
end of the socket, or the sandbox runner's network namespace.

There is no socket guard in the Go module or the npm package at all. Neither
language has a `sys.addaudithook` equivalent -- an interception point the
runtime itself calls and that cannot be removed once installed. The nearest
substitutes (patching `net.Dial`, patching `net.Socket.prototype.connect`) miss
datagrams, miss native code, and are undone by anything that re-imports the
module, and a partial guard reads as a guarantee. Network isolation for Go and
Node suites belongs entirely to the sandbox runner. The npm package omits a push
guard for the same reason: patching `node:child_process` is equally porous, and
transport lockdown already closes the outcome.

## License

MIT
