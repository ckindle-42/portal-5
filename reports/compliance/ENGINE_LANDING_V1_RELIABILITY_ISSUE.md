# TASK_COMPLIANCE_ENGINE_LANDING_V1 — the unresolved reliability issue

**Status: FIXED for the confirmed retrieval/classification defects (2026-09-04).
The historical FULL/PARTIAL discrepancy was not reproduced with identical
query text; its original cause remains unproven.** See the host investigation
below. The original report is preserved afterward as historical evidence.

## Host investigation and repair — 2026-09-04

### What was established

The baseline ran the unmodified proposer from `b103c63e` against the existing
`operator_corpus`: isolated Part 5.4, all 20 applicable CIP-007-6 Parts, then
isolated Part 5.4 again. All three returned `FULL`. The exact register query
was `Change known default passwords, per Cyber Asset capability`, SHA-256
`8e27805871165273862b531a959286318952c08ea0cd32075ab84ac1d3c8bb66`.
The target's complete search results were identical in isolation and in the
sweep, including policy chunk 43. Thus this experiment supports neither
query-text divergence nor VL-state corruption as the cause of the historical
observation; it cannot retroactively establish what those uncaptured calls did.

It did establish a concrete, systematic failure missed by the original report:

1. Multimodal retrieval returns page-image pointers with `text=None` and
   `content_available=False`. `_filter_candidates` converted those to empty
   strings and submitted them as `{"text": ""}` alongside real text chunks.
2. The VL server rejected the **whole classification rerank request** with
   HTTP 400: `item has neither text nor image`. This happened in **22 of 22**
   baseline Part evaluations. Part 5.4's batch contained seven empty documents
   among 15 candidates. These were immediate validation failures (~10 ms),
   not model hangs.
3. The broad exception handler silently replaced cross-encoder relevance with
   keyword overlap. Consequently the baseline's `FULL` results did **not**
   demonstrate successful semantic reranking. Search failures could likewise
   become an empty list and be reported as a substantively resolved gap.
4. Image pointers competed with usable text for the same top-k budget. A
   regression test using the real fusion stage demonstrates that its visual
   boost can evict every text candidate, including the governing policy.
   This is a confirmed failure mechanism, **not proof** that it caused the
   historical Part 5.4 result.
5. Compact citations blindly truncated the beginning of a multi-Part chunk.
   The correct Part 5.4 statement was present later in the policy/procedure
   text, beyond the compact excerpt. The original result ordering also ignored
   the classification rerank scores when choosing a representative citation.

The baseline full sweep took **808.95 seconds**. Its completed search calls
normally spent ~39–40 seconds reranking page images before the classification
rerank failed immediately. The VL service remained responsive. No server
restart, model change, or corpus re-ingest was necessary for the repair.
The older server-degradation hypothesis should not be read as an established
finding; `reports/runtime/HARDENING_V2_P4_MEASUREMENTS.md` S1 also explicitly
retracts an earlier degradation claim.

### Changes

- The coverage proposer uses the shared retrieval pipeline with a cloned,
  text-only composition. General `compliance_search` remains multimodal.
  Empty/non-content hits are also rejected defensively before classification.
- Search and rerank failures raise a typed `ProposalError`. The matrix records
  the affected Part as `NEEDS_REVIEW`, with stage/error details, excludes it
  from substantively resolved and full-gap counts, and continues other Parts.
  Compact and verbose tool responses both expose the error. Search is bounded
  at 60 seconds and classification rerank at 20 seconds. **Keyword fallback is
  removed.** A busy service can still exceed a deadline, but cannot silently
  change the classifier or invent a gap.
- Rerank responses must contain exactly one finite probability for every
  candidate, with valid unique indices. Missing/invalid scores are failures,
  not fabricated zero scores. Ambiguous relevance stays `NEEDS_REVIEW` when
  there is insufficient independently resolved support for `FULL`.
- Representative citations follow rerank score order. When a chunk contains
  an exact requirement restatement (allowing extraction whitespace), the
  excerpt starts there and remains an unchanged slice of the stored text.
- Candidate identities and the exact query hash are logged per node; verbose
  spans carry rerank scores. `scripts/compliance_reliability_probe.py` records
  raw search/rerank inputs, outputs, errors, timings, and full matrices. Its
  review proposals are captured in memory rather than written to the live
  operator queue, while retrieval/scope/mappings use the existing corpus.

### Verification and limits

The repaired probe ran isolated → full sweep → full sweep → isolated without
resetting the VL server:

| Run | Duration | Part 5.4 |
|---|---:|---|
| Isolated before | 2.54 s | FULL |
| First 20-Part sweep | 59.06 s | FULL |
| Second 20-Part sweep | 59.90 s | FULL |
| Isolated after | 2.61 s | FULL |

Across these runs: **42 successful searches, 42 successful classification
reranks, zero visual reranks, zero retrieval errors**. The target's complete
candidate lists and rerank scores are identical across all four runs. Both
full matrices, including all 20 rows and their candidate scores, are identical.
The governing policy's chunk 43 scores **0.7868062258**; the procedure's actual
default-account password instruction at chunk 26 scores **0.7430827618**.
Both contain relevant, locatable text. Sweep latency is approximately **13.6×
lower** than the baseline.

After the final citation-ordering change, `com.portal5.compliance-mcp` was
restarted through launchd and verified through its real HTTP tool endpoint.
The full sweep returned HTTP 200 in **59.06 seconds**; the subsequent isolated
Part 5.4 call returned HTTP 200 in **2.63 seconds**. Coverage and representative
policy/procedure citations match exactly, with zero retrieval errors. The
policy citation names chunk 43 and displays the Part 5.4 obligation; the
procedure citation names chunk 26 and displays its password-change instruction.
A concurrent `/health` call returned in **1.95 ms**, and `lookup_control(AC-2)`
also responded during the sweep. These normal live tool calls create review
proposals through the existing queue, unlike the diagnostic probe.

The broad unit/security run passed **3,114 tests, 4 skipped**. After the final
citation changes, the focused proposer/engine/planted suite passed **60 tests**
(23 new proposer regressions). Ruff and diff-whitespace checks pass.

Private trace artifacts (contain operator text; intentionally not committed):
`/private/tmp/compliance-reliability-baseline-20260904/` and
`/private/tmp/compliance-reliability-fixed-20260904/`. To repeat against the
currently configured corpus with the service environment:

```sh
PYTHONPATH=. .venv/bin/python scripts/compliance_reliability_probe.py \
  --output /private/tmp/compliance-reliability-new-run \
  --runs isolated sweep sweep isolated
```

This closes the demonstrated reliability defects and establishes repeatability
on this existing CIP-007-6 corpus. It does **not** convert model proposals into
SME-approved compliance judgments, validate every real-corpus label, or prove
the original uncaptured FULL/PARTIAL discrepancy's cause. The repaired sweeps
propose 18 FULL / 2 NONE; those labels still require substantive review. The
original report's acceptance requirement for human judgment remains in force.

---

## Full-corpus ingest and per-standard comparison — 2026-09-04

All 68 of the operator's PDFs across all 13 CIP standard folders (CIP-002
through CIP-014) were ingested — 2,915 chunks total, layer census 2 policy /
61 procedure / 5 evidence documents. `compliance_gaps` was run per standard
against the full corpus. Zero `retrieval_errors` across all 13 runs (~190
Parts examined total).

| Standard | FULL | PARTIAL | NONE | NEEDS_REVIEW |
|---|--:|--:|--:|--:|
| CIP-002-5.1a | 4 | 9 | 6 | 12 |
| CIP-003-9 | 1 | 8 | 19 | 0 |
| CIP-004-7 | 14 | 3 | 2 | 0 |
| CIP-005-7 | 10 | 2 | 0 | 0 |
| CIP-006-6 | 14 | 0 | 0 | 0 |
| CIP-007-6 | 18 | 1 | 1 | 0 |
| CIP-008-6 | 1 | 6 | 0 | 4 |
| CIP-009-6 | 7 | 1 | 2 | 0 |
| CIP-010-4 | 11 | 0 | 0 | 1 |
| CIP-011-3 | 3 | 0 | 0 | 1 |
| CIP-012-2 | 2 | 1 | 2 | 0 |
| CIP-013-2 | 3 | 6 | 0 | 1 |
| CIP-014-3 | 0 | 8 | 2 | 7 |

CIP-007-6 rose from 0 FULL / 20 PARTIAL (13-PDF corpus, pre-fix) to 18 FULL /
1 PARTIAL / 1 NONE against the full 68-PDF corpus with all of this session's
fixes applied — real, substantial improvement, not just a repeatability
demonstration. **CIP-006-6's 14/14 FULL is flagged, not accepted at face
value** — a perfect standard is unusual enough to warrant a sample review
before trusting it; not yet done.

### A second, unresolved false-conflict pattern

The topic-overlap gate above (`_shares_topic`) was verified to fix one real
class of false `COMPLIANCE_CONFLICT` (a locatable-but-topically-unrelated
span — tested, live-confirmed). It does **not** fix a second, harder pattern
observed live on `CIP-007-6 R5 Part 5.6`, which still carries **11** conflicts
after the fix, unchanged from before it:

```
CIP-007-6 R5 Part 5.6 says [15 calendar months];
LSPG Account Management Procedure v6.pdf #chunk37 says [30 calendar days]
```

Chunk 37 is a genuinely relevant, correctly-locatable procedure passage about
account/password management generally — it legitimately shares "password",
"account", "calendar", "interactive", "access" with the standard's own text,
which is *why* it scored high enough to be locatable in the first place. Its
own quoted duration belongs to a *different* numbered sub-item (an
access-revocation deadline, not the password-rotation cadence Part 5.6 states)
within the same broadly on-topic document. A bag-of-words overlap threshold
cannot distinguish "same broad topic" from "same specific obligation" — both
share the exact vocabulary that made the span relevant. Closing this
requires either genuine semantic/structural matching (an LLM judging whether
two spans discuss the *same* numbered obligation, not just the same topic) or
parsing sub-item structure out of retrieved spans — a materially larger
undertaking than a heuristic threshold, not attempted here given the risk of
overfitting to the handful of examples observed without a proper eval set.

**Practical framing, not an excuse**: this system's own design principle
(`tiers.py`) is that a `COMPLIANCE_CONFLICT` is never auto-resolved — it is
surfaced for an SME to review and dismiss or act on. A false-positive conflict
is a review-burden cost (an SME spends a few seconds recognizing "30 calendar
days" isn't about password rotation), not a compliance-exposure cost the way
a missed genuine conflict or an invisible false-covered gap would be. That
does not make it correct, and it should be fixed — but it is the less severe
of the two failure directions this task has spent most of its effort closing.

---

## Original report (historical)

This is a targeted writeup of one specific problem hit during
the Phase 6 real-corpus run, isolated from the rest of the task's (mostly
landed) work. See `reports/PROGRAM_RETRIEVAL_AND_COMPLIANCE_V1_CLOSEOUT.md`
(T5 section) for the full task rollup — everything else described there is
built, tested, and not in question here.

---

## What was done

`compliance_gaps` needed real retrieval to classify whether the operator's
ingested policy/procedure corpus covers each NERC CIP Part. Over the course of
this task's real-corpus run (Phase 6), the naive first version proved
insufficient and was hardened through several rounds, each triggered by a
specific observed failure:

1. **Real `propose()`** (`portal/modules/compliance/core/propose.py`) — retrieves
   from the ingested corpus via the shared retrieval composition
   (`portal.platform.retrieval.pipeline.search`) and classifies each candidate
   span to policy/procedure/evidence using the layer recorded at ingest.
2. **Folder-per-standard filter** — the operator's PDFs are organized in
   per-standard folders (`CIP-007/`, `CIP-003/`, ...). Added a filter so a
   *procedure* candidate from a document filed under a different standard's
   folder is excluded, closing a real false-positive (a CIP-007 procedure's
   boilerplate matching a CIP-014 Part on lexical overlap). **Policy is exempt**
   from this filter — a single cross-cutting policy document (filed once, e.g.
   under `CIP-003/`) legitimately speaks to every other standard; applying the
   folder filter to it zeroed out every policy citation in the corpus, verified
   live, and was reverted to policy-exempt.
3. **Cross-encoder rerank replacing keyword overlap** — `locatable` used to be a
   count of shared 4+ letter words between the requirement text and a
   candidate span, which produced a real false `COMPLIANCE_CONFLICT` (a
   password-rotation obligation matched against an unrelated access-revocation
   clause on shared vocabulary). Replaced with `vl_rerank`, the same
   cross-encoder the retrieval fusion already uses for its visual arm.
4. **Three-stage resolution** (exact match → rerank score → queued
   arbitration for the ambiguous middle) — borrowed from the entity-resolution
   pattern in `deeplethe/utopia` (an external reference the operator pointed
   to). A rerank score in the ambiguous band files a `low_confidence_extraction`
   review-queue item instead of guessing; the span stays `locatable=False`
   until reviewed.
5. **Per-node batching** — `coverage_matrix` calls `propose(node, side)` three
   times per Part (policy/procedure/evidence) with the *same* query text; the
   search and rerank were being redundantly repeated 3x. Cached per `node.id`
   and split by layer after one search + one rerank call, cutting VL
   round-trips ~3x with no change to the classification logic.
6. **Register pre-filtering by `standard`/`requirement`** — `compliance_gaps`'s
   scoping params were filtering only the *returned rows*, not the
   computation; a "just CIP-007-6" call was silently running the whole
   ~193-node register (386 VL round-trips). Filtering the `Register` itself
   before calling `coverage_matrix` cut a scoped call to the ~40 round-trips
   it should have needed.
7. **A real concurrency bug, found and fixed** — `compliance_mcp.py`'s generic
   `/tools/{tool_name}` dispatch (`invoke_tool`) is an `async def` that calls
   the tool function directly with no `await` in between. A long-running sync
   tool call therefore blocks the **entire process** — verified live: while a
   13-minute `compliance_gaps` call was in flight, this server's own
   `/health` and an unrelated, near-instant tool (`lookup_control`, a pure
   dict lookup) both timed out for the full duration. Fixed by running the
   tool call in the default executor (`loop.run_in_executor`). Verified fixed:
   a concurrent `/health` check returned in 8ms while a call was in flight,
   and the full unit test suite ran to completion concurrently with a live
   `compliance_gaps` call with neither blocking the other. This bug predates
   this task and affects every tool routed through `invoke_tool`, not just the
   new ones — it was only large enough to see once a tool call ran for
   minutes.
8. **A rerank-call timeout** — the VL retrieval server's `/rerank` endpoint was
   observed to hang (not error) on specific calls with no log line at all,
   consistent with the already-documented `KNOWN_LIMITATIONS.md` entry
   (`P5-VL-RETR-001`, single MLX worker, degrades under sustained load) but a
   new, more severe variant: a true hang rather than a slow queue. Added a 20s
   timeout around the rerank call in `propose.py`, falling back to keyword
   overlap for that one Part rather than blocking the whole matrix
   indefinitely.

Each of 1–7 was individually verified: unit tests (1332 passed throughout),
isolated single-Part live checks, and a direct A/B search-determinism check
(two identical queries against the live corpus returned byte-identical
top-15 results).

---

## What is observed

**`CIP-007-6 R5 Part 5.4`, queried in isolation
(`compliance_gaps(standard="CIP-007-6", requirement="Part 5.4")`), consistently
returns `FULL`** with a real, contextually correct policy citation — the
operator's CIP Cyber Security Policy, chunk 43, which explicitly names
`"(Part 5.4)"` in the matched text. Reproduced twice, both `FULL`.

**The same Part, queried as part of the full 20-Part `CIP-007-6` sweep
(`compliance_gaps(standard="CIP-007-6")`, no `requirement` filter), returned
`PARTIAL`** — zero policy candidates, procedure citation still present. This
was reproduced across two separate full-sweep runs (both post all fixes 1–8
above, both against the identical, unchanged corpus).

A direct search-determinism check (re-issuing the same query text twice)
showed **no non-determinism in the search layer** — identical top-15 results
both times. The divergence therefore sits somewhere between: (a) the exact
query text used (isolated calls in this investigation used a hand-typed
paraphrase of the requirement, not necessarily byte-identical to
`node.verbatim_text`), or (b) the state of the VL retrieval server partway
through a long sequential sweep — the same server whose `/rerank` endpoint is
independently documented to degrade under sustained load, and which was
observed mid-task to both slow down substantially (from ~20 calls/min to ~3
calls/min over 47 minutes of continuous use) and to hang outright on specific
calls (finding 8 above).

---

## Intent, as understood

The acceptance for this task is a coverage matrix an operator can trust well
enough to work from — "every citation resolving to a real span," "false-covered
and false-gap reported separately, never averaged," and explicitly: **"Do not
report the real run as passing because the tools returned without error. Whether
the output is usable is judged by a person."** A tool that gives a different,
better answer when asked about one Part in isolation than when asked about the
same Part as part of a larger sweep is not yet at that bar, regardless of how
correct the isolated answer is — an operator running the intended real
workflow (ask about a whole standard, not one Part at a time) would get the
worse answer without knowing a better one exists.

---

## The yet-to-solve problem

**Root cause not established.** Two credible hypotheses, neither confirmed:

1. **VL-server-state-dependent**: something about the retrieval or rerank
   pipeline's behavior changes partway through a long sequential run — plausibly
   connected to the same single-MLX-worker degradation already documented for
   this server, but manifesting as *wrong results* here rather than *slowness*
   or a *clean hang*. This would be new and more serious than what
   `KNOWN_LIMITATIONS.md` P5-VL-RETR-001 currently describes (which characterizes
   the failure mode as a queue/liveness issue, not silent result corruption).
2. **Query-text sensitivity**: the isolated verification calls in this
   investigation used a hand-typed paraphrase of R5 Part 5.4's requirement
   text rather than the exact `node.verbatim_text` `coverage_matrix` actually
   sends. If the embedding/rerank is more sensitive to exact wording than
   expected, the "isolated" and "full sweep" calls may not actually be
   comparable — this has **not** been ruled out and is the next thing to check.

**Not yet done, and needed before this is closed:**
- Re-run the *exact* `node.verbatim_text` for R5 Part 5.4 (not a paraphrase)
  through `compliance_search` in isolation, and diff it against what the
  candidate list looked like inside a live full-sweep run at the same Part —
  requires instrumenting `propose.py` to log/dump its candidate list per node
  (not currently done) rather than inferring from the final classification.
- If the VL-server-state hypothesis holds, determine whether it is specifically
  the *rerank* step (candidates present but reranked away) or the *search*
  step (candidates never retrieved) that degrades — the current data cannot
  distinguish these for the failing case, since only the two `compliance_gaps`
  outputs (isolated vs. full-sweep) were captured, not the intermediate
  candidate lists.
- Until resolved, **`compliance_gaps` full-standard (or full-corpus) sweeps
  should not be treated as authoritative** — only single-Part / single-
  requirement scoped calls have been verified reproducible. This is the
  honest state of Phase 6, not a passing result.
