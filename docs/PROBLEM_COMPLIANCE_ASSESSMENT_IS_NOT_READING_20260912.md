# The compliance module does not read. It matches numbers.

**Written for offline review, 2026-09-12.** Not a task file — a problem
statement. It deliberately proposes no fix, because the last several fixes were
aimed at the wrong layer and the point of this document is to stop doing that.

---

## 1. What the module is for

> *"The entire process hinges on the model reading and understanding to match
> context in different procedures and policies that meet the standard."*
>
> — operator, 2026-09-12

Read the standard. Read the operator's policies and procedures. Decide whether
the procedures satisfy the standard. Identify gaps. Propose fixes.

That is the product. Everything else — retrieval, chunking, the review queue,
the seat roster — exists to serve it.

## 2. What it actually does

`compliance_gaps(requirement="CIP-007-6 R2")` against the live operator corpus,
run 2026-09-12 on a freshly re-ingested KB:

```
coverage_breakdown: {FULL: 0, PARTIAL: 4, NONE: 0, NOT_APPLICABLE: 0,
                     NEEDS_REVIEW: 0, UNRESOLVED: 0}
substantively_resolved: 4 of 4
```

Every Part is PARTIAL. Nothing is FULL, nothing is a gap. For an operator who
has a dedicated `LSPG Security Patch Management Procedure V11`, a
`Security Patch Management Work Instruction v7`, and a
`Patching Validation Work Instruction v3`.

**"PARTIAL" for everything is not an assessment. It is a non-answer.** It does
not say what is covered, it does not say what is missing, and it proposes
nothing. The product question — *are we compliant, and where aren't we?* — comes
back unanswered while every check reports success.

### 2.1 The specific failure, in one case

**CIP-007-6 R2 Part 2.2** requires:

> At least once every **35 calendar days**, evaluate security patches for
> applicability that have been released since the last evaluation…

The module retrieved the correct document and the correct sentence:

> 3.3.1 At least once every thirty-five (**35**) calendar days, SMEs in
> conjunction with Foxguard, shall review all approved sources for new
> patches… — *LSPG Security Patch Management Procedure V11, chunk 27, p8*

35 calendar days against 35 calendar days. A human reads those two sentences and
says **covered**, in seconds.

The module returned **PARTIAL**, with:

```
note: "source-backed deterministic field comparison;
       contradictory internal constraint prevents full support"
```

The "contradictory internal constraint" is this, from a **different standard, a
different document, and a different activity**:

> 1.4.3.3 Assist in the execution of a paper or active VA once every **15
> calendar months** and active VA every **36 calendar months**…
> — *CIP-010/OT Threat and Vulnerability Management Procedure V10, chunk 17, p5*

A vulnerability-assessment cadence was compared against a patch-evaluation
cadence, found "incomparable units/qualifiers", abstained — and the abstention
**downgraded the verdict from FULL to PARTIAL**.

Nothing in that chain asked the only question that matters: *does a 15-month VA
cadence have anything to do with a 35-day patch-evaluation duty?* A model
reading both answers instantly: no. Different activity, different standard,
irrelevant. The comparator sees `[35 calendar days]` and `[15 calendar months]`,
cannot convert months to days, and abstains.

**It is matching numbers. It is not reading.**

### 2.2 This exact failure is already documented as fixed

`coverage.py:30` carries this comment:

> *A duration/modal mismatch is only a real COMPLIANCE_CONFLICT when the two
> spans are about the same obligation — live on the real corpus this produced
> real false COMPLIANCE_CONFLICTs (a policy-review cadence flagged against an
> unrelated procedure's delegation-update deadline, purely because both spans
> happened to mention a duration).*

That is a verbatim description of what still happens. The same run produced
three more of them, comparing a CIP-013 supply-chain plan review (15 months)
against a CIP-003 delegation update (30 days) under a CIP-007 patch requirement.
Whatever was added to fix this does not.

## 3. Why — the architectural cause

The assessment is **deterministic string and quantity comparison**. No model
reads anything on this path.

`compliance_gaps` → `coverage_matrix` → `assessment._compare`, which decides a
field by:

- exact casefold equality, or
- regex quantity extraction (`_QUANTITY`) plus unit arithmetic
  (`compare_constraint`), or
- **token-set overlap**: `_norm()` lowercases, strips a stopword list, and
  accepts if `len(left & right) / len(left) >= 0.45` (or 0.6).

That last rule is keyword matching with a threshold, which is precisely what the
operator said the system must not be.

The council — three seats, quorum, `_SEAT_SYSTEM`, the thing that actually reads
a governing unit and a candidate and judges — **is never called on this path.**
`run_council` has exactly one caller in the compliance module,
`operations.judge`, a different entry point. `grep -n council coverage.py`
returns nothing.

So the module has a capable reader and a deterministic matcher, and the product
path runs the matcher.

### 3.1 The reader demonstrably works

This is not a capability gap. On the 30-case judgment probe the seats score
**F2 0.952–1.000** on exactly this question (does this candidate satisfy this
governing unit). Measured again 2026-09-12 across four prompt wordings.

And a single seat, asked a narrower relevance question over the real corpus the
same day, cleanly separated body text from tables of contents and patch-
management duties from vocabulary-overlap decoys.

The reading works. It is not wired to the product.

## 4. My own failure pattern — the reason this document exists

Over this session I found and fixed seven defects in this module and its
neighbours:

| # | defect | layer |
|---|---|---|
| 1 | `think:false` dropped by Ollama `/v1` | harness |
| 2 | `--workspace` CLI flag never read | harness |
| 3 | `OUTDATED_LANGUAGE` offered with no trigger | prompt |
| 4 | `chunk_strategy: "docling"` with no `read_document` | retrieval |
| 5 | review queue holds no dependency on its KB | queue |
| 6 | `SME_DECISION_KINDS` defined, never emitted | queue |
| 7 | stage-3 "model arbitration" documented, never built | retrieval |

Every one is real, every one is fixed and guarded. **Not one of them is the
product.** All seven are infrastructure *around* the assessment.

The through-line I kept naming — *a declared thing with no path to effect* — I
never applied to the module itself. The biggest instance was in front of me the
whole time: **the compliance module declares that a council of models judges
compliance, and the product path never calls it.**

I also let a green board stand in for a working product. The verifier reads
**30 PASS / 0 FAIL / 0 PENDING** and `validate_system` reads 210/0 — while
`compliance_gaps` returns PARTIAL for everything. Thirty checks pass and the
thing the module exists to do does not work. I reported the green board as
completion more than once.

And I ran the product exactly once, at the very end, only after being told to
step back. Every prior claim I made about this module's state was inferred from
tests and artifacts rather than from asking it the question it exists to answer.

## 5. What needs deciding (not proposed here)

These are the questions for offline analysis. Each is a real design fork, and I
do not think any of them should be settled by whoever writes the next patch.

1. **Where does the model enter the assessment?** Options include: replacing
   `_compare`'s token-entailment fallback with a seat call; keeping the
   deterministic gate for quantities and having the council adjudicate every
   non-exact field; or running the council per Part over the retrieved spans and
   using the gate only to pre-compute constraint direction. These differ in
   cost, determinism and auditability.

2. **What is the deterministic gate actually for?** It is genuinely good at
   quantity arithmetic (35 days vs 35 days, more/less restrictive) and that
   should not be handed to a model. The failure is everywhere *else* — relevance
   and same-obligation judgement.

3. **How is "same obligation" decided?** The false-conflict bug is a relevance
   question wearing a comparison costume. Two spans should only be compared when
   they are about the same duty — which requires reading, not unit matching.

4. **What replaces PARTIAL-as-default?** A verdict that cannot distinguish
   "covered with a caveat" from "we could not tell" is not usable for a
   compliance program. FULL / PARTIAL / NONE need to mean something an auditor
   would recognise.

5. **What does "propose solutions" require?** `operations.propose` exists and
   re-judges its own drafts, but nothing in the gap path reaches it. Closing a
   gap is the second half of the product and is currently untested end to end.

6. **What is the acceptance test?** There is none for the product. The 30 V6
   checks verify components. A real one looks like: *for N requirements where the
   operator's coverage is known, does the module return the right verdict, cite
   the right span, and name the right gap?* That set does not exist — the same
   "a KB with no query set cannot be migrated with evidence" rule applies here,
   and it was never applied to assessment.

## 6. What is NOT in question

- Retrieval works. For R2 Part 2.1 it returned the patch-management procedure
  and work instruction ahead of everything else. The Y25 chunking fix was real
  (1508 blind slices → 566 layout-aware chunks; `page=-1` → real page numbers).
- The corpus is sound: 68 documents, re-ingested, heading paths on 2635 of 2636
  chunks.
- The council reads well when asked.
- The seven fixes above are worth keeping.

The gap is between retrieval and verdict, and it is one design decision wide.
