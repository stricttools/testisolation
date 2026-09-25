# One source for every fact the three ports share, plus the port alignments and fixes found on the way

## Context

testisolation ships the same isolation in three ports (`python/`, `go/`,
`typescript/`), and the Go and Python ports also each ship the ephemeral
PostgreSQL launcher (`go/pgcluster/`, `python/src/testisolation/pgcluster.py`).
The facts those ports share are hand-written in each port, kept in agreement by
`python/tests/test_cross_language_parity.py` (which reads the Go and TypeScript
sources) and by the "lockstep" rules in `CLAUDE.md`.

The copies had drifted in ways nothing documents as intended when this todo was
filed (see "Behavior alignments"), and the next change was going to be one more
triplicated fact: `maintenance.auto=false` for git (see "Step 1").

The owner's rule: a fact declared in several places is reduced to one authority;
a test asserting the copies agree is only a fallback. Applying it here, over the
old "duplicated on purpose" justification, is the owner's own call. The
`CLAUDE.md` template sentence making that justification is already removed
(commit 3964208, regenerated in 8c60833); the "lockstep" bullet still describes
the parity test and is rewritten along with the code.

Already done, not part of this work: the Python package moved to
`requires-python = ">=3.14"` (commits 57c4b23 and 2bed0c8).

Decision origins: every ruling below was made by the owner choosing the
recommended option in a question round, and is therefore held loosely, except
where marked "(owner's own call)". File, function, and constant names this todo
introduces were chosen when it was written; if one reads badly in the code, ask
the owner rather than renaming silently.

## Step 1, released alone first: background git maintenance

With git 2.55, a `git commit` can start `git maintenance run --auto --quiet
--detach` in the background (observed through `GIT_TRACE2_EVENT` in a repository
with `rerere.enabled=true`: it runs `git rerere gc`). The background process
writes into `.git` while a test's temporary directory is being removed, failing
cleanup with `unlinkat .git: directory not empty`. It made safegit's CI fail on
`TestReadReportsAQueueWithNoCurrentStep`, and safegit's pending 0.29.4 patch
release waits on a testisolation release that disables automatic maintenance.

- Every port writes `maintenance.auto = false` into its throwaway git system
  config file (the file layout is section 3's; for this step, add the setting to
  the files each port creates).
- Red tests first, one per port. The Go one exists, uncommitted, in
  `go/hygiene/env_test.go`: `TestACommitStartsNoBackgroundMaintenance` enables
  rerere, commits under `GIT_TRACE2_EVENT`, and fails if a `maintenance` child
  process starts. Commit it together with the Go fix; write the same test for
  Python and TypeScript.
- Before releasing, regenerate the CI router with `rlsbl monorepo sync`:
  `.github/workflows/ci-router.yml` still carries `# requires-python: >= 3.11`
  and a 3.12/3.13/3.14 matrix after the move to 3.14.
- Release this alone, as patch releases of every releasable it changes, through
  the monorepo release flow. Then safegit raises its dependency on
  `github.com/stricttools/testisolation/go` to that release.

Everything after this step ships together in one later release, a minor bump
for every releasable it changes, because it contains breaking changes (the
per-test database export API, what the git config files contain, Python's XDG
layout).

## Step 2: the single data file and its generator

### Layout: a development-only workspace member `spec/` (decided)

- `spec/isolation.toml`: the data file. Each fact carries a comment saying why
  it exists.
- `spec/generate/`: a Go program in its own Go module, reading the TOML with
  go-toml-edit (`github.com/smm-h/go-toml-edit`, the family's zero-dependency
  TOML library, at its latest version). It is not part of the published
  `go/` module, so users of `github.com/stricttools/testisolation/go` do not
  inherit the dependency.
- `spec/` is declared in the rlsbl workspace as a development-only member with
  its own CI job that runs the freshness check. The three ports declare a
  dependency on `spec/`, so the CI router (which includes a member's
  dependencies' directories in its trigger filter) runs every port's job when
  the data file changes. The repository root cannot carry a CI job, which is why
  the data file does not live there.
- Open point to settle or bring back: declaring the ports' dependency on `spec/`
  without adding anything to the published `go/go.mod`,
  `python/pyproject.toml`, or `typescript/package.json`. rlsbl derives the
  dependency graph from manifests (see `rlsbl/router_filters.py`). If no clean
  declaration exists, stop and ask.

### Generated files

The generator writes one committed constants file per place that needs them:

- `go/hygiene/spec_gen.go`
- `go/pgcluster/spec_gen.go`
- `python/src/testisolation/_spec.py` (environment facts and launcher constants)
- `typescript/src/spec.ts`

Per-language spellings (`go_path` / `GoPath` / `goPath`) are derived by the
generator, not written in the data file. The freshness check fails when any
generated file differs from what the generator would write.

### What moves into `spec/isolation.toml`

- the credential variables stripped from the environment (without
  `GIT_ASKPASS`, see section 3)
- the preserve enum (`PRESERVE_VARS` and its Go and TypeScript counterparts);
  generated messages that list its valid names use each port's spelling
- the throwaway identity (`testisolation` / `testisolation@example.invalid`)
- the throwaway-home variables (`HOME`, `USERPROFILE`) and the XDG mapping
  (`XDG_CONFIG_HOME` -> `.config`, `XDG_DATA_HOME` -> `.local/share`,
  `XDG_CACHE_HOME` -> `.cache`, `XDG_STATE_HOME` -> `.local/state`)
- the blocked command (`/bin/false`) and the transport variables
  (`GIT_ALLOW_PROTOCOL=file`, `GIT_SSH_COMMAND`, `GIT_PROXY_COMMAND`,
  `GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS`)
- the git config file names (`gitconfig-global`, `gitconfig-system`) and the
  settings and identity written into the system file (section 3)
- the throwaway directory prefix, the sandbox variable `TESTISOLATION_SANDBOX`,
  and the runner command `scripts/test.sh`
- message templates shared across ports. Their parameters are more than an
  option name: the bare-run refusal ("The sandbox binds the real repo
  read-only…") varies by runner command, sandbox variable, test count, and
  threshold, and Python's version ends with a pytest-specific tail ("a single
  file or a -k slice"), which becomes a per-port parameter. The preserve-enum
  rejection lists the valid names in each port's spelling (Go's text lists none
  and has drifted). The launcher's messages take the language-specific option
  name (`socket_parent` / `SocketParent`) as a parameter.
- a `[pgcluster]` section with the launcher constants: the 107-byte socket path
  limit, the socket file template `.s.PGSQL.<port>`, the socket and data parent
  candidates and their order, the binary search directories, the required
  binaries, the database-name pattern, the fast settings, the defaults (port,
  superuser, database, timeout), the initdb, pg_ctl, and psql flags, the `PG*`
  environment scrub plus `LC_ALL=C` / `LANG=C`, the `stpg-` / `stpg-data-`
  prefixes, the generated database name form, and the rejection labels
  (section 3). Process spawning, cleanup (Python's atexit, Go's `testing.TB`),
  and argument-list assembly stay hand-written.
- package metadata: the one-line description, keywords, homepage, repository,
  and issues URLs. The generator writes them into `python/pyproject.toml` (with
  go-toml-edit, preserving comments), `typescript/package.json`, `selfdoc.json`,
  and every hand-written document that states the description: the README
  template `.stricttools/docs/_README.md`, the docs index, and the port READMEs
  (or their selfdoc templates, where a port README is generated).

### Tests this replaces

`test_cross_language_parity.py` and the tests that only check the lists against
each other or against a hardcoded count become generator validation plus the
freshness check: `TestCredentialVarsCoversTheDocumentedVectors`, the
credential-list tests in `python/tests/test_env_overrides.py` and
`typescript/tests/env.test.ts`, `TestKnownVarsAreDistinct` in
`go/hygiene/hygiene_test.go` (including its `len(knownVars) != 10` assertion),
the list checks in `hygiene.test.ts`, and
`test_preserve_enum_maps_only_to_toolchain_vars`. Tests of behavior stay.

## Step 3: behavior alignments

Each is a behavior change in at least one port; write a red test first. All of
them read their values from the generated files.

- **Git config: two files, settings and identity in the system file.** Every
  port points `GIT_CONFIG_SYSTEM` at `gitconfig-system`, which carries the shared
  settings (`maintenance.auto = false`, `protocol.ssh.allow = never`,
  `init.defaultBranch = main`) and the identity (`[user] name`, `email`), and
  points `GIT_CONFIG_GLOBAL` at `gitconfig-global`, created empty. git reads the
  system file, then the global file, then the repository's own `.git/config`,
  and the last value read wins (verified by a probe), so the settings act as
  defaults a suite can override deliberately, and a suite that points
  `GIT_CONFIG_GLOBAL` at its own fixture keeps them. Python moves from one file
  for both variables to two. Go and TypeScript adopt `protocol.ssh.allow` and
  `init.defaultBranch`, which only Python set. Settings go in the file, not in
  `GIT_CONFIG_COUNT` variables, so they are inspectable and a suite setting its
  own `GIT_CONFIG_COUNT` cannot erase them.
  - Tests and comments that pin the old contents change with it:
    `TestIsolateGitConfigPointsAtEmptyFilesInTheThrowawayHome`
    (`go/hygiene/env_test.go`); in `typescript/tests/env.test.ts`,
    "isolateGitConfig empties git's config and replaces the identity", "the
    isolated git config really is what git reads", and "a poisoned home hides
    the developer's real dotfiles" (its list of planted files); and the
    "config files are empty rather than carrying the identity" rationale in
    `go/hygiene/env.go` and `typescript/src/env.ts`.
- **The identity is set in both the environment variables and the system config
  file** (the `GIT_AUTHOR_*` / `GIT_COMMITTER_*` variables stay). A tool that
  strips only those variables otherwise leaves git to guess an identity: a probe
  with the variables removed and no identity in any file got `unable to
  auto-detect email address (got 'm@fedora.(none)')`, and on a machine whose
  hostname has a domain git would commit under a guessed address built from the
  login name. Correct the Go and TypeScript comment that says the variables
  are enough.
- **`GIT_ASKPASS` is pinned to `/bin/false` in every port and leaves the
  credential-strip list.** In Go and TypeScript the pin moves into
  `LockdownTransports` / `lockdownTransports` (Python already pins it with its
  transport lockdown). Consequence to document: a consumer calling only
  `StripCredentials` no longer clears `GIT_ASKPASS`; `LockdownTransports` pins
  it instead, which is stronger (git cannot fall back to another askpass
  program).
- **Python's XDG directories move inside the throwaway home** at the standard
  relative paths, like Go and TypeScript. Python creates them as siblings of the
  home (`<session>/xdg-config` next to `<session>/home`), so a tool that
  hardcodes `~/.config` and one that honors `XDG_CONFIG_HOME` see different
  directories. `python/tests/test_env_overrides.py` pins the sibling layout and
  changes with it.
- **Per-test database export is an explicit choice with no default, in both
  launchers.** Python's `database()` exports the URL only with `export=True`;
  Go's `Database(t)` always exports it. Python's `database(export=...)` loses its
  default; Go's becomes `Database(t, pgcluster.Export)` /
  `Database(t, pgcluster.NoExport)`. A breaking change for both APIs, with no
  compatibility shim (pre-1.0).
- **Writability of a candidate directory is checked with a probe directory in
  both launchers.** Python uses `os.access(..., W_OK)`, which answers wrongly on
  overlays, read-only bind mounts, and full tmpfs; Go's `isWritableDir` creates
  and removes a probe directory. Python adopts the probe.
- **Rejected candidates are labeled in readable words in both launchers**
  ("socket path too long", "unusable socket directory"), from the data file.
  Python prints the exception class name (`SocketPathTooLong`, `ValueError`).
- **Go gets the sandbox bare-run refusal, always-only.** Add
  `hygiene.RequireSandbox(m *testing.M)` for a suite's `TestMain`: it refuses
  every run where `TESTISOLATION_SANDBOX` is not `"1"`, with the shared refusal
  text. No threshold policy: `testing.M` exposes no count of selected tests
  before they run, and a refusal that fires partway through would already have
  run tests outside the sandbox (TypeScript's `--import` form is always-only for
  the same reason). Go has no in-process network guard, so it needs the sandbox
  most; `go/README.md` says network isolation for Go suites belongs to the
  sandbox runner, but nothing enforces it.

## Step 4: bugs (red-green)

- **TypeScript ignores an empty `GOPATH`.** `typescript/src/hygiene.ts` uses
  `process.env["GOPATH"] ?? \`${realHome}/go\``, and `??` keeps an empty string;
  Python (`or`) and Go (`== ""`) fall back to the default. With `GOPATH=""`,
  preserving the Go module cache yields `/pkg/mod` in TypeScript only.
- **Database URLs break when the superuser contains `@`.** Python builds the
  URL with `quote()` and Go with `url.PathEscape`, which escape different
  characters; Go leaves `@` and `:` unescaped in the user part. Escape the user,
  database, and host parts each for their own URL component, identically in both
  ports.
- **Python repeats its own facts:** `python/tests/conftest.py` `SAFE_DEFAULTS`
  duplicates the required-keys block in `config.py`; `conftest.py`
  `INI_SECTIONS` (keyed by file name) duplicates `config.py`'s
  `_INI_SECTION_BY_SUFFIX` (keyed by suffix), so conftest looks the section up by
  the file's suffix; `tests/test_threshold.py` retypes every `DEFAULT_*` value.
  Reference the source instead.
- **`__version__` is hardcoded** in `python/src/testisolation/__init__.py`; read
  it from the installed package metadata (`importlib.metadata`).

## Step 5: documentation

- **Cross-port prose gets one home:** a "Scope and limits" section of the root
  README template. The caveat that the Python socket guard does not see the
  psycopg C driver, the statement that Go and TypeScript have no socket or push
  guard, and similar cross-port facts are repeated across the root README
  template, the docs index, the port READMEs, both launchers' doc comments, and
  `CLAUDE.md`; state each once there and link to it from the others. Comments in
  one port stop describing another port's behavior (for example `env.go` and
  `env.ts` explaining Python's `GIT_ASKPASS` handling, `hygiene.go` /
  `hygiene.ts` saying they mirror each other one-for-one, `sandbox.ts`
  describing Python's hook, `scope.ts` describing Go's `TB` plumbing,
  `pgcluster.go` describing Python's atexit and audit hook).
- **Stale claims to correct:** `typescript/README.md` says the ephemeral
  PostgreSQL helper "lives in the pytest plugin only", but Go ships
  `pgcluster`; the comments in `.rlsbl-monorepo/workspace.toml` describe watch
  keys the file does not have; the helper tables in the Go and TypeScript
  READMEs describe the git config files as empty, which step 3 makes false; the
  parity claims in the README template and `CLAUDE.md` ("a cross-language test
  holds…") become false when the generator replaces the parity test.
- **Docs version:** `selfdoc.json` declares documentation version 0.2.0, while
  at filing time the Python and Go releasables were at 0.3.0 and TypeScript at
  0.2.0. Find out how selfdoc and rlsbl intend a documentation version to be
  chosen for a repository whose releasables carry different versions, then ask
  before changing it.

## Waiting on testuniverse

The launchers' test data is mirrored by hand between the Python and Go suites:
the accepted and refused database names, the socket-path length cases around
the 107-byte limit, the DSN variable `TESTISOLATION_TEST_DATABASE_URL`, the
extension list (pgcrypto, vector), and the boot budget. The owner's decision
(owner's own call) is to declare these once in testuniverse (in the family, an
empty skeleton when this todo was filed) and make testisolation its first
consumer, rather than inventing a one-off test-case mechanism here. This item
waits until testuniverse can declare and generate them; nothing else in this
todo waits for it.

## Effort

- Step 1 including its release: half a day.
- Step 2 (member, generator, freshness check, replacing the list tests): one to
  two days.
- Steps 3 and 4, each change red-green: about a day.
- Step 5: half a day.
