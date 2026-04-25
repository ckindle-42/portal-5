# Coding Agent Prompt — Portal 5 v6.0.3 Review Fixes

You are a coding agent operating on the Portal 5 repository
(`github.com/ckindle-42/portal-5`, currently at v6.0.3).

Three task files describe the work in dependency order:

1. **`TASK_REVIEW_FIXES_PHASE1_QUICK_WINS.md`** — 16 confirmed defects + low-risk
   improvements. ~5h. Safe to execute end-to-end.
2. **`TASK_REVIEW_FIXES_PHASE2_HARDENING.md`** — 12 systemic safeguards. ~17h.
   Requires Phase 1 merged first (the hint validator would otherwise refuse
   to start the pipeline).
3. **`TASK_REVIEW_FIXES_PHASE3_ARCHITECTURE.md`** — 7 structural changes. ~5d.
   Bumps version to 7.0.0 because of the `backends.yaml` schema extension.
   Each task on its own feature branch, operator validation between merges.

**Your job is to execute the tasks in the order they appear within each phase.**
Do not skip tasks. Do not reorder. Do not add scope.

For each task:

1. Run the **Pre-flight** block at the top of the phase file before starting.
2. For each task in order:
   - Read the **Rationale** to understand why.
   - Apply the **Before → After** edit using the exact strings shown.
   - Run the **Verify** block. **Stop and report if any check fails.**
   - Commit using the exact message in the **Commit** block.
3. Run the **Phase verification** at the bottom of the phase file. Report the
   result.
4. **Stop after each phase.** Do not start the next phase without explicit
   operator approval.

**Constraints (per the project's CLAUDE.md and standing operator preferences):**

- All tests must pass: `pytest tests/unit/ -q --tb=no`
- Lint must pass: `ruff check . && ruff format --check .`
- Never `docker compose down -v` (nukes Ollama models)
- Never force push, never commit `.env`
- One concept per commit; messages follow `type(scope): description` form
  shown in each task
- If a verify step fails, **assume the test is right and the code is wrong**.
  Exhaust code-side fixes before deciding the test is broken.
- If you discover the actual code state diverges from what the task file
  describes (e.g., the line numbers have shifted, the surrounding context
  doesn't match), **stop and report** rather than guess.

**Report format after each phase:**

```
Phase N complete: <PASS|FAIL>
Commits landed: <count>
Verification block: <PASS|FAIL with line>
Live regression: <run if applicable, else "skipped">
Anything unexpected: <free text or "none">
```

Operator will review each phase's report before authorizing the next.
