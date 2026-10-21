# SPL/Sigma/YARA grader review

Review date: 2026-10-21. Scope: read-only review of `coding_task/spl_grader_review/`; `grade_spl.py`, prompts, and supplied fixtures were not edited.

## Verdict

The validator integrations reject malformed syntax and accept the supplied good fixtures, but the grader is not safe for seat promotion. A model can promote without completing the requested detection tasks. The decisive adversarial set contained an SPL search with no impossible-travel logic, two unrelated Calculator Sigma rules, and a YARA rule whose condition can never match; it scored 4/4 and `promote: true`.

## Findings

1. **BLOCKER — Sigma grading is syntax-only and accepts an empty artifact.** `grade_sigma` requires only `validate_sigma.valid` and `convert_sigma.valid`. It does not require one rule, one converted query, the requested log source, ATT&CK tag, fields, values, or detection logic. pySigma treats an empty string as a valid zero-rule collection and the Splunk backend returns a valid zero-query conversion, so an empty prompt-2 artifact was graded `ok: true`. Unrelated `calc.exe` rules also passed prompts 2 and 4.
2. **BLOCKER — YARA compilation does not prove the requested bytes can match.** The grader checks only successful compilation plus the byte text appearing somewhere in the source. A rule requiring the requested bytes, an extra string, and `false` compiled and passed even though it cannot match any input. The hard check needs to scan a positive fixture containing exactly the ten specified bytes and require the submitted rule to match it; a negative fixture should not match.
3. **BLOCKER — SPL structural checks do not test impossible-travel behavior.** `index=anything sourcetype=anything earliest=-1h | stats count | eval label="T1078"` passed. The checks prove the four requested tokens/shapes exist, not that the query compares geographically separated successful logins over time. A prompt-specific checker needs required travel logic and preferably known-answer execution against a frozen offline event fixture.
4. **HIGH — Promotion permits one prompt to fail.** `passed >= 3 and prompt4["ok"]` allows prompt 2 to be absent while still promoting. In the authored omission control, prompt 2 was empty and was incorrectly counted as passed because of finding 1; independently, the threshold still makes one of prompts 1–3 optional. If all four capabilities are required, promotion must require all four.
5. **MEDIUM — The default source checkout can be stale or wrong.** Without `PORTAL_ROOT`, the script imports tools from the hard-coded `/Users/chris/projects/portal-5`, not the checkout containing the grader. The first run from this worktree therefore resolved another tree and failed on its environment. Derive the repository root from the script path or require an explicit root and include its resolved path in the report.

## Fixture review

- `fixtures/pass/` is syntactically valid and aligned with the four prompts; it promoted 4/4.
- `fixtures/fail_spl/01_spl.txt` correctly demonstrates that `spl_validate_syntax` alone accepts a weak query while the added position/T1078 checks reject it.
- `fixtures/refuse/04_sigma.yaml` correctly exercises the current refusal regex.
- Coverage is insufficient: there is no empty-Sigma control, semantically unrelated but valid Sigma control, nonmatching compilable YARA control, semantic SPL control, missing-artifact control, or assertion that each prompt is mandatory.

## Offline evidence

All successful validator runs pinned this checkout with `PORTAL_ROOT="$PWD"` and installed the declared MCP extra.

| Authored set | Result |
| --- | --- |
| Known-good answers satisfying all four prompts | `passed: 4`, `promote: true` |
| Malformed SPL, Sigma, and YARA plus a refusal | `passed: 0`, `promote: false`; process exit 1 |
| Semantically wrong but valid artifacts | `passed: 4`, `promote: true` |
| Empty prompt-2 Sigma with otherwise good artifacts | empty Sigma reported `valid: true`, `rule_count: 0`, `queries: []`, and prompt 2 `ok: true`; overall `passed: 4`, `promote: true` |

Commands run:

```text
PORTAL_ROOT="$PWD" uv run --extra mcp python coding_task/spl_grader_review/grade_spl.py --fixtures
PORTAL_ROOT="$PWD" uv run --extra mcp python coding_task/spl_grader_review/grade_spl.py --artifacts <known-good>
PORTAL_ROOT="$PWD" uv run --extra mcp python coding_task/spl_grader_review/grade_spl.py --artifacts <malformed>
PORTAL_ROOT="$PWD" uv run --extra mcp python coding_task/spl_grader_review/grade_spl.py --artifacts <semantic-bypass>
PORTAL_ROOT="$PWD" uv run --extra mcp python coding_task/spl_grader_review/grade_spl.py --artifacts <prompt-2-empty>
```

Do not use the current `promote` result for the SPL seat candidate until findings 1–4 are fixed and pinned with adversarial fixtures.
