# A6.1 — instruction ablation for gemma4's one failure class

**Date:** 2026-09-20 · **Task:** TASK_COMPLIANCE_DELIVER_AND_SETTLE_ENGINE_V1 §A6.1

gemma4's two batch failures are one class — inference over material it correctly
retrieved: the `choice` answer quotes the operator policy joining Part 2.3's
three permitted actions with "and" where the Part grants one-of-three ("or")
without flagging the conflict, and the `no_operator_side` answer treats the
policy's verbatim restatement of Part 5.2 as demonstration of implementation.
Two candidate standing-instruction additions, tried SEPARATELY, each measured
on ALL six cases (never tuned against the one case that failed), via the
`extra_instruction` hook in `reading_material.render()` — it rides after the
fixed body, so no byte of the shared prefix moves.

## Result

| variant | target case | outcome | other five cells |
|---|---|---|---|
| `conjunction` | choice | **FIXED** — flags the conflict explicitly: the policy's "**and**" *«effectively requir[es] the entity to perform both actions rather than choosing one»*, while distinguishing the procedure's correct *"one of the following actions shall be taken"*; concludes the policy text is the defect | no regressions; the check also usefully hardened `read_check` (verifies by quoting both conjunctions) and `parent` (names the policy "and" as a clerical error against the or-reading both other texts support) |
| `restatement` | no_operator_side | **NOT FIXED** — still names the CIP Cyber Security Policy's restatement as the document that *«shows that the operator performs this duty»*; the added sentence did not move the answer | no regressions; `choice` drifted from wrong ("fully using") to cautious-uncertain — more honest, not fixed |

Receipts: `reports/compliance/prove_then_scale/p1/cell_gemma4_*__{conjunction,restatement}.json`;
baseline: the §P1 `cell_gemma4_*.json` set (4/6).

## Reading

* The conjunction failure yields to a one-sentence instruction — it is an
  attention default, not a capability limit.
* The restatement failure does not yield to its instruction — telling the seat
  *that* restatements are not evidence does not stop it treating the policy as
  the implementing document. That failure is positional (which document to
  cite for "shows we do it"), and the fix likely lives in the question's shape
  or in citation-time verification, not in a standing rule.

## Recommendation (recorded, not applied)

Adopt the `conjunction` sentence into the standing instruction of the map/read
prompts as a follow-up product change (it fixed its target with no observed
regression across the six cases). The `restatement` sentence: do not adopt;
re-approach via the follow-up-turn material tool or citation-resolution checks
(the A4 v2.3 mechanism), which catch the wrong-document citation
deterministically instead of hoping the model self-polices.
