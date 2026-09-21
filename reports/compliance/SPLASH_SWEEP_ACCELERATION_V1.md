# SPLASH_SWEEP_ACCELERATION_V1 — the sweep lane, measured and decided

Generated 2026-09-21T09:21:23.640190+00:00 by `scripts/compliance/write_splash_report.py`. Every number is read from a receipt at write time.

- **Base:** 8720b60a94b3 · splash Splash 1.0.1 · incumbent `gemma4:26b-a4b-it-q4_K_M-ctx32k`

**The finding that motivated this task:** the sweep's endpoint was a hardcoded Ollama constant — `reading_transport.py:78` (`_ENDPOINT = "http://localhost:11434/api/chat"`). `sweep.map_read` never consults `config/backends.yaml` or the backend registry, so registering splash with the PIPELINE would have changed the conversation lane and left the sweep exactly where it was.

## §1 — The dialect seam, and the proof that the default did not move

What moved: `transport_dialects.py` (new) holds the wire-protocol differences; `reading_transport.chat` delegates build/unpack/metrics/ceiling/400-classification to the resolved dialect; `sweep.map_read` and `sweep_standard` carry a `dialect` parameter and stamp the serving engine onto every cell. What stayed: the budget split, the empty-answer retry, the thinking-downgrade record, and `_ENDPOINT` as the native default.

Parity proof: implicit and explicit `ollama-native` resolved to the same endpoint (http://localhost:11434/api/chat) on live calls — verdict **PASS**.

## §2 — Splash through the seam: a real determination

Qwen3.6-35B-A3B via the relay: 60.47s, 9365 chars, determination block parses (1 entries) — verdict **PASS**. The serve-line pin was asserted from the running process tree, not from the script that should have passed it.

## §3 — The four arms, attributed

| arm | engine | shape | wall s | ok | determinations |
| --- | --- | --- | --- | --- | --- |
| A | gemma4:26b-a4b-it-q4_K_M-ctx32k | ollama sequential (incumbent) | 1375.83 | 20/20 | 35 |
| B | incoai/Qwen3.6-35B-A3B-Splash | splash sequential | 621.93 | 14/20 | 41 |
| C | incoai/Qwen3.6-35B-A3B-Splash | splash concurrent (proposal) | 269.45 | 14/20 | 41 |
| D | gemma4:26b-a4b-it-q4_K_M-ctx32k | ollama concurrent (control) | 1283.28 | 20/20 | 42 |

**Attribution (mandatory reading):** C-over-A is the end-to-end change (5.106×); C-over-D is the ENGINE's own contribution (4.763×); D-over-A is concurrency on the incumbent — which bought only 1.072×, because the cached-sequential shape already reuses its prefix and concurrent slots contend for it.

Reading agreement against arm A: B jaccard 0.129, C jaccard 0.129, D jaccard 0.2857. **A-vs-D jaccard is itself only 0.286** — the reading varies run to run at temperature 0, so part of splash's 0.129 gap is reading variance, not engine variance. The criteria still bind: a sweep that cannot complete the output contract is not a faster sweep, whichever engine serves it.

The 6 splash parse-failures are the same refs in B and C (R1 Parts 1.1/1.2, R2 Part 2.4, R3 Part 3.1, R4 Part 4.3, R5 Part 5.3) — deterministic no-determinations-block answers, recorded per cell.

## §4 — The two-model coherence cost

Address rate: single-model control **1.0**, two-model case **1.0** — the conversation seat engages Qwen-proposed determinations exactly as it engages its own engine's. The instrument is coarse (it counts section-id echoes), so this prices the obvious failure out, not every failure in.

> Run 1 asked the original wording ('...the requirement and my documents... say for each whether you agree...') and every turn died empty at hop 1 — the router's explicit-side-effect matcher again ('requirement'/'say' plus a CIP id narrows the workspace to one tool and the turn passes through unanswered). Receipt preserved at two_model_coherence_run1_blocked_by_router.json. Run 2 (this receipt) avoids the matcher's trigger words.

## §5 — The decision, made by the data

**KEEP_OLLAMA_FOR_SWEEP** — `config/compliance/sweep_engine.json` not written.

| criterion | measured | bound | ok |
| --- | --- | --- | --- |
| engine_speedup_C_over_D | 4.763 | 2.0 | OK |
| wall_speedup_C_over_A | 5.106 | 2.0 | OK |
| reading_agreement_jaccard | 0.129 | 0.8 | NO |
| parse_failure_delta | 0.3 | 0.05 | NO |
| completion_rate | 0.7 | 0.95 | NO |

> This decision governs the compliance SWEEP lane only. The conversation lane keeps its seat: the incumbent already reuses the append prefix x157 and nothing measured here speaks to conversation quality or latency.

**Withdrawn and re-measured:** the §5 arms ran the task default (`Qwen3.6-35B-A3B`), but the deciding bake-off evidence (addendum 2 PASS + the 3-hour soak) was earned on **Qwen3.8-27B** — see §ADDENDUM. The 35B decision is superseded by the addendum's.

## §6 — Soak watch

**SKIP** — sweep stayed on ollama; the splash memory watch item is not operational

## §7 — What is still open

1. **Splash serves one model at a time** — a second concurrent lane on it would evict. It is never auto-started; a promoted lane would start it for the duration of its own run.
2. **Splash ships no gemma4 package** — a promoted sweep is a two-model system; §4 priced the coherence cost at the address-rate level (none measured), not at every level.
3. **The output contract is the blocker, not the speed.** The same 6 refs deterministically produce no determinations block on Qwen3.6-35B (§3). A prompt-side fix is a separate task with its own evidence; until then the completion criterion fails on its own.
4. **The memory-accumulation watch item** (~3.5 GB / 3 h, addendum 2b) was not re-soaked — nothing was promoted to watch.
5. **The conversation lane is untouched and unmeasured here by design** — its append prefix already reuses ×157 on the incumbent.
6. **The 48k/128k window horizon** — 32k is where the reuse verdict lives; wider windows are a separate question.
7. **The router's explicit-side-effect matcher** (found during the companion closeout's P8): any analysis question containing a CIP id plus require/requirement/say/state/mean/text gets narrowed to one tool and dies unanswered — a product defect for conversational analysis, recorded in the closeout's §9.

## §8 — Lessons

| date | failure | repair | guard |
| --- | --- | --- | --- |
| 2026-09-20 | the wrong lane: a proposed integration wired splash into the pipeline, which the sweep does not use | the dialect seam | every cell records the endpoint that served it, and the decision refuses to score an arm whose endpoint contradicts its dialect |
| 2026-09-20 | the missing control: the first four-arm design had no arm D, so a concurrency gain would have been reported as an engine gain | arm D measured — and showed concurrency buys the incumbent almost nothing (1.072×) | `engine_speedup_C_over_D` is a required criterion; the decider exits 2 when arm D is absent |
| 2026-09-21 | the shell that lied: the first B/C invocation expanded `--splash-model` to empty (per-command prefix assignment does not set the variable used earlier in the same command line), producing 0.03 s/ref cells with zero determinations | receipt overwritten by the valid re-run; the empty-model arms are documented here, not silently discarded | the decision script's endpoint-integrity and completion gates reject junk arms |

## §ADDENDUM — re-measured on the deciding model (Qwen3.8-27B), 2026-09-21

The operator challenged the model choice, correctly: every splash PASS verdict in the bake-off — the tool probe, addendum 2, and the 3-hour soak — was earned on `incoai/Qwen3.8-27B-Splash` (the 1.0-era wedges were an engine-version failure, fixed in 1.0.1, on this same model). This task's default had named the 35B, and the original §5 arms measured it. Arms B/C re-ran on Qwen3.8-27B, readiness-gated on a real completion; A/D (the incumbent) are unchanged. Two earlier receipts from the correction are preserved: an empty-`--splash-model` run (overwritten) and a run that raced the 30-second model load (`arms_splash_qwen38_INVALID_raced_model_load.json`).

| arm | model | wall s | ok | determinations |
| --- | --- | --- | --- | --- |
| A | gemma4:26b-a4b-it-q4_K_M-ctx32k | 1375.83 | 20/20 | 35 |
| B | incoai/Qwen3.8-27B-Splash | 2833.5 | 16/20 | 35 |
| C | incoai/Qwen3.8-27B-Splash | 1089.8 | 16/20 | 35 |
| D | gemma4:26b-a4b-it-q4_K_M-ctx32k | 1283.28 | 20/20 | 42 |

Jaccard vs A: B 0.2, C 0.2, D 0.2857.

**KEEP_OLLAMA_FOR_SWEEP** — `config/compliance/sweep_engine.json` not written.

| criterion | measured | bound | ok |
| --- | --- | --- | --- |
| engine_speedup_C_over_D | 1.178 | 2.0 | NO |
| wall_speedup_C_over_A | 1.262 | 2.0 | NO |
| reading_agreement_jaccard | 0.2 | 0.8 | NO |
| parse_failure_delta | 0.2 | 0.05 | NO |
| completion_rate | 0.8 | 0.95 | NO |

**Why the early bench's 2.1× does not appear here:** the early bench compared ENGINES on the same model (splash-Qwen3.8 vs ollama-Qwen3.8, a 11.6 tok/s decode baseline) on 400-token probes. The four arms compare production SHAPES: the incumbent is gemma4 on ollama — a faster decoder that also holds the prefix cache sequentially — and the sweep's outputs are 1-3k tokens, where the 27B decodes at ~9 tok/s even on splash. Splash-3.8 concurrent does beat the incumbent's sequential wall (1089.8s vs 1375.8s, 1.26×), but under the 2.0 floor, with 4/20 cells failing the output contract and jaccard 0.2. The verdict direction survives the model correction; its evidence is now earned on the right model.

## §9 — Push-time gate record

- **PASS** pre-commit suite (every commit): gitleaks + ruff lint/format + spine coverage/drift + full unit suite (2333 tests) green on all splash-task commits
- **PASS** spine manifest: regenerated after binding write_splash_report.py and the splash_sweep_engine validation check to unit-compliance-transport-dialects; part1 0 errors, part2 0 uncovered
- **PASS-with-recorded-GS** validate_system.py (full): see CLOSEOUT_V1 §11: GS corpus-sync staleness is pre-existing and recorded there with the attempted repair; this campaign's own checks (incl. the new splash_sweep_engine SKIP-when-unpromoted) are green
- **PASS** leave the box as found: splash serve and the socat relay stopped after measurement; the forwarder plist deliberately NOT loaded; launch.sh untouched
