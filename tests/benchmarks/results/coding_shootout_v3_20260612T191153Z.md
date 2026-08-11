# Coding Shootout V2 — Capability Matrix

**Source matrix run(s)**: `coding_shootout_v3_20260612T191153Z.json`

This matrix shows per-shape assertion-pass-rate for each model.
No single-winner verdict — the matrix is the deliverable.
See TASK_CODING_SHOOTOUT_V2.md §A6.

## Per-Shape Pass Rate

| Model | REPL | Audit | Composite | Ship-It | Overall* | TPS (median) | Memory |
|---|---|---|---|---|---|---|---|
| `hf.co/Jackrong/Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf` | 87.5% | 75.0% | 88.9% | 92.3% | 88.2% | 38.9 | 19 GB |
| `laguna-xs.2:Q4_K_M` | 100.0% | 100.0% | 62.5% | 92.3% | 87.9% | 153.2 | ? GB |
| `devstral-small-2` | 62.5% | 75.0% | 100.0% | 92.3% | 85.3% | 55.6 | 15 GB |
| `hf.co/yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | 75.0% | 100.0% | 88.9% | 84.6% | 85.3% | 85.6 | 7 GB |
| `qwen3-coder:30b-a3b-q4_K_M` | 12.5% | 100.0% | 100.0% | 92.3% | 76.5% | 236.3 | 19 GB |
| `glm-4.7-flash:Q4_K_M` | 50.0% | 75.0% | 77.8% | 61.5% | 64.7% | 166.1 | ? GB |
| `qwen3-coder-next` (REF) | 62.5% | 75.0% | 77.8% | 92.3% | 79.4% | 123.8 | 46 GB |
| `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` (REF) | 62.5% | 100.0% | 88.9% | 92.3% | 85.3% | 131.0 | 46 GB |

*Overall = aggregate across all shapes. Reference models are NOT in candidate ranking.

## V1 Reconciliation

- Laguna under V1 (bench-laguna Creative Coder framing): **93.9%**
- Laguna under V2 (15 production personas across 4 shapes): **0.0%**
- Delta: **-93.9 pp**

If the delta is sharply negative, V1's verdict (INCONCLUSIVE) was correct for V1's question (single-system-prompt control) but uninformative for production load. V2's per-shape decomposition is the right input to the next design conversation.

## Per-Cell Detail

Drill-down per (model, persona, scenario). Each row's status reflects all assertions for that cell.

| Model | Persona | Scenario | Pass | Total | Status |
|---|---|---|---|---|---|
| `laguna-xs.2:Q4_K_M` | sqlterminal | sql-stateful-multi-statement | 3 | 3 | ✓ PASS |
| `laguna-xs.2:Q4_K_M` | linuxterminal | linux-terminal-stateful | 2 | 2 | ✓ PASS |
| `laguna-xs.2:Q4_K_M` | pythoninterpreter | python-repl-traceback | 2 | 2 | ✓ PASS |
| `laguna-xs.2:Q4_K_M` | javascriptconsole | js-console-strict-output | 1 | 1 | ✓ PASS |
| `laguna-xs.2:Q4_K_M` | codereviewer | code-review-with-confidence | 1 | 1 | ✓ PASS |
| `laguna-xs.2:Q4_K_M` | softwarequalityassurancetester | qa-test-enumeration | 1 | 1 | ✓ PASS |
| `laguna-xs.2:Q4_K_M` | bugdiscoverycodeassistant | bug-classification-by-type | 1 | 1 | ✓ PASS |
| `laguna-xs.2:Q4_K_M` | codereviewassistant | code-review-pr-scope | 1 | 1 | ✓ PASS |
| `laguna-xs.2:Q4_K_M` | e2etestauthor | e2e-playwright-login-test | 2 | 4 | ~ WARN |
| `laguna-xs.2:Q4_K_M` | e2edebugger | e2e-debugger-root-cause | 0 | 0 | ✓ PASS |
| `laguna-xs.2:Q4_K_M` | fullstacksoftwaredeveloper | jwt-three-endpoints | 3 | 4 | ~ WARN |
| `laguna-xs.2:Q4_K_M` | creativecoder | creative-particle-system | 5 | 5 | ✓ PASS |
| `laguna-xs.2:Q4_K_M` | pythoncodegeneratorcleanoptimizedproduction-ready | async-http-retry-wrapper | 3 | 4 | ~ WARN |
| `laguna-xs.2:Q4_K_M` | devopsautomator | k8s-manifest-complete | 3 | 3 | ✓ PASS |
| `laguna-xs.2:Q4_K_M` | githubexpert | github-destructive-warning | 1 | 1 | ✓ PASS |
| `glm-4.7-flash:Q4_K_M` | sqlterminal | sql-stateful-multi-statement | 2 | 3 | ~ WARN |
| `glm-4.7-flash:Q4_K_M` | linuxterminal | linux-terminal-stateful | 1 | 2 | ~ WARN |
| `glm-4.7-flash:Q4_K_M` | pythoninterpreter | python-repl-traceback | 0 | 2 | ✗ FAIL |
| `glm-4.7-flash:Q4_K_M` | javascriptconsole | js-console-strict-output | 1 | 1 | ✓ PASS |
| `glm-4.7-flash:Q4_K_M` | codereviewer | code-review-with-confidence | 1 | 1 | ✓ PASS |
| `glm-4.7-flash:Q4_K_M` | softwarequalityassurancetester | qa-test-enumeration | 1 | 1 | ✓ PASS |
| `glm-4.7-flash:Q4_K_M` | bugdiscoverycodeassistant | bug-classification-by-type | 0 | 1 | ✗ FAIL |
| `glm-4.7-flash:Q4_K_M` | codereviewassistant | code-review-pr-scope | 1 | 1 | ✓ PASS |
| `glm-4.7-flash:Q4_K_M` | e2etestauthor | e2e-playwright-login-test | 4 | 4 | ✓ PASS |
| `glm-4.7-flash:Q4_K_M` | e2edebugger | e2e-debugger-root-cause | 0 | 1 | ✗ FAIL |
| `glm-4.7-flash:Q4_K_M` | fullstacksoftwaredeveloper | jwt-three-endpoints | 3 | 4 | ~ WARN |
| `glm-4.7-flash:Q4_K_M` | creativecoder | creative-particle-system | 4 | 5 | ~ WARN |
| `glm-4.7-flash:Q4_K_M` | pythoncodegeneratorcleanoptimizedproduction-ready | async-http-retry-wrapper | 1 | 4 | ~ WARN |
| `glm-4.7-flash:Q4_K_M` | devopsautomator | k8s-manifest-complete | 3 | 3 | ✓ PASS |
| `glm-4.7-flash:Q4_K_M` | githubexpert | github-destructive-warning | 0 | 1 | ✗ FAIL |
| `devstral-small-2` | sqlterminal | sql-stateful-multi-statement | 2 | 3 | ~ WARN |
| `devstral-small-2` | linuxterminal | linux-terminal-stateful | 1 | 2 | ~ WARN |
| `devstral-small-2` | pythoninterpreter | python-repl-traceback | 1 | 2 | ~ WARN |
| `devstral-small-2` | javascriptconsole | js-console-strict-output | 1 | 1 | ✓ PASS |
| `devstral-small-2` | codereviewer | code-review-with-confidence | 0 | 1 | ✗ FAIL |
| `devstral-small-2` | softwarequalityassurancetester | qa-test-enumeration | 1 | 1 | ✓ PASS |
| `devstral-small-2` | bugdiscoverycodeassistant | bug-classification-by-type | 1 | 1 | ✓ PASS |
| `devstral-small-2` | codereviewassistant | code-review-pr-scope | 1 | 1 | ✓ PASS |
| `devstral-small-2` | e2etestauthor | e2e-playwright-login-test | 4 | 4 | ✓ PASS |
| `devstral-small-2` | e2edebugger | e2e-debugger-root-cause | 1 | 1 | ✓ PASS |
| `devstral-small-2` | fullstacksoftwaredeveloper | jwt-three-endpoints | 4 | 4 | ✓ PASS |
| `devstral-small-2` | creativecoder | creative-particle-system | 5 | 5 | ✓ PASS |
| `devstral-small-2` | pythoncodegeneratorcleanoptimizedproduction-ready | async-http-retry-wrapper | 4 | 4 | ✓ PASS |
| `devstral-small-2` | devopsautomator | k8s-manifest-complete | 3 | 3 | ✓ PASS |
| `devstral-small-2` | githubexpert | github-destructive-warning | 0 | 1 | ✗ FAIL |
| `gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | sqlterminal | sql-stateful-multi-statement | 2 | 3 | ~ WARN |
| `gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | linuxterminal | linux-terminal-stateful | 1 | 2 | ~ WARN |
| `gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | pythoninterpreter | python-repl-traceback | 2 | 2 | ✓ PASS |
| `gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | javascriptconsole | js-console-strict-output | 1 | 1 | ✓ PASS |
| `gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | codereviewer | code-review-with-confidence | 1 | 1 | ✓ PASS |
| `gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | softwarequalityassurancetester | qa-test-enumeration | 1 | 1 | ✓ PASS |
| `gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | bugdiscoverycodeassistant | bug-classification-by-type | 1 | 1 | ✓ PASS |
| `gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | codereviewassistant | code-review-pr-scope | 1 | 1 | ✓ PASS |
| `gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | e2etestauthor | e2e-playwright-login-test | 4 | 4 | ✓ PASS |
| `gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | e2edebugger | e2e-debugger-root-cause | 1 | 1 | ✓ PASS |
| `gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | fullstacksoftwaredeveloper | jwt-three-endpoints | 3 | 4 | ~ WARN |
| `gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | creativecoder | creative-particle-system | 5 | 5 | ✓ PASS |
| `gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | pythoncodegeneratorcleanoptimizedproduction-ready | async-http-retry-wrapper | 3 | 4 | ~ WARN |
| `gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | devopsautomator | k8s-manifest-complete | 3 | 3 | ✓ PASS |
| `gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | githubexpert | github-destructive-warning | 0 | 1 | ✗ FAIL |
| `qwen3-coder-next` | sqlterminal | sql-stateful-multi-statement | 2 | 3 | ~ WARN |
| `qwen3-coder-next` | linuxterminal | linux-terminal-stateful | 1 | 2 | ~ WARN |
| `qwen3-coder-next` | pythoninterpreter | python-repl-traceback | 1 | 2 | ~ WARN |
| `qwen3-coder-next` | javascriptconsole | js-console-strict-output | 1 | 1 | ✓ PASS |
| `qwen3-coder-next` | codereviewer | code-review-with-confidence | 1 | 1 | ✓ PASS |
| `qwen3-coder-next` | softwarequalityassurancetester | qa-test-enumeration | 0 | 1 | ✗ FAIL |
| `qwen3-coder-next` | bugdiscoverycodeassistant | bug-classification-by-type | 1 | 1 | ✓ PASS |
| `qwen3-coder-next` | codereviewassistant | code-review-pr-scope | 1 | 1 | ✓ PASS |
| `qwen3-coder-next` | e2etestauthor | e2e-playwright-login-test | 4 | 4 | ✓ PASS |
| `qwen3-coder-next` | e2edebugger | e2e-debugger-root-cause | 0 | 1 | ✗ FAIL |
| `qwen3-coder-next` | fullstacksoftwaredeveloper | jwt-three-endpoints | 3 | 4 | ~ WARN |
| `qwen3-coder-next` | creativecoder | creative-particle-system | 5 | 5 | ✓ PASS |
| `qwen3-coder-next` | pythoncodegeneratorcleanoptimizedproduction-ready | async-http-retry-wrapper | 4 | 4 | ✓ PASS |
| `qwen3-coder-next` | devopsautomator | k8s-manifest-complete | 3 | 3 | ✓ PASS |
| `qwen3-coder-next` | githubexpert | github-destructive-warning | 0 | 1 | ✗ FAIL |
| `huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` | sqlterminal | sql-stateful-multi-statement | 2 | 3 | ~ WARN |
| `huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` | linuxterminal | linux-terminal-stateful | 1 | 2 | ~ WARN |
| `huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` | pythoninterpreter | python-repl-traceback | 1 | 2 | ~ WARN |
| `huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` | javascriptconsole | js-console-strict-output | 1 | 1 | ✓ PASS |
| `huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` | codereviewer | code-review-with-confidence | 1 | 1 | ✓ PASS |
| `huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` | softwarequalityassurancetester | qa-test-enumeration | 1 | 1 | ✓ PASS |
| `huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` | bugdiscoverycodeassistant | bug-classification-by-type | 1 | 1 | ✓ PASS |
| `huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` | codereviewassistant | code-review-pr-scope | 1 | 1 | ✓ PASS |
| `huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` | e2etestauthor | e2e-playwright-login-test | 4 | 4 | ✓ PASS |
| `huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` | e2edebugger | e2e-debugger-root-cause | 1 | 1 | ✓ PASS |
| `huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` | fullstacksoftwaredeveloper | jwt-three-endpoints | 3 | 4 | ~ WARN |
| `huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` | creativecoder | creative-particle-system | 5 | 5 | ✓ PASS |
| `huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` | pythoncodegeneratorcleanoptimizedproduction-ready | async-http-retry-wrapper | 4 | 4 | ✓ PASS |
| `huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` | devopsautomator | k8s-manifest-complete | 3 | 3 | ✓ PASS |
| `huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` | githubexpert | github-destructive-warning | 0 | 1 | ✗ FAIL |
| `Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf` | sqlterminal | sql-stateful-multi-statement | 3 | 3 | ✓ PASS |
| `Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf` | linuxterminal | linux-terminal-stateful | 2 | 2 | ✓ PASS |
| `Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf` | pythoninterpreter | python-repl-traceback | 1 | 2 | ~ WARN |
| `Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf` | javascriptconsole | js-console-strict-output | 1 | 1 | ✓ PASS |
| `Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf` | codereviewer | code-review-with-confidence | 1 | 1 | ✓ PASS |
| `Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf` | softwarequalityassurancetester | qa-test-enumeration | 0 | 1 | ✗ FAIL |
| `Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf` | bugdiscoverycodeassistant | bug-classification-by-type | 1 | 1 | ✓ PASS |
| `Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf` | codereviewassistant | code-review-pr-scope | 1 | 1 | ✓ PASS |
| `Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf` | e2etestauthor | e2e-playwright-login-test | 4 | 4 | ✓ PASS |
| `Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf` | e2edebugger | e2e-debugger-root-cause | 0 | 1 | ✗ FAIL |
| `Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf` | fullstacksoftwaredeveloper | jwt-three-endpoints | 4 | 4 | ✓ PASS |
| `Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf` | creativecoder | creative-particle-system | 5 | 5 | ✓ PASS |
| `Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf` | pythoncodegeneratorcleanoptimizedproduction-ready | async-http-retry-wrapper | 4 | 4 | ✓ PASS |
| `Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf` | devopsautomator | k8s-manifest-complete | 3 | 3 | ✓ PASS |
| `Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf` | githubexpert | github-destructive-warning | 0 | 1 | ✗ FAIL |
| `qwen3-coder:30b-a3b-q4_K_M` | sqlterminal | sql-stateful-multi-statement | 0 | 3 | ✗ FAIL |
| `qwen3-coder:30b-a3b-q4_K_M` | linuxterminal | linux-terminal-stateful | 1 | 2 | ~ WARN |
| `qwen3-coder:30b-a3b-q4_K_M` | pythoninterpreter | python-repl-traceback | 0 | 2 | ✗ FAIL |
| `qwen3-coder:30b-a3b-q4_K_M` | javascriptconsole | js-console-strict-output | 0 | 1 | ✗ FAIL |
| `qwen3-coder:30b-a3b-q4_K_M` | codereviewer | code-review-with-confidence | 1 | 1 | ✓ PASS |
| `qwen3-coder:30b-a3b-q4_K_M` | softwarequalityassurancetester | qa-test-enumeration | 1 | 1 | ✓ PASS |
| `qwen3-coder:30b-a3b-q4_K_M` | bugdiscoverycodeassistant | bug-classification-by-type | 1 | 1 | ✓ PASS |
| `qwen3-coder:30b-a3b-q4_K_M` | codereviewassistant | code-review-pr-scope | 1 | 1 | ✓ PASS |
| `qwen3-coder:30b-a3b-q4_K_M` | e2etestauthor | e2e-playwright-login-test | 4 | 4 | ✓ PASS |
| `qwen3-coder:30b-a3b-q4_K_M` | e2edebugger | e2e-debugger-root-cause | 1 | 1 | ✓ PASS |
| `qwen3-coder:30b-a3b-q4_K_M` | fullstacksoftwaredeveloper | jwt-three-endpoints | 4 | 4 | ✓ PASS |
| `qwen3-coder:30b-a3b-q4_K_M` | creativecoder | creative-particle-system | 5 | 5 | ✓ PASS |
| `qwen3-coder:30b-a3b-q4_K_M` | pythoncodegeneratorcleanoptimizedproduction-ready | async-http-retry-wrapper | 4 | 4 | ✓ PASS |
| `qwen3-coder:30b-a3b-q4_K_M` | devopsautomator | k8s-manifest-complete | 3 | 3 | ✓ PASS |
| `qwen3-coder:30b-a3b-q4_K_M` | githubexpert | github-destructive-warning | 0 | 1 | ✗ FAIL |

---

## Next Step

This matrix is INPUT to a workspace-decomposition design conversation, not a repin recommendation. Read the per-shape columns; identify whether one model dominates every shape (→ simple repin candidate) or whether different models win different shapes (→ workspace decomposition needed).

The successor task (workspace decomposition or repin) is not generated by this script.
