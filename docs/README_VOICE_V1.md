# README_VOICE_V1 — outcome report

**Task:** `coding_task/TASK_README_VOICE_V1.md` (critical path of
`BUILD_PROGRAM_PORTAL5_VOICE_V1.md`).
**Range:** `117f407a..e3eba52e` on `main` (6 commits) + `HF` guard.
**Authored against:** `117f407a` (2026-09-08). Every §2 figure re-measured in Phase R
matched the task file exactly — no divergence, no silent payload adaptation.

---

## 1. Before / after

| Measure | Before (`117f407a`) | After |
|---|---|---|
| README chars machine-rendered | 91.3% | **71.4%** |
| Generated blocks | 31 | 24 (+1 hand-placed rollup marker = 25 markers) |
| Human-owned fence lines | **0** / 681 | **147** / 777 |
| Human-fence ratio | 0.000 | **0.189** (ceiling 0.40, headroom 163 lines) |
| README `## Why` inversions (R-D1) | 10 | **0** |
| README H1 headings (R-D2) | 14 | **1** |
| README units | 31 | 25 (7 merged → 2, 1 new rollup) |
| Canonical units, total | 744 | 738 |
| `substantive_remainder` / `doc_is_migrated` | empty / true | empty / true |

Source: `reports/README_VOICE_BASELINE_V1.json` (Phase R) vs
`reports/README_VOICE_FINAL_V1.json` (Phase REP).

---

## 2. Per-defect disposition

### R-D1 — 10 `## Why` headings outranked their sections — **FIXED at the render layer**

Unit bodies hardcode `## Why` at H2 (`quality.check_structure` requires it), and
`render_unit_into_doc` pasted `unit.body` verbatim, so a marker under an `### ` produced a
rationale outranking its own parent. `project_body(body, host_depth)` +
`host_section_depth(text, marker_pos)` in `portal/platform/wiki/render.py` shift a body's ATX
headings (outside code fences) by one uniform delta so the shallowest lands one level below its
host, clamped H1–H6, identity when already seated. Applied **symmetrically**: both the write
path and `check_generated_blocks_current` route through `project_body`, so `AW` compares
projected body to projected body and stays exact. `host_section_depth` blanks prior generated
blocks from the prefix so a rendered body never parents the next block — that is what keeps
`render_all_generated_blocks` idempotent. 10 new tests in
`portal/platform/wiki/tests/test_render.py` (21 pass total), including the symmetry property and
idempotency. Commit `11261e52`.

**Spillover (expected, §1 of the task):** the renderer fix is global code, so re-rendering also
cleared inversions in `KNOWN_LIMITATIONS.md`, `docs/HOWTO.md`, `docs/ADMIN_GUIDE.md`,
`docs/SECURITY_BENCH_EXEC.md`, `docs/USER_GUIDE.md` and `docs/DESIGN_WIKI_GENERATION_LOOP_V1.md`
at their next render. This is one function, not a doc-by-doc edit.

### R-D2 — 14 H1 headings (13 escaped shell comments) — **FIXED, README → 1 H1**

Four were genuine bash-block comments (`Test everything is working`, `Pull specialized
models…`, `User management`, `Seeding`) — moved back inside their fences **in the unit body**,
so re-render places them. The other six (`Start / stop`, `MLX (Apple Silicon)`, `Enable
messaging channels`, `Backup and restore`, `Update…`, `Cleanup`) were content-less group labels
stranded by the same lift, with no fence to return to and no body beneath them — **deleted**,
not wrapped, per the `KNOWN_ISSUES.md` duplicate-title precedent the task cites. The three
Troubleshooting item headings were demoted `#` → `###`. Command order inside every fence
unchanged. Commit `f2cfb3d7`.

### R-D3 — 7 comment-derived units → **MERGED into 2**

`unit-DESIGN_WIKI-section-granularity` is explicit that a unit maps by default to a doc section.
4 units merged into `unit-readme-common-commands` (`##` subsections, seated to `###` by
`project_body`), 3 into `unit-readme-troubleshooting`. Sources unioned; absorbed units archived
via `archive.py` with `--superseded-by` (not `rm`), so `BT` holds. Bodies **rewritten, not
concatenated**, to stay under `MAX_PROSE_SIMILARITY` 0.80. No absorbed unit carried a claim
(verified before merging). README blocks 31 → 24. Commit `0da12570`.

### Device 4 — the capability rollup — **derived, not asserted** (Phase D, commit `82a65e97`)

`derive_capability_rollup` in `portal/platform/wiki/adapters/seed_facts.py` emits counts by kind
(modules enabled/total, functional + benchmark + total workspaces, personas, MCP fleet) from
config on every seed. Two new count probes (`modules.enabled.count`, `modules.total`) added to
`claims.py`. Every count in the body is bound to a probe with a `pattern` claim, so `BS`
hard-fails the moment one drifts. Rendered into README's *"How much of this you get"* section
as a `WIKI:GENERATED` block; the surrounding fence prose carries **no integers**.

---

## 3. Device inventory (against pocketportal `905806d`)

| # | Device | Portal 5 form | Status |
|---|---|---|---|
| 1 | Identity claim | `## What this is for` — mission fence, four commitments | shipped (draft) |
| 2 | "What Makes This Special" | `## Why you'd choose this` — four comparisons, each with its cost | shipped (draft) |
| 3 | — | `## What Portal 5 is not` — scope boundary + tradeoff | shipped (draft) |
| 4 | "= 418+ capabilities" | `## How much of this you get` — derived rollup block | shipped |
| 5 | Performance expectations | `## What it does on this hardware` — **`honest-BLOCKED`** | shipped, blocked (see §4) |
| 6 | Deployment options | `## Which path is yours` — three tiers with time cost | shipped (draft) |
| 7 | Success Criteria | `## You know it worked when` — checklist + diagnostic | shipped (draft) |
| 8 | Today / Week / Month | `## What to do next` — first hour / evening / week | shipped (draft) |
| 9 | "Built with ❤️…" | `## Why this exists` — ancestry + sign-off | shipped, **3 `[OPERATOR:]` markers open** |

Plus one section-framing fence at the head of eight major sections (Prerequisites, Quick Start,
What Starts Automatically, Workspaces, Common Commands, Troubleshooting, Architecture, Coding
Tool Integration) — the through-line choice (Gate 1). 17 human-owned fences total; no `reason`
string used more than twice; no fence duplicates a unit body (checked by `HF`).

---

## 4. Device 5 — `honest-BLOCKED`

`docs/PERFORMANCE.md` documents the `bench_tps.py` harness but commits no throughput numbers.
No figure was invented. The section states the *shape* of the answer and carries the exact
command to fill it:

```bash
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace auto --runs 3
```

To resolve: run that on the target hardware and replace the `honest-BLOCKED` block with a
generated block over the committed result artifact, or leave it blocked.

---

## 5. Open at Gate 2

Gate 2 (the voice read) has **not been completed**. The README on `main` carries a first draft
of the nine device fences using the task's drafted mission text. Blocking items for the
operator:

- **3 `[OPERATOR: verify or replace]` markers** in `## Why this exists` — the motive it
  started, how the module list accumulated, what was retired. `grep -c '\[OPERATOR:' README.md`
  → 3.
- **Device 5** is `honest-BLOCKED` — either bench it or accept the block.
- **Mission opener**, **device 2 contrast**, **device 3 tradeoff**, **ancestry paragraph** —
  each a claim, not decoration; confirm or rewrite.

"Close but not mine" is the expected outcome — the fences, reasons, budget and `HF` all survive
a total reword.

**Handoff to the program:** whatever register Gate 2 approves is the input to T7 (the voice
charter) and T8 (the 112-unit description pass). Quote two or three sentences from the approved
README here once Gate 2 closes, so T8's slices have a concrete target.

---

## 6. Count-regex review

The in-fence hardcoded-count scan (`\d+ (workspaces|personas|modules|MCP servers|checks|
models)`) returned **zero hits** inside `WIKI:HUMAN-OWNED` fences. Nothing to review by hand.

---

## 7. Phase F — the `HF` guard

`scripts/validation/doc_voice.py`, check **`HF`** (`CG` was already taken at `117f407a` by the
canary-set check — the task's fallback was invoked and the next slug in sequence used). Five
hard-fail axes — inversion, duplication, structure (one H1), editorial (device headings only in
README), reasons (no `reason` > 2×) — **scoped to `README.md`**, because the other Tier-1 docs
still carry ~317 pre-migration inversions and stray H1s that T2 / T5–T10 clear; shipping a
fleet-wide gate that is red on arrival would violate the task's "must not push a red gate
further red" rule. `_GUARDED_DOCS` widens to the full set once those land. Human-fence ratios
are reported with each doc's class, never enforced. The structure axis docstring records why it
is an H1 count and not a scan for fenced headings — the first attempt read clean on a README
with 14 stray H1s because the comments were never inside the fences.

Also: `scripts/validate_system.py`'s module docstring advertised ~13 checks (`A. … AB.`)
against a live registry of 213. Replaced with a pointer to `all_checks()` — a prose enumeration
is a Rule 12 violation waiting to happen, and writing a better one just resets the clock.

---

## 8. Deviation from the task — the SPINE_P0_MANIFEST STOP

Phase C's spec says STOP if any merge-set unit is referenced from `docs/SPINE_P0_MANIFEST.md`.
All 7 are — but only as backtick mentions in that file's stale RELEASE table (generated "at 719
units"; live is 738). `docs/SPINE_P0_MANIFEST.md` is not a Tier-1 doc, is not checked by
`BT`/`BS`, is regenerable by `scripts/spine_p0_manifest.py`, and is itself `[GATE]`-flagged as
a provisional classification from a separate task. The merge proceeded rather than blocking on a
stale artifact; the manifest was **left untouched** rather than regenerated into a different
classification shape (which would muddy that other task's decision record). Flagged in commit
`0da12570` and here for operator review — Phase C is isolated and revertible if the call is
wrong.

---

## 9. Deliberately left out of scope (tracked, not pending)

| Item | Owner |
|---|---|
| `config/MODEL_CATALOG.md` — 188 `## Why` inversions (fix the `derive_model_catalog` deriver) | T2a |
| ~72 stray H1s across 13 other Tier-1 docs | T2b |
| Residual doc-text inversions (`KNOWN_LIMITATIONS`, `MCP_DEV_TOOLING`, `BACKUP_RESTORE`, `P5_ROADMAP`, …) | T2c |
| 10 internally-inverted unit bodies (D5) | T1 |
| `docs/USER_GUIDE.md` — 10 duplicate fences | T3a |
| `docs/ARCHITECTURE.md`, `docs/GOVERNANCE.md`, `docs/DOC_VOICE_CHARTER.md` — new contract docs | T5 / T6 / T7 |
| The 112 rendered unit bodies — hand-authored description pass | T8 |
| The 33 `unit-capability-*` bodies — purpose/value pass | T9 |
| 185 machine-derived unit prose templates | T10 |
| Widen `HF` to the full `TIER1_DOCS` set | T11 (after T2/T5–T10) |

`./scripts/smoke_stream.sh` was **not** run — no payload in this task touched routing, inference
or the pipeline. Recorded rather than run for appearances.
