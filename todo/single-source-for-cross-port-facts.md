# One source for every fact the three ports share, plus the port alignments and fixes found on the way

## Context

testisolation ships the same isolation in three ports (`python/`, `go/`,
`typescript/`), and the Go and Python ports also each ship the ephemeral
PostgreSQL launcher (`go/pgcluster/`, `python/src/testisolation/pgcluster.py`).
The facts those ports share are hand-written in each port, kept in agreement by
`python/tests/test_cross_language_parity.py` (which reads the Go and TypeScript
sources) and by the "lockstep" rules in `CLAUDE.md`.

The copies have already drifted in ways nothing documents as intended (listed
under "Behavior alignments" below), and the next change was going to be one more
triplicated fact: `maintenance.auto=false` for git (see "Background maintenance
race").

The owner's rule: a fact declared in several places is reduced to one authority;
a test asserting the copies agree is only a fallback. Applying it here, over
the old "duplicated on purpose" justification, is the owner's own call. The `CLAUDE.md` template
sentence claiming the duplication was deliberate has already been removed
(commit 3964208, regenerated in 8c60833); the "lockstep" bullet itself still
describes the parity test and must be rewritten when this lands in code.

Already done and not part of this work: the Python package moved to
`requires-python = ">=3.14"` (commits 57c4b23 and 2bed0c8).

Decision origins: every ruling below was made by the owner choosing the
recommended option in a question round, and is therefore held loosely, except
where marked "(owner's own call)".

## Background maintenance race (the trigger)

With git 2.55, a `git commit` can start `git maintenance run --auto --quiet
--detach` in the background (observed through `GIT_TRACE2_EVENT` in a repository
with `rerere.enabled=true`: it runs `git rerere gc`). The background process
writes into `.git` while a test's temporary directory is being removed, failing
cleanup with `unlinkat .git: directory not empty`. This made safegit's CI fail
on `TestReadReportsAQueueWithNoCurrentStep`; safegit's 0.29.4 patch release waits
on a testisolation release that disables automatic maintenance.

A red test for this already exists, uncommitted, in `go/hygiene/env_test.go`:
`TestACommitStartsNoBackgroundMaintenance` enables rerere, commits under
`GIT_TRACE2_EVENT`, and fails if a `maintenance` child process starts. Keep it,
and give the Python and TypeScript ports the same test.

## 1. The single data file and its generator

- **Data file:** one commented TOML file at the repository root (for example
  `isolation.toml`). Each fact carries a comment saying why it exists.
- **Generator:** a Go program that reads the TOML with go-toml-edit
  (`github.com/smm-h/go-toml-edit`, the family's zero-dependency TOML library,
  used at its latest version) and writes one committed constants file into each
  port (for example `go/hygiene/spec_gen.go`, `python/src/testisolation/_spec.py`,
  `typescript/src/spec.ts`, plus the launcher constants for `go/pgcluster/` and
  the Python launcher). The generator lives in its own small Go module, not
  inside the published `go/` module, so users of `github.com/stricttools/testisolation/go`
  do not inherit the dependency. If rlsbl's monorepo rules make a separate
  module awkward, stop and ask.
- **Per-language spellings** (`go_path` / `GoPath` / `goPath`) are derived by the
  generator, not written in the data file.
- **Freshness:** a check fails whenever a generated file differs from what the
  generator would write, and it must run in CI whenever the data file or any
  generated file changes. The repository root is a development-only workspace
  member with no CI job, and the CI router triggers each port only on its own
  directory (`python/**`, `go/**`, `typescript/**`), so a root-level data file
  edited alone triggers nothing today. Find a mechanism that fits rlsbl's
  monorepo rules (territory is derived from declared member paths; no `watch`
  keys); if none fits, stop and ask.
- **Replaced tests:** `test_cross_language_parity.py` and the tests that only
  check the lists against each other or against a hardcoded count
  (`TestCredentialVarsCoversTheDocumentedVectors`, the credential-list tests in
  `test_env_overrides.py` and `env.test.ts`, `TestKnownVarsAreDistinct`,
  `hygiene.test.ts`'s list checks, `test_preserve_enum_maps_only_to_toolchain_vars`)
  become generator validation and the freshness check. Tests of behavior stay.

### What moves into the data file

- the credential variables stripped from the environment
- the preserve enum (`PRESERVE_VARS` and its Go and TypeScript counterparts)
- the throwaway identity (`testisolation` / `testisolation@example.invalid`)
- the throwaway-home variables (`HOME`, `USERPROFILE`) and the XDG mapping
  (`XDG_CONFIG_HOME` -> `.config`, `XDG_DATA_HOME` -> `.local/share`,
  `XDG_CACHE_HOME` -> `.cache`, `XDG_STATE_HOME` -> `.local/state`)
- the blocked command (`/bin/false`) and the transport variables
  (`GIT_ALLOW_PROTOCOL=file`, `GIT_SSH_COMMAND`, `GIT_PROXY_COMMAND`,
  `GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS`)
- the git config file names and the git settings written into them (section 2)
- the throwaway directory prefix, the sandbox variable `TESTISOLATION_SANDBOX`,
  and the runner command `scripts/test.sh`
- error message templates shared across ports, with the language-specific
  option name as a parameter: the bare-run refusal ("The sandbox binds the real
  repo read-only…"), the preserve-enum rejection (Go's text has drifted and does
  not list the valid names), and the launcher's messages
- a `[pgcluster]` section with the launcher constants: the 107-byte socket path
  limit, the socket file template `.s.PGSQL.<port>`, the socket and data parent
  candidates and their order, the binary search directories, the required
  binaries, the database-name pattern, the fast settings, the defaults (port,
  superuser, database, timeout), the initdb, pg_ctl, and psql flags, the `PG*`
  environment scrub plus `LC_ALL=C` / `LANG=C`, the `stpg-` / `stpg-data-`
  prefixes, and the generated database name form. Process spawning, cleanup
  (Python's atexit, Go's `testing.TB`), and argument-list assembly stay
  hand-written.
- package metadata: the one-line description, keywords, homepage, repository,
  and issues URLs. The generator writes them into `python/pyproject.toml` (with
  go-toml-edit, preserving comments), `typescript/package.json`, and
  `selfdoc.json`; the READMEs take the description from selfdoc.

## 2. Behavior alignments

Each is a behavior change in at least one port; write a red test first.

- **Git settings go into the throwaway config file in every port.** Python
  writes one config file with settings; Go and TypeScript point
  `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` at empty files. Every port writes
  the shared settings into its config file: `maintenance.auto = false`,
  `protocol.ssh.allow = never`, `init.defaultBranch = main` (Go and TypeScript
  adopt the last two, which only Python sets). Settings go in the file, not in
  `GIT_CONFIG_COUNT` variables, so they are inspectable and a suite setting its
  own `GIT_CONFIG_COUNT` cannot erase them.
- **`GIT_ASKPASS` is pinned to `/bin/false` in every port** and leaves the
  credential-strip list. Go and TypeScript remove it today; Python pins it.
  Pinning is stronger (git cannot fall back to another askpass program), and
  the credential list becomes identical in all ports.
- **Python's XDG directories move inside the throwaway home** at the standard
  relative paths, like Go and TypeScript. Python creates them as siblings of the
  home (`<session>/xdg-config` next to `<session>/home`), so a tool that
  hardcodes `~/.config` and one that honors `XDG_CONFIG_HOME` see different
  directories. `python/tests/test_env_overrides.py` pins the old layout and
  changes with it.
- **Per-test database export is an explicit choice with no default, in both
  launchers.** Python's `database()` exports the URL only with `export=True`;
  Go's `Database(t)` always exports it. Both require the caller to choose (for
  example Python `database(export=...)` with no default, Go
  `Database(t, pgcluster.Export)` / `Database(t, pgcluster.NoExport)`). A
  breaking change for both APIs, with no compatibility shim (pre-1.0).
- **Writability of a candidate directory is checked with a probe directory in
  both launchers.** Python uses `os.access(..., W_OK)`, which answers wrongly on
  overlays, read-only bind mounts, and full tmpfs; Go creates and removes a
  probe directory. Python adopts the probe.
- **Rejected candidates are labeled in readable words in both launchers**
  ("socket path too long", "unusable socket directory"), from the data file.
  Python prints the exception class name (`SocketPathTooLong`, `ValueError`).
- **Go gets the sandbox bare-run refusal** that Python and TypeScript have (for
  example `hygiene.RequireSandbox(m *testing.M, ...)` for a suite's TestMain,
  reading `TESTISOLATION_SANDBOX` with the same threshold or always policy and
  the shared refusal text). Go has no in-process network guard, so it needs the
  sandbox most; today a bare `go test ./...` runs with full network and write
  access and no README says so.

## 3. Bugs to fix (red-green)

- **TypeScript ignores an empty `GOPATH`.** `typescript/src/hygiene.ts` uses
  `process.env["GOPATH"] ?? \`${realHome}/go\``, and `??` keeps an empty string;
  Python (`or`) and Go (`== ""`) fall back to the default. With `GOPATH=""`,
  preserving the Go module cache yields `/pkg/mod` in TypeScript only.
- **Database URLs break when the superuser contains `@`.** Python builds the
  URL with `quote()` and Go with `url.PathEscape`, which escape different
  characters; Go leaves `@` and `:` unescaped in the user part. Build the URL so
  the user, database, and host parts are each escaped for their URL component,
  identically in both ports.
- **Python repeats its own facts:** `python/tests/conftest.py` `SAFE_DEFAULTS`
  duplicates the remediation block in `config.py`; `conftest.py` `INI_SECTIONS`
  duplicates `config.py`'s `_INI_SECTION_BY_SUFFIX`; `tests/test_threshold.py`
  retypes every `DEFAULT_*` value. Reference the source instead.
- **`__version__` is hardcoded** in `python/src/testisolation/__init__.py`; read
  it from the installed package metadata (`importlib.metadata`).

## 4. Documentation

- **Cross-port prose gets one home.** The caveat that the Python socket guard
  does not see the psycopg C driver, the statement that Go and TypeScript have
  no socket or push guard, and similar cross-port facts are repeated across the
  root README template, the docs index, the port READMEs, both launchers' doc
  comments, and `CLAUDE.md`. State each once on one docs page (for example a
  "Scope and limits" section) and link to it from the others. Comments in one
  port stop describing another port's behavior (for example `env.go` and
  `env.ts` explaining Python's `GIT_ASKPASS` handling, `hygiene.go` /
  `hygiene.ts` "mirrors one-for-one", `sandbox.ts` describing Python's hook,
  `scope.ts` describing Go's `TB` plumbing, `pgcluster.go` describing Python's
  atexit and audit hook).
- **Stale claims to correct:** `typescript/README.md` says the ephemeral
  PostgreSQL helper "lives in the pytest plugin only", but Go ships `pgcluster`;
  the comments in `.rlsbl-monorepo/workspace.toml` describe watch keys the file
  no longer has; the helper tables in the Go and TypeScript READMEs describe the
  git config files as empty, which section 2 makes false; the parity claims in
  the README template and `CLAUDE.md` ("a cross-language test holds…") become
  false when the generator replaces the parity test.
- **Docs version:** `selfdoc.json` declares documentation version 0.2.0 while
  the Python and Go releasables are at 0.3.0 and TypeScript at 0.2.0. Find out
  how selfdoc and rlsbl intend a documentation version to be chosen for a
  repository whose releasables carry different versions, then ask before
  changing it.

## 5. Waiting on testuniverse

The launchers' test data is mirrored by hand between the Python and Go suites:
the accepted and refused database names, the socket-path length cases around
the 107-byte limit, the DSN variable `TESTISOLATION_TEST_DATABASE_URL`, the
extension list (pgcrypto, vector), and the boot budget. The owner's decision
(owner's own call) is to declare these once in testuniverse (in the family, still an empty skeleton)
and make testisolation its first consumer, rather than inventing a one-off
test-case mechanism here. This item waits until testuniverse can declare and
generate them; everything else in this todo does not wait for it.

## Releases

Patch releases through the monorepo flow for every releasable whose package
changes. safegit's pending patch release depends on the release that disables
background maintenance; after it, safegit raises its testisolation dependency.

## Effort

- Data file, generator, freshness check, and replacing the list tests: one to
  two days.
- Behavior alignments and bugs, each red-green: about a day.
- Documentation consolidation: half a day.
