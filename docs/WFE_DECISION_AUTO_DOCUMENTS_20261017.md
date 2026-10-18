# WFE decision — auto-documents (2026-10-17)

Informational (harness validation). **The seat is not changed by this document.**

## Cells, builds, instrument

| | |
|---|---|
| Campaign | `wfe_documents_20261017h` (screen + confirm) |
| Plan | `tests/wfe/plans/documents_decision_v1.yaml` (sha `ae4a2527c9d2`) |
| Suite | `documents_production` — 36 tasks (12 create / 12 read / 12 read-then-create), digest `8962941b18dadb10` |
| Deployed build | `6813621a` — pipeline + documents, data, memory, rag, compliance, compliance_eval; `build_dirty` 0; 12/12 backends |
| Engine path | `WFE_ENGINE=pipeline` (:9099), tool_mode `production` on all 432 rows |
| Incumbent | `granite4.1:8b-ctx16k` (ollama-general) |

Served identities (from the manifest identity map): granite4.1:8b-ctx16k and granite4.1:30b-ctx96k on
ollama-general; gemma-4-26b-a4b-it-4bit and Qwen3.8-27B-oQ4e-mtp on omlx-general. Every row served the
model its arm named.

Voided before h: `wfe_documents_20261017f` (launch without `WFE_ENGINE=pipeline`, then the router
defect below; dir kept as `…_void_confirmtier` and `…f`), `wfe_documents_20261017g` (screen only; the
`create_excel` defect below; superseded by h).

## Verdicts

**Screen** (12 tasks, 1 repeat): 46/48 PASS; all three challengers ADVANCE (lost 0).

**Confirm** (36 tasks × 3 repeats; repeats policy = 3 because not every arm served temperature 0):

| Candidate vs incumbent | n | wins | losses | ties | p (sign) | Verdict |
|---|---|---|---|---|---|---|
| gemma4:26b-a4b-it-q4_K_M-ctx32k | 36 | 7 | 0 | 29 | 0.0156 | **BETTER** |
| Qwen3.8-27B Q4_K_M-ctx32k | 36 | 7 | 0 | 29 | 0.0156 | **BETTER** |
| granite4.1:30b-ctx96k | 36 | 4 | 1 | 31 | 0.375 | NOT_SEPARATED |

Recorded in `tests/wfe/fitness_ledger.yaml` (89decd5f).

## Per-task-kind pass rate (confirm rows)

| Arm | create | read | read-then-create |
|---|---|---|---|
| gemma4:26b-a4b | 36/36 | 36/36 | 36/36 |
| Qwen3.8-27B | 36/36 | 36/36 | 36/36 |
| granite4.1:30b | 36/36 | 33/36 | 27/36 |
| granite4.1:8b (incumbent) | 36/36 | 33/36 | 18/36 |

## Row validity

- 432/432 rows tool_mode `production`, served identity = arm; 0 HARNESS_ERROR, 0 BUDGET_EXHAUSTED,
  0 hop-limit, 0 raw `<tool_call>` markup, 0 zero-width garbling; no HALT in h.
- Repeat degeneracy on 216 rows = the two granite arms (temperature 0 / unset → identical draws). Their
  failures are therefore 3/3 per task, not independent samples.
- Every FAIL's `tool_call_log` was read: correct tool, correct args, correct tool output.
- **Quarantine:** `doc-read-01` for granite4.1:30b (3 rows) — the instruction "In terms.docx, how many
  days…" invited reading the file name as "In terms.docx", and the seat did exactly that at temperature
  0. Instrument defect, fixed f5c0fcd6. Effect on verdicts: none (it is a tie between gemma/Qwen and the
  incumbent, who both pass it; granite-30b would become 4/0, p=0.125, still NOT_SEPARATED).
- `doc-trip-01`'s checker matched "3" as a substring (a wrong "13" would have passed). No row was
  mis-scored by it in h (the only wrong value written was "4"); fixed f5c0fcd6 (`exact` cell match).

## Seat findings (valid evidence)

- **granite4.1 arithmetic over tool output.** Both granite sizes read the file correctly and then sum or
  count wrongly: doc-trip-06 148 / 200 vs 198, doc-trip-11 210 vs 212, doc-trip-01 count 4 vs 3,
  doc-read-05 2335 vs 2235 (8b). The incumbent loses 18/36 read-then-create rows this way.
- **Incumbent sampling is undefined:** granite4.1:8b-ctx16k rows carry `served_temperature: null` — no
  temperature is sent, so the engine default applies. Every other seat sends an explicit value. Belongs
  to the sampling-authority audit (P5), not to this decision.

## Found and fixed during S0–S4 for documents

| Commit | Class | What |
|---|---|---|
| S0 2244ad6b (+5) | production | tool-name garbling; pptx unknown keys |
| S1 (6 commits) | static audit | 5 defect classes across workspaces/MCPs |
| c67453c5 | production (router) | explicit-required-tool narrowing took "Read X.xlsx … create a Word document" down to `create_excel` alone; read tool never offered — gemma invented `create_word` ×16, granite-30b returned empty |
| 0f046f6f | production (documents MCP) | `create_excel` sheet `headers` items untyped; nested header row → raw openpyxl error naming no field → identical retries to budget |
| f5c0fcd6 | instrument | "In <file>," opener; substring value matching |
| 7107252f | supervisor | false "spoiled answer" on terse JSON answers |

## Open

- Create answers hand the user a container path (`/app/data/generated/…`) as the download link —
  verify in a real OWUI turn (S2 production smoke).
- The ledger cells are on the pre-f5c0fcd6 suite; the next documents campaign runs the fixed suite.

## Addendum 2026-10-18 — G1 head-to-head, computed offline

Campaign h already ran both FOLD candidates on the same suite, instrument, build and repeats, so the
gemma-vs-Qwen3.8 pairing comes from its rows, with no new inference (the planned
`documents_h2h_v1` run is not needed). Arms are the h challengers, each at its card sampling (both
served temperature 1.0).

| | gemma4:26b-a4b q4_K_M ctx32k | Qwen3.8-27B Q4_K_M ctx32k |
|---|---|---|
| PASS (36 × 3) | 108/108 | 108/108 |
| Paired sign test | — | 0 wins / 0 losses / 36 ties, NOT_SEPARATED |
| Total s per task, median (p90) | **3.7** (5.3) | 20.3 (45.1) |
| Lineage seats today | gemma: 6 | Qwen3.8: 3 |

Accuracy is at the suite's ceiling, so the suite can't separate the two. A live re-run on the same
suite would only repeat that, so the call rests on speed (gemma about 5.5× faster per task) and
lineage. Also corrected: the "incumbent temperature null" finding above was a receipt defect
(`options_applied` read only top-level sampling), fixed de1e657e; granite's seat sampling was
delivered.
