# Coding Shootout V2 — Capability Matrix

**Source matrix run(s)**: `coding_shootout_v2_20260513T180038Z.json, coding_shootout_v2_fixes_codereviewer_20260513T193122Z.json, coding_shootout_v2_fixes_e2etestauthor_20260513T193122Z.json`

This matrix shows per-shape assertion-pass-rate for each model.
No single-winner verdict — the matrix is the deliverable.
See TASK_CODING_SHOOTOUT_V2.md §A6.

## Per-Shape Pass Rate

| Model | REPL | Audit | Composite | Ship-It | Overall* | TPS (median) | Memory |
|---|---|---|---|---|---|---|---|
| `mlx-community/Laguna-XS.2-4bit` ◀ incumbent | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 219.1 | 19 GB |
| `lmstudio-community/Devstral-Small-2507-MLX-4bit` | 62.5% | 25.0% | 88.9% | 92.3% | 76.5% | 53.5 | 15 GB |
| `mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit` | 25.0% | 75.0% | 100.0% | 92.3% | 76.5% | 178.2 | 22 GB |
| `mlx-community/GLM-4.7-Flash-4bit` | 62.5% | 50.0% | 44.4% | 61.5% | 55.9% | 188.9 | 15 GB |
| `mlx-community/Qwen3-Coder-Next-4bit` (REF) | 37.5% | 50.0% | 88.9% | 100.0% | 76.5% | 169.5 | 46 GB |

*Overall = aggregate across all shapes. Reference models are NOT in candidate ranking.

## V1 Reconciliation

- Laguna under V1 (bench-laguna Creative Coder framing): **93.9%**
- Laguna under V2 (15 production personas across 4 shapes): **100.0%**
- Delta: **+6.1 pp**

If the delta is sharply negative, V1's verdict (INCONCLUSIVE) was correct for V1's question (single-system-prompt control) but uninformative for production load. V2's per-shape decomposition is the right input to the next design conversation.

## Per-Cell Detail

Drill-down per (model, persona, scenario). Each row's status reflects all assertions for that cell.

| Model | Persona | Scenario | Pass | Total | Status |
|---|---|---|---|---|---|
| `GLM-4.7-Flash-4bit` | sqlterminal | sql-stateful-multi-statement | 2 | 3 | ~ WARN |
| `GLM-4.7-Flash-4bit` | linuxterminal | linux-terminal-stateful | 1 | 2 | ~ WARN |
| `GLM-4.7-Flash-4bit` | pythoninterpreter | python-repl-traceback | 1 | 2 | ~ WARN |
| `GLM-4.7-Flash-4bit` | javascriptconsole | js-console-strict-output | 1 | 1 | ✓ PASS |
| `GLM-4.7-Flash-4bit` | codereviewer | code-review-with-confidence | 1 | 1 | ✓ PASS |
| `GLM-4.7-Flash-4bit` | softwarequalityassurancetester | qa-test-enumeration | 0 | 1 | ✗ FAIL |
| `GLM-4.7-Flash-4bit` | bugdiscoverycodeassistant | bug-classification-by-type | 0 | 1 | ✗ FAIL |
| `GLM-4.7-Flash-4bit` | codereviewassistant | code-review-pr-scope | 1 | 1 | ✓ PASS |
| `GLM-4.7-Flash-4bit` | e2etestauthor | e2e-playwright-login-test | 1 | 4 | ~ WARN |
| `GLM-4.7-Flash-4bit` | e2edebugger | e2e-debugger-root-cause | 0 | 1 | ✗ FAIL |
| `GLM-4.7-Flash-4bit` | fullstacksoftwaredeveloper | jwt-three-endpoints | 3 | 4 | ~ WARN |
| `GLM-4.7-Flash-4bit` | creativecoder | creative-particle-system | 4 | 5 | ~ WARN |
| `GLM-4.7-Flash-4bit` | pythoncodegeneratorcleanoptimizedproduction-ready | async-http-retry-wrapper | 2 | 4 | ~ WARN |
| `GLM-4.7-Flash-4bit` | devopsautomator | k8s-manifest-complete | 2 | 3 | ~ WARN |
| `GLM-4.7-Flash-4bit` | githubexpert | github-destructive-warning | 0 | 1 | ✗ FAIL |
| `Devstral-Small-2507-MLX-4bit` | sqlterminal | sql-stateful-multi-statement | 2 | 3 | ~ WARN |
| `Devstral-Small-2507-MLX-4bit` | linuxterminal | linux-terminal-stateful | 1 | 2 | ~ WARN |
| `Devstral-Small-2507-MLX-4bit` | pythoninterpreter | python-repl-traceback | 1 | 2 | ~ WARN |
| `Devstral-Small-2507-MLX-4bit` | javascriptconsole | js-console-strict-output | 1 | 1 | ✓ PASS |
| `Devstral-Small-2507-MLX-4bit` | codereviewer | code-review-with-confidence | 0 | 1 | ✗ FAIL |
| `Devstral-Small-2507-MLX-4bit` | softwarequalityassurancetester | qa-test-enumeration | 0 | 1 | ✗ FAIL |
| `Devstral-Small-2507-MLX-4bit` | bugdiscoverycodeassistant | bug-classification-by-type | 1 | 1 | ✓ PASS |
| `Devstral-Small-2507-MLX-4bit` | codereviewassistant | code-review-pr-scope | 0 | 1 | ✗ FAIL |
| `Devstral-Small-2507-MLX-4bit` | e2etestauthor | e2e-playwright-login-test | 4 | 4 | ✓ PASS |
| `Devstral-Small-2507-MLX-4bit` | e2edebugger | e2e-debugger-root-cause | 1 | 1 | ✓ PASS |
| `Devstral-Small-2507-MLX-4bit` | fullstacksoftwaredeveloper | jwt-three-endpoints | 3 | 4 | ~ WARN |
| `Devstral-Small-2507-MLX-4bit` | creativecoder | creative-particle-system | 5 | 5 | ✓ PASS |
| `Devstral-Small-2507-MLX-4bit` | pythoncodegeneratorcleanoptimizedproduction-ready | async-http-retry-wrapper | 4 | 4 | ✓ PASS |
| `Devstral-Small-2507-MLX-4bit` | devopsautomator | k8s-manifest-complete | 3 | 3 | ✓ PASS |
| `Devstral-Small-2507-MLX-4bit` | githubexpert | github-destructive-warning | 0 | 1 | ✗ FAIL |
| `Laguna-XS.2-4bit` | sqlterminal | sql-stateful-multi-statement | 3 | 3 | ✓ PASS |
| `Laguna-XS.2-4bit` | linuxterminal | linux-terminal-stateful | 2 | 2 | ✓ PASS |
| `Laguna-XS.2-4bit` | pythoninterpreter | python-repl-traceback | 2 | 2 | ✓ PASS |
| `Laguna-XS.2-4bit` | javascriptconsole | js-console-strict-output | 1 | 1 | ✓ PASS |
| `Laguna-XS.2-4bit` | codereviewer | code-review-with-confidence | 1 | 1 | ✓ PASS |
| `Laguna-XS.2-4bit` | softwarequalityassurancetester | qa-test-enumeration | 1 | 1 | ✓ PASS |
| `Laguna-XS.2-4bit` | bugdiscoverycodeassistant | bug-classification-by-type | 1 | 1 | ✓ PASS |
| `Laguna-XS.2-4bit` | codereviewassistant | code-review-pr-scope | 1 | 1 | ✓ PASS |
| `Laguna-XS.2-4bit` | e2etestauthor | e2e-playwright-login-test | 4 | 4 | ✓ PASS |
| `Laguna-XS.2-4bit` | e2edebugger | e2e-debugger-root-cause | 1 | 1 | ✓ PASS |
| `Laguna-XS.2-4bit` | fullstacksoftwaredeveloper | jwt-three-endpoints | 4 | 4 | ✓ PASS |
| `Laguna-XS.2-4bit` | creativecoder | creative-particle-system | 5 | 5 | ✓ PASS |
| `Laguna-XS.2-4bit` | pythoncodegeneratorcleanoptimizedproduction-ready | async-http-retry-wrapper | 4 | 4 | ✓ PASS |
| `Laguna-XS.2-4bit` | devopsautomator | k8s-manifest-complete | 3 | 3 | ✓ PASS |
| `Laguna-XS.2-4bit` | githubexpert | github-destructive-warning | 1 | 1 | ✓ PASS |
| `Qwen3-Coder-30B-A3B-Instruct-8bit` | sqlterminal | sql-stateful-multi-statement | 0 | 3 | ✗ FAIL |
| `Qwen3-Coder-30B-A3B-Instruct-8bit` | linuxterminal | linux-terminal-stateful | 1 | 2 | ~ WARN |
| `Qwen3-Coder-30B-A3B-Instruct-8bit` | pythoninterpreter | python-repl-traceback | 1 | 2 | ~ WARN |
| `Qwen3-Coder-30B-A3B-Instruct-8bit` | javascriptconsole | js-console-strict-output | 0 | 1 | ✗ FAIL |
| `Qwen3-Coder-30B-A3B-Instruct-8bit` | codereviewer | code-review-with-confidence | 0 | 1 | ✗ FAIL |
| `Qwen3-Coder-30B-A3B-Instruct-8bit` | softwarequalityassurancetester | qa-test-enumeration | 1 | 1 | ✓ PASS |
| `Qwen3-Coder-30B-A3B-Instruct-8bit` | bugdiscoverycodeassistant | bug-classification-by-type | 1 | 1 | ✓ PASS |
| `Qwen3-Coder-30B-A3B-Instruct-8bit` | codereviewassistant | code-review-pr-scope | 1 | 1 | ✓ PASS |
| `Qwen3-Coder-30B-A3B-Instruct-8bit` | e2etestauthor | e2e-playwright-login-test | 4 | 4 | ✓ PASS |
| `Qwen3-Coder-30B-A3B-Instruct-8bit` | e2edebugger | e2e-debugger-root-cause | 1 | 1 | ✓ PASS |
| `Qwen3-Coder-30B-A3B-Instruct-8bit` | fullstacksoftwaredeveloper | jwt-three-endpoints | 4 | 4 | ✓ PASS |
| `Qwen3-Coder-30B-A3B-Instruct-8bit` | creativecoder | creative-particle-system | 5 | 5 | ✓ PASS |
| `Qwen3-Coder-30B-A3B-Instruct-8bit` | pythoncodegeneratorcleanoptimizedproduction-ready | async-http-retry-wrapper | 4 | 4 | ✓ PASS |
| `Qwen3-Coder-30B-A3B-Instruct-8bit` | devopsautomator | k8s-manifest-complete | 3 | 3 | ✓ PASS |
| `Qwen3-Coder-30B-A3B-Instruct-8bit` | githubexpert | github-destructive-warning | 0 | 1 | ✗ FAIL |
| `Qwen3-Coder-Next-4bit` | sqlterminal | sql-stateful-multi-statement | 0 | 3 | ✗ FAIL |
| `Qwen3-Coder-Next-4bit` | linuxterminal | linux-terminal-stateful | 1 | 2 | ~ WARN |
| `Qwen3-Coder-Next-4bit` | pythoninterpreter | python-repl-traceback | 1 | 2 | ~ WARN |
| `Qwen3-Coder-Next-4bit` | javascriptconsole | js-console-strict-output | 1 | 1 | ✓ PASS |
| `Qwen3-Coder-Next-4bit` | codereviewer | code-review-with-confidence | 1 | 1 | ✓ PASS |
| `Qwen3-Coder-Next-4bit` | softwarequalityassurancetester | qa-test-enumeration | 0 | 1 | ✗ FAIL |
| `Qwen3-Coder-Next-4bit` | bugdiscoverycodeassistant | bug-classification-by-type | 1 | 1 | ✓ PASS |
| `Qwen3-Coder-Next-4bit` | codereviewassistant | code-review-pr-scope | 0 | 1 | ✗ FAIL |
| `Qwen3-Coder-Next-4bit` | e2etestauthor | e2e-playwright-login-test | 4 | 4 | ✓ PASS |
| `Qwen3-Coder-Next-4bit` | e2edebugger | e2e-debugger-root-cause | 0 | 1 | ✗ FAIL |
| `Qwen3-Coder-Next-4bit` | fullstacksoftwaredeveloper | jwt-three-endpoints | 4 | 4 | ✓ PASS |
| `Qwen3-Coder-Next-4bit` | creativecoder | creative-particle-system | 5 | 5 | ✓ PASS |
| `Qwen3-Coder-Next-4bit` | pythoncodegeneratorcleanoptimizedproduction-ready | async-http-retry-wrapper | 4 | 4 | ✓ PASS |
| `Qwen3-Coder-Next-4bit` | devopsautomator | k8s-manifest-complete | 3 | 3 | ✓ PASS |
| `Qwen3-Coder-Next-4bit` | githubexpert | github-destructive-warning | 1 | 1 | ✓ PASS |

---

## Next Step

This matrix is INPUT to a workspace-decomposition design conversation, not a repin recommendation. Read the per-shape columns; identify whether one model dominates every shape (→ simple repin candidate) or whether different models win different shapes (→ workspace decomposition needed).

The successor task (workspace decomposition or repin) is not generated by this script.
