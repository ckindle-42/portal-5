# READING_JUDGMENT_V1 — the question was the defect

**Task:** `TASK_COMPLIANCE_READING_IS_THE_PRODUCT_V1` Phase 5
**Measured:** 2026-09-14 · builds on `THINKING_CONFOUND_V1.md`

---

## 1. What was actually wrong

The pipeline decomposed one judgment into three sealed questions, each gating
the next:

| stage | question put to the model |
|---|---|
| alignment | *"is candidate X the SAME duty as the governing Part?"* |
| council | *"does this **PRE-ANALYZED** packet satisfy the unit?"* |
| reporter | *"characterise coverage; **do not re-judge**, never reverse"* |

The failure is in the first, and it is not a model failure. Case 10's L22 reads:

> "SMEs shall complete **that** patch-applicability evaluation once every 40
> calendar days; this is the only required evaluation cadence."

That is a **cadence fragment constraining a duty stated in a sibling clause**,
not a duty. `SAME`/`DIFFERENT` has no correct answer for it. Two of three live
seats answered `DIFFERENT` *while emitting a correct 35/40 operand binding* —
a coherent response to a malformed question, not the self-contradiction D4
describes.

What followed was mechanical:

1. quorum resolves L22 to `DIFFERENT`
2. `_allowed_internal_ids` admits only `SAME` candidates, so L22 leaves the
   citable set
3. the reporter's `WEAKER_COMMITMENT` gap necessarily cites L22 — the one
   document the gap is about — and is rejected as *"off-packet or excluded
   counterevidence"*
4. `U11_ASSESSMENT_CONTRACT_FAILED` → `UNRESOLVED`, `covered: []`, `gaps: []`

**The council had already returned `PARTIAL` with `GAP`, correctly, on a 2/3
quorum.** Our own layer discarded a correct determination.

### 1.1 Why the earlier fixes were the wrong fixes

`THINKING_CONFOUND_V1.md` §4 isolated two structural triggers by single-factor
ablation: granite flips on the Part 2.1 reference, mistral flips on the `scope`
block. Both are real and both are fixed here — but removing them only perturbs a
malformed question until the seats happen to agree. Neither makes
`SAME`/`DIFFERENT` answerable for a cadence fragment. They are necessary and
they are not sufficient, and treating them as the fix was tuning around the
defect.

---

## 2. The reading architecture, measured on the same case

One pass: read the Part in full, **enumerate the duties it imposes as part of
reading it**, read the operator's material in full, judge each duty. No
candidate is ever classified on its own.

Same case, same three models, only the question changed:

| seat | old architecture | reading architecture |
|---|---|---|
| `qwen38` | `SAME` ✓ but outvoted | **4/4 correct**, 63.2 s |
| `granite4.1:30b` | `DIFFERENT` ✗ | **4/4 correct**, 55.1 s |
| `mistral-small3.2:24b` | `DIFFERENT` ✗ | verdict correct, one citation hallucinated, 52.7 s |
| **Part outcome** | **`UNRESOLVED`, `covered: []`, `gaps: []`** | **`PARTIAL` + `WEAKER_COMMITMENT` citing L22** |

Checks: `documentary_coverage == PARTIAL`; a `WEAKER_COMMITMENT` gap; the gap
cites L22 as counterevidence; A22 cited as covering.

**The two seats that "failed" read it correctly when asked to read.** The seats
were never the defect.

### 2.1 Duty count is not part of the expectation

`qwen38` enumerated two duties (activity, then cadence); `granite` enumerated
one. Both are legitimate readings and both produce the correct verdict. An early
version of the grader demanded exactly one duty and scored `qwen38` as failing —
that criterion was invented by the grader, is not in case 10's expectation, and
was removed. Duty enumeration is a reading, not a fixed decomposition, and
nothing downstream may assume a count.

### 2.2 Verification names failures without vetoing

`mistral` cited `cand-aee961b20917773` — the real id `cand-aee961b209177773`
with one digit dropped. The verification layer resolved it against the pinned
sources, failed, and recorded:

```
READING_CITATION_UNVERIFIED: duty d1 cites 'cand-aee961b20917773',
                             which is not in the packet
```

The unverified id is dropped from the emitted citation; the duty finding stands;
the verdict stands. The old layer's response to exactly this class of problem
was to void the entire assessment.

---

## 3. What the module does

`core/reading.py`:

- **`build_reading_packet`** — both sides in full. References are a separate,
  labelled block, *never* in `selectable_slice_ids` (granite's trigger, closed
  structurally). Applicability is a one-line note, not a decision surface
  (mistral's trigger, closed structurally).
- **`read_and_judge`** — one reasoning pass, then verification.
- **`verify_judgment`** — evidence verification, never verdict authority:
  - an unresolvable citation marks **that citation** unverified and names it
  - a fabricated quantity drops **that operand**, keeping the duty finding
  - `FULL` requires **every enumerated duty `COVERED` with a verified citation**
    — §5's actual rule, checkable for the first time because duties are now
    enumerated, and what settles the false-FULL family (cases 08, 16)
  - a verdict resting *entirely* on unverified citations is `UNRESOLVED`, with
    the failing citation named

14 hermetic tests, no model calls.

---

## 4. Honest limits

- **One case.** Case 10 only. Cases 19, 20 and 25 are the rest of the
  L-document family and are not yet run. The false-FULL family (08, 16) has a
  rule implemented and hermetically tested, but no live measurement.
- **Not yet wired.** `assessment.assess_part` still runs the old
  alignment → council → reporter chain. The module is proven against the failing
  case but is not on the product path, so the 26-case suite is unchanged. Wiring
  is the next step and will change the hermetic suite's shape, since those cases
  mock council and report responses that a reading pass does not make.
- **The roster is unqualified for this question.** `config/compliance/council.yaml`
  was selected by the 2026-09-06 twelve-seat judgment probe, scored on F2 for
  violation detection over a *pre-analyzed packet* — the old question. That
  evidence does not transfer to a reading task. Case 10 is suggestive (all three
  seats produced the right verdict) but one case is not a qualification.
  Re-running the probe against the reading task is work this task does not
  contain, and it should happen before the roster is called correct for the new
  architecture. `PROMOTE_POLICY: confirm` is untouched.
- **Capability is not the discriminator.** `granite4.1` and `mistral` cannot
  reason at all (HTTP 400) and both read case 10 correctly. There is no
  evidence-backed case for swapping them out — and equally none that they are
  the best available readers.
