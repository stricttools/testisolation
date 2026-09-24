+++
title = "CLAUDE.md"
+++
# testisolation

Always-on test isolation: a pytest plugin (`python/`), a Go module
carrying the same environment isolation plus an ephemeral PostgreSQL launcher (`go/`), and
a Node env-hygiene package (`typescript/`).

## Layout

| Path | Releasable | Registry | Notes |
|------|-----------|----------|-------|
| `python/` | `py-testisolation` | PyPI (`testisolation`) | hatchling, src layout, `pytest11` entry point |
| `go/` | `go-testisolation` | Go module proxy | `github.com/stricttools/testisolation/go`, library artifact |
| `typescript/` | `ts-testisolation` | npm (`testisolation`) | ESM, Node >= 22, `node:test` |

## Rules for this repo

- **The plugin must stay dependency-light and framework-free.** It depends on
  `pytest` and the standard library, nothing else. Consumers adopt it before
  they adopt anything else in the fleet, so it must never require them to
  upgrade another package first.
- **No implicit safety defaults.** The socket stance, both allowlists, and the
  sandbox stance are required ini keys. Never add a default for one to make
  adoption smoother -- the configure-time abort is the feature.
- **No escape hatches.** No `--disable-testisolation`, no env var that turns the
  isolation off, no "warn instead of fail" mode. If a guard is wrong, fix the guard.
- **Closed enums stay closed.** `testisolation_preserve` accepts only names in
  `PRESERVE_VARS`. Never accept a raw environment variable name.
- **The three implementations stay in lockstep.** The credential list and the preserve
  enum are duplicated in Python, Go and TypeScript on purpose (each implementation must
  be readable on its own), and `python/tests/test_cross_language_parity.py`
  reads the Go and TypeScript sources to prove they have not drifted. Changing
  one list means changing all three in the same commit.
- **Nothing half-guarded.** The socket guard exists only in Python because only
  Python has `sys.addaudithook`. Never add a `net.Dial` or
  `net.Socket.prototype.connect` patch to the Go module or the npm package: a
  partial guard reads as a guarantee and is worse than none.
- **Never write that the socket guard covers a libpq driver.** The audit events
  are raised by Python's `socket` module, so `psycopg` -- a C extension --
  connects where the hook never runs. There is no event to allow, so
  `testisolation_unix_socket_allowlist` changes nothing for it in either
  direction. `asyncpg` is pure Python, is seen, and does need the allowlist
  entry. Any doc that mentions the guard and a database driver in the same
  breath has to make that distinction.
- **The two cluster launchers stay in lockstep.** `python/src/testisolation/pgcluster.py`
  and `go/pgcluster/` boot the same cluster: the same `initdb` and `pg_ctl`
  flags, the same 107-byte `sun_path` refusal, the same parent-candidate order,
  the same closed database-name character set, the same `PG*` environment
  scrub. Changing one means changing the other in the same commit. The one
  documented divergence is the killed-binary postmaster leak: Python reaps
  through `atexit`, Go has no equivalent and says so in its package doc.
- **Guards raise `BaseException` subclasses on purpose.** `NetworkBlocked` and
  `pytest.fail`'s `Failed` slip past production `except Exception` handlers so a
  swallowed refusal cannot become a silent pass. Do not "fix" this.
- **Every isolation piece has a meta-test.** A guard with no test proving it fires is
  not shipped.

## Development

```bash
cd python && uv run pytest        # plugin suite
cd go && go test ./... -race
cd typescript && npm test         # builds, type-checks, then node --test
```

The plugin is active in its own suite via the entry point, so `python/pyproject.toml`
carries the required safety keys like any consumer. Tests that need a different
stance run an inner pytest session through the `pytester` fixture in a
subprocess, because the audit hook is permanent for the life of a process.

## Release workflow

This is an rlsbl monorepo with three releasables.

- `rlsbl monorepo release init`, then edit `.rlsbl-monorepo/releases/unreleased.toml`
- `rlsbl monorepo release run --no-allow-dirty --watch --yes`
- Never publish manually.

## License

MIT
