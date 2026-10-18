# WFE P5-B2 — GATE list: the seat decisions that need the operator

2026-10-18 · read-only draft · **nothing here is applied, no campaign was run.**
Acceptance row **P5-B2** — "GATE list presented; operator decisions recorded". The decisions are
the operator's; each block ends with a slot to record the call.

Source: `docs/WFE_FITNESS_MAP.md`, re-derived with
`uv run python -m tests.wfe.report --fitness-map` (output matches the committed file), over
`tests/wfe/fitness_ledger.yaml` (7 decision-grade cells) and `tests/wfe/candidate_queue.yaml`.
Every seat change below ends with `./launch.sh sync-config`; never hand-edit `workspace_routing`,
`.mcp.json` or `imports/openwebui/workspaces/*.json`.

## Summary (6 lines)

1. 5 models carry a seat-implying disposition: FOLD ×3 (gemma4 26b, granite 30b/64k, Qwen3.8 27b), REDUNDANT ×1 (granite 30b/96k), RETAIN_DIVERSITY ×1 (Nemotron 3.5).
2. auto-documents: gemma and Qwen3.8 tie exactly (36 rows, 7-0-29, p .0156, zero losses each) — one seat, so this gate picks between them.
3. auto-data: granite's BETTER cell predates the lane's guard; the guarded incumbent now scores 106/108 vs granite 105/108.
4. auto-compliance: granite does not qualify — 0 tool calls on all 36 determination rows.
5. granite 30b/96k is redundant as a *seat* but is the tag behind the live 98k reading bench; do not delete it blind.
6. 5 calls needed: ADOPT / HOLD / REMOVE / KEEP — one line each to close P5-B2.

---

## G1 — gemma4:26b-a4b-it-q4_K_M-ctx32k → auto-documents

**Decision asked:** adopt gemma as the auto-documents seat? (disposition FOLD — BETTER in its intended lane)

**Change (`config/portal.yaml`, auto-documents block):**
```
1603  model_hint: granite4.1:8b-ctx16k   →  gemma4:26b-a4b-it-q4_K_M-ctx32k
1604  context_limit: 16384               →  32768
1606  temperature: 0.0                   →  1.0
1607  top_p: 0.9                         →  0.95
1608  top_k: 40                          →  64
1609  min_p: 0.05                        →  (delete — the card sets none)
```
Then `./launch.sh sync-config`. Card values are the ones already served by the gemma compliance
seats (`config/portal.yaml:1973-1975`).

**Evidence** — cell `tests/wfe/fitness_ledger.yaml:104-128`
n=36 · 7 W / 0 L / 29 T · p=0.015625 (worst case 0.015625) · campaign `wfe_documents_20261017h`
· instrument `75344932172b255f` · suite `documents_production` digest `8962941b18dadb10`
· incumbent `granite4.1:8b-ctx16k` (ollama-general, content `f7013632…`) · arm served
`mlx-community--gemma-4-26b-a4b-it-4bit` (omlx-general, content `69bee520…`).
Raw confirm: gemma 108/108 vs incumbent 87/108 (create 36/36, read 36/36, read-then-create 36/36).

**Caveats**
- Cells are on the **pre-`f5c0fcd6` suite** (documents decision doc, "Open"); the two fixed
  defects were shown not to affect these verdicts (quarantine hits granite only; the `doc-trip-01`
  substring checker mis-scored no row in h).
- Speed not measured in this cell; the window sweep has 55.8 tok/s decode / 494 prefill / 9.1 s
  cold load, 19.3 GB resident (`config/MODEL_CATALOG.md:2159`, `docs/TASK_MEMORY_FOOTPRINT_REDUCTION_V1.md:84`).
- Card temperature 1.0 on a lane that ran 0.0: `settings_audit` records this as INFO
  "card over lane", not a FAIL (`tests/wfe/settings_audit.py:255-265`).
- Co-residency: gemma ctx64k/ctx128k already serve compliance seats (`config/portal.yaml:1970`,
  `:2193`); a *different* `num_ctx` tag is a separate Ollama load (19.3 GB) beside the 5.7 GB
  router classifier and the Docker VM. The cell served on the oMLX conversion, whose footprint is
  not recorded.

**Recommendation:** **ADOPT** — zero losses on the seat's own tool suite, and 55.8 tok/s keeps
document turns short where the dense alternative runs ~12.
**Operator:** ☐ ADOPT ☐ HOLD — note: ____________________ date: __________

---

## G2 — hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k → auto-documents

**Decision asked:** adopt Qwen3.8 as the auto-documents seat instead of gemma? (FOLD; **mutually
exclusive with G1** — one seat, two separating arms never compared head-to-head)

**Change (`config/portal.yaml`, auto-documents block):**
```
1603  model_hint: granite4.1:8b-ctx16k  →  hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k
1604  context_limit: 16384              →  32768
1606  temperature: 0.0                  →  0.7
1607  top_p: 0.9                        →  0.8
1608  top_k: 40                         →  20
1609  min_p: 0.05                       →  0.0
      + presence_penalty: 1.5, repeat_penalty: 1.0, think: false   (as :1861-1864)
```
Then `./launch.sh sync-config`.

**Evidence** — cell `tests/wfe/fitness_ledger.yaml:150-170`
n=36 · 7 W / 0 L / 29 T · p=0.015625 · campaign `wfe_documents_20261017h` · instrument
`75344932172b255f` · suite `documents_production@8962941b18dadb10` · arm served
`Qwen3.8-27B-oQ4e-mtp` (omlx-general, content `7228ad7f…`); raw 108/108 vs incumbent 87/108.
Its other cell: auto-data NOT_SEPARATED, n=36, 10/3/23, p=0.0923 (`:83-103`).

**Caveats**
- Same pre-`f5c0fcd6` suite as G1; identical counts, so the data cannot separate G1 from G2.
- Speed not measured in this cell; fleet figures are ~12 tok/s on the GGUF, ~18 with MTP
  (`config/portal.yaml:1515`) — about a third of gemma's.
- Memory ~18 GB (`config/portal.yaml:1512`), but the model already serves auto-reasoning-deep
  (`:1519`), auto-compliance (`:1853`) and compliance-council-qwen38 (`:2130`): documents would be
  its third production home, concentrating the fleet on one lineage.
- Its documented tendency to re-issue an identical tool call (compliance loop, bounded by the
  pipeline guard `c58f32f1`) is not absent on a second tool lane.

**Recommendation:** **HOLD** — same separation as gemma with no extra evidence, ~3× slower, and it
would put a third production home on one model family.
**Operator:** ☐ ADOPT ☐ HOLD ☐ HOLD-AS-FALLBACK — note: ____________________ date: __________

---

## G3 — granite4.1:30b-ctx64k → auto-data

**Decision asked:** adopt granite 30b/64k as the auto-data seat? (FOLD — BETTER in auto-data)

**Change (`config/portal.yaml`, auto-data block):**
```
1787  model_hint: hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx32k → granite4.1:30b-ctx64k
1788  context_limit: 32768            (unchanged — the tag bakes 64k)
1790  temperature: 0.7                → 0.0
1791-1796 top_p 0.8, top_k 20, min_p 0.0, repeat_penalty 1.0, presence_penalty 1.5
        → delete all five (with the 1794 no-op note; the granite card is greedy)
1800  require_tool_before_answer: true  (keep)
```
Then `./launch.sh sync-config`.

**Evidence** — cells `tests/wfe/fitness_ledger.yaml:37-61` and `:12-36`
auto-data: n=36 · 10 W / 1 L / 25 T · p=0.01171875 (worst case same) · campaign
`wfe_data_decision_20261016` · instrument `ac1570b30b378576` · suite `data_production@efda19faecd2333f`
· served `granite-4.1-30b-4bit` (omlx-reasoning). Raw confirm: granite 105/108, Qwen3.8 102,
Nemotron 99, incumbent 95.
auto-compliance: n=36 · 4 W / 5 L / 27 T · p=1.0 · campaign `wfe_compliance_decision_20261016`
· suite `compliance_production@789df4f811db070f` — **does not qualify it**: 0 tool calls on all
36 determination rows; re-screen 2/11 vs Qwen 10/11.

**Caveats**
- The incumbent in that cell was measured **off-guidance** (repetition 1.05, no presence) and
  **before** the data guard (`:1800`); the re-screen at guidance sampling was screen-only (no cell).
- With the guard the same incumbent is **106/108** (`wfe_data_guard_confirm_20261016`,
  `docs/WFE_DECISION_AUTO_DATA_CFIX_20261016.md:34-45`) — one row ahead of granite.
- Memory/speed not measured here. This is the model the lane was moved off for a ~55 GB resident
  working set, 96-97 % memory and emergency evictions (`config/portal.yaml:1779-1786`,
  `config/MODEL_CATALOG.md:1462`); the dense 30B runs 5-12 tok/s vs the MoE's 54.2.
- Card temperature 0.0 would make the lane deterministic — a sampling change, not just a hint swap.

**Recommendation:** **HOLD** — the BETTER was measured against a seat that production no longer
serves, and adopting it restores the 55 GB residency failure the seat change was made to fix.
**Operator:** ☐ ADOPT ☐ HOLD — note: ____________________ date: __________

---

## G4 — granite4.1:30b-ctx96k (REDUNDANT)

**Decision asked:** remove the tag from the fleet (literal REDUNDANT), or keep it as a bench-only
window tag?

**Change if removed:**
```
config/backends.yaml:70-71   delete  - id: granite4.1:30b-ctx96k / supports_tools: true
config/portal.yaml:2314      model_hint: granite4.1:30b-ctx96k → granite4.1:30b-ctx64k
config/portal.yaml:2315      context_limit: 98304 → 65536
tests/wfe/candidate_queue.yaml:16-22   drop the queue entry
+ ollama rm granite4.1:30b-ctx96k ; ./launch.sh sync-config
```

**Evidence** — cell `tests/wfe/fitness_ledger.yaml:129-149`
n=36 · 4 W / 1 L / 31 T · p=0.375 · campaign `wfe_documents_20261017h` · instrument
`75344932172b255f` · suite `documents_production@8962941b18dadb10` · served `granite4.1:30b-ctx96k`
(ollama-general). Raw 96/108 vs incumbent 87/108 — better in aggregate, but only 5 tasks separate,
so not a verdict. Lineage `granite4.1` is not unique (ctx16k and ctx64k live).

**Caveats**
- The tag is the `model_hint` of **bench-granite41-30b-ctx98k** (`config/portal.yaml:2314`), built
  for the 98k reading window because the pipeline drops request-time `num_ctx`
  (P5-FANOUT-001 W3) and reserving a 31.7 GiB footprint (`:2308-2313`).
- Removing it deletes a live bench lane and its window evidence; keeping it costs nothing unless
  the bench is loaded. The workspace id would also name a window it no longer has.
- Its documents cell was measured against the 8b incumbent, not against gemma/Qwen — it was never
  a contender for the seat once they separated. No speed figure in this cell.

**Recommendation:** **KEEP bench-only** — redundant as a seat, but it is the 98k bench's window
tag; record it RETAINED_FOR_PURPOSE (bench) rather than deleting a live lane.
**Operator:** ☐ KEEP-BENCH ☐ REMOVE — note: ____________________ date: __________

---

## G5 — hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k (RETAIN_DIVERSITY)

**Decision asked:** confirm it stays **unseated** on auto-data (keep as diversity), with no
model_hint change?

**Change:** **none.** Explicitly: do not repoint auto-data `:1787`; leave the registration
(`config/backends.yaml:31-32`) and its own seat `auto-nemotron` (`config/portal.yaml:535`) as-is.

**Evidence** — cell `tests/wfe/fitness_ledger.yaml:62-82`
n=36 · 8 W / 3 L / 25 T · p=0.2265625 · campaign `wfe_data_decision_20261016` · instrument
`ac1570b30b378576` · suite `data_production@efda19faecd2333f` · served on ollama-general
(content `4b88e645…`). Raw 99/108 vs incumbent 95/108. Only member of lineage
`nemotron-3.5-lightning`.

**Caveats**
- Same stale comparison as G3: the incumbent was unguarded; with the guard it reaches 106/108,
  which erases Nemotron's +4 raw edge as well.
- The cell measured it on auto-data's tools, not on its actual home (auto-nemotron); it has no
  speed or memory figure in this cell (fleet: ~70 tok/s on oMLX+MTP, ~53 on the GGUF,
  `config/portal.yaml:530`).
- Keeping it registered costs nothing while unloaded; it is the fleet's nemotron lineage.

**Recommendation:** **KEEP** — no separation, but it is the only nemotron-lineage member and
already has a seat elsewhere; zero-change diversity.
**Operator:** ☐ KEEP ☐ REMOVE — note: ____________________ date: __________

---

## Operator decisions (recorded 2026-10-18, in session)

Operator: "Remember we do want diversity."

| Item | Call | Action |
|---|---|---|
| G1 / G2 auto-documents | **HEAD-TO-HEAD** first | documents campaign, gemma4:26b-a4b q4_K_M ctx32k vs Qwen3.8-27B ctx32k, on the fixed suite (post-f5c0fcd6) with phase timing; decide on accuracy + speed + lineage diversity (Qwen3.8 already holds 3 production seats) |
| G3 granite4.1:30b-ctx64k → auto-data | **HOLD** | no change |
| G4 granite4.1:30b-ctx96k | **KEEP** (bench-only) | record RETAINED_FOR_PURPOSE (98k bench window tag) |
| G5 Nemotron-3.5 ctx32k | **KEEP** (diversity) | no change |

## Scope notes

- This list covers the **5 queued models with cells**. The fleet's other seats carry no confirm
  cell — check HP WARNs that nearly all of the 58 seats have none — so they have no disposition
  and no GATE item here.
- Four `wfe_math_20261018a-d` campaign directories exist in the primary checkout but hold no
  ledger cells; no math disposition exists, so none is listed.
- All five recommendations are advisory. P5-B2 is only closed when each block above carries the
  operator's call.
