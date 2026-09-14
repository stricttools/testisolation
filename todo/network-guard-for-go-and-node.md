# Network guard for the Go and Node floors

## Context

The Python plugin installs a socket guard through `sys.addaudithook`, so a
test that opens a network connection is refused. The Go module and the npm
package ship no network guard: the typescript README states that Node has no
audit-hook equivalent and that network isolation for Node suites is owned by
the sandbox runner (the bubblewrap wrapper that runs a suite with no network
namespace), and the Go module omits its guard for the same reason.

## Problem

The public description promises isolation from real files, secrets and the
git identity, and deliberately does not promise network isolation, because
two of the three packages cannot deliver it on their own. A suite run under
Go or Node outside the sandbox runner can still reach a real database or a
remote API with whatever credentials leak past the environment hygiene.

## Solutions

### In-process guards where the runtime allows one

- Go: a guard installed by the module at init, refusing `net.Dial` and the
  `net/http` default transport unless the address is loopback, through the
  module's own dialer wrappers plus a check that no test bypassed them (the
  module already inspects the environment; it can inspect the resolver and
  transport it hands out). Cannot intercept a raw syscall.
- Node: monkey-patching `net.Socket.prototype.connect` and the `http`/`https`
  agents, with the known gap that a native addon or a worker thread bypasses
  it.
- Pros: the guarantee travels with the package, no sandbox runner needed.
- Cons: neither guard is airtight; the README's own reasoning for omitting
  them stands, so shipping one must state its holes.

### Make the sandbox runner the documented requirement

Keep the packages as they are and make the sandbox runner (network
namespace removed) a first-class, documented part of running a Go or Node
suite under stricttest, with a check that refuses to run outside it.

- Pros: airtight isolation, no partial guard to caveat.
- Cons: Linux-only, and one more thing to install.

## Affected files

- `go/hygiene/` (a new guard file and its tests)
- `typescript/src/` (a new guard module and its tests)
- both READMEs and `docs/`, which currently explain why no guard ships
- the public description, if network isolation becomes a promise

## Effort

Medium for the in-process guards; small for the documented-runner route.
