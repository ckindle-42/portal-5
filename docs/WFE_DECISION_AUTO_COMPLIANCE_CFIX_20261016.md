# WFE decision — auto-compliance, re-screen at guidance sampling (informational, harness validation)

Campaign `wfe_compliance_decision_20261016cf` · HEAD `6671b1db` · plan `tests/wfe/plans/compliance_decision_v1.yaml` · engine pipeline, production tool mode · **screen tier only** (operator: no confirm re-run).
Purpose: validate the corrected harness and the corrected seat sampling. Not a seat contest; no `model_hint` changed.

## Why this run exists
The earlier C1 campaigns measured a seat running on known-bad settings. Evidence kept as the "before":
- `wfe_compliance_decision_20261016` (lookup half valid; its determination half was invalid: three instrument defects, below) and `wfe_compliance_decision_20261016r3` (stopped after 76 rows).
- Qwen3.8 hit the 20-hop limit on 16 of 58 r3 rows and 25 of 108 in `20261016`, with one call re-issued up to 19 times; granite, Qwen3.6 and Nemotron on the same tools and pipeline never did (C2 data: 5/108 for Qwen3.8).

## Outcome (screen, 11 tasks per arm)
| arm | PASS | lookup | determination |
|---|---|---|---|
| Qwen3.8-27B (incumbent, seat at guidance sampling) | **10 / 11** | 6 / 6 | 4 / 5 |
| granite4.1:30b (card arm) | 2 / 11 | 2 / 6 (4 answered with 0 tool calls) | 0 / 5 |

Before (same screen, old sampling): Qwen 7/11, granite 2/11.
- Screen decision: `ADVANCE granite` (lost 8, won 0; intended workspace, always confirmed). No confirm was run, so **no fitness cell is recorded** from this campaign.
- Exit codes: both arm runs 0; `--verify-complete` 0 problems.
- Rows: 22, all `evidence.tool_mode == production`, 0 duplicates, 0 hop-limit rows (max 13 calls), 0 rows ending in raw `<tool_call>` markup, `tool_calls == len(tool_call_log)` on every row, `sampling_undelivered` empty. The one Qwen FAIL (`comp-prod-det-applicability-ot-pol-006`, 13 calls) is a content miss, not a loop.
- Check HP: WARN only (seats without a confirm cell).

## Seat sampling (C-FIX)
auto-compliance now serves the build provider's (Unsloth) Qwen3.8 non-thinking guidance: 0.7 / 0.8 / 20 / min_p 0 / presence 1.5 / repetition 1.0 (it ran 0.3 / 0.95 / 1.1 with no presence penalty since `7b5d2afd`, which lowered it only to pass the lane ceiling in `settings_audit`). Delivery is proven on both engine adapters by `scripts/engine_contract_check.py` (Ollama 0.40.5, oMLX 0.7.0). The pipeline also now answers an identical repeated tool call from the earlier result and ends the loop after a third (`c58f32f1`, `6671b1db`).

Live replay of the one task that looped (`comp-prod-det-future-effective-ot-pol-013fe`, 6 runs): before, 3 of 6 reached 19–20 hops; after, 0 of 6, 5 of 6 PASS, at most 6 calls.

## The Qwen3.8 loop, with the evidence (record for the operator)
It is model behaviour on this task, not delivery. Proven: the pipeline sent the whole 4707-character `role:tool` result on every hop (trace digest, `991600b8`), both chat templates render the tool result and anchor the post-tool turn, and the loop also occurred on the Ollama GGUF (one call repeated 17 times). Not causes: MTP (off: still looped), a pinned seed (advanced per hop: still looped), the vendor sampling alone (card 1/5, lane ceiling + presence 2/6). Cache-off arm was inconclusive (re-prefill made runs exceed the budget). Combined, sampling plus the guard cleared it on the replay set; the underlying tendency of Qwen3.8 to re-issue a call remains and the guard is what bounds it.

## Defects found and fixed in C1 (commit, test, live re-check)
| defect | commit | live re-check |
|---|---|---|
| variant arm ids did not match `candidate_queue.yaml`, so the screen override and fitness cells were lost | `3b9f4f29` | the screen decision above (`intended workspace, always confirmed`) |
| `compliance_coverage` double-prefixed a fully qualified requirement (also a production bug) | `92982bb6` | attainability 12/12 |
| the eval store held no standards; determinations were unattainable; attainability check added | `a58459eb` | store rebuilt; 12/12 attainable |
| the determination instruction used coverage and signal values it never defined | `3e8dc44d` | r3 / this run's det rows |
| tool-loop connect timeout failed the turn over (a granite HARNESS_ERROR in C2) | `abcff920` | 3 tests; the failure did not recur |
| trace bodies were dropped whole on a long turn | `991600b8` | 20-hop trace read back with every `role:tool` result |
| failover tool turns got one round and leaked `<tool_call>` text | `bb192b94` | 6/6 forced-failover replays clean |
| repeated identical tool call ran to the hop limit | `c58f32f1` | 013fe 0/6 hop-limit |
| toolless final turn delivered raw call markup | `6671b1db` | 013fe 5/6 PASS, no markup |
| settings_audit let a lane cap override the guidance; registry lacked presence 1.5; seats off-guidance | `434c8ef3`, `1de34bd8`, `cc3c1e30`, `ce8a3763` | audit 31 → 2 FAIL (both pre-existing) |

The determination half of `20261016` was invalid because: the store lacked the standards (1a), the coverage tool rejected a qualified address (1b), and the instruction named values it did not define (third defect). Its lookup half stands (Qwen 63/72, granite 57/72).

## Proposals for the operator (not applied)
- Granite remains unsuited to this lane: 0 tool calls on most rows; no change.
- The four override seats (task-router, auto-image, auto-video, auto-music) carry `evidence: pending`; each needs a measured campaign.
