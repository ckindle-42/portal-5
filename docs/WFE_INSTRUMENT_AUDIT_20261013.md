# Model-evaluation instrument audit — 2026-10-13

This audit was prompted by the review of TASK_WFE_PROMPT_SURFACE_REBASELINE_V2. It covers every
instrument that fed a model disposition:

- WFE (`tests/wfe/`);
- the compliance judgment probe (`tests/benchmarks/bench_judgment_probe_v6.py`);
- the domain capability probes (`tests/benchmarks/bench_*_probe.py`);
- `bench_tps` quality.

The question was whether any instrument defect decided a model instead of the model deciding.
Several did.

Each fix below has a unit test. No production code or config changed.

## Defects that biased model choice

| # | Instrument | Defect | Direction of bias | Fix |
|---|---|---|---|---|
| 1 | WFE | Every workspace was measured with the alphabetically-first persona bound to it (auto-coding `agenticheavy` of 40, auto-compliance `cippolicywriter`, tools-specialist `toolcomposer`; 10 of 11 workloads), not the prompt Open WebUI sends for the workspace. `auto-general-uncensored` got an invented `<description> Perform the user's task faithfully.` where production sends none. | Arbitrary. The measured seat was not the product. | `workspace_context` uses `owui_system_prompt`. A persona is measured only when named (`persona:` on an arm). An empty prompt sends no system message. |
| 2 | WFE | Challengers ran at the **incumbent's** workspace sampling (auto-compliance: temperature 0.3, repetition_penalty 1.1; gpt-oss's card is 1.0/1.0). | **Toward the incumbent.** | A challenger with no explicit `sampling` runs at its card's `recommended_sampling`, in the mode matching the lane's think policy. `sampling: seat` opts out. |
| 3 | WFE | Compliance tasks were graded on the **exact** label. The probe the tasks come from says exact accuracy is not a headline (PARTIAL/CONTRADICTED/ABSENT is ambiguous). Its keys also disagree on structurally identical packets: P6J-05 (logs retained instead of reviewed) is CONTRADICTED, while P6J-11 and P6J-27 (plan reviewed instead of tested; bulletins instead of an assessment) are ABSENT. P6J-05/17/18 were relabelled after an 11-of-12 seat-consensus vote. | **Toward the incumbent.** Re-graded by class: incumbent Qwen3.8 +1; glm-4.7-flash +6, granite4.1:30b +6, granite4.2 +4, gpt-oss +3. | Graded on violation class (met / unmet / abstain), with the exact label kept as `evidence.exact_label_match`. |
| 4 | WFE | The p6j instruction stated none of the council seat's decision rules: stricter satisfies, ABSENT = complete packet with no addressing candidate, and the Y21 dated-term rule. P6J-19's key depends entirely on Y21, which the council needed because every roster seat missed it. | Toward models that share the key author's conventions. | The council seat's rules are in every p6j instruction. |
| 5 | WFE | Compliance packet tasks could read the whole repository, including Portal's compliance source and the y21 adjudication notes about P6J-14/19 by id (later also the WFE closeouts quoting keys). | Loops and leakage; 11/12 V2 compliance loops read those files. | `repo_read: false` on all packet tasks: sandbox only, and the tool description says so. |
| 6 | WFE | `repo_search(pattern, <file>)` searched the whole sandbox instead of the file. | Manufactured repeated-call loops. | A scoped search; a missing path is an error; repo directories keep the deny list. |
| 7 | WFE | Silent context truncation was never detected. Ollama cuts an over-long prompt to about half the window, keeping 5 tokens (the system prompt and task go first). It context-shifts a full generation by half. Its log shows this inside `wfe_full_20260911` (granite4.1:8b-ctx8k, Nex ctx16k, Qwen3.6-abliterated ctx8k), and no row recorded it. | Against small-context tags, invisibly. | Per-turn usage and sent characters; `evidence.context_overflow` when a prompt shrinks, reaches the window, or runs to more than 8 chars/token. |
| 8 | WFE | The pipeline's "⚠️ The model did not produce an answer" placeholder was scored as the model's answer. | Engine faults read as model FAILs (tools-specialist V2). | Stripped and flagged (`evidence.pipeline_no_answer`). |
| 9 | WFE | Pipeline rows served by the failover engine counted as seat rows; the arm kept the failover resident. | Mixed two engines into one "seat" number. | `seat_primary` + `served_mismatch`: BLOCKED, sticky on rescore, arm stops. |
| 10 | WFE | `code-cli-args` passed on `summarize.py` existing with `def summarize` (a stub scored like a working implementation). `res-ollama-ctx` passed without the workaround. `res-repo-grounded` passed without the artifacts it asks for (9 historical PASS rows named none). | Everyone passed; the lanes could not separate models. | Hidden suite `graded/code_summarize` (7 tests: stub 1/7, correct 7/7); the answer patterns require the substance. |
| 11 | WFE | The code-kv instruction said `\\;` (two backslashes) while the hidden suite tests `\;`. | Laguna loops on its own tests, with the hidden suite passing 7/7 in all 5 loop rows. | The instruction says `\;`. |
| 12 | WFE | Temperature-0 repeats were one draw counted three times in the Wilson intervals. The degeneracy flag read the workspace temperature, not the arm's. | Toward a deterministic arm being "separated". | The rate counts one draw per task when repeats are degenerate; the flag follows the arm's sampling. |
| 13 | WFE | `/workspace` paths (named in general-deep's prompt) were not mapped. The tool log under-reported errors. Pipeline error frames were read as empty answers. The debug record and `prompt_sha` showed the wrong prompt in pipeline mode. | Misattribution. | All fixed. |
| 14 | Judgment probe v6 | The 2026-09-06 roster sweep ran with `think:false`, temperature 0 and a **700-token cap**. The council runs seats with reasoning allowed and an 8192 budget; DeepSeek-R1 scored ERR on every case. Transport errors and budget-skipped cases scored as missed violations. | **Against reasoning models**, and against any seat behind a flaky load. | The default transport is the council's own (`reading_transport.chat`, `_SEAT_BUDGET`, the council temperature table). `--transport legacy-native` reproduces the old run. Errors are excluded and counted (`instrument_errors`). |
| 15 | Compliance / data / CAD probes | `num_predict` 512/512/1024 covered reasoning **and** answer, so a reasoning model's empty answer was scored wrong. Transport errors were in the denominator. | Against reasoning models. | `PROBE_PREDICT = 4096`. Reasoning-only replies are `budget_exhausted` and excluded; errors are excluded and counted. |
| 16 | Tool-use / security-exec / vision probes | Scored `content + thinking`: a keyword the model only *considered* in private reasoning counted as its answer. | **Toward reasoning models.** | Scored on the answer only; a reasoning-only reply is `budget_exhausted`. |
| 17 | SPL / long-context / refusal / reasoning probes | Transport errors were in the denominator. | Against seats behind a flaky load. | Excluded and counted. |
| 18 | `bench_tps` quality | Scored `reasoning_text` when the answer was empty. A missing scorer silently gave 1.0. | Inflated tps_quality for non-answers. | Answer only; unscored is `None` with `quality_unscored`, ranked on speed and labelled. |
| 19 | WFE unit tests | `TestTransientPreflightIsRecoverable` called `execute_arm` without stubbing the drains. Every test run evicted the live router model from Ollama. | Perturbed live benchmarks run beside the tests. | Drains stubbed. |

## Decisions at risk

These dispositions rest on evidence measured with one or more of the defects above. None is
reversed here. Each needs re-measurement on the corrected instrument (TASK_WFE_PROMPT_SURFACE_REBASELINE_V3,
P4). Numbers are class re-grades of the recorded answers. They are not re-runs, so defects 1, 2,
5 and 7 remain in them.

| Decision (source) | Defects | Class re-grade of the recorded rows |
|---|---|---|
| auto-compliance incumbent Qwen3.8-27B "confirmed on clean evidence" (`docs/WFE_CLOSEOUT_20260912.md` §5b) | 1, 2, 3, 4, 5 | `wfe_think_rerun_20260912`: Qwen3.8 24/30 vs **granite4.1:30b 24/30** (exact grading: 24 vs 18). Not separated. |
| granite4.2:30b FOLDED (tie with granite4.1:30b) | 1, 2, 3, 4, 5 | granite4.1:30b 24/30 vs granite4.2 20/30. The rule still fires, but on biased data. |
| gpt-oss:20b RETAINED (compliance arm) | 1, 2, 3, 14 | 21/30. |
| glm-4.7-flash, kat-coder, Qwen3.8-Uncensored as auto-coding / compliance contenders (`wfe_full_20260911`) | 1, 2, 3, 7 | glm-4.7-flash 15→21/30; kat 22→23; Qwen3.8-Uncensored 26→27. |
| tools-specialist incumbent granite4.1:8b-ctx8k vs gemma4:e4b (`workloads.yaml`) | 1, 7, 8, 11 | The Ollama log shows context truncation on granite4.1:8b-ctx8k rows in `wfe_full_20260911` and V1; the V2 FAILs are the oMLX stream drop. |
| Laguna-XS-2.1 seat over MiMo (29/42 vs 11/42; `wfe_mimo_fit_*`, `wfe_laguna21_seat_*`) | 1, 2, 3, 11 | Laguna +3 by class. MiMo's arms ran at seat sampling, with HTTP 400 harness errors. |
| auto-research Nex-N2-mini over granite4.2 | 1, 2, 10 | Research checkers were weak (defect 10). |
| Compliance council roster qualification (probe v6, 2026-09-06 sweep) | 14 | Reasoning seats were measured think-off at 700 tokens; DeepSeek-R1 scored ERR on every case. |
| Routing "per-dimension winners" from the domain probes | 15, 16, 17 | Biased both ways, by reasoning behaviour. |

Not affected: `bench_tps` speed numbers (TPS, TTFT) and dispositions recorded as "no production
ref" (dependency scans).
