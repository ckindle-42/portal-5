# Phase 4 — Post-merge fix execution

Execute the task defined in:

**TASK_UAT_PHASE4_POSTMERGE_FIXES.md**

This is a small follow-up to Phase 1/2/3 that fixes two narrow defects discovered while auditing the merged commits. No live system supervision is required — this is a code-only task with deterministic verification.

---

## Quick start

```bash
git clone https://github.com/ckindle-42/portal-5/
cd portal-5
git log --oneline -5
# Confirm Phase 1, 2, 3 commits are present:
#   e3aae7c router: plumb predict_limit into MLX path; cap auto-coding output
#   d9e15ac test(uat): catalog corrections phase 2
#   a9de56e test(uat): driver hardening phase 1

# Read the task file
cat TASK_UAT_PHASE4_POSTMERGE_FIXES.md

# Confirm pre-flight passes
python3 -m pytest tests/unit/test_uat_grading.py -v
# Expected: 7 passed
```

---

## Scope

Three edits to two files:

- `tests/portal5_uat_driver.py` — Edit 1 (remove `lives--`/`lives++` from `_CC01_ASSERTIONS`) and Edit 2 (drop `word_boundary` from CIP citations in WS-16 and P-C01).
- `tests/unit/test_uat_grading.py` — Edit 3 (append two regression tests pinning the `\b` limitation).

**No other files are touched.** Do not edit personas, configs, pipelines, or backends.

---

## Why this phase exists

Two issues discovered during the post-merge audit of Phase 2:

1. `word_boundary: True` silently fails on keywords that begin or end with non-word characters. `lives--` and `lives++` in `_CC01_ASSERTIONS["Lives system"]` are dead code because `\b` can't anchor when both sides are `\W`.
2. The `word_boundary` flag on CIP citations was added based on an incorrect example in the original review plan (`"r1"` was claimed to substring-match `"router 1"`, but the space prevents that). The flag introduces a real regression on smashed citation forms (`R1.2.6`) without a meaningful upside.

The task file contains the diagnosis traces, exact diffs, and reasoning for each edit.

---

## Execution discipline

- **Read the task file first.** It has the exact before/after diffs and the rationale for each edit.
- **Run the pre-flight before editing.** If unit tests don't show 7 PASS, stop and report — Phase 1 is missing.
- **Verify after every edit.** The task file's Verification section has 5 commands; all must pass.
- **One commit at the end** with the exact message in the task file's Commit section. Do not reformat or split.
- **Rollback is `git restore`** on the two files. No services to restart.

---

## Hand-off

When verification passes:

```bash
git diff --cached --stat
# Expected: 2 files changed, ~30 insertions, ~5 deletions

git commit -m "$(cat <<'EOF'
test(uat): phase 4 post-merge fixes

[full message from TASK_UAT_PHASE4_POSTMERGE_FIXES.md Commit section]
EOF
)"

git log --oneline -1
# Confirm the commit landed
```

Report: number of unit tests passing (must be 9), the commit SHA, and whether any verification step warned. If any criterion in the Acceptance section fails, do NOT push — report and wait for direction.

---

## Out of scope (do not do)

- Re-running the UAT suite. The fix is defensive — outcomes don't change for any model already shipping standard `this.lives` patterns. UAT re-run belongs to a separate verification cycle.
- Generalizing `word_boundary` to handle non-word-edge keywords. The task file documents the rule (don't combine word_boundary with non-word-edge keywords) via the new regression tests; that's sufficient for now.
- Cleaning up the orphaned `update_summary` function from Phase 1. Harmless dead code; leave it.
- Renumbering rows in `UAT_RESULTS.md` after `--rerun`. Cosmetic only.

---

*Source: post-merge audit of HEAD `e3aae7c` on 2026-04-29.*
