---
id: unit-design-spine-drift-census
kind: mixed
title: "Spine drift census \u2014 binding doc prose to live code"
sources:
- type: code
  path: portal/platform/wiki/claims.py
- type: code
  path: portal/platform/wiki/drift.py
- type: code
  path: tests/unit/test_spine_drift.py
- type: code
  path: tests/unit/test_detector_precision.py
claims:
- probe: validate.checks
  pattern: '{value} validate checks'
confidence: high
tags:
- drift
- spine
- verified-v1
- wiki
created_at: 1785825842.272556
updated_at: 1785859017.192845
---

Three gates guarded the spine and none of them objected while README asserted 60
benchmark workspaces against a live 65 and 22 MCP servers against a live 21:
 `AW` passes by comparing a generated block with its own unit body, `BR` passes by
proving a new code surface is cited by *some* unit without asking whether the
citation is true, and the retired `AK` ledger check bound zero docs —
honestly, but leaving no doc-currency signal in the harness at all.
Of 567 generated blocks across 25 Tier-1 docs, 7 came from a machine-derived
`unit-fact-*` unit; the remaining 560 were authored prose with no executable link
to code. Check `BS` closes that gap, bringing the harness to 158 validate checks
(`BT` later asserting archived units stay unreachable from the live store, `BU`
the complexity-census advisory, `BX` the pending-model-verdicts backlog cap,
`BY`-`CI` the TASK_BULLY_RELATE_AND_INVESTIGATE_V1 operating/measurement
invariants, `CJ`-`CQ` the TASK_BULLY_COUSIN_RELATION_V1 cousin-relation
contract invariants, `CR`-`DA` the TASK_BULLY_UNKNOWN_COUSIN_V1 unit-level
grading/measurement invariants, `DB`-`DK` the TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1
universal-intake and honest-metrics invariants, `DL`-`DS` the
TASK_BULLY_LOOP_REINTEGRATION_V1 loop-reintegration and pyramid-of-pain
invariants, `DT`-`DZ` the TASK_BULLY_SCOREBOARD_CONFORMANCE_V1
scoreboard-conformance invariants, `EA`-`EG` the TASK_BULLY_ANALYST_LOOP_V1
analyst-verdict-loop invariants, `EH`-`EO` the TASK_BULLY_TRUTH_ACCEPTANCE_V1
truth-joined-acceptance invariants, `EP`-`EW` the TASK_BULLY_DISCOVERY_FIRST_V1
discovery-first and doc-currency invariants, `EX`-`FD` the
TASK_BULLY_CORPUS_BED_V1 corpus-bed invariants (the haystack floor, cousins
derived from a published answer key, floor/product/cost kept apart, the
answer key never reaching the grader, fit-wide/score-narrow, Lane A index
resolution, and D.4's permanent non-haystack regression); the doc-ledger `AK`
check was removed once the ledger was emptied in TASK_WIKI_ZERO_DEBT_V1).

A **claim** binds a figure in a unit body to a live probe. The claim names the
probe and a `pattern` containing `{value}`; the probe result is substituted and
the result must appear in the body. There is deliberately no second copy of the
number — an earlier draft allowed `equals: 65`, which compared the probe with
itself and passed while the body still read 60. `equals` and `contains` survive
only for structural invariants the prose describes qualitatively, such as the
backend type set becoming `[ollama, omlx]` when the oMLX backend landed.

Claims are opt-in. Prose explaining *why* a design is shaped a certain way has
nothing to assert, and demanding an assertion from it would produce exactly the
mass-stubbing this project refused when it declined to force 100% code-surface
coverage. Units whose body states a countable quantity without declaring a claim
are reported as visible debt instead, so the next units to instrument are always
known without a fuzzy signal being promoted to a failure. The signal itself is
deliberately narrow (TASK_DETECTOR_PRECISION_V1): a figure is only a count when
the noun is plural and the number is not preceded by a digit or a dot, fenced
terminal excerpts are stripped, and the `unit-fact-*` / `unit-T*-signature`
families are skipped because their figures regenerate from live config or the
MITRE mapping and are already gated by `AW`. `tests/unit/test_detector_precision.py`
locks the narrowing.

The census carried a second axis until P0 (`TASK_BULLY_P0_SPINE_REDUCTION_V1`
A1) deleted it whole: **pin health** classified every unit that cited a
repo-local path against its `last_generated_commit` pin. 461 units shipped
pinned to `05e42ec2`, a SHA absent from all 1904 commits — the pin resolving
to a real commit never proved the body was still true, so it added no
truth-checking `claims` didn't already provide, while forcing a two-commit
re-pin dance on every fact edit (`scripts/repin_stale.py`, now removed). There
is no pin axis to restore. **Doc path references** is the axis P0 kept
alongside `claims`: it reports repo-relative paths named in Tier-1 docs that do
not exist and are not gitignored — `portal/<workspace-or-persona>` is
suppressed as an OpenAI-style served model id by checking the live roster (so
retired ids such as `portal/auto-agentic-ornith` are still reported while live
ones are not), and a path git itself reports as intentionally untracked (`git
check-ignore`, e.g. a scratch task file under `coding_task/` or a
harness-written directory like `results/candidates/`) is not a broken
reference — it was never going to exist in any checkout, so its absence is
not drift.

`TASK_WIKI_ZERO_DEBT_V1` deleted `config/spine_drift_baseline.yaml`: claims
and doc refs are both absolute now, with nothing left to ratchet or tolerate.
The census is re-runnable outside CI as `python3 -m portal_wiki drift`, which
exits non-zero on any claim violation or any doc-ref drift.

## Operational note: a fact change is a single commit (post-P0)

Before P0, `BS` ran at push and hard-failed the moment HEAD advanced past a
unit's pin while a cited path had moved — including the commit that made the
fact change itself, since a unit could not be pinned to a hash that did not
exist yet. That forced the functional commit and a separate
`chore(spine): re-pin units stale after <change>` commit before every push.
P0 A1 removed the pin outright, so there is no second commit: editing a
fact-unit's live-config-derived body and landing it is one commit, full stop.

## Why

The census exists because the three prior gates certified a doc's block
against its own unit body or proved a code surface had *some* citation —
never that the cited prose was true — which is how README carried a wrong
workspace count with every gate green. The mechanism is grounded in the
code it describes: `claims.py` defines the probes and the `{value}`
pattern contract, `drift.py` classifies broken doc path references
(delegating "is this path allowed to be missing" to `git check-ignore`
rather than a hand-maintained allowlist, so a renamed or newly-ignored path
never needs a second update to stay accurate), and
`tests/unit/test_spine_drift.py` and `tests/unit/test_detector_precision.py`
lock the behavior. The declared claim on
`validate.checks` keeps the unit's own count honest, and the axis vocabulary
is re-derivable by re-running the census rather than trusting this prose.
