# testisolation (Go)

Uncompromising test isolation: your tests structurally cannot touch your real files, secrets, or git identity -- First-class support for Go, Python with pytest, and TypeScript with Node

This is the Go module. The isolation is the `hygiene` package -- a throwaway HOME,
an isolated git config and identity, transport lockdown, credential stripping,
and cleanup-restoring chdir. A second package in the same module, `pgcluster`,
boots a throwaway PostgreSQL cluster for suites that need a real database.

```bash
go get github.com/stricttools/testisolation/go
```

```go
import "github.com/stricttools/testisolation/go/hygiene"

func TestSomething(t *testing.T) {
	hygiene.Isolate(t)
	// HOME is a throwaway directory, git reads an empty global config under a
	// throwaway identity, only file:// transports are allowed, and every
	// ambient credential variable is gone -- all restored when the test ends.
}
```

## Surface

### hygiene

| Helper | What it binds |
|--------|---------------|
| `Isolate(t, opts...)` | Everything below, in one call |
| `ThrowawayHome(t) string` | `HOME` / `USERPROFILE` and `XDG_CONFIG_HOME` / `XDG_DATA_HOME` / `XDG_CACHE_HOME` / `XDG_STATE_HOME` → a temporary directory (memoized per test) |
| `IsolateGitConfig(t)` | Empty `GIT_CONFIG_GLOBAL`, a `GIT_CONFIG_SYSTEM` carrying only `maintenance.auto = false` (no background `git maintenance` racing test cleanup), throwaway author and committer identity, `GIT_TERMINAL_PROMPT=0` |
| `LockdownTransports(t)` | `GIT_ALLOW_PROTOCOL=file`, plus `GIT_SSH_COMMAND` and `GIT_PROXY_COMMAND` pinned to `/bin/false` |
| `StripCredentials(t)` | Removes every variable in `CredentialVars` |
| `Chdir(t, dir)` | Working directory for the test, restored afterwards (a failed restore fails the test) |
| `Preserve(v ...KnownVar)` | `Isolate` option: keeps the named toolchain caches pointing at the real home |

Every helper takes a `testing.TB`, undoes itself through `TB.Cleanup`, and
mutates the environment through `TB.Setenv` -- which panics when the test has
called `t.Parallel`. That is intended: a parallel test cannot own a
process-wide variable like `HOME`.

### pgcluster

[`pgcluster/`](pgcluster/) is a cluster *launcher*, one layer below the per-test
database managers consumers already have: `initdb --no-sync` into tmpfs, a
postmaster with `fsync=off` on a short dedicated unix socket and no TCP listener
at all, and a base libpq URL exported under the environment variable **you**
name. One shared cluster per test binary, many ephemeral databases inside it --
booting a cluster costs about a second, creating a database inside a running one
costs milliseconds. It drives `initdb`, `pg_ctl` and `psql` as subprocesses and
never links a driver, so adopting it cannot drag a database driver into a
consumer's module graph.

```go
import "github.com/stricttools/testisolation/go/pgcluster"

var cluster *pgcluster.Cluster

func TestMain(m *testing.M) {
	started, err := pgcluster.Start("MYAPP_DATABASE_URL")
	switch {
	case errors.Is(err, pgcluster.ErrPostgresUnavailable):
		// Leave cluster nil; each test skips with err.Error().
	case err != nil:
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	default:
		cluster = started
	}
	code := m.Run()
	if cluster != nil {
		cluster.Stop()
	}
	os.Exit(code)
}

func TestSomething(t *testing.T) {
	url := cluster.Database(t)
	// MYAPP_DATABASE_URL now names a fresh empty database, dropped when t ends.
}
```

| Helper | What it does |
|--------|--------------|
| `Start(dsnEnv, opts...) (*Cluster, error)` | Boots the cluster and exports its base URL; takes no `testing.TB`, so it belongs in `TestMain` |
| `Cluster.Stop()` | Stops the postmaster, removes everything it wrote, restores `dsnEnv`; idempotent |
| `Ephemeral(t, dsnEnv, opts...) *Cluster` | The TB-bound alternative: a whole cluster scoped to one test, shut down through `TB.Cleanup`. Fails the test rather than returning an error |
| `Cluster.Database(t) string` | A fresh database for the duration of `t`, exported under `dsnEnv` and dropped afterwards |
| `Cluster.CreateDatabase(name)` / `DropDatabase(name)` | The same pair without a `testing.TB`; an empty name gets a generated one |
| `Cluster.SQL(stmt)` / `SQLIn(db, stmt)` | One statement through `psql`, trimmed output |
| `FindBinaries(extraDirs...) (Binaries, error)` | Locates `initdb`, `pg_ctl` and `psql` -- the "should this suite skip?" answer, replayable through the `UseBinaries` option |
| `CheckSocketDir(dir, port) (string, error)` | The `sun_path` guard, usable on its own |
| Options | `Port`, `Superuser`, `MaintenanceDB`, `DataParent`, `SocketParent`, `UseBinaries`, `StartTimeout` |

There is no default for `dsnEnv`: the variable an application reads its
connection string from is the application's decision, and guessing it would
either do nothing or silently point production configuration at a test cluster.
Every error wraps a sentinel -- `ErrPostgresUnavailable`, `ErrSocketPathTooLong`,
`ErrInvalidArgument`, `ErrCluster` -- so a machine without a PostgreSQL server
skips with the discovery message verbatim instead of failing. The kernel's
107-byte `sun_path` limit (`SUNPathMax`) is checked before anything is executed,
so a long temp path fails with a precise message rather than an unexplained
`bind()` error.

One thing is documented rather than solved: a test binary killed outright
(SIGKILL, a cancelled CI job) never runs `Stop`, and Go has no `atexit` to reap
the postmaster the way the Python launcher does. Everything the package creates
is named `stpg-*`, so `pkill -f stpg-` and `rm -rf /dev/shm/stpg-*` clear the
strays; the package documentation explains why no substitute is shipped.

## No network guard, and what that means for a database driver

There is no network guard here. Go has no `sys.addaudithook` equivalent, so
network isolation for Go suites belongs to the sandbox runner, not to this
module.

It is worth being exact that an in-process guard would not close the database
case even where one exists. The Python plugin's socket guard is built on
`sys.addaudithook`, which sees only connects made through Python's `socket`
module, so a libpq-backed driver (`psycopg`) opens its connection inside a C
extension where no audit event is ever raised -- the guard cannot see such a
connection, cannot refuse it, and cannot be made to allow it, so an allowlist
entry changes nothing for it in either direction. The protection that does work
is the same in every language and is structural rather than a stance: point the
application's DSN at an ephemeral cluster, and a connection nothing ever saw
still lands in a throwaway database on a private socket. See the `pgcluster`
package documentation ("No in-process network guard can see a C driver") and the
[repository README](../README.md)'s Scope section.

## License

MIT
