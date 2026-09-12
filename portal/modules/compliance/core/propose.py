"""The real ``propose`` for ``coverage.coverage_matrix`` (§A).

``coverage_matrix`` never implements retrieval — layer separation is delegated
to the caller. This is the caller for real ingested corpora: it retrieves from
the compliance composition and assigns each candidate span to
``policy``/``procedure``/``evidence`` using the layer recorded at ingest
(``ingest.py``). A span whose document has no layer assignment is queued as
``document_tier`` and treated as its derived layer meanwhile — never silently
dropped, since a dropped procedure span is an invisible ``FULL`` degrading to
``PARTIAL`` (§B).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import hashlib
import json
import logging
import math
import re
from collections.abc import Awaitable
from dataclasses import replace
from typing import Any, cast

from portal.modules.compliance.core import review_queue as rq
from portal.modules.compliance.core.cip_register import RegisterNode
from portal.modules.compliance.core.coverage import ProposalError, ProposeFn
from portal.modules.compliance.core.ingest import derive_tier, read_sidecar
from portal.modules.compliance.core.text_signals import is_aspirational

logger = logging.getLogger(__name__)


def _standard_base(standard: str) -> str:
    """``"CIP-007-6"`` -> ``"CIP-007"`` — the family-and-number the operator's
    own folder names use, version-independent."""
    bits = standard.split("-")
    return "-".join(bits[:2]) if len(bits) >= 2 else standard


def _run(coro: Awaitable[Any], timeout: float | None = None) -> Any:
    """Run an async call from sync code. MCP tool functions are plain sync
    callables with no event loop of their own; guard the (untested-in-practice)
    case of already being inside one by running in a fresh thread.

    ``timeout`` bounds a single call independent of the client's own timeout —
    ``embedding.vl_rerank`` uses a 300s httpx timeout shared with the RAG
    composition. Bound the coverage call separately so a busy or unavailable
    service cannot stall each Part for five minutes. ``asyncio.TimeoutError`` is
    caught by the caller and reported as unresolved retrieval, never as a
    different coverage classifier."""

    async def _bounded() -> Any:
        return await asyncio.wait_for(coro, timeout) if timeout else await coro

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_bounded())
    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, _bounded()).result()


# Three-stage resolution (borrowed from the deeplethe/utopia entity-resolution
# pattern: exact match -> embedding/rerank similarity -> model-based
# arbitration of the ambiguous middle): (1) the standard-folder filter above is
# the exact-match stage; (2) a rerank score is confident above HIGH (relevant)
# or below LOW (irrelevant, dropped without comment — real search noise); (3)
# the middle band is neither, and a MODEL READS BOTH TEXTS to settle it.
#
# Stage 3 was documented here from the start and was not implemented until
# 2026-09-12: the middle band filed a `low_confidence_extraction` review item
# and returned False. That is not arbitration, it is a human ticket — and
# returning False meant an ambiguous procedure/standard pair silently became a
# NON-match, which under-reports coverage (a requirement the procedure does
# satisfy reads as uncovered). 812 of 1107 open review items on the operator
# corpus were this band. The judgment is well within reach: the council seats
# score F2 0.952-1.000 on exactly this question (does this candidate address
# this governing unit) over the 30-case probe. The band just never asked.
#
# A rerank score measures topical similarity between two embeddings. It cannot
# tell "this procedure implements this requirement" from "this procedure
# mentions the same equipment" — that needs reading, which is what the arbiter
# now does. Only a genuinely undecidable pair reaches a human.
RERANK_THRESHOLD_HIGH = 0.5
RERANK_THRESHOLD_LOW = 0.25

# One seat, one narrow question — not the full listwise council, which runs 3
# seats with quorum for a *satisfies* determination. Relevance is cheaper and
# the band is large, so this is a single call per ambiguous pair.
_ARBITER_SYSTEM = (
    "You decide ONE thing: does the candidate text from an internal document "
    "address the governing compliance requirement? Addressing it means the text "
    "states a duty, control, process or record that implements, or is directly "
    "governed by, that requirement.\n"
    "- Topical overlap is NOT enough. Naming the same system, asset class or "
    "team, without stating a duty or control that bears on the requirement, is "
    "NOT_RELEVANT.\n"
    "- You are NOT deciding whether the requirement is SATISFIED, only whether "
    "this text is about it. Partial or weak implementation still counts as "
    "RELEVANT.\n"
    "- Answer UNSURE only if the candidate text is too truncated or garbled to "
    "read. Do not use UNSURE for a hard judgment call.\n"
    'Return ONE JSON object: {"verdict":"RELEVANT|NOT_RELEVANT|UNSURE",'
    '"reason":"one short sentence"}'
)

# Bounds one rerank call independent of embedding.vl_rerank's own 300s httpx
# timeout (see _run's docstring). A failure leaves the Part NEEDS_REVIEW.
RERANK_CALL_TIMEOUT_S = 20.0
SEARCH_CALL_TIMEOUT_S = 60.0


def _resolve_meta(source_file: str, sidecar: dict[str, Any], queued: set[str]) -> dict[str, Any]:
    """The sidecar record for a hit's document, or a live best-guess (queued,
    never dropped) when ingest never recorded one."""
    meta = sidecar.get(source_file)
    if meta is not None:
        return cast("dict[str, Any]", meta)
    derived = derive_tier(source_file)
    derived["standard_hint"] = None  # no ingest-time folder on record to read
    if source_file not in queued:
        rq.propose(
            "document_tier",
            subject_id=source_file,
            proposed_value={"layer": derived["layer"], "tier": derived["tier"]},
            evidence=[
                {
                    "document": source_file,
                    "section": "(no ingest-time record — derived at query time)",
                    "page": None,
                    "span": derived["evidence"],
                }
            ],
            confidence=derived["confidence"],
        )
        queued.add(source_file)
    return derived


def _filter_candidates(
    hits: list[dict[str, Any]],
    sidecar: dict[str, Any],
    target_std: str,
    queued: set[str],
) -> list[dict[str, Any]]:
    """Eligibility filter over raw retrieval hits.

    A document's folder-derived standard is a ranking hint only.  Cross-standard
    procedures are common and must remain eligible; atom comparison rejects
    irrelevant boilerplate on its merits. NOT layer-filtered here — ``node.verbatim_text`` is the same query
    for policy/procedure/evidence, so one search result set is filtered by
    standard, reranked once, and split by layer per side by the caller
    (``propose``'s cache) instead of repeating the search+rerank 3x per Part.

    The folder filter applies to procedure/evidence only, not policy. A
    procedure is filed under the one standard it implements (real, verified:
    the operator's CIP-007 procedures live only in ``CIP-007/``); a policy is
    routinely a single cross-cutting document — "the CIP Cyber Security
    Policy" filed once, under CIP-003, that legitimately speaks to CIP-007
    password management, CIP-005 access control, etc. Excluding it from every
    Part outside its own folder was verified live to zero out every policy
    citation across the whole corpus — an over-strict application of a filter
    that is exactly right for procedures and exactly wrong for policy."""
    out = []
    for hit in hits:
        text = hit.get("text") or ""
        if hit.get("content_available") is False or not text.strip():
            continue  # a page pointer cannot substantiate a quoted text span
        source_file = hit.get("source_file", "")
        meta = _resolve_meta(source_file, sidecar, queued)
        out.append(
            {
                "document_id": source_file,
                "section_id": f"{source_file} #chunk{hit.get('chunk_index')} p{hit.get('page')}",
                "span": text[:400],
                "text": text,
                "layer": meta["layer"],
                "standard_hint": meta.get("standard_hint"),
                "folder_rank_prior": 1.0 if meta.get("standard_hint") == target_std else 0.0,
            }
        )
    return out


def _verify_anchor(candidate: dict[str, Any]) -> bool:
    """Literal source-location verification (P1.1): the quoted ``span`` is a
    verbatim substring of the retrieved chunk ``text``. This is the ONLY thing
    "anchor verified" means — it says nothing about relevance. Previously a
    rerank RELEVANCE score alone decided the field named ``locatable``; that
    conflated "this text is about the right topic" with "this citation
    actually points at real text", which let a confidently-scored but
    unverified span certify a source location."""
    span, text = candidate.get("span") or "", candidate.get("text") or ""
    return bool(span) and span in text


ArbiterFn = Any  # (model, system, user) -> raw JSON string; injected in tests


def _arbiter_model() -> str:
    """The strongest seat on the roster, and the one Y23 measured as insensitive
    to prompt wording (F2 0.952 flat across four paraphrases) — which matters
    for a stage whose whole job is reading two texts and judging."""
    import os

    return os.environ.get(
        "COMPLIANCE_ARBITER_MODEL", "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k"
    )


def default_arbiter() -> ArbiterFn:
    """The production arbiter — one council seat over Ollama. Imported lazily so
    the module stays importable (and unit-testable) with no inference stack."""
    from portal.modules.compliance.core.council import _ollama_seat

    return cast("ArbiterFn", _ollama_seat)


def arbitrate_relevance(
    candidate: dict[str, Any],
    node: RegisterNode,
    *,
    arbiter_fn: ArbiterFn | None = None,
) -> tuple[str, str]:
    """Stage 3. Read the requirement and the candidate text, decide whether the
    candidate ADDRESSES the requirement. Returns (verdict, reason) where verdict
    is RELEVANT / NOT_RELEVANT / UNSURE.

    UNSURE is also what an unreachable or unparseable arbiter yields, so the
    caller's fallback is the pre-2026-09-12 behaviour (queue it for a human) —
    this stage can only ever REMOVE work from the human queue, never add it.

    ``arbiter_fn`` is REQUIRED. There is deliberately no live default: the band
    is resolved inside ``coverage_matrix``, which live routes call, and a hidden
    default would put a model call per ambiguous pair on that path and make
    every unit test touching the band reach the network. ``default_arbiter()``
    returns the production one; the caller opts in."""
    if arbiter_fn is None:
        return "UNSURE", "no arbiter supplied"
    user = json.dumps(
        {
            "governing_requirement": {"ref": node.id, "text": getattr(node, "text", "") or ""},
            "candidate_text": candidate.get("text") or "",
            "candidate_document": candidate.get("document_id") or "",
        },
        indent=2,
        ensure_ascii=False,
    )
    try:
        raw = arbiter_fn(_arbiter_model(), _ARBITER_SYSTEM, user)
    except Exception as exc:  # noqa: BLE001 - an unreachable arbiter degrades to the queue
        logger.warning("relevance arbiter unavailable (%s) — falling back to review queue", exc)
        return "UNSURE", f"arbiter unavailable: {exc}"
    obj = None
    with contextlib.suppress(json.JSONDecodeError):
        obj = json.loads(raw.strip())
    if not isinstance(obj, dict):
        return "UNSURE", "arbiter returned no JSON object"
    verdict = str(obj.get("verdict", "")).strip().upper()
    if verdict not in {"RELEVANT", "NOT_RELEVANT", "UNSURE"}:
        return "UNSURE", f"arbiter returned unknown verdict {verdict!r}"
    return verdict, str(obj.get("reason", ""))[:200]


def _resolve_relevance(
    candidate: dict[str, Any],
    score: float,
    node: RegisterNode,
    side: str,
    *,
    arbiter_fn: ArbiterFn | None = None,
) -> tuple[bool, str]:
    """Stages 2+3: a confident rerank score decides; the ambiguous middle band
    is READ by the arbiter, and only a pair it cannot settle is queued. Returns
    (relevant, queue_item_id) — RELEVANCE only (renamed from
    ``_resolve_locatability``; see ``_verify_anchor`` for anchor proof)."""
    if score >= RERANK_THRESHOLD_HIGH:
        return not is_aspirational(candidate["text"]), ""
    if score < RERANK_THRESHOLD_LOW:
        return False, ""  # confidently irrelevant — ordinary search noise

    verdict, reason = arbitrate_relevance(candidate, node, arbiter_fn=arbiter_fn)
    if verdict == "RELEVANT":
        # Aspirational text ("we strive to...") is not a control, and that check
        # applies here exactly as it does above the HIGH threshold.
        return not is_aspirational(candidate["text"]), ""
    if verdict == "NOT_RELEVANT":
        return False, ""

    # UNSURE only: the arbiter could not read it, or was unreachable. This is
    # the sole path that still costs a human a decision.
    item = rq.propose(
        "low_confidence_extraction",
        subject_id=candidate["section_id"],
        proposed_value={
            "requirement_id": node.id,
            "side": side,
            "rerank_score": round(score, 3),
            "arbiter_verdict": verdict,
            "arbiter_reason": reason,
        },
        evidence=[
            {
                "document": candidate["document_id"],
                "section": candidate["section_id"],
                "page": None,
                "span": candidate["span"],
            }
        ],
        confidence=score,
    )
    return False, item.id


def _validated_scores(ranked: list[dict[str, Any]], count: int) -> dict[int, float]:
    """Missing, duplicate, or invalid scores are failures, not irrelevant hits."""
    scores = {}
    for row in ranked:
        index, score = row["index"], float(row["score"])
        if (
            type(index) is not int
            or not 0 <= index < count
            or index in scores
            or not math.isfinite(score)
            or not 0 <= score <= 1
        ):
            raise ValueError("invalid or duplicate rerank score")
        scores[index] = score
    if len(scores) != count:
        raise ValueError(f"rerank returned {len(scores)} scores for {count} candidates")
    return scores


def _quote_span(text: str, requirement: str) -> str:
    """Keep an exact requirement restatement visible in compact citations.

    The real policy/procedure chunks contain several Parts. Blindly quoting
    their first 400 (then 180) characters hid Part 5.4 even when the full chunk
    restated it verbatim. Match across extraction whitespace, but return an
    unchanged slice of the stored text. This does not decide relevance.
    """
    pattern = r"\s+".join(re.escape(word) for word in requirement.split())
    match = re.search(pattern, text, re.I) if pattern else None
    start = match.start() if match else 0
    return text[start : start + 400]


def make_real_proposer(
    kb_id: str = "operator_corpus",
    top_k: int = 15,
    *,
    arbiter_fn: ArbiterFn | None = None,
) -> ProposeFn:
    """A ``propose(node, side)`` over the real ingested corpus. Documents with
    no ingest-time layer record are given a live best-guess tier (queued, not
    dropped) so a stale sidecar never silences a real span.

    **Folder-per-standard is an association claim, not just an organizing
    convenience — for procedures.** The operator files documents under
    ``CIP-007/``, ``CIP-003/``, etc.; a *procedure* candidate span from a
    document filed under a different standard's folder is excluded —
    free-text retrieval alone will happily match a CIP-007 procedure's
    boilerplate against a CIP-014 Part on lexical overlap, which is exactly
    the false-coverage risk this filter closes. A document with NO folder
    hint (unrecognized directory name) is never excluded on that basis — only
    a known *mismatch* is. **Policy is exempt from this filter** — see
    ``_filter_candidates``'s docstring for why a blanket application zeroed
    out every policy citation in the operator's real corpus.

    **Locatability is a cross-encoder rerank, not a keyword count.** A
    compliance document routinely names other standards in passing (a CIP-007
    procedure's boilerplate header quotes CIP-005 language, a cross-reference
    footnote, a shared glossary term) — counting shared 4+ letter words treats
    that mention as coverage. Every candidate that survives the standard
    filter is reranked against the Part's own verbatim text with the same
    cross-encoder the retrieval fusion already uses for the visual arm
    (``vl_rerank``); a three-stage decision (``_resolve_locatability``) turns
    the score into ``locatable`` — confident either way, or queued as
    ``low_confidence_extraction`` in the ambiguous middle. Retrieval errors
    raise ``ProposalError`` so the matrix reports NEEDS_REVIEW. A timeout must
    never switch to keyword matching and invent coverage or gaps.

    Coverage requires quoted text, so this composition searches the text arm
    only. Image-only pointers cannot prove a span and must not crowd text out
    of the top-k pool or be submitted to the reranker as empty strings. General
    ``compliance_search`` remains multimodal.

    **One search + one rerank per Part, not per side.** ``coverage_matrix``
    calls ``propose(node, side)`` three times (policy/procedure/evidence) per
    Part with the *same* ``node.verbatim_text`` query — three redundant
    round-trips to the retrieval/rerank service for identical work. Resolved
    candidates are cached per ``node.id`` on first call and split by layer for
    the other two, cutting VL round-trips ~3x (a real fix for the documented
    single-worker MLX serialization ceiling — fewer calls, not more workers)."""
    from portal.modules.compliance.tools import compliance_retrieval as _cr
    from portal.platform.retrieval import embedding as _embedding
    from portal.platform.retrieval import pipeline as _pipeline

    _queued_this_process: set[str] = set()  # avoid re-queuing the same file every call
    _resolved_cache: dict[
        str, list[dict[str, Any]]
    ] = {}  # node.id -> every resolved candidate, all layers
    comp = replace(_cr._composition(), visual_table=lambda _kb_id: None)

    def _resolve_all_layers(node: RegisterNode) -> list[dict[str, Any]]:
        sidecar = read_sidecar()
        target_std = _standard_base(node.standard)
        try:
            result = _run(
                _pipeline.search(comp, kb_id, node.verbatim_text, top_k),
                timeout=SEARCH_CALL_TIMEOUT_S,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced on the affected cell
            logger.warning("compliance search failed for %s: %s", node.id, exc)
            raise ProposalError("search", f"{type(exc).__name__}: {exc}") from exc

        candidates = _filter_candidates(
            result.get("results", []), sidecar, target_std, _queued_this_process
        )
        for candidate in candidates:
            candidate["span"] = _quote_span(candidate["text"], node.verbatim_text)
        logger.info(
            "compliance candidates %s",
            json.dumps(
                {
                    "requirement_id": node.id,
                    "kb_id": kb_id,
                    "query_sha256": hashlib.sha256(node.verbatim_text.encode()).hexdigest(),
                    "hits": [
                        {
                            "document": h.get("source_file"),
                            "chunk": h.get("chunk_index"),
                            "kind": h.get("kind"),
                        }
                        for h in result.get("results", [])
                    ],
                    "candidates": [c["section_id"] for c in candidates],
                }
            ),
        )
        if not candidates:
            return []

        try:
            ranked = _run(
                _embedding.vl_rerank(
                    node.verbatim_text,
                    [{"text": c["text"]} for c in candidates],
                    len(candidates),
                ),
                timeout=RERANK_CALL_TIMEOUT_S,
            )
            scores = _validated_scores(ranked, len(candidates))
        except Exception as exc:  # noqa: BLE001 — surfaced on the affected cell
            logger.warning("compliance rerank failed for %s: %s", node.id, exc)
            raise ProposalError("rerank", f"{type(exc).__name__}: {exc}") from exc

        out = []
        for i, c in enumerate(candidates):
            relevant, queue_item_id = _resolve_relevance(
                c, scores[i], node, c["layer"], arbiter_fn=arbiter_fn
            )
            anchor_verified = _verify_anchor(c)
            out.append(
                {
                    "document_id": c["document_id"],
                    "section_id": c["section_id"],
                    "span": c["span"],
                    "anchor_verified": anchor_verified,
                    "relevant": relevant,
                    # legacy compatibility field only — never the field consumers
                    # should read to certify a source anchor (see coverage.py).
                    "locatable": anchor_verified and relevant,
                    "queue_item_id": queue_item_id,
                    "rerank_score": scores[i],
                    "layer": c["layer"],
                }
            )
        return sorted(out, key=lambda candidate: -candidate["rerank_score"])

    def propose(node: RegisterNode, side: str) -> list[dict[str, Any]]:
        if node.id not in _resolved_cache:
            _resolved_cache[node.id] = _resolve_all_layers(node)
        return [
            {k: v for k, v in c.items() if k != "layer"}
            for c in _resolved_cache[node.id]
            if c["layer"] == side
        ]

    return propose
