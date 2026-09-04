# TASK_COMPLIANCE_ENGINE_LANDING_V1 — the unresolved reliability issue

**Status: OPEN.** This is a targeted writeup of one specific problem hit during
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
