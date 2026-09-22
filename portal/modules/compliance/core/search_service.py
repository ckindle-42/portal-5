"""The compliance search composition — ONE implementation, pushed down.

SUBSTRATE_PROPERTIES_V1 P3 property 1: every filter is composed as a
``.where()`` predicate and applied BEFORE ranking, so a filter targets the
search rather than shrinking its aftermath. A filter that runs after ranking and
one that runs before it produce the same count and completely different
evidence.

It lives here rather than in ``tools/compliance_mcp`` because it has two
callers. The reader's tool surface had grown its own copy that retrieved an
unscoped top-k and filtered the results afterwards — the keyhole this predicate
exists to remove, rebuilt beside it. Worse, that copy filtered against
``sections_for_requirement``, which holds the REGULATORY anchors, so passing
``requirement=`` also discarded every operator hit: a bilateral search that
could not return the operator's side.

``requirement`` narrows by IDENTITY through :mod:`core.requirement_scope`, so a
parent requirement reaches its Parts' sections and a sibling never arrives by
prefix. The pool is bilateral: the requirement's own anchors AND the operator
sections recorded as related to it. A relation narrows WHICH of a requirement's
material is asked for; it never bars a passage from an unscoped search.
"""

from __future__ import annotations

import asyncio
from typing import Any

from portal.modules.compliance.core.addressing import addressed_hits as _addressed_hits
from portal.modules.compliance.core.addressing import clip as _clip
from portal.modules.compliance.core.addressing import provenance as _provenance
from portal.modules.compliance.core.addressing import with_cite_header as _with_cite_header
from portal.modules.compliance.core.addressing import within_clocks as _within_clocks
from portal.platform.retrieval import predicates


def _contains_group(column: str, value: str) -> list[Any]:
    """Case-variant substring match as an OR-group of LIKEs.

    The pre-pushdown filter compared ``value.lower() in stored.lower()`` — a
    case-insensitive substring. DataFusion's ``LIKE`` is case-sensitive, so the
    group tries the value in its given, lower and upper spellings; a caller
    that passes what the store spells differently still matches. The values
    stay quoted literals inside the group (``predicates.build`` escapes them),
    so a quote or a clause fragment in a ``standard`` argument remains data.
    """
    variants = list(dict.fromkeys([value, value.lower(), value.upper()]))
    return [(column, "LIKE", f"%{v}%") for v in variants]


def search_predicate(
    *, standard: str, layer: str, valid_at: str, known_at: str, extra: Any = None
) -> str:
    """The pushdown predicate for ``compliance_search`` (SUBSTRATE_PROPERTIES_V1 P3).

    Property 1: the clocks filter BEFORE ranking. Written against the P1
    projection columns and their ``""`` open-bound convention:

    * valid-time at ``valid_at``: ``(effective_from = '' OR effective_from <= V)
      AND (effective_to = '' OR effective_to > V)``
    * transaction-time at ``known_at``: ``(recorded_from = '' OR recorded_from
      <= K) AND (recorded_to = '' OR recorded_to > K)``
    * neither given: ``is_superseded = 0`` — a search with no clock asks about
      what governs NOW, and superseded revisions must not spend top-k slots by
      default. A caller who wants history says so.
    """
    from portal.modules.compliance.core.section_index import _date_of

    v, k = _date_of(valid_at), _date_of(known_at)
    entries: list[Any] = []
    if standard:
        entries.append(_contains_group("logical_id", standard))
    if layer:
        entries.append(_contains_group("source_kind", layer))
    if v:
        entries.append([("effective_from", "=", ""), ("effective_from", "<=", v)])
        entries.append([("effective_to", "=", ""), ("effective_to", ">", v)])
    if k:
        entries.append([("recorded_from", "=", ""), ("recorded_from", "<=", k)])
        entries.append([("recorded_to", "=", ""), ("recorded_to", ">", k)])
    if not v and not k:
        entries.append(("is_superseded", "=", 0))
    if extra is not None:
        # P4.1: the requirement's exact section ids, composed with the clocks by
        # AND. Exact, so no substring hazard, and no schema change.
        entries.append(extra)
    return predicates.build(entries)


#: The largest ``chunk_id IN (…)`` list pushed into the arms.
#:
#: MEASURED, and the measurement says something other than what §P4.1 expected.
#: Timed against the live 4,477-row ``nerc_corpus`` at 10 / 100 / 500 / 1000 /
#: 2000 / 3000 / 4000 ids, prefiltered, the median was 5.9 / 8.5 / 12.0 / 19.7 /
#: 26.0 / 32.4 ms against a 4.9 ms clock-only baseline — **linear, with no knee**
#: even at an id list naming every row in the table. There is no latency turn to
#: set a cap from.
#:
#: So the cap comes from the population instead: across the 252 joined
#: requirements the sections-per-requirement distribution is median 3, p90 35,
#: max 97. 500 sits five times above the observed maximum at 8.5 ms, so it never
#: refuses a real requirement — it refuses a request that has stopped being a
#: requirement and become a whole standard. Both numbers are in
#: reports/compliance/ONE_REGULATORY_EXTRACTION_V1.md.
#:
#: Above it the tool returns honest-BLOCKED naming the count, because a silent
#: fallback to an unfiltered search would LOOK filtered, which is worse than
#: refusing.
MAX_REQUIREMENT_SECTION_IDS = 500


def requirement_predicate(repo: Any, requirement: str, relations: tuple[str, ...]) -> Any:
    """Resolve a requirement to exact section ids, two-step (P4.1).

    **No new predicate column.** A section bears several relations to a
    requirement and can bear on several requirements, so a multi-value index
    column would need ``LIKE`` matching on ids — and ``'CIP-007-6 R2'`` is a
    substring of ``'CIP-007-6 R2 Part 2.2'``, so ``LIKE`` is wrong here, not
    merely inelegant. Repeated index rows are also out: they break
    ``chunk_id = section_id``, the identity BILATERAL_CORPUS_V1 P4 unified.

    So: resolve in SQLite through the join, then push exact ids as
    ``chunk_id IN (…)``, which composes with the clock clauses by ``AND``.

    Returns ``(entry, section_ids, blocked)``. ``blocked`` is a populated
    honest-BLOCKED payload when the requirement resolves to nothing or to more
    ids than the measured ceiling.
    """
    from portal.modules.compliance.core import requirement_scope

    # P4.3: the whole scope, both sides. An exact match on a parent requirement
    # resolved to nothing (its Parts hold every anchor and every edge), and a
    # pool built from `sections_for_requirement` alone is the REGULATORY side
    # only — so scoping a bilateral search to a requirement used to discard
    # every operator hit it was meant to find.
    scope = requirement_scope.population(repo, requirement, relations=relations)
    section_ids = list(scope["section_ids"])
    if not section_ids:
        misses = [
            m
            for m in repo.anchor_misses()
            if str(m["requirement_id"]) in set(scope["scope"]["leaves"]) | {requirement}
        ]
        return (
            None,
            [],
            {
                "signal": "honest-BLOCKED",
                "detail": (
                    f"{requirement!r} resolves to no section through the requirement join"
                    + (
                        f" — it is recorded UNANCHORED: {misses[0]['reason']}"
                        if misses
                        else " — it is not a requirement this store carries"
                    )
                ),
                "requirement": requirement,
                "relations": list(relations),
                "unanchored": misses,
            },
        )
    if len(section_ids) > MAX_REQUIREMENT_SECTION_IDS:
        return (
            None,
            section_ids,
            {
                "signal": "honest-BLOCKED",
                "detail": (
                    f"{requirement!r} resolves to {len(section_ids)} sections, above the "
                    f"measured pushdown ceiling of {MAX_REQUIREMENT_SECTION_IDS}. Ask for a "
                    "narrower requirement (a Part rather than a whole standard) — this tool "
                    "will not silently fall back to an unfiltered search, which would look "
                    "filtered."
                ),
                "requirement": requirement,
                "section_count": len(section_ids),
                "ceiling": MAX_REQUIREMENT_SECTION_IDS,
            },
        )
    return (("in", "chunk_id", section_ids), section_ids, None)


def filter_notes(valid_at: str, known_at: str) -> list[str]:
    """What the pushed-down filter excluded, said in the payload.

    A pushdown filter cannot enumerate what it filtered out — the rows never
    come back. The exclusion CLASSES are still stated, in the same vocabulary
    the post-filter used, so a short result list is explainable instead of
    mysterious (UNKNOWN_KNOWLEDGE is the late-recorded shape's name and stays).
    """
    notes: list[str] = []
    if valid_at:
        notes.append(
            f"revisions not in force at {valid_at} were excluded below ranking "
            "(not effective yet, or inactive by then)"
        )
    if known_at:
        notes.append(
            f"UNKNOWN_KNOWLEDGE: revisions first recorded after {known_at} were excluded "
            "below ranking — the store did not know them then"
        )
    if not valid_at and not known_at:
        notes.append(
            "superseded revisions were excluded by default (is_superseded = 0); "
            "pass valid_at or known_at to query history"
        )
    return notes


def clock_addressed(
    addressed: list[dict[str, Any]], valid_at: str, known_at: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Clock-check the addressed hits, keeping the per-hit reasons.

    An addressed hit is resolved directly from the store, past the search
    arms, so the clocks must be applied to it here — with the reason string
    the pushdown path cannot carry. UNKNOWN_KNOWLEDGE survives verbatim in
    ``excluded`` through this function.
    """
    if not (valid_at or known_at):
        return addressed, []
    kept: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for a in addressed:
        ok, why = _within_clocks(a, valid_at, known_at)
        if ok:
            kept.append(a)
        else:
            excluded.append({"section_id": a.get("section_id"), "why": why})
    return kept, excluded


def search(
    repo: Any,
    query: str,
    jurisdiction: str = "",
    standard: str = "",
    layer: str = "",
    valid_at: str = "",
    known_at: str = "",
    requirement: str = "",
    relations: str = "governing",
    top_k: int = 10,
    max_chars: int = 4000,
) -> dict[str, Any]:
    """Ranked sections across BOTH corpora — regulatory and operator together.

    Every hit's ``section_id`` resolves to a canonical ``source_sections`` row
    (BILATERAL_CORPUS_V1 P4), so a result can be read, cited, linked and
    followed. Text is verbatim up to ``max_chars`` with truncation stated.
    ``jurisdiction`` is ``US`` / ``internal`` / ``operator_note``; ``standard``
    and ``layer`` filter by document; both clocks are honoured.

    ONE_REGULATORY_EXTRACTION_V1 P4 — ``requirement`` narrows by IDENTITY:
    ``"CIP-007-6 R2 Part 2.2"`` resolves through the requirement scope to exact
    section ids, pushed as ``chunk_id IN (…)`` BEFORE ranking. Not a ``LIKE``:
    ``'CIP-007-6 R2'`` is a substring of ``'CIP-007-6 R2 Part 2.2'`` and of
    ``'CIP-007-6 R20'``, so substring matching would be wrong here, not merely
    inelegant — a parent reaches its Parts through the register (P4.3), never
    through string shape. The pool is BILATERAL: the requirement's anchors and
    the operator sections recorded as related to it.
    ``relations`` is a comma-separated subset of ``governing`` / ``measure`` /
    ``applicable_systems`` / ``technical_basis`` and narrows WHICH of the
    requirement's material is asked for — it never bars a passage from an
    unscoped search. Every hit then carries ``requirement_id``, ``relation``,
    ``vrf``, ``time_horizon`` and ``applicable_systems``, so a passage arrives
    knowing what it governs and how.

    SUBSTRATE_PROPERTIES_V1 P3 — property 1: every filter is pushed DOWN as a
    ``.where()`` predicate and applied BEFORE ranking, so a filter can target
    the search rather than shrink its aftermath. ``filter_applied`` carries the
    clause that ran and ``filter_notes`` the exclusion classes; ``excluded`` no
    longer lists sieve rejects (there is no sieve) — it lists hits that do not
    resolve in the canonical store, which is an integrity signal.
    """
    from portal.modules.compliance.core import section_index
    from portal.modules.compliance.tools.compliance_retrieval import search as _kb_search

    # An exact address is an ADDRESS, not a search. Resolving it directly
    # beats hoping the sparse arm ranks it first: a requirements-table row's
    # verbatim text is "2.2 | High Impact ... " and never contains the
    # string "CIP-007-6 R2 Part 2.2", so lexical matching on the full
    # address is luck. Addressed hits lead, labelled as addressed.
    addressed = _addressed_hits(repo, query, max_chars)
    addressed, addressed_excluded = clock_addressed(addressed, valid_at, known_at)

    requirement_entry, requirement_sections, blocked = (None, [], None)
    if requirement:
        wanted = tuple(r.strip() for r in relations.split(",") if r.strip()) or ("governing",)
        requirement_entry, requirement_sections, blocked = requirement_predicate(
            repo, requirement, wanted
        )
        if blocked:
            return {"query": query, "num_results": 0, "results": [], **blocked}

    where = search_predicate(
        standard=standard,
        layer=layer,
        valid_at=valid_at,
        known_at=known_at,
        extra=requirement_entry,
    )

    corpora = (
        [section_index.CORPUS_FOR_JURISDICTION[jurisdiction]]
        if jurisdiction in section_index.CORPUS_FOR_JURISDICTION
        else list(dict.fromkeys(section_index.CORPUS_FOR_JURISDICTION.values()))
    )
    hits: list[dict[str, Any]] = []
    searched, unavailable = [], []
    filter_report: dict[str, Any] = {}
    for kb_id in corpora:
        try:
            body = asyncio.run(_kb_search(kb_id, query, max(top_k, 3), where=where))
        except Exception as exc:  # noqa: BLE001 - an absent corpus is reported
            unavailable.append({"kb_id": kb_id, "detail": str(exc)})
            continue
        searched.append(kb_id)
        if body.get("filter_report"):
            filter_report[kb_id] = body["filter_report"]
        for row in body.get("results", []):
            row["kb_id"] = kb_id
            hits.append(row)
    hits.sort(key=lambda r: -float(r.get("fused_score", 0) or 0))

    resolved = section_index.resolve_sections(repo, [str(h.get("chunk_id", "")) for h in hits])
    out: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    addressed_ids = {a["section_id"] for a in addressed}
    for hit in hits:
        section_id = section_index.parent_section_id(str(hit.get("chunk_id", "")))
        entry = resolved.get(section_id)
        if entry is None:
            excluded.append(
                {
                    "chunk_id": hit.get("chunk_id"),
                    "why": "does not resolve in the canonical store",
                }
            )
            continue
        text, note = _clip(entry.get("text", ""), max_chars)
        if section_id in addressed_ids:
            continue
        out.append(
            {
                **_provenance(entry),
                "kb_id": hit.get("kb_id"),
                "match": "retrieval",
                "score": hit.get("fused_score"),
                "text": _with_cite_header(entry, text),
                **note,
            }
        )
        if len(out) + len(addressed) >= top_k:
            break
    out = addressed + out
    return {
        "query": query,
        "addressed": len(addressed),
        "corpora_searched": searched,
        "corpora_unavailable": unavailable,
        "valid_at": valid_at or "latest effective",
        "known_at": known_at or "latest recorded knowledge",
        "filter_applied": where,
        "requirement": requirement,
        "requirement_relations": (
            [r.strip() for r in relations.split(",") if r.strip()] if requirement else []
        ),
        # the candidate pool the ARMS scored, not the result count. A caller
        # checking that identity-scoping worked has to be able to see the
        # pool it narrowed to, not infer it from how many rows came back.
        "requirement_pool": requirement_sections,
        "filter_notes": filter_notes(valid_at, known_at)
        + (
            [
                f"scoped to {len(requirement_sections)} section(s) joined to "
                f"{requirement!r} — the arms scored only those"
            ]
            if requirement
            else []
        ),
        "filter_report": filter_report,
        "excluded_meaning": (
            "hits that do not resolve to a canonical source_sections row — an "
            "integrity signal, not a filter rejection (filters run below ranking)"
        ),
        "num_results": len(out),
        "results": out,
        "excluded": addressed_excluded + excluded,
    }
