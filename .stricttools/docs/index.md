+++
title = "stricttest"
description = "Always-on test isolation for Python, Go, and Node suites: what each of the three implementations carries, the required pytest ini keys, and the libpq caveat."
nav_order = 0
+++

# stricttest

Uncompromising test isolation: your tests structurally cannot touch your real files, secrets, or git identity -- First-class support for Go, Python with pytest, and TypeScript with Node

Three implementations ship the same guarantees for three languages:

| Package | Registry | What it carries |
|---------|----------|-----------------|
| `stricttest` (Python) | PyPI | The pytest plugin: environment overrides, git identity pinning, credential stripping, the socket audit hook, the push guard, a per-test `chdir` into `tmp_path`, and the ephemeral PostgreSQL launcher |
| `github.com/smm-h/stricttest/go` | Go module proxy | The env-hygiene package and the ephemeral PostgreSQL launcher |
| `stricttest` (npm) | npm | The env-hygiene package for Node test runners |

Installing the pytest plugin *is* adoption -- there is no opt-in switch. Five keys under `[tool.pytest.ini_options]` are required and have no defaults, so every repo chooses its socket, allowlist, loopback, and sandbox stances deliberately: `stricttest_sockets`, `stricttest_socket_allowlist`, `stricttest_unix_socket_allowlist`, `stricttest_loopback`, `stricttest_sandbox_required`.

## The libpq caveat

The socket guard is built on Python's audit hooks, which only fire for connections made through Python's `socket` module. `asyncpg` is pure Python and is seen. `psycopg` and everything else built on libpq connect inside a C extension where no audit event is ever raised, so the guard can neither see nor refuse those connections.

Database isolation must therefore be structural: point the application's DSN at the ephemeral cluster from `stricttest.pgcluster`. A connection the guard never saw still ends up in a throwaway database on a private socket.

## Reference

- [API reference](gen-index.md) -- every module in all three implementations
