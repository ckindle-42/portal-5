# DESIGN_WIKI_GENERATION_LOOP_V1

## Principles

### Single write-point

Authored knowledge lives in `portal_wiki/canonical/`. Live `unit-fact-*` units are computed on demand through the wiki MCP from current config, code, and probes, and are not persisted. `uv run portal docs build` is the explicit command that refreshes managed blocks across `TIER1_DOCS` and renders generated views.

Runtime config generation and documentation generation have separate lifecycles. `sync-config` writes routing, MCP, Open WebUI preset, and module artifacts only. The docs build replaces only content between `WIKI:GENERATED` markers, leaving human-authored narrative untouched.

The former AW generated-doc and stored-fact freshness gate is retired. `BS` checks authored claims and computed fact claims against live probes. Documentation is refreshed explicitly with `portal docs build` when needed.

## Why

The canonical store owns durable authored guidance. Computed facts resolve from current inputs when queried, and docs remain separate build outputs. This keeps routine runtime artifact generation from writing documentation or materializing fact snapshots.

### Fence contract

A migrated doc contains exactly two managed content types. First, `WIKI:GENERATED` blocks, delimited by an opening `&lt;!-- WIKI:GENERATED unit=&lt;id&gt; --&gt;` marker and a closing `&lt;!-- /WIKI:GENERATED --&gt;` marker, whose content is filled from the spine unit body by `render_all_generated_blocks`. The marker is placed once by hand; the renderer only replaces content between markers and never invents a location, so the inside of a generated fence is never hand-edited. Second, `WIKI:HUMAN-OWNED` fences, whose current opening form carries a `reason="..."` attribute; the older bare V1 form without a reason is detected and treated as unreasoned, which fails `doc_is_migrated`. Human-owned fences hold irreducible judgment -- rationale, caveats, opinions. A fact (a count, a path, a name, a behavior of the code) belongs in a unit; a judgment may live in a fence.

`doc_is_migrated` demands more than clean fences: at least one generated block, a human-fence share at or below the `_HUMAN_FENCE_MAX` bound, every fence reasoned, and zero `substantive_remainder`. Inert markdown structure -- headings, horizontal rules, blank lines, table separator rows, standalone tags, non-WIKI HTML comments -- may sit outside fences without triggering discovery.

## Why

The fence contract is what makes "migrated" a mechanically checkable property instead of a claim. V2 made the reason attribute a hard requirement because an unreasoned fence is indistinguishable from dumping narrative into a doc to dodge discovery. The generated-block floor and the bounded human-fence ratio close the mirror-image loophole: a doc cannot pass by fencing everything, which is the exact game `doc_is_migrated` and the validate gate exist to catch.
### Section-level granularity

A unit maps by default to a doc section -- the chunk a human or agent thinks of as the thing they edit. Finer fact-unit decomposition is reserved for values that earn it: a value reused across more than one doc, or a value independently volatile on its own schedule, such as counts, ports, model IDs, or thresholds. Rationale is the tiebreaker between the two; the aim is the unit best for an agent to manage and easiest for a human to read. Pure fact-atomization of everything is forbidden, because it turns a doc into a flood of unreadable micro-units and is worse for both audiences.

The `seed_facts.py` derivers build fact units in memory for each wiki MCP request. They do not write unit files or timestamps, and `sync-config` does not run them.

## Why

Granularity is a management choice, not a data-model property. Durable guidance belongs in readable authored units; volatile values belong in reusable computed fact units that stay out of the canonical directory.

## Mechanism

### Discovery and termination

The migration loop repeatedly calls `discover_unmigrated_docs()` and halts when the returned list is empty. The candidate set is computed at runtime as the `TIER1_DOCS` tuple unioned with any paths still present in a legacy ledger file (via `_ledger_doc_paths`); it is never chosen by hand on each run. Results are processed highest-priority first: `priority` is a git-churn count over the last 30 commits touching the file, plus a fixed boost for high-value seed docs, sorted descending.

Every doc migration is an atomic green slice. After a single doc migrates the repo is fully working, the doc is generated and round-trip proven; the loop may stop after any commit and resume later with no cleanup. `render_report()` supplies the standing dashboard as `{migrated, unmigrated, gamed, blocks_total, coverage_pct, human_ratio}`. The dashboard reports migration state; generated-doc freshness is handled by an explicit docs build rather than a validate gate.

## Why

Mechanical termination exists so migration is never an open-ended rewrite campaign. Because each doc commits atomically and the candidate set is derived from git churn plus the Tier-1 tuple, an operator can interrupt the loop at any commit and resume later. The docs build is explicit, and live fact units are computed by the wiki MCP rather than synchronized into canonical files.

### Migration coverage

Current migration coverage is computed on demand. Query `unit-fact-doc-migration-coverage` through the wiki MCP; use `uv run portal docs build` to refresh generated docs for a release.

## Migration procedure

For each doc `D` returned by `discover_unmigrated_docs()`, processed highest priority first, the loop body is:

1. Read `D` and read HEAD reality; verify every substantive claim against actual code, config, or data and author units from HEAD truth, never from stale prose.
2. Decompose `D` into section-level units, reserving fact-atom decomposition for values that are reused or independently volatile (see the section-granularity unit).
3. Convert `D` into a shell whose substance is `WIKI:GENERATED` blocks plus `WIKI:HUMAN-OWNED` fences for the irreducible judgment.
4. Render through `uv run portal docs build`, then prove round-trip: an edit to the unit propagates and a hand-edit inside a generated fence is clobbered.
5. Verify the per-commit gate is green, commit, then re-discover and continue.

Each doc lands as one atomic commit, the repo is green after every commit, and the loop is resumable at any point without cleanup.

## Why

The procedure is a fixed loop body because a migration that cannot be verified at each step silently degrades into docs-are-the-source authoring. Rendering through the separate docs build and proving propagation and clobbering closes the loop. Runtime artifact generation remains independent of documentation output.
