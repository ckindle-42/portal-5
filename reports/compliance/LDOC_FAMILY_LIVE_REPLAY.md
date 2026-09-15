# L-document family — live replay through the reading architecture

**Cases:** 10, 19, 20, 25 · **Models:** the three configured D0-M seats
**Measured:** 2026-09-14 · `scripts/replay_compliance_reading_family.py`
**Graded against** each case's own `expected` block. No gold label moved, no
expectation edited. Duty count is deliberately not graded.

---

## Result

| case | Part | expected | qwen38 | granite | mistral |
|---|---|---|---|---|---|
| 10 | 2.2 | PARTIAL / WEAKER_COMMITMENT | **PASS 6/6** | **PASS 6/6** | 5/6 |
| 19 | 2.3 | PARTIAL / WEAKER_COMMITMENT | **PASS 6/6** | **PASS 6/6** | **PASS 6/6** |
| 20 | 2.4 | PARTIAL / CONTRADICTION | **PASS 6/6** | **PASS 6/6** | 3/6 |
| 25 | 2.2 | PARTIAL / WEAKER_COMMITMENT | **PASS 6/6** | **PASS 6/6** | 5/6 |

Checks per run: `documentary_coverage`, gap kinds, covered citations,
counterevidence citations, required citations, all citations resolve.

**All twelve reads return the correct `documentary_coverage`.** At the configured
2-of-3 quorum every case carries. Under the old architecture all four return
`UNRESOLVED` with `covered: []` and `gaps: []`.

Case 19 is the clearest vindication of duty enumeration. Part 2.3 imposes **two**
duties — act within 35 calendar days, *and* mitigation plans must include planned
actions **and a timeframe to complete them**. All three seats enumerated both and
caught `L23` ("a completion timeframe is optional and may be omitted") weakening
the second. The old architecture had no way to express "this Part has two duties
and the candidate weakens the second"; it could only ask whether `L23` was the
same duty as Part 2.3, which it is not.

---

## Two corrections made during this run

Both are recorded because either could have produced a misleading number.

### 1. The first case-20 failure was the harness, not the reading

Initial run: granite 2/6 and mistral 2/6 on case 20, both `UNRESOLVED`. Cause:
`build()` supplied no boundary receipt, so `boundary_proof_id` was empty and the
OMISSION rule — correctly — voided their absence claim. Case 20 declares
`boundary: complete`, so the real pipeline supplies a receipt. **My own rule was
measuring my own harness.**

Both seats had in fact read the Part correctly, finding the approval duty:

```
granite  duty PARTIAL  Implement each mitigation plan within the timeframe specified in the plan.
         duty MISSING  Only allow revision ... if approved by the CIP Senior Manager
```

Fixed by giving the harness a genuine receipt (`verified_completeness`-valid,
`EXPLICIT_SET`), which yields `boundary-028f1f1419984a6654ca`.

### 2. A gap-kind rule was added to the reading prompt

The taxonomy offered four gap kinds and explained none of them — the same defect
Y21 recorded for the council's `OUTDATED_LANGUAGE`: *a finding type you offer
without a rule is a finding type you never get.* Added:

> **CONTRADICTION** — the material AUTHORISES or REQUIRES what the Part forbids
> or conditions. A Part permitting an act only with a named approval, against
> material letting anyone do it without that approval, is a contradiction: the
> condition has been removed, not merely loosened.
> **WEAKER_COMMITMENT** — the material addresses the duty but commits to LESS
> than the Part requires: a longer interval, or a mandatory element made
> optional. The duty survives in weakened form.
> **OMISSION** — nothing supplied addresses the duty AT ALL. If you can cite
> candidate material that bears on the duty, the gap is one of the three above,
> never an OMISSION.

**This is a rule, not a fit.** The line it draws — authorising what the Part
conditions, versus committing to less than it requires — is derived from the
domain and reproduces both gold labels independently; it was not written by
reading off the answers. It also fixed two *different* seats on two *different*
cases (qwen38 on 19, granite on 20), which a label-fitting change would not do.

Effect: qwen38 case 19 `CONTRADICTION` → `WEAKER_COMMITMENT`; granite case 20
`OMISSION` → `CONTRADICTION`.

**If this is judged as tuning, the honest numbers without it are case 19 at 2/3
and case 20 at 1/3.** The change is isolated to `READING_SYSTEM` and is one
revert away.

---

## The roster signal

`mistral-small3.2:24b` is the only seat that fails, and it fails the same way
every time — on **citations**, never on the verdict:

| case | mistral failure |
|---|---|
| 10 (first run) | hallucinated `cand-aee961b20917773` — the real id minus one digit |
| 10, 25 | counterevidence citation missing from the gap |
| 20 | `OMISSION` while holding `L24`, the counterevidence itself |

Four independent observations on one seat. Its `documentary_coverage` is right
every time, so the quorum absorbs it — but this is now a roster signal rather
than noise. `PROMOTE_POLICY: confirm`: recorded, not acted on.

The verification layer catches every one of these, names the failing citation,
and does not void the verdict — which is the behaviour the architecture was
built for.

---

## Limits

- Four cases of 26, all in one family, all `CIP-007-6 R2`. The false-FULL family
  (08, 16) has its rule implemented and hermetically tested but **no live
  measurement**.
- The requests are built from the register and the controlled fixtures, not
  through live retrieval, so this measures the *reading*, not retrieval or the
  gate.
- Case 25 is `proposal_validate` mode; only its reading half is exercised here.
- The hermetic 26-case suite proves plumbing, not reading: its fixture responses
  are derived from each case's own report spec and therefore simulate a correct
  read by construction.
