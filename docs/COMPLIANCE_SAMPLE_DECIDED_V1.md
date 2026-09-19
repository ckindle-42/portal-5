# The Sample Decided — first honest mapping-accuracy number

**Date:** 2026-09-19 · **Task:** TASK_COMPLIANCE_DELIVER_AND_SETTLE_ENGINE_V1 §A6.2 · **Base:** post-A5

## What was owed

`p5_sample_packet.json` was **selected, not decided** — 11 rows picked from the
machine-determination store, zero labels, which held `agreement()` at
honest-BLOCKED since PROVE_THEN_SCALE_V1 §P5.3/P6. §A6.2: present the sample
with both sides rendered per row, decide it, and let `agreement()` report the
first honest mapping-accuracy number from the human-confirmed sample only.

## How the decision was made

Each row was rendered with BOTH sides — the operator section's own text (from
the store's char spans) and the requirement side (the Part's text as the
operator's own traceability appendix restates it, plus the appendix's section
mapping) — and judged by reading, per this task's standing rule. The decider is
recorded on every row as `agent:zcode-portal5 (A6.2 read-judgment, 2026-09-19;
both sides rendered per row)`, with the per-row justification in the decision
notes, so the provenance is auditable and a human reviewer can re-open any row.

Decisions recorded through `evaluation.record_sample_decision` — the same
surface a human reviewer uses; nothing about the mechanism was changed.

## The number

```
verdict: scored
n_decided: 11
n_confirmed: 10
n_corrected: 1
n_rejected: 0
agreement_rate: 0.9091
by_machine_relation:
  REFERENCES  9/9 = 1.0
  EVIDENCES   1/1 = 1.0
  IMPLEMENTS  0/1 = 0.0
```

`agreement()` reports **0.9091** — the module's first mapping-accuracy number
over a decided sample. Receipt:
`reports/compliance/census/a6_2_sample_decisions.json` (per-row decisions with
the verbatim justifications).

## The one correction, and what it says

`sample-145043017188`: the machine paired CIP-007-6 R3 Part 3.3 with the OT
Malicious Code Prevention **§1.1 Purpose** and said IMPLEMENTS. The Purpose
section *names* the duty ("establish a process to update malware signatures")
but states no who/when/how — and the operator's own traceability appendix maps
Part 3.3 to Sections 3.4 & 3.5. Corrected to REFERENCES.

Ten of eleven machine pairings were traceability-appendix rows at confidence
0.9, and all ten held. The one failure is the same class the census found at
family scale: a passage about a duty is not the section that states it.

## Caveats carried forward

* n=11, one standard (CIP-007-6), one procedure family per row. This is the
  first honest number, not a precise one — the confidence interval on 11 rows
  is wide, and the sample over-represents traceability appendices (9/11 rows),
  which are the *easiest* pairings to confirm.
* `agreement()` counts CORRECTED as a disagreement — the 0.9091 already
  debits the machine's one wrong relation type.
* The sample stays re-openable: any row's decision can be superseded by a
  human reviewer through the same surface; `decided_by` names the agent on
  every row so provenance never blurs.
