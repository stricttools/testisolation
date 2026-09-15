# stricttest (npm)

Uncompromising test isolation: your tests structurally cannot touch your real files, secrets, or git identity -- First-class support for Go, Python with pytest, and TypeScript with Node

This is the Node package. For Node suites the floor is a throwaway `HOME` and
XDG directories, an isolated git configuration and identity, transport lockdown,
credential stripping, and bare-run refusal.

It is the Node member of a three-language floor. The
[pytest plugin](https://pypi.org/project/stricttest/) and the
[Go module](https://pkg.go.dev/github.com/smm-h/stricttest/go/hygiene) ship from
the same repository, and a cross-language test holds their credential lists and
preserve enums in lockstep, so a polyglot repo gets the same guarantee in every
language it tests in.

```bash
npm install --save-dev stricttest
```

Requires Node >= 22. ESM only.

## Usage

```ts
import { test } from "node:test";
import { isolate } from "stricttest";

test("something", (t) => {
  isolate(t);
  // HOME is a throwaway directory, git reads an empty global config with a
  // throwaway identity, only the file:// transport is allowed, and every
  // ambient credential variable is gone -- until this test finishes.
});
```

`node:test`'s `TestContext` is a cleanup registry as-is, so no adapter is
needed. Other runners need a one-line object literal:

```ts
import { onTestFinished } from "vitest";
isolate({ after: onTestFinished });
```

## Surface

| Export | What it does |
|--------|--------------|
| `isolate(t, options?)` | Binds the whole floor: preserved caches, throwaway home, git config, transports, credentials. |
| `throwawayHome(t)` | Repoints `HOME`, `USERPROFILE` and the four XDG base directories at a fresh temp dir; returns it. Memoized per test. |
| `isolateGitConfig(t)` | Empty `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` inside the throwaway home, throwaway `GIT_AUTHOR_*`/`GIT_COMMITTER_*`, `GIT_TERMINAL_PROMPT=0`. |
| `lockdownTransports(t)` | `GIT_ALLOW_PROTOCOL=file`, plus `GIT_SSH_COMMAND` and `GIT_PROXY_COMMAND` pinned to `/bin/false`. |
| `stripCredentials(t)` | Removes every variable in `CREDENTIAL_VARS`. |
| `chdir(t, dir)` | Moves the working directory (and `PWD`) for the test and restores it after. |
| `preserveVars(t, names)` | Pins toolchain caches so they survive the `HOME` repoint. Closed enum. |
| `requireSandbox(options)` | Refuses a run happening outside the sandbox runner. |
| `insideSandbox(env?)` | Whether this process is inside the sandbox runner. |
| `CREDENTIAL_VARS`, `KNOWN_VARS` | The two closed lists, exported for inspection. |

Everything undoes itself when the test that bound it finishes. Nothing is
process-wide or permanent.

### Preserving toolchain caches

`GOCACHE`, `UV_CACHE_DIR`, `PYTHONUSERBASE` and friends all default to a
location under the real home, so moving `HOME` sends the toolchain into a cold
rebuild. Opt them back in by name:

```ts
isolate(t, { preserve: ["goCache", "goModCache", "uvCache"] });
```

The enum (`KNOWN_VARS`) is closed in TypeScript and re-checked at runtime for
plain JavaScript callers. Arbitrary variable names are rejected on purpose: a
credential vector must never become preservable by typo.

### Bare-run refusal

```ts
requireSandbox({ policy: "threshold", threshold: 50, count: files.length });
// or
requireSandbox({ policy: "always" });
```

The policy is required -- a suite declares where it stands rather than
inheriting one. Both forms are keyed on `STRICTTEST_SANDBOX=1`, which the
sandbox runner exports.

The count has to come from wherever the consumer genuinely knows it, because
Node's runner has no pre-run collection hook: `node --test` runs each test FILE
in its own child process, and a module loaded with `--import` is loaded in those
children, never in the parent that owns the run. A setup module therefore sees
exactly one file and can never learn how large the run is. (Custom reporters do
run in the parent, but they are fed events as tests complete -- too late to
refuse a run, and with no way to abort one. A permanent test in this package
pins that topology so the claim cannot rot.)

So there are two honest call sites:

- **A programmatic runner entry**, where `node:test`'s `run({ files })` is
  called with the file list. Use `policy: "threshold"` there and keep a fast
  bare inner loop for small runs.
- **An `--import`ed setup module**, for suites that run through plain
  `node --test`. A child cannot count the run, so the only honest stance there
  is `policy: "always"`: every bare run is refused, including small ones.

## What this package deliberately does NOT do

**No socket guard.** Python has `sys.addaudithook`, a hook the interpreter calls
on every socket operation and which cannot be removed once installed. Node has
no equivalent. The nearest thing is monkey-patching `net.Socket.prototype
.connect`, which misses `dgram`, misses anything reaching the syscall through a
native addon, and is undone by any code that re-imports `node:net` through a
fresh module loader. A partial guard reads as a guarantee and is worse than
none. Network isolation for Node suites is owned by the sandbox runner -- the
bubblewrap wrapper that runs the suite with no network namespace -- and
`requireSandbox` is what makes sure the suite actually goes through it. The Go
module omits its socket guard for the same reason.

**No push guard.** The pytest plugin intercepts `subprocess.Popen` to refuse a
real `git push` to a non-local remote. The equivalent here would be patching
`node:child_process`, and it fails the same honesty test: `spawn`, `exec`,
`execFile`, `fork` and their sync twins all reach the same binding, native
addons bypass the module entirely, and a fresh loader restores the original.
`lockdownTransports` already closes the outcome that guard exists to prevent --
a push over `ssh://` or `https://` dies at the protocol check with the ssh and
proxy helpers pinned to a command that only fails.

**No ephemeral-Postgres helper.** That one lives in the pytest plugin only; it
is a cluster launcher, not part of the environment floor.

## Concurrency

`HOME`, the working directory and the git identity belong to the process, not to
a test. Nested tests are fine -- a subtest starts and finishes inside its parent
-- but two tests isolating at the same time is not, and this package detects it
rather than letting one test's `HOME` leak into another's: a test that finishes
its isolation while another's is still open fails with an explanatory error. Run
the tests in an isolating file sequentially (`node:test`'s default).

## License

MIT
