# WFE decision — auto-compliance (informational, harness validation)

Campaign `wfe_compliance_decision_20261016` · HEAD `3b9f4f29` · plan `tests/wfe/plans/compliance_decision_v1.yaml` · engine pipeline, production tool mode.
Purpose: validate the corrected harness end to end. Not a seat contest; no seat changed.

## Outcome
- Incumbent `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` vs `granite4.1:30b-ctx64k` (card arm).
- Screen: Qwen 7/11, granite 2/11 → ADVANCE (intended workspace, always confirmed).
- Confirm (3 repeats, 97 rows per arm): Qwen 58 PASS / 39 FAIL, granite 55 PASS / 42 FAIL.
- Fitness cell auto-compliance × granite: NOT_SEPARATED (sign test p=1.000); disposition RETAIN_DIVERSITY. Recorded in `tests/wfe/fitness_ledger.yaml` (+1 cell).
- Exit codes: all four arm runs exit 0; `--verify-complete` 0 problems (screen and confirm).
- Check HP: WARN only — "57 of 58 seats have no confirm cell yet" (Part 5's sweep records them).

## Pass rate per task kind (confirm + screen rows)
| kind | Qwen3.8 27B | granite 4.1 30B |
|---|---|---|
| lookup | 63/72 | 57/72 |
| determination (det) | 2/36 | 0/36 |

Granite on `det`: 0 tool calls on all 36; answers are "coverage NONE / NEEDS_REVIEW" JSON from memory. Qwen makes 6–12 grounded calls per det row and still fails on content (valid FAILs).

## Row-validity summary
- 216 rows, all `evidence.tool_mode == production`; 0 duplicate run_ids; 0 quarantined rows.
- Identities frozen at preflight (2/2 OK) and checked per row; no identity error.
- `tool_grounded` graded on the pipeline's own `exec_audit` trace: every row with tool_calls>0 carries a `tool_call_log` of the same length (168 rows); the 48 rows with 0 calls carry none.
- Eval store key-free, 12 planted documents; no answer-key leak observed.
- Granite zero-call pattern verified as model behaviour, not delivery (probe via :9099, `?model=granite4.1:30b-ctx64k`): prompt_tokens 480 with `portal_no_tools` vs 6247 with tools (~5.8k of schemas); `/v1/trace` tools_offered = 46 incl. `nerc_cip_requirement`; served `granite-4.1-30b-4bit` on omlx-reasoning; completion_tokens 29 = exactly the answer JSON (no dropped tool-call text); direct oMLX with only the one tool schema returns `finish_reason=tool_calls` with the correct call. Caveat: `PORTAL_TRACE_BODIES` off, so oMLX receipt is inferred from the token delta, not the request body.

## Defect found and fixed in C
- Variant arm ids (`<tag>@<label>-<digest>`) did not match the candidate queue (keyed by bare tag): the screen's intended-workspace override did not fire and fitness lost the cells, so granite's first confirm (campaign `wfe_compliance_decision_20261015`) never ran. Fixed in `3b9f4f29` (`tests/wfe/report.py`, two regression tests that fail without the fix); re-run under a new campaign id; no rebuild needed (tests/wfe only).
