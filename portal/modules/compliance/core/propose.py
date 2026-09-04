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

from portal.modules.compliance.core import review_queue as rq
from portal.modules.compliance.core.ingest import derive_tier, read_sidecar
from portal.modules.compliance.core.text_signals import is_aspirational, keywords


def _standard_base(standard: str) -> str:
    """``"CIP-007-6"`` -> ``"CIP-007"`` — the family-and-number the operator's
    own folder names use, version-independent."""
    bits = standard.split("-")
    return "-".join(bits[:2]) if len(bits) >= 2 else standard


def _run(coro, timeout: float | None = None):
    """Run an async call from sync code. MCP tool functions are plain sync
    callables with no event loop of their own; guard the (untested-in-practice)
    case of already being inside one by running in a fresh thread.

    ``timeout`` bounds a single call independent of the client's own timeout —
    ``embedding.vl_rerank`` hardcodes a 300s httpx timeout shared with the RAG
    composition, generous by design there, but a `compliance_gaps` matrix over
    ~200 Parts cannot afford one hung candidate stalling the whole run for
    5 minutes (observed live: the VL server's ``/rerank`` occasionally hangs on
    a specific payload with no error, no log line — a real, reproducible
    server-side issue, not a client bug). ``asyncio.TimeoutError`` here is
    caught by the caller the same as any other reranker failure — degrade to
    the keyword-overlap fallback, don't block."""

    async def _bounded():
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
# the exact-match stage; (2) a rerank score is confident above HIGH (locatable)
# or below LOW (irrelevant, dropped without comment — real search noise); (3)
# the middle band is neither — filing it as `low_confidence_extraction` rather
# than forcing a binary call is the "model-based arbitration" stage. A span
# rests as not-locatable meanwhile (conservative: an ambiguous span must not
# inflate a PARTIAL/FULL claim), but it is visible and queued, not discarded.
RERANK_THRESHOLD_HIGH = 0.5
RERANK_THRESHOLD_LOW = 0.25

# Bounds one rerank call independent of embedding.vl_rerank's own 300s httpx
# timeout (see _run's docstring) — one hung candidate degrades to keyword
# overlap for that Part instead of stalling a ~200-Part matrix for 5 minutes.
RERANK_CALL_TIMEOUT_S = 20.0


def _resolve_meta(source_file: str, sidecar: dict, queued: set[str]) -> dict:
    """The sidecar record for a hit's document, or a live best-guess (queued,
    never dropped) when ingest never recorded one."""
    meta = sidecar.get(source_file)
    if meta is not None:
        return meta
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
    hits: list[dict], sidecar: dict, target_std: str, queued: set[str]
) -> list[dict]:
    """Standard-folder filter (stage 1: exact match) over the raw retrieval
    hits. NOT layer-filtered here — ``node.verbatim_text`` is the same query
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
        source_file = hit.get("source_file", "")
        meta = _resolve_meta(source_file, sidecar, queued)
        standard_hint = meta.get("standard_hint")
        if meta["layer"] != "policy" and standard_hint and standard_hint != target_std:
            continue  # filed under a DIFFERENT standard's folder — not this Part's evidence
        text = hit.get("text") or ""  # a chunk row can carry text=None, not just a missing key
        out.append(
            {
                "document_id": source_file,
                "section_id": f"{source_file} #chunk{hit.get('chunk_index')} p{hit.get('page')}",
                "span": text[:400],
                "text": text,
                "layer": meta["layer"],
            }
        )
    return out


def _resolve_locatability(candidate: dict, score: float, node, side: str) -> tuple[bool, str]:
    """Stages 2+3: a confident rerank score decides; the ambiguous middle band
    is queued (`low_confidence_extraction`) rather than guessed. Returns
    (locatable, queue_item_id)."""
    if score >= RERANK_THRESHOLD_HIGH:
        return not is_aspirational(candidate["text"]), ""
    if score < RERANK_THRESHOLD_LOW:
        return False, ""  # confidently irrelevant — ordinary search noise
    item = rq.propose(
        "low_confidence_extraction",
        subject_id=candidate["section_id"],
        proposed_value={"requirement_id": node.id, "side": side, "rerank_score": round(score, 3)},
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


def make_real_proposer(kb_id: str = "operator_corpus", top_k: int = 15, overlap_threshold: int = 2):
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
    ``low_confidence_extraction`` in the ambiguous middle. Falls back to the
    keyword overlap only when the reranker itself is unreachable — degraded,
    not silently wrong.

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
    _resolved_cache: dict[str, list[dict]] = {}  # node.id -> every resolved candidate, all layers

    def _keyword_locatable(text: str, req_kw: set[str]) -> bool:
        return len(req_kw & keywords(text)) >= overlap_threshold and not is_aspirational(text)

    def _resolve_all_layers(node) -> list[dict]:
        sidecar = read_sidecar()
        target_std = _standard_base(node.standard)
        try:
            result = _run(_pipeline.search(_cr._composition(), kb_id, node.verbatim_text, top_k))
        except Exception:  # noqa: BLE001 - VL unavailable / unknown kb -> no candidates, not a crash
            return []

        candidates = _filter_candidates(
            result.get("results", []), sidecar, target_std, _queued_this_process
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
            scores: dict[int, float] | None = {r["index"]: float(r["score"]) for r in ranked}
        except Exception:  # noqa: BLE001 - reranker unreachable/hung/timed out: degrade, don't block
            scores = None

        req_kw = keywords(node.verbatim_text)
        out = []
        for i, c in enumerate(candidates):
            if scores is not None:
                locatable, queue_item_id = _resolve_locatability(
                    c, scores.get(i, 0.0), node, c["layer"]
                )
            else:
                locatable, queue_item_id = _keyword_locatable(c["text"], req_kw), ""
            out.append(
                {
                    "document_id": c["document_id"],
                    "section_id": c["section_id"],
                    "span": c["span"],
                    "locatable": locatable,
                    "queue_item_id": queue_item_id,
                    "layer": c["layer"],
                }
            )
        return out

    def propose(node, side: str) -> list[dict]:
        if node.id not in _resolved_cache:
            _resolved_cache[node.id] = _resolve_all_layers(node)
        return [
            {k: v for k, v in c.items() if k != "layer"}
            for c in _resolved_cache[node.id]
            if c["layer"] == side
        ]

    return propose
