# DESIGN_WIKI_GENERATION_LOOP_V1

## Principles

### Single write-point

<!-- WIKI:GENERATED unit=unit-DESIGN_WIKI-spine-write-point -->
The `portal_wiki/canonical/` spine is the single place truth is edited. Every downstream doc is a **shell** whose substance is rendered from spine units. You edit one unit; a process regenerates every downstream file that draws on it. You never update the same fact in two places.

This inverts the traditional documentation model (hand-maintain prose, then audit for drift) into a mechanical one: drift is impossible because the doc has no independent prose to drift -- its content IS the unit body, filled in by `render_all_generated_blocks` during `sync-config`.

The enforcement gate is AW in `validate_system.py`: it diffs each WIKI:GENERATED block against its unit's current body. A mismatch means `sync-config` was not re-run after a source change.
<!-- /WIKI:GENERATED -->

### Fence contract

<!-- WIKI:GENERATED unit=unit-DESIGN_WIKI-fence-contract -->
A migrated doc contains exactly two types of managed content:

1. **WIKI:GENERATED blocks** -- delimited by `&lt;!-- WIKI:GENERATED unit=&lt;id&gt; --&gt;` and `&lt;!-- /WIKI:GENERATED --&gt;`. Content is filled from a spine unit by `render_all_generated_blocks`. Never hand-edit inside this fence -- edit the unit instead.

2. **WIKI:HUMAN-OWNED fences** -- delimited by `&lt;!-- WIKI:HUMAN-OWNED --&gt;` and `&lt;!-- /WIKI:HUMAN-OWNED --&gt;`. Irreducible human judgment (rationale, caveats, opinions). This is first-class, not a loophole for un-migrated facts. A fact (a count, a path, a name, a behavior of the code) belongs in a unit; a judgment may live here.

Any substantive line outside both fences is **un-migrated content** -- a discovery hit. Inert markdown structure (headings, horizontal rules, blank lines) may exist outside fences without triggering discovery.
<!-- /WIKI:GENERATED -->

### Section-level granularity

<!-- WIKI:GENERATED unit=unit-DESIGN_WIKI-section-granularity -->
A unit maps to a **doc section** -- the chunk a human/agent thinks of as "the thing I edit." This is the default granularity. Decompose to a finer fact-unit **only** when a value is:

- **(i) Reused** across more than one doc, or
- **(ii) Independently volatile** (counts, ports, model IDs, thresholds).

Rationale is the tiebreaker: best for the agent to manage, easiest for the human to read. **Pure fact-atomization of everything is forbidden** -- it produces hundreds of unreadable micro-units, worse for both audiences.

The existing `seed_facts.py` derivers follow the `_make_unit` idempotent pattern: they only advance `last_generated_commit` when the body actually changes, preventing no-op churn on every `sync-config` run.
<!-- /WIKI:GENERATED -->

## Mechanism

### Discovery and termination

<!-- WIKI:GENERATED unit=unit-DESIGN_WIKI-discovery-termination -->
The migration loop processes whatever `discover_unmigrated_docs()` returns, highest-priority first, and **halts when it returns empty**. The doc list is computed, never hardcoded.

Each iteration is an **atomic green slice**: after any single doc migrates, the repo is fully working -- that doc is generated + round-trip-proven + de-ledgered; all other docs are untouched. The loop may stop after any commit and resume later with no cleanup.

Priority is a hint (most-important/most-churned first), not a fixed sequence. `render_report()` provides the standing progress dashboard: `{migrated, unmigrated, blocks_total, coverage_pct}`.

When `discover_unmigrated_docs` returns empty, the commit-stamp ledger (`docs/.doc_ledger.yaml`) should be at or near empty -- every graduated doc has been pruned by `doc_ledger.py prune`, and only content-hash currency (AW) governs them.
<!-- /WIKI:GENERATED -->

### Migration coverage

<!-- WIKI:GENERATED unit=unit-fact-doc-migration-coverage -->
# Doc migration coverage (25/25 docs migrated, 100.0%)

Total generated blocks across migrated docs: 551

## Migrated docs (content-hash gate only)

- `README.md`
- `P5_ROADMAP.md`
- `KNOWN_ISSUES.md`
- `KNOWN_LIMITATIONS.md`
- `docs/HOWTO.md`
- `docs/ADMIN_GUIDE.md`
- `docs/SECURITY_BENCH_EXEC.md`
- `docs/USER_GUIDE.md`
- `docs/CLUSTER_SCALE.md`
- `docs/ALERTS.md`
- `docs/PERFORMANCE.md`
- `docs/MCP_DEV_TOOLING.md`
- `docs/COMFYUI_SETUP.md`
- `docs/FISH_SPEECH_SETUP.md`
- `docs/COMPLIANCE_FALLBACK_POLICY.md`
- `docs/BACKUP_RESTORE.md`
- `docs/LAB_SETUP.md`
- `docs/PERSONA_MATRIX_CI.md`
- `docs/AGENT_LOOP.md`
- `docs/DESIGN_WIKI_GENERATION_LOOP_V1.md`
- `docs/security/corpus_injection.md`
- `config/MODEL_CATALOG.md`
- `tests/PORTAL5_ACCEPTANCE_EXECUTE_V9.md`
- `tests/PORTAL5_BENCH_EXECUTE_V4.md`
- `tests/PORTAL5_BENCH_SEC_EXECUTE_V3.md`

## Unmigrated docs (commit-stamp ledger)
<!-- /WIKI:GENERATED -->

## Migration procedure

<!-- WIKI:GENERATED unit=unit-DESIGN_WIKI-migration-procedure -->
For each doc `D` returned by `discover_unmigrated_docs()` (highest priority first):

1. Read `D` and read HEAD reality. For every substantive claim, verify against actual code/config/data. Author units from HEAD truth, not stale prose.
2. Decompose `D` into section-level units (A2 granularity rule).
3. Convert `D` to a shell of WIKI:GENERATED blocks and WIKI:HUMAN-OWNED fences for irreducible judgment.
4. Render via `sync-config`, prove round-trip (edit-propagates, hand-edit-is-clobbered).
5. Retire `D` from commit-stamp ledger via `doc_ledger.py prune`.
6. Verify green, commit. Re-discover and continue.

Each doc is one atomic commit. The repo is green after every commit. The loop is resumable at any point.
<!-- /WIKI:GENERATED -->
