# TASK: Comment Discipline Audit — Narrative Comments vs. Wiki Spine

**Task ID:** TASK-COMMENT-DISCIPLINE-001
**Priority:** Low (quality/maintainability, not correctness)
**Category:** Codebase hygiene

---

## Context

2026-07-29: while fixing a Qwen-Image memory-crash incident, added several
code comments that narrated the incident itself ("Confirmed live 2026-07-29:
...", "A prior version of this file assumed... that was never live-verified
and was wrong") directly into `portal/modules/media/tools/comfyui_mcp.py`,
`video_mcp.py`, and `scripts/lib/services.sh`. Caught and trimmed in-session:
this violates CLAUDE.md's own comment guidance ("Don't reference the current
task, fix, or callers... those belong in the PR description and rot as the
codebase evolves") and the project's wiki-spine principle (Rule 12/13) —
durable narrative belongs in a `portal_wiki/canonical/` unit (rendered into
`KNOWN_LIMITATIONS.md` etc.), not baked permanently into source comments next
to code that will keep changing after the incident is forgotten.

A quick grep during that same fix showed this is **not new** — the same
pattern exists well outside anything touched that session, concentrated in
`portal/modules/security/` (the largest module, most actively developed
across many prior sessions):

- `portal/modules/security/core/exec_chain.py:1659` — "observable -- confirmed
  live 2026-07-24 after building a full self-callback..."
- `portal/modules/security/core/exec_chain.py:2336` — "issues from earlier
  this session made it low-confidence -- see..."
- `portal/modules/security/core/exec_chain.py:3649` — "confirmed live
  2026-07-23: a model produced 4..."
- `portal/modules/security/core/siem/capture_enrichment.py:254` — "A prior
  version of this function had a 'broader attack evidence' fallback:"
- `portal/modules/security/core/cli.py:1354` — "2026-07-03: multiple crashes
  this session lost an entire run's..."
- `portal/modules/security/tests/test_ablation_attribution.py:252` — "A prior
  version of this test asserted the opposite (HANDOFF_LOSS), on the..."

This list is from one grep pass (`confirmed live\|confirmed 2026\|prior
version\|a prior claim\|was never live-verified\|found while diagnosing\|
previous session\|this session`), not an exhaustive audit — there are almost
certainly more instances and more patterns worth searching for (dates in
comments generally, "discovered", "root cause", "it turns out", "diagnosed",
etc.).

## Scope

This is explicitly a **quality/maintainability cleanup**, not a correctness
fix — none of the flagged comments are wrong, they're just in the wrong
place and will rot as the code around them changes without anyone updating
the historical narrative embedded in it.

## To do

- [ ] Full grep pass across `portal/`, `scripts/`, `tests/` for narrative/
      incident-history comment patterns (dates, "confirmed", "prior version",
      "this session", "discovered", "root cause", "it turns out", etc.) —
      broader than the single pass that found the examples above.
- [ ] For each hit: decide whether the narrative content is (a) genuinely
      durable and belongs in a `portal_wiki/canonical/` unit (rendered into
      the relevant doc), (b) already covered by an existing wiki unit and can
      just be trimmed/cross-referenced, or (c) truly ephemeral and can be
      deleted outright (e.g. a session-scoped debugging note with no lasting
      relevance).
- [ ] Trim each comment to durable WHY-only content (what CLAUDE.md's comment
      guidance actually asks for), moving narrative to the wiki where it adds
      real value.
- [ ] Full verification ladder: `pytest tests/unit/ -q && ruff check . &&
      ruff format --check .`, then `bash scripts/ci_local.sh`.
- [ ] `python3 scripts/doc_ledger.py status` after any doc/wiki changes.

## Definition of Done

- [ ] Comment audit complete (or explicitly scoped down with reasoning if the
      full sweep turns out to be much larger than expected — this could be a
      multi-session effort given the security module's size).
- [ ] Full verification ladder green.
- [ ] Doc ledger clean.
