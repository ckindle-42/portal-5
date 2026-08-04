# SIMPLIFY_RENDER_PROPOSAL — R5, TASK_PORTAL_SIMPLIFY_V1

**Status:** Discovery + proposal only (R5.3 not implemented pending operator review).
**Discovery date:** live reads at `cb5f261a` (R3 landed).

## R5.1 — Current behavior (established by reading the source)

`portal/platform/wiki/render.py` defines `TIER1_DOCS` (25 paths: README, P5_ROADMAP, KNOWN_ISSUES, KNOWN_LIMITATIONS, 18 docs/*.md, config/MODEL_CATALOG.md, three tests/*.md).

- `render_all_generated_blocks(repo_root, doc_paths=None)` scans the Tier-1 docs, finds `<!-- WIKI:GENERATED unit=... -->` markers, and re-renders each block from its unit's current body. It returns the list of docs that changed.
- `check_generated_blocks_current(repo_root, doc_paths=None)` is the read-only drift twin: which docs have a generated block that does not match its unit's body right now. Empty = clean.
- Both skip a doc that does not exist (`if not doc_path.exists(): continue`) — **the "every doc must exist" requirement is already soft.** AW (`check_wiki_facts_current`) asserts the freshness half (generated doc blocks vs units) plus fact-unit currency plus the A1 no-un-fenced-substance rule for migrated docs. It does **not** assert that all 25 Tier-1 docs exist.
- `render --check` (the CLI view check, `portal_wiki/__main__.py:cmd_render`) is a *different* gate: it renders `admin_guide` + `architecture_map` into a temp dir and compares against committed `docs/generated/`. That is the one "must be in sync" assertion that covers all committed generated views.

**So the eager-freshness cost is narrower than the task's brief assumed**: AW already tolerates a missing doc (only docs that exist are freshness-checked). What remains eager is (a) `render --check`'s two committed views and (b) AW's freshness assertion that *every existing* generated block be current at push time.

## R5.2 — Proposed on-demand path

Add `--doc <path>` to the `render` CLI and thread it through:

```
python3 -m portal_wiki render --doc docs/FISH_SPEECH_SETUP.md
```

Implementation sketch: `cmd_render` gains a `--doc` flag; when present it calls
`render_all_generated_blocks(repo_root, [repo_root / rel])` for just that path
and reports which blocks changed. `render_unit_into_doc` already handles a
single doc, so this is a thin arg-plumbing change, not a new renderer.

## R5.3 — Proposed gate change (do not implement without review)

Keep the freshness assertion for docs that **exist**, drop any requirement that
all 25 exist (already effectively true — make it explicit rather than
incidental), and let the rest render on request.

- **Preserve:** a committed doc is never stale. AW's `generated doc blocks vs
  units` stays as-is for every existing Tier-1 doc, and `render --check` stays
  for the two committed `docs/generated/` views.
- **Drop:** nothing material — the "all 14 must exist" reading is already not
  enforced. The proposal therefore mostly *documents* the current softness and
  adds the `--doc` on-ramp, rather than deleting an enforcement.
- **Add:** a `scripts/OPERATOR_TOOLS.md`-style note or a wiki HOWTO entry naming
  `render --doc` as the repair path for a single drifted doc, so an operator
  fixing one doc does not need a full `render --all`.

**Verdict:** low-value as a behavior change (the gate is already effectively
on-demand-tolerant); the only concrete deliverable is the `--doc` CLI flag.
Recommend deferring unless an operator wants the flag now. Per R5.3, this phase
is optional to the program's value — the program continues to Part II with this
proposal recorded.
