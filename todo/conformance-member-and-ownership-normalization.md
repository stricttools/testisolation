# Conformance member for the parity test, and ownership normalization

## Background

rlsbl is adopting single-owner workspace attribution: every file has exactly
one owning member (most specific path wins; a mandatory root member owns the
remainder), the `watch` key is removed, and CI triggering derives from
declared `depends_on` edges (all scopes trigger) plus built-in rules
(workspace-root manifest changes trigger all members; release-machinery
commits are auto-appended to CI filters; router changes re-run everything).

This workspace's watch lists serve several jobs that all get better homes
under that model:

- The Python member watches the Go and TypeScript source trees because the
  cross-language parity test lives in the Python suite and must run when
  either sibling changes.
- Members watch the workspace snapshot and releasable directories because of
  a recorded release incident where a machinery-only commit carried the tags
  and every CI job skipped.
- `LICENSE` and other root files are watched because nothing else owns them.

## What to consider doing

- Move the cross-language parity test out of the Python member into a new
  dev-node conformance member that declares `depends_on` on all three
  implementation members. That restores the triggering property (a Go-only
  or TypeScript-only change re-runs the parity test) through declared edges
  instead of cross-territory globs.
- Drop the release-machinery watch entries once rlsbl's auto-append rule
  ships; drop the shared-root-file entries once the mandatory root member
  exists (add it as a dev node — there is no root project).
- During the migration, remove the changelog coverage entries that exist
  only because of cross-scope watch claims: the entries covering commits
  that touch only per-releasable release-archive files (those commits become
  exempt under the tool-owned machinery exemption), and the Python-side
  duplicate of the TypeScript doc-comment commit (a TypeScript-side entry
  for the same commit already exists).
- Regenerate the CI router — the committed one predates the router's
  manual-dispatch run-all input.

## Why

Under single-owner attribution the cross-territory watch globs are removed;
without the conformance member and its edges, the one test that catches
cross-language drift stops running on exactly the changes it polices. The
entry cleanup prevents the changelog range checks from going red when the
ownership model changes commit attribution.
