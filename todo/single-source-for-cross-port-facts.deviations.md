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
