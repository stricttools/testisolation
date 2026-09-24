# Sandbox requirement rollout: scope decision + resource-behavior design

Deferred by explicit user decision (2026-08-05): not a priority right now. Do not
resolve the scope question unilaterally — it needs a user ruling when picked up.

## Context

The isolation stack has two tiers: the in-process pytest floor (this package's
plugin) and the bwrap sandbox runner (distributed as a scaffold template by the
release-orchestration tool, detected by the plugin via `TESTISOLATION_SANDBOX`).
Floor adoption is spreading across consumer repos, but every adopter so far sets
`testisolation_sandbox_required = "false"`, so the adoption check effectively
enforces floor-presence only. The sandbox runner is in real use in exactly one
consumer repo.

## Problem

1. **Scope is undecided.** Which consumer repos should be REQUIRED to run
   sandboxed (runner locally + sandbox in CI) versus floor-only? Fleet-wide
   sandboxing multiplies a known CI maintenance surface (sandbox tool source
   builds per run, runner-image drift, warm-cache entries that must track each
   repo's build backends). A risk-ordered subset — the repos whose suites sit
   closest to real credentials — is the plausible landing zone, but the
   decision was deliberately deferred, not made.
2. **Resource behavior must be designed BEFORE any wider rollout.** Witnessed
   side effect on the development machine: sandboxed full-suite runs have
   caused out-of-RAM conditions and system-wide lag. Likely contributors:
   tmpfs-backed TMPDIR (RAM-backed by design), parallel xdist workers each
   holding RAM-resident temp state, and multiple concurrent agent sessions
   running suites simultaneously. Spreading the sandbox requirement without a
   resource design spreads this harm.

## Solution directions (for the future design round)

- (a) **Resource design first, then risk-ordered rollout.** Add explicit
  resource controls to the sandbox contract: tmpfs size caps, an optional
  disk-backed TMPDIR mode for large suites, worker-count ceilings, a documented
  RAM budget, and possibly a concurrency guard so simultaneous sandboxed runs
  on one machine queue rather than stack. Then flip
  `testisolation_sandbox_required = "true"` only for the highest-credential-
  exposure consumers. Pros: fixes the witnessed harm before spreading it;
  bounded maintenance surface. Cons: two design efforts in sequence.
- (b) **Floor-only as the permanent fleet posture.** The sandbox stays a
  single-repo practice; the adoption check permanently enforces plugin/module
  presence only. Pros: zero new maintenance or resource surface. Cons: the
  highest-risk suites keep only in-process protection, and the in-process
  socket guard is structurally blind to C-extension DB drivers — the sandbox
  is the only complete network boundary available.
- (c) **Fleet-wide requirement.** Maximum isolation everywhere. Pros:
  uniformity. Cons: multiplies both the CI maintenance surface and the
  witnessed RAM/lag problem; almost certainly wrong without (a)'s resource
  work first.

## Affected

- This repo: the plugin's sandbox detection + the `testisolation_sandbox_required`
  key semantics; sandbox contract docs.
- The distributing tool's runner template + adoption check (lives outside this
  repo; coordinate at pickup).

## Effort

A design round (scope ruling + resource model) plus small-to-medium
implementation of the chosen resource controls.
