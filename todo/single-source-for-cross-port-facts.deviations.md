# Deviations: single-source-for-cross-port-facts.md

Append-only. Each entry records what the plan says, what reality showed, and
what was done instead.

## Step 1: regenerating the CI router does not update the Python matrix

- **What the plan says:** before releasing, regenerate the CI router with
  `rlsbl monorepo sync`, because `.github/workflows/ci-router.yml` still carries
  `# requires-python: >= 3.11` and a 3.12/3.13/3.14 matrix after the move to
  Python 3.14.
- **What reality showed:** `rlsbl monorepo sync` (rlsbl 0.127.3) inlines each
  member's own CI workflow into the router and produced no change at all. The
  stale matrix comes from `python/.github/workflows/ci.yml`, a file written by
  `rlsbl scaffold`, which still states `# requires-python: >= 3.11` and
  `python-version: ["3.12", "3.13", "3.14"]`. Regenerating the router alone
  cannot fix it; the member workflow has to change first, either by rerunning
  `rlsbl scaffold` in `python/` (which may also bring in unrelated template
  changes from the installed rlsbl) or by editing the scaffolded file by hand.
- **What was done:** nothing was changed in either workflow file. The choice
  between rerunning the scaffold and a hand edit was left to the owner.

## Step 1: the Python release is a minor bump, not a patch

- **What the plan says:** step 1 ships as patch releases of every releasable it
  changes.
- **What reality showed:** the unreleased changelog of `py-testisolation`
  already holds a `breaking` entry from before step 1, the move to
  `requires-python = ">=3.14"`. A release carrying a breaking entry is a minor
  bump in 0.x.
- **What was done:** `py-testisolation` is released as a minor bump;
  `go-testisolation` and `ts-testisolation` are released as patch bumps.

## Step 1: the stale Python CI matrix is left until rlsbl's template changes

- **What the plan says:** regenerate the stale Python CI matrix before
  releasing.
- **What reality showed:** `rlsbl monorepo sync` does not change it, because
  the matrix comes from the rlsbl-scaffolded `python/.github/workflows/ci.yml`,
  not from the router.
- **What was done:** the owner ruled to leave the matrix as it is until rlsbl
  releases its template change (one explicit job on the `requires-python`
  lower bound), and then to rerun the scaffold. CI still tests Python 3.14,
  because uv selects an interpreter satisfying `>=3.14`.
