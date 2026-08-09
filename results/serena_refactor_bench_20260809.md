# Serena vs text-path refactor bench — 2026-08-09

**Task:** TASK-BATCH-BENCH-001 Part D.step-2. Rename `score_execution` → `score_execution_v2` in
`portal/modules/security/core/scoring.py`, updating every real caller. Chosen because a second,
unrelated `score_execution` function exists in `tests/scripts/capability_probe.py` and is called
by `tests/unit/test_capability_probe.py` — a genuine same-name/different-symbol collision, not a
contrived one, discovered by grepping the security arm for multi-file symbols.

Both arms ran against a fresh full-repo copy (`cp -R` snapshot), never the live tree. Both arms'
end state was verified with `pytest portal/modules/security/tests/ tests/unit/test_capability_probe.py -k "not lab"` + `ruff check` on the touched files.

## Arm 1 — text/line path (grep + sed/regex substitution, no LSP)

| # | Action | Outcome |
|---|--------|---------|
| 1 | `grep -rl` scoped to `portal/modules/security/core/`, `tests/unit/`, `tests/benchmarks/` | found 6 files (later proven incomplete) |
| 2 | `sed -i -E 's/\bscore_execution\b/.../'` across the 6 files | **ERROR** — BSD/macOS `sed`'s `-E` doesn't support `\b` (a GNU extension); silent no-op, 0 files changed, no error surfaced by the tool itself |
| 3 | Retry with Python `re.sub(r"\bscore_execution\b", ...)` across the 6 files | 6 files edited |
| 4 | Run `pytest tests/unit/test_capability_probe.py` | **ERROR** — 3 failures: the naive text substitution had also renamed calls to the *unrelated* `capability_probe.score_execution` inside `test_capability_probe.py`, which happens to reference the same string but resolves to a different symbol entirely |
| 5 | Revert the incorrect edit in `test_capability_probe.py` | fixed |
| 6 | Re-run `pytest tests/unit/test_capability_probe.py` | green |
| 7 | Run the broader `portal/modules/security/tests/` suite | **ERROR** — collection failure: `test_bench_scoring.py` (in `portal/modules/security/tests/`, outside the original grep scope) imports the real `score_execution` and was never touched |
| 8 | Repo-wide `grep -rl --include="*.py" .` | found the missed file |
| 9 | `re.sub` on `test_bench_scoring.py` | fixed |
| 10 | Full re-verify | **green** — 1697 passed, ruff clean |

**Tally: 10 tool-invocation steps, 3 real errors**, none caught by the editing tool itself — every
error was only discovered by actually running the test suite afterward. Two of the three errors
(the missed-scope discovery, the wrong-symbol over-match) are the exact class of mistake that
text/grep tooling structurally cannot prevent: it has no notion of import bindings or symbol
identity, only string matching.

## Arm 2 — Serena (LSP-backed symbol tools), driven live via the MCP `mcp` client SDK

| # | Action | Outcome |
|---|--------|---------|
| 1 | `activate_project` | ok (auto-generated `.serena/project.yml`, started `pyright-langserver` — first-run `uvx` fetch of `pyright==1.1.403`, no pre-staging needed since this box has live internet) |
| 2 | `find_symbol("score_execution", relative_path=".../scoring.py")` | resolved the exact target function, no ambiguity |
| 3 | `find_referencing_symbols(...)` | returned **exactly** the 5 true reference files — correctly **excluded** `test_capability_probe.py`'s calls to the unrelated same-named `capability_probe.score_execution` (LSP import-binding resolution, not string matching) |
| 4 | `rename_symbol(new_name="score_execution_v2")` | "Successfully renamed ... (6 changes applied)" — single call, all 6 real files, zero manual follow-up |
| — | Full verify | **green on the first attempt** — 1702 passed, ruff clean |

**Tally: 4 tool-invocation steps, 0 errors.** Correct on the first try — the exact symbol collision
that produced 2 of Arm 1's 3 errors was resolved correctly by construction, because
`find_referencing_symbols`/`rename_symbol` operate on the language server's understanding of which
`score_execution` a given call site actually binds to, not on the literal string.

## Verdict

Symbol-aware editing cuts both step count (4 vs 10, ~60% fewer tool calls) and error count (0 vs 3)
on a realistic cross-file rename that included a genuine name collision. The collision is exactly
the failure mode Serena's LSP backend is designed to avoid, and it did — first try, no retries.
This is a small sample (one refactor, one collision), not a statistical claim, but the delta is
large enough and the failure mode specific enough (import-binding resolution vs string matching)
to be a real, generalizable argument for the standing MCP slot: **promote-candidate** for symbol-
heavy refactor work in this codebase's size range (672 Python source files per Pyright's scan).

Air-gap note (GATE-D1): this box has live internet access throughout this session (confirmed by
~60GB of HF model pulls in Parts A-C), so the "pre-stage language server binaries" concern in the
task file did not apply here — `uvx`/Serena fetched `pyright` on first activation with no issue,
the same way every other tool in this task fetched what it needed. An actually air-gapped
deployment would need `pyright`/`pylsp` pre-staged per the task's original caveat.

PROMOTE_POLICY=confirm — this result is a recommendation, not an automatic fleet change. Adopting
Serena as a standing MCP slot is a separate operator decision.
