# DESIGN_WIKI_GENERATION_LOOP_V1

## Principles

### Single write-point

The `portal_wiki/canonical/` spine is the single write-point for documentation: a fact is edited in one unit, and `render_all_generated_blocks` rewrites every `WIKI:GENERATED` block that references it across the `TIER1_DOCS` set. Downstream docs are shells -- their generated substance is the unit body, not a separate copy -- so the same fact is never maintained in two places.

This inverts the traditional model of hand-maintaining prose and then auditing for drift. A generated block cannot drift independently because it has no independent prose: `sync-config` invokes `render_all_generated_blocks`, and only the content between the `WIKI:GENERATED` markers is replaced, leaving human-authored narrative untouched.

The enforcement gate is validate check AW in `scripts/validate_system.py`: `check_wiki_facts_current` diffs each generated block against its unit's current body via `check_generated_blocks_current`, so a mismatch is a precise signal that `sync-config` was not re-run after the source unit changed. AW also verifies fact-units against live config and that migrated docs carry no un-fenced substance.

## Why

Concentrating the write-point in the spine is what makes doc currency mechanical rather than reviewable. If facts lived in two places, nothing could stop them from diverging except an audit nobody schedules; the block-fill contract turns divergence into a per-block diff failure a pre-commit gate can catch. AW diffs against the unit body rather than a hash or timestamp because only an exact body comparison produces the precise, actionable mismatch that a coarse directory-changed signal cannot.

### Fence contract

A migrated doc contains exactly two managed content types. First, `WIKI:GENERATED` blocks, delimited by an opening `&lt;!-- WIKI:GENERATED unit=&lt;id&gt; --&gt;` marker and a closing `&lt;!-- /WIKI:GENERATED --&gt;` marker, whose content is filled from the spine unit body by `render_all_generated_blocks`. The marker is placed once by hand; the renderer only replaces content between markers and never invents a location, so the inside of a generated fence is never hand-edited. Second, `WIKI:HUMAN-OWNED` fences, whose current opening form carries a `reason="..."` attribute; the older bare V1 form without a reason is detected and treated as unreasoned, which fails `doc_is_migrated`. Human-owned fences hold irreducible judgment -- rationale, caveats, opinions. A fact (a count, a path, a name, a behavior of the code) belongs in a unit; a judgment may live in a fence.

`doc_is_migrated` demands more than clean fences: at least one generated block, a human-fence share at or below the `_HUMAN_FENCE_MAX` bound, every fence reasoned, and zero `substantive_remainder`. Inert markdown structure -- headings, horizontal rules, blank lines, table separator rows, standalone tags, non-WIKI HTML comments -- may sit outside fences without triggering discovery.

## Why

The fence contract is what makes "migrated" a mechanically checkable property instead of a claim. V2 made the reason attribute a hard requirement because an unreasoned fence is indistinguishable from dumping narrative into a doc to dodge discovery. The generated-block floor and the bounded human-fence ratio close the mirror-image loophole: a doc cannot pass by fencing everything, which is the exact game `doc_is_migrated` and the validate gate exist to catch.
### Section-level granularity

A unit maps by default to a doc section -- the chunk a human or agent thinks of as the thing they edit. Finer fact-unit decomposition is reserved for values that earn it: a value reused across more than one doc, or a value independently volatile on its own schedule, such as counts, ports, model IDs, or thresholds. Rationale is the tiebreaker between the two; the aim is the unit best for an agent to manage and easiest for a human to read. Pure fact-atomization of everything is forbidden, because it turns a doc into a flood of unreadable micro-units and is worse for both audiences.

The `seed_facts.py` derivers implement this through the `_make_unit` idempotency pattern: when the newly derived body matches what is already stored, the prior unit's sources and timestamps are reused wholesale, so a unit file changes on disk only when its body actually changed. (Before P0 A1, a `last_generated_commit` pin was reused the same way and this paragraph described it; P0 deleted the pin outright, so the idempotency now governs sources/timestamps only.) A body change lands in a single commit — repeated `sync-config` runs with no body change produce no churn either way.

## Why

Granularity is a management choice, not a data-model property, so the rule exists to stop the cheapest failure mode: machine-seeded authors splitting everything into atoms and flooding the canonical directory with near-duplicate noise. The `_make_unit` pattern exists for the parallel reason -- if the stamp advanced on every run, every fact-unit would be rewritten on every `sync-config`, turning an idempotent render step into a permanent diff generator and making HEAD pinning meaningless.

## Mechanism

### Discovery and termination

The migration loop repeatedly calls `discover_unmigrated_docs()` and halts when the returned list is empty. The candidate set is computed at runtime as the `TIER1_DOCS` tuple unioned with any paths still present in a legacy ledger file (via `_ledger_doc_paths`); it is never chosen by hand on each run. Results are processed highest-priority first: `priority` is a git-churn count over the last 30 commits touching the file, plus a fixed boost for high-value seed docs, sorted descending.

Every doc migration is an atomic green slice. After a single doc migrates the repo is fully working, the doc is generated and round-trip proven; the loop may stop after any commit and resume later with no cleanup. `render_report()` supplies the standing dashboard as `{migrated, unmigrated, gamed, blocks_total, coverage_pct, human_ratio}`. Content-hash currency (validate check AW) diffs every generated block against its unit body, so the candidate discovery set collapses to the Tier-1 set once the legacy commit-stamp ledger is gone.

## Why

Mechanical termination exists so migration is never an open-ended rewrite campaign. Because each doc commits atomically and the candidate set is derived from git churn plus the Tier-1 tuple, an operator can interrupt the loop at any commit, resume later, and still find every intermediate state passes the migration gate. The legacy commit-stamp ledger (the `docs`-tree ledger file and its `scripts`-tree pruning script) was deleted in TASK_WIKI_ZERO_DEBT_V1 once its empty state made the `AK` doc-currency check a no-op; AW diffs generated blocks against unit bodies directly, so the commit-stamp model is redundant and the discovery surface is just the Tier-1 set.

### Migration coverage

<!-- WIKI:GENERATED unit=unit-fact-doc-migration-coverage -->
# Doc migration coverage (0/25 docs migrated, 0.0%)

Total generated blocks across migrated docs: 12

## Migrated docs (content-hash gate only)


## Unmigrated docs

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

## Why

The migration numbers come from `render_report()` in `portal/platform/wiki/render.py`, which classifies every Tier-1 doc as migrated, unmigrated, or gamed and counts the generated blocks. Deriving the coverage figure from that same function keeps the documented migration state and the one the renderer actually computes identical.
<!-- /WIKI:GENERATED -->

## Migration procedure

For each doc `D` returned by `discover_unmigrated_docs()`, processed highest priority first, the loop body is:

1. Read `D` and read HEAD reality; verify every substantive claim against actual code, config, or data and author units from HEAD truth, never from stale prose.
2. Decompose `D` into section-level units, reserving fact-atom decomposition for values that are reused or independently volatile (see the section-granularity unit).
3. Convert `D` into a shell whose substance is `WIKI:GENERATED` blocks plus `WIKI:HUMAN-OWNED` fences for the irreducible judgment.
4. Render through `sync-config`, which invokes `render_all_generated_blocks`, then prove round-trip: an edit to the unit propagates and a hand-edit inside a generated fence is clobbered.
5. Verify the per-commit gate is green, commit, then re-discover and continue.

Each doc lands as one atomic commit, the repo is green after every commit, and the loop is resumable at any point without cleanup.

## Why

The procedure is a fixed loop body because a migration that cannot be verified at each step silently degrades into docs-are-the-source authoring. Rendering through `sync-config` and proving propagation and clobbering closes the loop. The atomic-commit rule keeps every intermediate state buildable, which is what makes the loop safe to interrupt and resume. The legacy commit-stamp ledger (the `docs`-tree ledger file and its `scripts`-tree pruning script) was deleted in TASK_WIKI_ZERO_DEBT_V1 once its empty state made `AK` a no-op; discovery now collapses to the Tier-1 set and AW diffs generated blocks against unit bodies directly.
