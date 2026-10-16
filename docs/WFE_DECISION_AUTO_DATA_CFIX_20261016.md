# WFE decision — auto-data, re-screen at guidance sampling (informational, harness validation)

Campaign `wfe_data_decision_20261016cf` · HEAD `6671b1db` · plan `tests/wfe/plans/data_decision_v1.yaml` · engine pipeline, production tool mode · **screen tier only**.
Purpose: validate the harness after the seat-sampling fix. Not a seat contest; no `model_hint` changed. The "before" evidence is `wfe_data_decision_20261016` (confirm, 432 rows).

## Outcome (screen, 12 tasks per arm)
| arm | PASS |
|---|---|
| Qwen3.6-35B-A3B UD-Q4_K_XL (incumbent, seat at guidance sampling) | 7 / 12 |
| Qwen3.8-27B (card) | 11 / 12 |
| granite4.1:30b (card) | 11 / 12 |
| Nemotron-3.5-Lightning (card) | 11 / 12 |

- Screen decisions: all three challengers ADVANCE (lost 0, won 4 of 12 each). No confirm was run, so no fitness cell is recorded.
- Exit codes: all four arm runs 0; `--verify-complete` 0 problems.
- Rows: 48, all production tool mode, 0 duplicates, 0 hop-limit rows, 0 raw-markup rows, `tool_calls == len(tool_call_log)` on every row.

## The incumbent's 7/12 was noise, checked
Four of its five fails were 0-call answers (a fabricated number, in 1.2 s). The earlier confirm showed 11 zero-call rows in 108, so I measured it: a diagnostic confirm of the incumbent alone at the new sampling (`wfe_data_diag_q36_20261016`, 108 rows, served options 0.7 / 0.8 / presence 1.5 / repetition 1.0) gave **95 PASS / 13 FAIL with 11 zero-call rows — the same as before at the old sampling (95/108, 11)**. The sampling change is neutral for auto-data; the Qwen3.6 seat's intermittent no-tool answer (about 10%) is pre-existing and unchanged.

## The incumbent's no-tool answers: delivery checked, model behaviour (seat-level finding for the operator)
The reviewer asked whether the fast fails are a delivery or template defect, as with granite on compliance. Checked on the diagnostic campaign (`wfe_data_diag_q36_20261016`, 108 rows) and a 3-run replay of one affected task (`data-prod-sales-00`, `wfe_data_diag2_q36_20261016`):
- Tools were offered on every request: `/v1/trace` `tools_offered` = `attach_source, create_excel, list_session, profile_table, run_sql` for the zero-call turn and for the calling turns alike.
- oMLX's log for the replay: the zero-call turn and the first turn of both calling runs have the identical prompt, 833 tokens. The same prompt produced a 9-token answer once (`finish_reason=stop`) and a 50-token tool call twice (`finish_reason=tool_calls`); the calling runs' later prompts grow to 1026/1028 and 1206/1208 as the results are appended. So the schemas and the request were the same; the model chose differently.
- It generated 6–34 tokens, `finish_reason=stop`, and the text is exactly the answer JSON (`{"answer": null}`, `{"answer": 12}`, or "Cannot determine without attaching the file first"). 0 of the 11 zero-call finals contain `<tool_call>` or `<function=` text, so no call was dropped.
- It is random per run, not per task: 10 of 36 tasks had a zero-call repeat and none had it in all three; the same task, same seed, other repeats called the tools.
- Rate: 11 of 108 (10%) at the old sampling and 11 of 108 at the guidance sampling. 

Conclusion: model behaviour, not delivery. On roughly one data row in ten Qwen3.6-35B-A3B (think off) answers from nothing, often with a fabricated number, instead of calling `run_sql`. It is the weakest of the four arms on this lane (95/108 against granite 105, Qwen3.8 102, Nemotron 99 in the confirm run), so the operator may want a guard (a data answer with no query must be refused) or a different incumbent. No seat is changed here.

### Operator-approved data guard, measured
`require_tool_before_answer: true` on auto-data (`7d8f29f2`): a turn that ends with an answer and no tool call is held, the model is asked once to answer from a query (tools still offered), and a still-ungrounded answer is delivered with a visible notice; streaming and failover paths; metric `portal5_answer_without_tool_retried_total`. Tests cover retry-then-call, still-ungrounded-with-notice, a normal turn untouched, an unflagged workspace untouched.
- Live: `data-prod-sales-00` x12 through the pipeline, 12/12 PASS (12040); the retry fired twice and both recovered a call.
- Re-measure, incumbent alone, new campaign `wfe_data_guard_confirm_20261016` (confirm, 108 rows, HEAD `7d8f29f2`):

| incumbent Qwen3.6 on auto-data | PASS | zero-call rows |
|---|---|---|
| without the guard (`wfe_data_decision_20261016`) | 95 / 108 | 11 |
| without the guard, guidance sampling (`wfe_data_diag_q36_20261016`) | 95 / 108 | 11 |
| **with the guard** | **106 / 108** | **0** |
| granite 4.1 30B (earlier confirm, no guard) | 105 / 108 | 0 |
| Qwen3.8 27B (earlier) | 102 / 108 | 0 |
| Nemotron 3.5 (earlier) | 99 / 108 | 0 |

The guard fired 11 times in the 108 rows and each retry produced a tool call (no notice was delivered). The two remaining FAILs are `data-prod-sales-01` (answer 40 correct, but graded ungrounded: no successful `run_sql`/`profile_table` call returned the value), unrelated to the guard. With the guard the incumbent is ahead of granite on this lane by 1 row, within noise; the gap that made it the weakest arm is closed. No seat is changed; the operator decides.

## Seat sampling (C-FIX)
auto-data now serves Unsloth's Qwen3.6 non-thinking guidance (0.7 / 0.8 / 20 / 0 / presence 1.5 / repetition 1.0); it ran repetition 1.05 and no presence penalty.

## Correction to the earlier decision doc
The HARNESS_ERROR in `wfe_data_decision_20261016` (granite, `data-prod-tickets-32`) was not "transient infrastructure". Root cause: the oMLX tool-loop request hit an `httpx` connect timeout 5.0 s after it started (the client allows 5 s to connect); the 125 s total was `load_guard`'s 120 s wait after the failover to Ollama was refused with 507, because the oMLX copy is protected for 300 s after a failover. Why oMLX was slow to accept is not proven. Mitigation: `abcff920` retries the same backend once on a connect timeout (3 tests); a read timeout still fails over.

## Row-validity and defects
No new harness defect in this re-screen; the fixes shipped in C1 apply (listed in the auto-compliance re-screen doc).
