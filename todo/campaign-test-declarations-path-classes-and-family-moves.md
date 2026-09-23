# Campaign: test declarations in stricttest, repository path classes in rlsbl, rule registries, and the family moves

This is a fleet campaign plan filed in stricttest because its largest piece,
the test-declaration half of stricttest, lives here. It names other family
projects by their real paths under the family exemption of the todo
confidentiality rule. strictgo, strictdraw, and linguini are named although
they sit outside `~/Projects/stricttools/tools/` today, because this plan
moves them in.

Every decision below was made by the user in one decision round before this
plan was written, and every current-world claim was verified by reading the
repositories at that time. A deviations companion file beside this plan
records any place reality turns out to differ.

## Purpose

Three defect classes run through the fleet, measured rather than supposed:

- **Hand-copied test inputs.** strictgo keeps 3159 tracked files under
  `testdata/`; 1127 of them repeat its own module path and 331 manifests
  copy the same dependency block. strictcli's 1481 conformance cases carry
  pasted expectation text in 1453 of them, and 737 cases repeat an app
  definition verbatim. strictspec's corpus has 62 byte-identical duplicate
  files. safegit and rlsbl tests paste the tool's own sentences in about
  three of every ten test functions.
- **No rule identity.** strictgo's finding type carries an analyzer-sized
  bucket, not a refusal identity, and its module path constant is declared
  three times. strictcli has no error identity in any of its three
  implementations, and its parity checker recovers 536 signatures by regex.
- **No repository shape.** Nothing says which tracked file is authored,
  generated, or historical. A measurement over 25 repositories and 15228
  tracked files classified all but 84 from artifacts that already exist, but
  found 165 tracked scratch files, 43 generator headers in nine home-grown
  wordings, no enforcement of the read-only mode rlsbl sets on records
  because git does not store it, and scratch ignore files missing in 23
  repositories.

The campaign removes the three classes with one test-declaration tool, one
path-class discipline, and per-tool rule registries, then completes the
family moves and strictdraw, which those pieces unblock.

## Decisions on record

Product and homes:

- The test-declaration half lives in stricttest, not in a new project: a
  Go `corpus` package plus a strictcli-based command binary, a Python
  `stricttest.corpus` subpackage, and a TypeScript `corpus` export. Three
  minor bumps, no fourth releasable.
- The source of truth for a corpus is TOML, validated by a strictspec
  schema, with generated readers in the three languages. Go-only projects
  may additionally generate a Go table from it.
- Rendered worlds go to scratch only, never committed; a `render` command
  writes one named cell to a directory of the user's choosing.
- A cell asserts a rule identity plus arguments; the expected sentence is
  rendered from the tested tool's registry and, where the tool has
  structured output, the reported identity is asserted too.
- strictgo, strictdraw, and linguini join the stricttools family. strictgo
  and strictdraw move under `~/Projects/stricttools/tools/` with
  `github.com/stricttools/<name>` module paths. linguini becomes a private
  git repository under `~/Projects/linguini` and is not built in this plan.
- strictdraw's license is MIT, now as the user's decision.

strictspec:

- Design decision 35 is amended: one built-in scalar type is added after
  the freeze, named `sourcecode`, with a required language, an optional
  declared formatter, and text rules all three targets decide identically
  (non-empty, one newline convention, no trailing whitespace, final newline,
  consistent leading indentation). Formatter enforcement is a separate
  command with effects, never inside the validators.
- strictspec's home moves from the root `.strictspec/` directory to
  `.stricttools/schemas/`, registered in selfdoc's layout with strictspec as
  owner. Schema files are named `<name>.schema.strict.toml`; the list of
  schemas and their generation targets is `schemas.strict.toml` in that
  directory.
- strictspec refuses to read any schema or governed document whose name
  does not end in `.strict.toml`; generated validators refuse other names.
  Governed documents in every consumer are renamed accordingly.
- The conformance harness's message catalogue becomes generated from the
  error-code appendix like the three implementation catalogues.

strictcli:

- Every message becomes an identity with a template and typed slots in one
  source document; the Go, TypeScript, and Python catalogues are generated
  from it; each implementation renders through its catalogue; machine mode
  carries the identity; the parity checker compares generated tables by
  identity and its regex extractors are deleted.
- A generator command group feature: a group with only `generate` and
  `status`, JSON output on both, `status` read-only and pure and derived
  from `generate` under dry run, pre-declared outputs and reads, the stamp
  injected by the framework, no timestamps, rendering of the group's
  outputs into the repository's path declarations, and an optional
  autocommit hook. Filed separately as `todo/generator-command-group.md` in
  strictcli.

rlsbl and the repository shape:

- A directory `.stricttools/paths/`, owned by rlsbl and registered in
  selfdoc's layout, holds `paths.strict.toml` (hand-authored entries),
  `exceptions.strict.toml` (recognized file names the extension table
  cannot classify, each with its reason and language if any), and one
  rendered file per generator group named `<tool>-<group>.strict.toml`.
- An entry is a directory or an exact file, never a wildcard pattern.
  Fields: `origin` (authored, generated, or vendored), `mutability`
  (editable, read-only, or append-only), `counted` (whether the files are
  the repository's substance), `extensions` (the admitted set), and
  `max_depth` (relative to the entry's directory). Nested entries resolve
  by most specific wins, the rule rlsbl's ownership module already uses.
  Language is derived from a fleet extension-to-language table and stated
  only in the exceptions file for names without one; an unrecognized file
  name is refused.
- The ignored class comes from `.gitignore`, which scaffold writes for
  scratch directories.
- Every generated file carries one stamp: first line "Code generated by
  TOOL VERSION from SOURCE. DO NOT EDIT.", second line naming the command
  group; JSON files carry an object with `tool`, `version`, `source`, and
  `command`. No timestamp. The first line matches Go's convention, which
  GitHub Linguist and Go tooling recognize.
- rlsbl is the authority. A preflight check refuses: a tracked file
  matching no entry; a tracked file `.gitignore` matches; a tracked file
  under a fixture directory (`testdata`, `fixtures`); a fixture file naming
  the repository's own module path; a generated text file without the
  stamp; a file carrying a generator header the fleet does not recognize; a
  read-only path whose content differs from the previous release tag; an
  append-only path whose content does not begin with its tagged content;
  and a file violating its entry's extension set or depth. The fixture and
  self-reference refusals are errors from the first release that ships
  them, accepted knowing ten projects cannot release until migrated.
- `.gitattributes` receives a derived, marked block only, mapping generated
  to `linguist-generated`, vendored to `linguist-vendored`, selfdoc's
  documentation directories to `linguist-documentation`, `counted` on a
  data or prose language to `linguist-detectable`, and derived language to
  `linguist-language` where Linguist knows the name. The block is a derived
  artifact with a freshness check.
- safegit's commit-time cooperation is optional and filed separately as
  `todo/path-class-cooperation-at-commit-time.md` in safegit.
- A release-tagged, network-bound rlsbl check refuses a family repository
  whose GitHub wiki is enabled.

Vocabulary and suffixes:

- In strictdraw and linguini: "reference" replaces "golden", "check"
  replaces "gate", and the scene format's text alignment key becomes
  `align` with `migrate` mapping predraw's key to it. In stricttest's tests,
  "sentinel" names a planted value and "throwaway home" the installed one.
- Every Go file of a strict module is named `*.strict.go` (tests
  `*.strict_test.go`) and strictgo refuses a strict module with any other
  Go file; every strictspec schema and governed document ends in
  `.strict.toml`.

Corpus content:

- Contexts, placements, actions, support modules, and cells; each rule
  declares which axes vary and the corpus fills their product or marks a
  cell not applicable with a reason; exemptions use the vocabulary of
  strictcli's parity checker; a byte-output column serves single-engine
  layers; applicability per target is a column.
- For safegit and rlsbl, whose tests build thousands of distinct worlds
  from an already shared helper layer, the corpus governs the rule
  registry, base contexts, and a closed operation vocabulary only, not
  full worlds.

## Phase 0: foundational groundwork

Everything later depends on at least one item here. No design work; each
item has a verification an implementor can run.

0.1 **Record strictdraw's parallel measurement.** Run the existing
benchmarks in `/home/m/strictdraw/parallel_test.go` (whole frame, serial
tiles, tiles through the parallel call, tiles without payload) on this
machine and commit the numbers into strictdraw's design record beside the
4K budget decision, with the machine named. Verify: the design record
carries a measurement table, and the benchmark command in a code comment
reproduces it.

0.2 **Send strictgo the two requests with the measurement.** File a strictgo
todo asking for a frozen form of a sealed-element slice that can cross the
parallel call, and for the region-parallel primitive, quoting the recorded
numbers. Verify: the todo exists and names the measurement file.

0.3 **Scratch ignore files fleet-wide.** Run rlsbl's scaffold in every
family repository so `experiments/.gitignore` and `screenshots/.gitignore`
exist with the committed marker files, and fix the scaffold template
application if any repository still lacks them afterwards. Verify: a
capped find over the 25 repositories lists both files in each, and a
tracked file under either directory is only the marker.

0.4 **Reclassify tinymoon's screenshots.** Its 164 tracked element previews
are README assets, not captures: move them to `assets/` and update the
README references. Verify: no tracked file under `screenshots/` except the
marker, and the README renders every image.

0.5 **The extension-to-language table and the stamp definition.** Add to
rlsbl one committed table mapping extensions to languages, one stamp
renderer per comment syntax, and one recognizer, each with red-green tests,
including the case of a template whose content is itself a stamp with
unexpanded placeholders. Verify: the recognizer matches every stamp the
fleet's generators will emit and rejects the six template files the
measurement found.

0.6 **Promote the measurement script.** Move
`/home/m/Projects/stricttools/tools/rlsbl/experiments/fourclass/classify.py`
into rlsbl's `scripts/` as a reusable report, since the path-class check
starts from its rules. Verify: the script runs from `scripts/` and prints
the fleet totals it printed before.

0.7 **Move the strictgo checkout into the family directory.** Move
`~/Projects/strictgo` to `~/Projects/stricttools/tools/strictgo`, and change
the absolute replace directives in reposummary and strictdraw to relative
sibling paths. Verify: `go build ./...` passes in reposummary and
strictdraw, and strictgo's own suite command `scripts/full-suite.sh` still
runs.

0.8 **Create linguini's repository.** `git init` at
`~/Projects/linguini`, move the two design files there, commit, and record
in its design that license and family membership are pending. Verify: the
repository exists with two committed files and a clean tree.

## Phase 1: repository hygiene for strictdraw, linguini, and stricttest

1.1 **strictdraw joins the family.** Move the checkout to
`~/Projects/stricttools/tools/strictdraw`, create the repository under the
stricttools organization after the user confirms the name, set the module
path to `github.com/stricttools/strictdraw` in all three modules, replace
the absolute strictgo path with a relative sibling replace, fix the CI
clone address, and run rlsbl's scaffold so the repository is rlsbl-managed.
Verify: the module-identity preflight check passes and CI runs green once
on GitHub.

1.2 **License recorded.** Keep the MIT text and rule the design record's
pending license entry as decided by the user. Verify: the entry no longer
reads pending.

1.3 **Vocabulary renames in strictdraw.** A dry-run batch with asserted
counts: the `golden` package becomes `reference`, `goldens.txt` becomes
`references.txt`, the recording tool becomes `recordreferences`, test
names follow, "gate" becomes "check" in the design and CI, "anchor" leaves
prose and the scene key becomes `align` with the corpus scene updated and
reference hashes re-recorded, and every other banned term in the design and
critique files is reworded. Verify: a grep for every banned term over
tracked files returns only quoted identifiers of external formats, the
suite passes, and `strictgo check` reports no refusals.

1.4 **strictdraw README truth.** Remove the claim of a hit-test stub that
does not exist and the stale milestone title; state milestone one as done.
Verify: every claim in the README names something the tree contains.

1.5 **strictdraw scratch and renders.** Add the scaffold's scratch
directories; move the committed renders out of the tree since rendered
output is never committed, keeping the reference hashes and the render
command. Verify: no tracked file under `renders/`, and the path-class
report classifies every strictdraw file.

1.6 **linguini vocabulary.** Reword the banned terms in its design and
critique, renumber the critique's proposed open items so they do not
collide with the existing ones, and record "check" and the alignment
wording. Verify: the banned-term grep is clean and the open-item numbers
are unique.

1.7 **stricttest test words.** Rename the planted values to sentinel and
the two prose uses to throwaway home in the four test files. Verify: the
three suites pass and the word "poisoned" is gone.

## Phase 2: strictspec

2.1 **The `sourcecode` type.** Amend decision 35 in the design record, add
the type to the schema model and reader in all three targets, the runtime
validators, the emitter bindings, the JSON Schema export, the error-code
appendix with regenerated catalogues, the surface-syntax and semantics
appendices, a gap note and draft schema per the process, and conformance
fixtures for every refusal (missing language, unknown language, trailing
whitespace, missing final newline, inconsistent indentation) plus valid
multi-line literal bodies. Verify: the conformance run passes on all four
targets, every new code has a fixture, and an unknown type name is no
longer silently skipped but refused with the catalogued code.

2.2 **The formatter command.** A command beside `validate` that reads a
schema, finds every `sourcecode` field with a declared formatter, runs it
through strictcli's process effect, and refuses any value that changes,
with a remedy naming the field, the language, and the formatter. Verify: a
fixture exercises the remedy and the command reports clean afterwards, and
`--dry-run` records the process without running it.

2.3 **The schemas directory.** Register `.stricttools/schemas/` in
selfdoc's layout with strictspec as owner, move the manifest and schemas
there under the new names, and ship a one-time `migrate` subcommand that
moves a consumer's files and rewrites its manifest. Verify: rlsbl, selfdoc,
claudestream, claudewheel, predraw, and orxtra migrate with the command,
`strictspec check` is green in each, and the old root directory is refused.

2.4 **Strict suffix refusal.** strictspec refuses schema or document names
not ending in `.strict.toml`; generated validators carry the same refusal;
consumers rename governed documents (rlsbl's workspace and release files,
strictcli's checks documents, and the rest found by grep) and update every
path that names them. Verify: each consumer's suite passes and the refusal
has a fixture with its remedy executed.

2.5 **Harness catalogue generated.** Extend the Python catalogue generator
with a target that writes the harness's catalogue module, and extend the
freshness test to slot types and areas. Verify: the harness catalogue is
byte-identical to a fresh generation and the test fails when one template
is edited by hand.

2.6 **Batch regeneration helper.** The required deliverable named in the
design's drift decision: a helper that regenerates every consumer's
validators and commits with the machine-made trailer. Verify: the five
consumers on older generated formats are regenerated and green.

2.7 **Release.** One minor release of the strictspec releasable. Verify: the
release run completes and the changelog carries the type, the move, the
suffix, and the generated catalogue as user-facing entries.

## Phase 3: strictcli

3.1 **One message source document.** Author every message as an identity
with a template and typed slots in one document, following strictspec's
appendix, including strictcli's 440 unnamed Python templates. Generate the
Go, TypeScript, and Python catalogues; make every implementation render
through its catalogue; add the identity to machine-mode diagnostics and
error output. Verify: the three suites pass, the conformance run passes,
and no message text exists in an implementation outside its generated
catalogue.

3.2 **Parity by identity.** Rewrite the parity checker to compare the
generated tables by identity, re-key the exemption table by identity, and
delete the regex extractors and their tests. Verify: the checker reports
the same exemption count by identity as it did by signature, and coverage
is computed from cases' rule references once phase 6 adds them.

3.3 **Generator command group.** Implement the filed todo in Go, then
Python and TypeScript, with conformance cases. Verify: a registered group
with a third command is refused at registration, an undeclared write is
refused at run time, the stamp appears per extension, and `status` reports
fresh, stale, and missing correctly in all three implementations.

3.4 **Release.** One minor release of the three strictcli releasables.
Verify: completed run, changelog entries for the registry, the identity in
machine mode, and the generator group.

## Phase 4: rlsbl, the repository shape

4.1 **The paths directory.** Register `.stricttools/paths/` in selfdoc's
layout with rlsbl as owner, author the strictspec schema for its files in
rlsbl's schemas directory, and ship the extension table and exceptions
format. Verify: an empty paths directory validates, an entry with a
wildcard is refused, and the six field names are the decided ones.

4.2 **The path-class check.** One preflight check, pure, enumerating
tracked files through `git ls-files`, resolving entries most specific
first, and refusing each of the nine conditions listed under decisions,
with a red-green test per refusal and per remedy. Read-only and
append-only comparisons read the previous release tag. Verify: rlsbl's own
tree passes with a paths declaration generated from the measurement, and
each refusal is demonstrated in the test suite against a real repository.

4.3 **Fixture and self-reference refusals.** Two preflight errors from the
same walk: any tracked file under `testdata` or `fixtures`, and any fixture
file containing the repository's own module path, each remedy naming the
migration. rlsbl's scanners that treat `testdata` as legitimate test
context are reworked to read the paths declaration instead. Verify: rlsbl
and stricttest pass, and the ten family projects with fixtures fail with
the expected sentence.

4.4 **The derived attributes block.** Render the Linguist mappings into a
marked block in `.gitattributes`, with a freshness refusal when the block
is missing or stale. Verify: a repository with the block passes, a clobbered
file is refused with the re-render remedy.

4.5 **Generators adopt the stamp.** rlsbl's changelog, router, and publish
generators become generator groups and emit the stamp; selfdoc's page and
root-file generators do the same in their next release; pgdesign's stamp
follows; the eight project-local scripts adopt the stamp or are wrapped in
a group. Verify: the recognizer finds no unrecognized generator header in
the fleet.

4.6 **The wiki check.** A release-tagged check asking GitHub whether the
repository's wiki is enabled and refusing with the settings remedy. Verify:
tested against a fixture of the API response both ways.

4.7 **Fleet authoring pass.** Generate each family repository's
`paths.strict.toml` and `exceptions.strict.toml` from the measurement,
review by hand, set extension sets and depths where the set is closed, and
commit. Verify: the path-class check passes in every repository except the
ten awaiting fixture migration, whose only refusals are the fixture ones.

4.8 **Release.** One minor release of rlsbl. Verify: completed run; the
changelog names the check, the directory, the attributes block, and the
wiki check.

## Phase 5: rule registries in the tools

5.1 **strictgo.** Collapse the module path constant to one declaration;
give the finding type a refusal identity with arguments; promote the
message tables, the message constants and functions across the rule
packages, the commands package's constructors, and the runtime's sentences
into one registry with identities and message functions; keep the wording
tests. Verify: every sentence the checker or runtime can emit is produced
by a registry entry, the suite passes, and a wording change is one edit.

5.2 **safegit and rlsbl.** Introduce message constants or functions for
every sentence tests currently paste, so a test can name the message.
Verify: the pasted-sentence count from the census falls to zero in both
suites.

## Phase 6: the test-declaration half of stricttest

6.1 **The format and schema.** Author the corpus schema in stricttest's
schemas directory using the `sourcecode` type for action bodies, with
contexts, placements, actions, support modules, cells, per-rule axis
declarations, exemptions with reasons, applicability, and the byte-output
column. Verify: strictspec validates the schema, and a fixture corpus of
every table shape validates in all three targets.

6.2 **Readers.** The Go `corpus` package, the Python subpackage, and the
TypeScript export, each loading a corpus through the generated validator
and exposing typed tables; the lockstep test extended to the operation
vocabulary. Verify: the same fixture corpus loads identically in the three
languages, and a vocabulary drift fails the lockstep test.

6.3 **Generic renderers.** File tree and git repository renderers over the
closed operation vocabulary from the census, writing under scratch inside
stricttest's own isolation. Verify: each operation has a red-green test,
and a rendered git repository matches a recorded expected state.

6.4 **The command binary.** A strictcli Go program with `check`
(completeness both ways, exemptions, axis products, applicability,
formatting of action bodies through strictspec's formatter command, no
fixture directories), `render`, and `coverage`. Verify: every refusal has
a fixture that performs its remedy and clears, and `check` passes on the
fixture corpus.

6.5 **Registry adapters.** The contract by which a tested tool exposes its
registry to the checker, with strictgo's registry as the first adapter.
Verify: the checker renders strictgo's expected sentence for a cell and
detects a cell naming an unknown rule.

6.6 **Docs and release.** Documentation through selfdoc, and one minor
release of each of the three releasables. Verify: completed run and the
three package installs expose the corpus readers.

## Phase 7: corpus migrations

Each migration deletes the scripts and tests it obsoletes and is verified
by the same refusal sentences the old suite asserted, now derived.

7.1 **strictgo escapes.** Declare the 159 fixtures as cells using the
placement and action features the extraction script already produces,
share the sixteen library copies as one support module, declare the two
support directories, express absences through omit actions, mark the
compiler-closed cases with the compile verb, and render the escapes
documentation page from the cells. Delete the escapes directory, the two
consistency tests, and the five maintenance scripts. Verify: the same
refusals fire, the docs page is generated and fresh, and no tracked file
under `testdata` remains for this suite.

7.2 **strictgo command fixtures and analyzer stubs.** Fold the 560 command
fixtures, including the 184 the generator does not know, into cells with
the message constructors as registry references; render the analyzer
suite's inputs against the stub runtime as a second renderer target and
replace the 283 regex comments with cell expectations. Verify: the suites
pass with no `testdata` directory in strictgo, and the examples directory
stays committed and checked.

7.3 **strictspec.** Adopt the corpus for its conformance fixtures: collapse
the 62 duplicates, add rule-to-cell coverage over its 130 codes with
reasoned exemptions, add the target-applicability column, fold the
toolchain fixtures into the byte-output column, and delete the second
fixture format. Verify: the conformance run passes and every code has a
cell or an exemption.

7.4 **strictcli.** Add the rule column to cases, lift the 963 app
definitions into a contexts table and the checks and config contents into
support material, replace pasted expectations with rule references, retire
the capture script, and turn the pairwise generator's axes into per-rule
axis declarations. Verify: the conformance run and parity pass, and the
coverage direction covers all 536 identities or exempts them with reasons.

7.5 **selfdoc, pgdesign, safegit, strictcli's Go fixtures, dirstat,
go-toml-edit, claudestream, toolstream.** Each project's fixture directory
is either migrated to cells or reclassified as authored assets where the
files are documentation inputs, so that the fixture refusal passes. Verify:
each project's preflight passes.

7.6 **safegit and rlsbl worlds.** Register their base contexts as rows,
adopt the operation vocabulary in their helpers, and switch pasted
sentences to registry references; per-test deltas stay in the tests.
Verify: the census script reports zero pasted sentences and every world
operation from the vocabulary.

## Phase 8: the family module-path moves and first releases

8.1 **strictgo's rename and first release.** With no fixture naming the
path, rewrite the module to `github.com/stricttools/strictgo` with rlsbl's
rewrite command, fix by hand what it does not cover (README, docs, scripts,
CI), backfill nothing, and run strictgo's first release, staying below
1.0. Verify: the module-identity check passes, the release completes, and
reposummary and strictdraw build against the published version with no
replace directive.

8.2 **The nine family modules.** Rewrite and release in dependency order:
go-toml-edit, stricttest, and tinymoon; then strictcli and strictspec
re-released against them; then dirstat, howmuchleft, safegit, and saferm;
then pgdesign; then selfdoc; then reposummary. Clear the known blockers
first: tinymoon's ten uncovered commits, strictcli's empty root release
record, reposummary's red suite. For each, do the hand steps the rewrite
does not: README install lines, publish workflows, npm and PyPI package
metadata, docs templates. Verify: the module-identity check passes in
every family module and every release completes.

8.3 **Site and consumers.** Update the site's tool data and regenerate its
pages; move the external consumers (gamehome's two modules, strictcode,
strictexpr, wmra, the auth gateway) to the new paths. Verify: no `go.mod`
under `~/Projects` requires a family module by its old path, and the site
publishes no old install line.

## Phase 9: strictdraw to completion

9.1 **Design revision four.** Fold the 65 findings of the third critique,
the ten additions to the still-to-write list, and the contradictions list;
resolve the strict-library versus kernel contradiction by keeping the
library declaration; record the font-matching component as from scratch;
rule the pending decisions the user has since decided. Verify: a blind
review by a fresh reader reports no stale mention and no unresolved
referent.

9.2 **Milestone two.** Layers, blends, masks, blur, images and the
resampler, the SVG emitter in both text modes, limits in lowering, hit
testing, and `migrate` with its refusals including WebP and font stacks.
Verify: the skipped corpus outputs gain reference hashes and the round-trip
check over every corpus scene passes.

9.3 **Milestone three.** The typesetting fork with the font-matching
package deleted and matching written from scratch, the glyph cache, bitmap
strikes, variable fonts, line breaking, the lockfile, and the license
warning. Verify: the text scene renders and joins the reference hashes.

9.4 **Milestone four.** The command-line program on strictcli, packaging,
and predraw's retirement with its two examples migrated into the corpus.
Verify: predraw's final release points at strictdraw and both examples
render.

9.5 **Milestone five.** Region parallelism once strictgo ships the frozen
slice and the region primitive. Verify: the parallel benchmark beats the
recorded copy cost.

9.6 **Corpus adoption.** strictdraw's scenes, outputs, and scales become
cells. Verify: the corpus check passes in strictdraw.

## Ordering

Phase 0 first. Phases 1 and 2 are independent of each other. Phase 3
depends on 2 for the schema type used by its message document. Phase 4
depends on 3 for the generator group and on 0 for the table and stamp.
Phase 5 depends on nothing after 0 and may run beside 2 through 4. Phase 6
depends on 2, 3, and 5. Phase 7 depends on 4 and 6. Phase 8 depends on 7
for strictgo and on 4 for the fixture refusals not blocking the others.
Phase 9 depends on 1 and on 7 for its corpus adoption; its milestones two
through four may run beside phases 3 through 8.

## Effort

Phase 0: a week. Phase 1: a week. Phase 2: two to three weeks. Phase 3:
four to six weeks, the message document being the largest single item.
Phase 4: three weeks. Phase 5: two weeks. Phase 6: four to six weeks. Phase
7: six to eight weeks across the projects. Phase 8: two weeks plus release
review time. Phase 9: the longest, several months, dominated by fonts.
