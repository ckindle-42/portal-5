# TASK_COMPLIANCE_READING_IS_THE_PRODUCT_V1 — resume point, 2026-09-14

**Branch:** `main` · **Head at handoff:** `bacc850c`
**Governing task:** `coding_task/TASK_COMPLIANCE_READING_IS_THE_PRODUCT_V1.md`

Read this first, then the three reports it points at. Everything below is
measured, not assumed; where something was not measured it says so.

---

## 1. The headline: the task's central hypothesis was wrong

The task's thesis was that compliance assessment fails because *reasoning is
disabled at every model call site*. **That is not why it fails**, and the
evidence is unambiguous.

On the real case-10 alignment packet, one variable, same prompt and model:

| `think` | elapsed | thinking | result |
|---|---:|---:|---|
| `false` | 52 s | 0 | correct |
| `low` | 180 s | 5,206 ch | correct |
| `medium` | 224 s | 8,710 ch | correct |
| `true` (= `xhigh`) | 683 s | 34,097 ch | correct |

Four settings, one answer, up to 13× the cost.

**What actually failed was the question being asked.** The pipeline decomposed
one judgment into three sealed sub-questions, each gating the next, and the first
one — *"is candidate X the SAME duty as the governing Part?"* — is malformed for
a clause that is not a duty. Case 10's `L22` is a cadence fragment (*"that
patch-applicability evaluation ... once every 40 calendar days"*) constraining a
duty stated in a sibling clause. `SAME`/`DIFFERENT` has no correct answer for it,
so two of three seats answered `DIFFERENT` **while emitting a correct 35/40
binding** — coherent, not self-contradictory. Quorum then struck `L22` from the
citable set, the reporter's gap necessarily cited `L22`, that was rejected as
off-packet, and the Part returned `UNRESOLVED` with empty `covered` and `gaps` —
**discarding a council determination of PARTIAL/GAP that was already correct**.

Consequence for the task document: **D4 is not a model defect** and should not be
treated as one. The task's framing of it as a "self-contradictory response" is
wrong.

## 2. What landed

| phase | state |
|---|---|
| 0 — discovery | **done** (`d24f0649`) |
| 1 — unblock CI | **done** (`efc00c10`) |
| 2 — measure the confound | **done, redesigned** (`f0af27e7`, `7e79c454`) |
| 3 — reasoning as a channel | **done, but it is not the fix** (`f0af27e7`) |
| 4 — packet carries the standard | **partial** — see §3 |
| 5 — the reading judgment | **done and wired** (`b1612cd2`, `5f5f93b8`) |
| 6 — demote the vetoes | **partial** — D1 only |
| 7–10 | **not started** |

Live evidence: the whole L-document family (10, 19, 20, 25) now reads correctly
on all three seats — 12/12 correct `documentary_coverage`, all four cases
carrying at the 2-of-3 quorum, where the old architecture returned `UNRESOLVED`
for every one (`5ae8ffe1`).

Hermetic: 26/26 acceptance cases, 1848 unit tests, ruff and mypy clean. **No gold
label moved and no case expectation was edited.**

### Method note for whoever continues

The original Phase 2 design — ten cases × two arms, live — was stopped after one
case on the operator's instruction: *prove the concept on a small problem before
burning the time*. That was correct and it should be the default here. What
replaced it, **byte-exact replay of stored traces**, reproduces a live failure in
81 seconds instead of hours:

```sh
uv run python scripts/replay_compliance_trace.py --trace <trace-dir>/model-002.json --think false
uv run python scripts/replay_compliance_reading_family.py 10,19,20,25
```

## 3. What is NOT done — verified against HEAD, not assumed

**Phase 4.1 — `measure_text` still reaches nothing in production.** This is the
most misleading gap, because the reading packet *looks* like it carries Measures:
`build_reading_packet` reads `getattr(governing, "measures", "")`. But
`GoverningBundle` has **no `measures` field** and `resolve_governing_bundle` never
populates one, so in production that value is **always `""`**. The live family
replay set it by hand on the request. To close it: add `measures` to
`GoverningBundle`, populate it in `assessment_source.resolve_governing_bundle`
from `node.measure_text`, and carry it as a `SourceSlice` with `role="measure"`
so it is citable. 99 of 254 register nodes carry Measures text.

**Phase 4.2 / 4.3 — untouched.** The council `_SEAT_SYSTEM` still opens *"You
receive a PRE-ANALYZED problem"* with candidates *"already checked"*, still caps
`rationale` at `"one sentence"`, and still has the `ABSENT` rule that asks a seat
to certify corpus completeness it cannot see. `gate.py:94-95` still says the
packet is *"a pre-analyzed problem, never raw text"*. The council is now a
cross-check rather than the verdict authority, so this is lower-stakes than it
was — but the text is still wrong.

**Phase 6 — only D1 closed.** `gate._substantive` promoted to `is_substantive`
and the assessment layer now uses it, so an immaterial UNKNOWN no longer vetoes a
Part. Still open at HEAD: D2 (`obligation_alignment.py:300`), D3 (`:472`), D4
(`:336`), D5 (`_text_has_quantity` whitespace). **Re-examine D4 before
implementing it** — §1 says the behaviour it calls a defect is a reasonable
answer to a malformed question, and that question is no longer on the verdict
path.

**Phase 7 — D6 open.** `council.py:173` is still
`r == a.lower() or r in a.lower() or a.lower() in r`. Substring matching, in the
module whose thesis is *not grep*.

**Phases 8, 9, 10 — not started.** Case 23's injection point, the interpretive
corpus ingest, and the live re-qualification.

## 4. Next steps, in the order I would take them

1. **Re-run the new question against the models** (the operator's stated next
   step). The reading task is a *different question* from the one the roster was
   qualified on — the 2026-09-06 twelve-seat probe scored F2 for violation
   detection over a pre-analyzed packet. That evidence does not transfer. Extend
   `scripts/replay_compliance_reading_family.py` beyond the L-doc family and run
   **three observations per case**; case 02/04's history shows single runs
   confound stable failure with sampling variance.
2. **Replace the mistral seat** —
   `docs/TASK_COMPLIANCE_READING_SEAT_REPLACEMENT_V1.md`. Run **D2 first**: it is
   a quantization control, not a swap, and if `Magistral-Small-2509 Q8_0` fixes
   citation attachment the finding generalises to every seat and costs nothing.
3. **Close Phase 4.1** (Measures into `GoverningBundle`) — small, mechanical, and
   it is the "intent" half of the task's own problem statement.
4. **The false-FULL family (08, 16) has a rule but no live measurement.** The
   `FULL` rule is implemented in `reading._derive_coverage` and hermetically
   tested; it has never been run against a live model.
5. **Phase 10's real question, which is the only one that matters:**
   `compliance_gaps(requirement="CIP-007-6 R2")` against the live operator
   corpus. The failure that started all of this was not a test failure — it was
   that call returning PARTIAL for all four Parts against a corpus containing a
   dedicated patch-management procedure. **If it still does, the task did not
   succeed regardless of the suite score.**

## 5. Traps — each of these cost real time, do not re-pay them

- **An omitted `think` key is not suppression.** It hands control to the chat
  template, and a Qwen3/DeepSeek/GLM template opens `<think>` anyway. Two arms
  came back byte-identical (34,097 thinking chars, `eval_count` 7996) — the
  signature of one request run twice, not a null result. Pinned by
  `test_the_think_key_is_never_omitted`.
- **`think: true` is not "reasoning on", it is maximum effort.** This roster's
  template reads `reasoning_effort|default('xhigh')`. `DEFAULT_EFFORT` is `False`
  by measurement; raising it anywhere needs a measurement *on that call site*.
- **A `store=` parameter is not an injection seam until an empty value survives
  it.** `MappingStore` defines `__len__`, so an empty store was falsy and
  `store or MappingStore()` silently swapped in the ambient 1067-row store. This
  is what `P5-CI-DRAFT-REVISIONS-FLAKE-001` actually was.
- **Check your harness before blaming the model.** The first case-20 result was
  granite 2/6 and mistral 2/6; the cause was that my harness supplied no boundary
  receipt, so my own OMISSION rule voided two correct readings. I reported it
  twice before checking.
- **Duty count is not part of any expectation.** qwen38 reads case 10 as two
  duties, granite as one; both are correct. Nothing downstream may assume a
  decomposition, and a grader that demands one is wrong (mine was).
- **The hermetic 26-case suite proves plumbing, not reading.** Its fixture
  responses are derived from each case's own report spec, so they simulate a
  correct read by construction. Only live replay measures reading.

## 6. Reports

- `reports/compliance/READING_IS_PRODUCT_V1_D0.md` — discovery, with three
  measured corrections to the task document
- `reports/compliance/THINKING_CONFOUND_V1.md` — why reasoning is not the defect
- `reports/compliance/READING_JUDGMENT_V1.md` — the architecture and its proof
- `reports/compliance/LDOC_FAMILY_LIVE_REPLAY.md` — the live family result
- `docs/TASK_COMPLIANCE_READING_SEAT_REPLACEMENT_V1.md` — the seat diagnosis
