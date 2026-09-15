# THINKING_CONFOUND_V1 — what actually breaks the reading

**Task:** `TASK_COMPLIANCE_READING_IS_THE_PRODUCT_V1` Phase 2
**Measured:** 2026-09-14 · baseline HEAD `2b666477`, Phase 1 at `efc00c10`
**Method changed from the task's:** the planned ten-case × two-arm live sweep was
stopped after one case on the operator's instruction — *prove the concept on a
small problem before burning the time*. What replaced it is narrower and
strictly more informative: a byte-exact replay of the stored live packets.

---

## Headline

**Reasoning suppression is not what breaks the compliance reading.** The task's
central hypothesis does not survive measurement. What breaks it is the
**alignment packet carrying material that is not duty-identity evidence** — and
that defect appears nowhere in the task's D1–D7 list.

Phases 3–5 still land (the architecture argument is independent and correct),
but the Phase 2 result must be read as it is, not as the task predicted it.

---

## 1. Two defects in the instrument, found before any conclusion was drawn

Both would have produced a confident, false Phase 2 result.

**1.1 — An omitted `think` key is not suppression.** The first transport
expressed "do not reason" by omitting `think` from the payload. On this model
that hands control to the chat template, which opens `<think>` by default. The
two arms returned **byte-identical** responses:

| arm | thinking | eval_count | elapsed | L22 |
|---|---:|---:|---:|---|
| "A" (`think` omitted) | 34097 ch | 7996 | 682.6 s | SAME |
| B (`think: true`) | 34097 ch | 7996 | 663.5 s | SAME |

Identical output is the signature of one request run twice, not of a null
effect. A ten-case sweep on this instrument would have reported "reasoning
changes nothing" — a false negative that would have looked entirely plausible
and would have been believed.

Fixed: `think` is now always sent as an explicit value, including on the
post-400 retry. Pinned by `test_the_think_key_is_never_omitted`, which carries
this measurement as its rationale.

**1.2 — `think: true` silently meant maximum effort.** The Qwen3.8 template
reads `reasoning_effort|default('xhigh')` and supports `xhigh`/`medium`/`low`.
So "restore reasoning" was buying the most expensive setting the model has, and
the 683-second call was an artefact of that default rather than an inherent cost
of reading. The transport now carries a level (`bool | str`) instead of
coercing to a bool.

---

## 2. Reasoning does not change this reading, at any effort level

Same packet, same prompt, same model, one variable.

| `think` | elapsed | thinking | eval | A22 | L22 | binding |
|---|---:|---:|---:|---|---|---|
| `false` | **52.4 s** | 0 | 639 | SAME ✓ | SAME ✓ | 35/40 ✓ |
| `low` | 179.5 s | 5206 ch | 1943 | SAME ✓ | SAME ✓ | 35/40 ✓ |
| `medium` | 224.0 s | 8710 ch | 2738 | SAME ✓ | SAME ✓ | 35/40 ✓ |
| `true` (= `xhigh`) | **683 s** | 34097 ch | 7996 | SAME ✓ | SAME ✓ | 35/40 ✓ |

Identical correct answers. Reasoning costs 3.4×–13× the wall time and buys
nothing on this reading. **Attribution for the L-document family: not reasoning
suppression.**

Operational consequence: if a live re-qualification is run with `think: true`
on the current roster, it costs ~13× arm A for no measured accuracy gain. The
defensible default is `false` or `low`, not `true`.

---

## 3. The failure is context-triggered, not model capability

The same two "failing" seats read a *hand-built* packet — same governing text,
same candidate texts — **correctly**:

| model | isolated packet | live packet |
|---|---|---|
| `qwen38` | SAME ✓ | SAME ✓ |
| `granite4.1:30b` | **SAME ✓** | **DIFFERENT ✗** |
| `mistral-small3.2:24b` | **SAME ✓** | **DIFFERENT ✗** |

So "the non-reasoning seats can't read" is also wrong, and swapping the roster
would not have addressed the cause. The trigger is in the real packet.

A byte-exact replay harness (`system`/`input` restored from the stored trace,
both sha256-verified before use) reproduces the live failure deterministically
in **81 seconds**:

```
RECORDED     81.0s  a4a03040=SAME  2bb2bef4=DIFFERENT[(35, 40)]
think:false  81.7s  a4a03040=SAME  2bb2bef4=DIFFERENT[(35, 40)]
```

This replaces multi-hour sweeps for diagnosis and should be the first
instrument reached for in any future compliance-reading investigation.

---

## 4. Root cause: the packet carries non-duty-identity material

Single-factor ablation on the real packet, each variant changing exactly one
structural element:

**granite4.1:30b**

| variant | L22 |
|---|---|
| baseline (unmodified) | DIFFERENT ✗ |
| readable candidate ids | DIFFERENT ✗ |
| **no Part 2.1 reference** | **SAME ✓** |
| no R2 lead-in slice | DIFFERENT ✗ |
| no scope block | DIFFERENT ✗ |
| no filename locator | DIFFERENT ✗ |

**mistral-small3.2:24b**

| variant | L22 |
|---|---|
| baseline (unmodified) | DIFFERENT ✗ |
| readable candidate ids | DIFFERENT ✗ |
| no Part 2.1 reference | DIFFERENT ✗ |
| no R2 lead-in slice | DIFFERENT ✗ |
| **no scope block** | **SAME ✓** |
| minimal (all ablations) | SAME ✓ |

Two seats, two different distractors, one architectural cause:

- **The Part 2.1 reference** is a *different duty* ("a patch management process
  for tracking, **evaluating**, and installing…"). It is placed in
  `governing.source_slices` **and** in `selectable_slice_ids`, so it presents as
  co-equal governing evidence rather than as context for resolving Part 2.2's
  terms. L22's "that patch-applicability evaluation" then anchors to Part 2.1's
  "evaluating" instead of Part 2.2's 35-day cadence — at which point
  `DIFFERENT` is a *correct* answer to the question the packet actually asked.
- **The scope block** (`impact_present`, `has_erc`, `has_control_center`, …) is
  applicability data. The alignment task's only question is duty identity — the
  prompt opens "Read duty identity, never satisfaction or confidence." Scope
  cannot bear on duty identity and serves only as a distractor.

Neither is a model defect. Both are packet-construction defects, and they belong
in **Phase 4**, which is the phase that owns what the reader is given.

---

## 5. The full case-10 chain, end to end

Reconstructed from `case-10/run-0.json` and `trace-0/`, not inferred:

1. Seats vote on L22 — `qwen38` SAME ✓, `granite41` DIFFERENT, `mistral`
   DIFFERENT — **all three emitting a valid 35/40 `max_interval` binding.** A
   record that binds a matched-duty operand while denying duty identity is the
   **D4** self-contradiction, and here it is confirmed live in two seats.
2. 2-of-3 quorum ⇒ L22's relation resolves to `DIFFERENT`.
3. `_allowed_internal_ids` (`assessment_report.py:483`) admits only
   `relation == "SAME"` candidates, so L22's slice ids are struck from the
   reporter's citable set.
4. The reporter correctly finds the `WEAKER_COMMITMENT` gap — whose
   counterevidence **is** L22 — and is rejected at `assessment_report.py:347`:
   *"gap entry cites an off-packet or excluded counterevidence slice"*.
5. `U11_ASSESSMENT_CONTRACT_FAILED` ⇒ `documentary_coverage: UNRESOLVED`,
   `covered: []`, `gaps: []`.

**The council had already returned `PARTIAL` with `GAP`, correctly, on a 2/3
quorum.** Our own layer then discarded a correct determination because the
reporter cited the one document the gap is about.

### 5.1 — A fix-ordering finding the task does not anticipate

Phase 6's D4 patch rejects a self-contradictory record rather than flipping it.
Applied here it would drop *both* wrong seats, leaving one valid SAME vote
against a required quorum of `ceil(0.66 × 3) = 2` — which yields `UNKNOWN`, not
`SAME`, and case 10 still would not reach its expected `PARTIAL`.

**So D4 is containment, not the cure.** Case 10 needs the Phase 4 packet fix, so
that the seats read the question they were meant to be asked and vote SAME on
the merits. Landing Phase 6 alone and re-running the suite would show little
movement and would invite the wrong conclusion about why.

---

## 6. Dispositions

| failure family | task's attribution | measured attribution |
|---|---|---|
| excluded-L-doc (10, 19, 20, 25) | reasoning suppression | **packet contamination** (§4), with D4 as containment |
| fabricated-binding (02, 04, 05, 06, 15) | reasoning suppression | not measured — case 02 passed live (FULL, 7 calls, 435 s) |
| false-FULL (08, 16) | reasoning suppression | not measured |
| corpus-breadth omission | corpus | unchanged; Phase 9 still applies |

Only the L-document family was measured. The other three keep their existing
dispositions, and this report does not claim otherwise.

---

## 7. What this changes

1. **Phase 3 lands on its own merits, not on a measured gain.** Reasoning as a
   first-class channel with an explicit downgrade record is the right
   architecture, and the two instrument defects it exposed are worth the change
   by themselves. But it does not move this family, and the report says so.
2. **Phase 4 is promoted to the highest-value phase.** It already owns the
   packet; it now has a measured, single-factor root cause to fix — remove
   non-duty-identity material from the alignment packet, and stop presenting
   reference-closure duties as selectable governing evidence.
3. **The default effort level should be `false` or `low`, never `true`.** On
   this roster `true` means `xhigh`: 13× the cost for no measured gain.
4. **Diagnosis moves to trace replay.** 81 seconds and byte-exact, versus hours
   and non-reproducible.

## 8. Honest limits

- One case, one Part, one candidate pair. Enough to **refute** the reasoning
  hypothesis for this family; not enough to confirm the packet fix generalises.
  The ablation must be repeated on 19, 20 and 25 before the family is called.
- Arm A of the original design was stopped after case 02 (PASS, FULL, 7 calls,
  435 s). The nine remaining cases were not run, so no per-case A/B table exists
  and none is presented.
- The mid-run edit question: Phase 3's files were edited on disk while arm A's
  process was live. CPython resolves already-imported modules from
  `sys.modules` and never re-reads them, and the only lazy import on that path
  (`council._ollama_seat` inside `explain`) resolves from `sys.modules` too, so
  arm A ran entirely on pre-Phase-3 code. Case 02's result is recorded on that
  basis.
- `granite4.1:30b` and `mistral-small3.2:24b` cannot reason at all (HTTP 400).
  Any future "reasoning restored" claim covers **one of three** council seats
  until the operator decides otherwise. `PROMOTE_POLICY: confirm` is untouched
  by this report.
