# WFE decision — auto-data (informational, harness validation)

Campaign `wfe_data_decision_20261016` · HEAD `f4d64d42` · plan `tests/wfe/plans/data_decision_v1.yaml` · engine pipeline, production tool mode.
Purpose: validate the corrected harness end to end. Not a seat contest; no seat changed.

## Outcome
- Incumbent `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx32k`; challengers Qwen3.8 27B (card), granite4.1:30b-ctx64k (card), Nemotron-3.5-Lightning-30B-A3B (card).
- Screen (12 tasks/arm): all three challengers ADVANCE (lost 0; won 4 / 3 / 4).
- Confirm (3 repeats, 108 rows/arm) — fitness cells for auto-data:
  - granite4.1:30b-ctx64k: **BETTER** (sign test p=0.0117, worst case p=0.0117)
  - Nemotron-3.5-Lightning: NOT_SEPARATED (p=0.227)
  - Qwen3.8 27B: NOT_SEPARATED (p=0.092)
  - `--record`: +3 cells in `tests/wfe/fitness_ledger.yaml`.
- Exit codes: all eight arm runs exit 0; the confirm `--verify-complete` first reported 1 problem (below), then 0 after the rerun.
- Check HP: WARN only — "56 of 58 seats have no confirm cell yet" (Part 5's sweep).
- The BETTER cell is informational; per the operator, the seat is unchanged.

## Pass rate per dataset (screen + confirm rows, 36 per cell)
| dataset | Qwen3.6 35B (incumbent) | Qwen3.8 27B | granite 4.1 30B | Nemotron 3.5 |
|---|---|---|---|---|
| inventory | 32 | 35 | 36 | 33 |
| sales | 28 | 34 | 33 | 33 |
| tickets | 35 | 33 | 36 | 33 |

## Row-validity summary
- 432 rows, all `evidence.tool_mode == production`; 0 duplicate run_ids; 0 quarantined; `tool_calls` equals the length of `tool_call_log` on every row (pipeline `exec_audit` trace).
- Outcomes: 401 PASS, 31 FAIL, 0 HARNESS_ERROR after the rerun.
- Identities frozen at preflight (4/4 OK).
- One HARNESS_ERROR (granite, `data-prod-tickets-32`, r0): the oMLX stream timed out mid-generation at 125 s and the Ollama fallback was refused (507: projected 20.4 GiB over 13.5 GiB headroom). Transient infrastructure, one row in 108. Resume alone does not redo it (`appended 0 rows`); `run_arm ... --rerun-failed` re-ran only that row (PASS, 16.6 s) and `--verify-complete` then reported 0 problems. Pre-rerun campaign dir backed up at `/tmp/wfe_data_decision_20261016.bak`.
- No defect in the harness found in C2.
