"""One identity space: the retrieval index as a projection of the section store
(BILATERAL_CORPUS_V1 P4).

Before this, retrieval and the canonical store were **parallel extractions of
the same documents**. 68 internal documents existed as 2,508 classified
``source_sections`` with ``isection-…`` ids, and as 2,636 docling chunks with
sha1 ids, and the intersection of those two id sets was **empty**. A hit could
not be resolved to a section; a section could not be found by search;
``_boundary_proof_id``'s ``set(examined_sections) == {chunk_id}`` check could
never pass, because the two sets came from different worlds.

The fix is not to reconcile them. It is to stop having two: the canonical
``source_sections`` row is the unit of reference for **both** jurisdictions, and
the index is emitted from it, at section granularity, with
``chunk_id = section_id``. No change to the shared Arrow schema — the existing
field carries the identity.

**Splitting is a projection detail, never a new identity.** A section longer
than the embedding window becomes ordered sub-units ``<section_id>#<n>`` that
still resolve to the parent through :func:`parent_section_id`.

**A section is projectable only if its text can be produced verbatim.** That
means a captured coordinate space (``document_texts``) it has a span into.
Pre-P1 sections have neither, so they are reported as unprojectable and named —
an index that silently omits part of the declared population cannot support an
absence claim, which is the whole reason this phase exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: characters per indexable unit. The VL embedder truncates a long input rather
#: than failing, so an unsplit 77k-character section would be indexed as its
#: first few thousand characters with the rest silently unreachable.
MAX_UNIT_CHARS = 6000

#: The predicate columns every projected row carries on top of the base nine
#: (TASK_COMPLIANCE_SUBSTRATE_PROPERTIES_V1 P1). Property 1 — temporal validity
#: filters *before* ranking — was not expressible until the index held something
#: to push a ``.where()`` predicate onto: the projected row carried none of the
#: fields the post-filter read, so every clock and document filter ran as a
#: SQLite lookup *after* retrieval had already returned. Each column is a flat
#: scalar because a LanceDB predicate cannot traverse structure, and each is
#: copied from the canonical store — a second derivation is how the identity
#: spaces diverged before P4 unified them.
#:
#: ``effective_from``/``effective_to``/``recorded_from``/``recorded_to`` are
#: zero-padded ``YYYY-MM-DD`` or ``""`` — never ``None``, never a mixed format —
#: because a ``.where()`` string compares lexicographically and a ``NULL``
#: comparison silently excludes the row. An OPEN bound is ``""``, so a
#: "still in force" predicate is written against ``""`` explicitly; the wrong
#: choice here hides *current* material rather than superseded material.
PREDICATE_COLUMNS: tuple[str, ...] = (
    "jurisdiction",
    "logical_id",
    "revision_id",
    "source_kind",
    "effective_from",
    "effective_to",
    "recorded_from",
    "recorded_to",
    "is_superseded",
    "unit_kind",
    # P4: a document's recorded authority tier, as "0".."4" — or "" when the
    # document carries no recorded tier, which must stay VISIBLE (an untiered
    # document is never silently a Tier 3 or a Tier 4).
    "authority_tier",
)

#: the corpus each jurisdiction projects into. Both sit under the ``compliance_``
#: table prefix, so ``search_all`` spans them.
CORPUS_FOR_JURISDICTION: dict[str, str] = {
    "internal": "operator_corpus",
    "US": "nerc_corpus",
    # P5: an operator note is a source like any other, so it projects like one.
    "operator_note": "operator_notes",
    # P6: a stored answer is one analyst's notes pinned to the revisions it
    # read. Retrievable and contestable, never promoted to a fact.
    "derived": "conversation",
}


@dataclass(frozen=True)
class IndexableUnit:
    """One row destined for the retrieval index, carrying its own identity."""

    chunk_id: str
    section_id: str
    kb_id: str
    source_file: str
    chunk_index: int
    text: str
    headings: str
    page: int
    char_start: int
    char_end: int
    # the predicate columns (P1): the store's own answer to "what is this row",
    # copied verbatim so a filter can run BEFORE ranking.
    jurisdiction: str = ""
    logical_id: str = ""
    revision_id: str = ""
    source_kind: str = ""
    effective_from: str = ""
    effective_to: str = ""
    recorded_from: str = ""
    recorded_to: str = ""
    is_superseded: int = 0
    unit_kind: str = ""
    authority_tier: str = ""

    def as_row(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "kb_id": self.kb_id,
            "source_file": self.source_file,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "page": self.page,
            "headings": self.headings,
            **{c: getattr(self, c) for c in PREDICATE_COLUMNS},
        }


@dataclass
class ProjectionPlan:
    """What a projection will index, and what it cannot — all of it named.

    Three populations, kept apart because they mean different things:

    * ``eligible_sections`` — the declared corpus. A revision's CAPTURE is a
      total cover of that revision (100% of its characters, no gap, no overlap),
      so for a captured revision the captured sections ARE the population.
    * ``superseded_sections`` — pre-capture sections on a revision that now has
      a capture. They are a second extraction of the same bytes, which is the
      duplication this phase exists to remove. Not eligible, and counted.
    * ``uncaptured_revisions`` — revisions with no capture at all. Their
      documents are not in the corpus yet. Not eligible, named by document, and
      the corpus cannot be declared whole while any remain.
    """

    kb_id: str
    jurisdiction: str
    units: list[IndexableUnit] = field(default_factory=list)
    eligible_sections: list[str] = field(default_factory=list)
    unprojectable: list[dict[str, str]] = field(default_factory=list)
    superseded_sections: list[str] = field(default_factory=list)
    uncaptured_revisions: list[dict[str, str]] = field(default_factory=list)

    @property
    def examined_sections(self) -> list[str]:
        return sorted({u.section_id for u in self.units})


def parent_section_id(chunk_id: str) -> str:
    """The section a hit belongs to. A split sub-unit resolves to its parent."""
    return chunk_id.split("#", 1)[0]


def split_text(text: str, limit: int = MAX_UNIT_CHARS) -> list[str]:
    """Ordered pieces of at most ``limit`` characters, split on a paragraph or
    sentence boundary where one is available so a sub-unit is still readable."""
    if len(text) <= limit:
        return [text]
    pieces: list[str] = []
    rest = text
    while len(rest) > limit:
        window = rest[:limit]
        cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(". "))
        if cut < limit // 2:
            cut = limit
        elif window[cut : cut + 2] == ". ":
            cut += 2
        pieces.append(rest[:cut])
        rest = rest[cut:]
    if rest:
        pieces.append(rest)
    return pieces


def _heading_of(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("heading_path") or ""),
        str(row.get("title") or ""),
        str(row.get("path") or ""),
    ]
    seen: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    return " > ".join(seen)


def _span_of(entry: dict[str, Any]) -> tuple[int, int]:
    """``(char_start, char_end)``, treating an absent value as -1.

    Written out rather than ``int(x or -1)``: the FIRST section of every
    document starts at offset 0, and ``0 or -1`` is -1, which silently
    classified it as unanchored.
    """
    start = entry.get("char_start")
    end = entry.get("char_end")
    return (int(start) if start is not None else -1, int(end) if end is not None else -1)


def _date_of(value: Any) -> str:
    """A clock column as a lexicographically comparable ``YYYY-MM-DD``, or ``""``.

    ``recorded_from`` is a full timestamp in the store (``2026-09-05T13:12:41…``);
    left whole it would never compare ``<=`` to a ``known_at`` date —
    ``"2026-09-05T13:…" <= "2026-09-05"`` is false because the longer string
    sorts after its own prefix. Truncated, every date column is
    ``YYYY-MM-DD`` or empty, which is the only shape a ``.where()`` predicate
    can compare. An absent value is ``""`` (an open bound), never ``None``.
    """
    text = str(value or "")
    return text[:10] if len(text) >= 10 and text[4] == "-" and text[7] == "-" else ""


def _governing_revisions(repo: Any, jurisdiction: str) -> set[str]:
    """The revision_id of each document that governs its document *now*.

    The index holds every captured revision — history is answerable — so the
    row needs a cheap marker for "this revision has been replaced".
    ``plan.superseded_sections`` names pre-capture sections duplicating bytes
    the capture already covers, and those are not projected; the superseded
    population that IS in the index is a document's non-governing revisions
    (the old Glossary revision, a retired lifecycle). The selection rule is
    the store's own, the same one :func:`reading_assembly._revision_for` uses:
    newest live revision by ``(effective_date, retrieved_at)``, else the newest
    revision at all — derived from the store's columns, never re-derived from
    filenames or section text.
    """
    rows = repo._conn.execute(
        """SELECT r.revision_id, r.logical_id, r.effective_date, r.inactive_date, r.retrieved_at
           FROM document_revisions r
           JOIN source_documents d ON d.logical_id = r.logical_id
           WHERE d.jurisdiction = ?
           ORDER BY r.logical_id, COALESCE(r.effective_date, ''), r.retrieved_at""",
        (jurisdiction,),
    ).fetchall()
    today = _today()
    governing: dict[str, str] = {}
    latest: dict[str, str] = {}
    live: dict[str, str] = {}
    for row in rows:
        revision_id, logical_id = str(row[0]), str(row[1])
        effective = str(row[2] or "")
        inactive = str(row[3] or "")
        latest[logical_id] = revision_id
        if effective and not (inactive and inactive <= today):
            live[logical_id] = revision_id
    for logical_id, revision_id in live.items():
        governing[logical_id] = revision_id
    for logical_id, revision_id in latest.items():
        governing.setdefault(logical_id, revision_id)
    return set(governing.values())


def _today() -> str:
    from portal.modules.compliance.core.temporal import now_iso

    return now_iso()[:10]


def build_plan(repo: Any, *, jurisdiction: str, kb_id: str = "") -> ProjectionPlan:
    """Every canonical section of one jurisdiction, as indexable units.

    The eligible population is every section of every document in the
    jurisdiction. The examined population is those actually projected. A section
    that cannot yield verbatim text is in the first and not the second, and the
    reason is recorded — never dropped silently.

    Every unit carries the predicate columns (P1): the jurisdiction, document,
    revision, source kind, both clocks, supersession and unit kind, copied from
    the canonical store so a query can filter BEFORE ranking instead of sieving
    the results afterwards.
    """
    kb_id = kb_id or CORPUS_FOR_JURISDICTION.get(jurisdiction, jurisdiction)
    plan = ProjectionPlan(kb_id=kb_id, jurisdiction=jurisdiction)
    governing = _governing_revisions(repo, jurisdiction)
    from portal.modules.compliance.core.tiers import recorded_tier

    tier_of: dict[str, str] = {}

    def _tier(logical_id: str, source_kind: str) -> str:
        if logical_id not in tier_of:
            tier_of[logical_id] = recorded_tier(logical_id, source_kind)
        return tier_of[logical_id]

    rows = repo._conn.execute(
        """SELECT s.section_id, s.revision_id, s.path, s.title, s.heading_path,
                  s.page_start, s.char_start, s.char_end, s.unit_kind, s.ordinal,
                  r.alias_path, r.effective_date, r.inactive_date,
                  r.recorded_from, r.recorded_to,
                  d.logical_id, d.source_kind, d.jurisdiction
           FROM source_sections s
           JOIN document_revisions r ON r.revision_id = s.revision_id
           JOIN source_documents d ON d.logical_id = r.logical_id
           WHERE d.jurisdiction = ?
           ORDER BY d.logical_id, r.revision_id, s.ordinal, s.section_id""",
        (jurisdiction,),
    ).fetchall()

    texts: dict[str, str] = {}
    uncaptured: dict[str, str] = {}
    for row in rows:
        entry = dict(row)
        section_id = str(entry["section_id"])
        revision_id = str(entry["revision_id"])
        if revision_id not in texts:
            texts[revision_id] = repo.get_document_text(revision_id) or ""
        full = texts[revision_id]
        start, end = _span_of(entry)
        if not full:
            # the revision has no capture: the DOCUMENT is not in the corpus yet
            uncaptured[revision_id] = str(entry["logical_id"])
            continue
        if start < 0:
            # a pre-capture section on a revision that now has one. The capture
            # covers the same bytes completely, so this row is superseded, not
            # missing.
            plan.superseded_sections.append(section_id)
            continue
        plan.eligible_sections.append(section_id)
        if end <= start or end > len(full):
            plan.unprojectable.append(
                {
                    "section_id": section_id,
                    "reason": f"span [{start}, {end}) does not resolve in the captured text",
                }
            )
            continue
        body = full[start:end]
        if not body.strip():
            plan.unprojectable.append({"section_id": section_id, "reason": "span is whitespace"})
            continue
        headings = _heading_of(entry)
        pieces = split_text(body)
        for n, piece in enumerate(pieces):
            offset = sum(len(p) for p in pieces[:n])
            plan.units.append(
                IndexableUnit(
                    chunk_id=section_id if len(pieces) == 1 else f"{section_id}#{n}",
                    section_id=section_id,
                    kb_id=kb_id,
                    source_file=str(entry["alias_path"] or entry["logical_id"]),
                    chunk_index=len(plan.units),
                    text=piece,
                    headings=headings,
                    page=int(entry["page_start"] or 0),
                    char_start=start + offset,
                    char_end=start + offset + len(piece),
                    jurisdiction=str(entry["jurisdiction"] or ""),
                    logical_id=str(entry["logical_id"] or ""),
                    revision_id=revision_id,
                    source_kind=str(entry["source_kind"] or ""),
                    effective_from=_date_of(entry["effective_date"]),
                    effective_to=_date_of(entry["inactive_date"]),
                    recorded_from=_date_of(entry["recorded_from"]),
                    recorded_to=_date_of(entry["recorded_to"]),
                    is_superseded=0 if revision_id in governing else 1,
                    unit_kind=str(entry["unit_kind"] or ""),
                    authority_tier=_tier(str(entry["logical_id"] or ""), str(entry["source_kind"] or "")),
                )
            )
    plan.uncaptured_revisions = [
        {"revision_id": rid, "logical_id": logical} for rid, logical in sorted(uncaptured.items())
    ]
    return plan


def boundary_receipt(
    repo: Any,
    plan: ProjectionPlan,
    *,
    scope_sections: list[str] | None = None,
    index_generation: str = "",
) -> dict[str, Any]:
    """The boundary, as a fact rather than as a fixture (P4.6).

    ``eligible_sections`` is every section in the declared corpus;
    ``examined_sections`` is those projected and searchable;
    ``document_revision_hashes`` come from the store. ``complete`` is true only
    when the two sets are equal — which is exactly the claim an absence rests
    on, and which was previously unprovable because no production code path ever
    emitted this at all.

    ``scope_sections`` narrows the declared population to a requested subset
    (one standard, one requirement's neighbourhood); the receipt is complete
    when every section in THAT population was examined.
    """
    eligible = set(plan.eligible_sections)
    examined = set(plan.examined_sections)
    if scope_sections is not None:
        scope = set(scope_sections)
        eligible &= scope
        examined &= scope
    omissions = sorted(eligible - examined)
    revision_hashes = {
        str(row[0]): str(row[1])
        for row in repo._conn.execute(
            """SELECT DISTINCT r.logical_id, r.revision_id
               FROM document_revisions r
               JOIN source_documents d ON d.logical_id = r.logical_id
               WHERE d.jurisdiction = ?""",
            (plan.jurisdiction,),
        ).fetchall()
    }
    return {
        "kb_id": plan.kb_id,
        "jurisdiction": plan.jurisdiction,
        "acquisition_mode": "RETRIEVAL",
        "index_generation": index_generation,
        "eligible_sections": sorted(eligible),
        "examined_sections": sorted(examined),
        "document_revision_hashes": revision_hashes,
        "omissions": omissions,
        "omission_reasons": [
            entry for entry in plan.unprojectable if entry["section_id"] in set(omissions)
        ],
        "superseded_sections": len(plan.superseded_sections),
        "documents_not_captured": sorted({r["logical_id"] for r in plan.uncaptured_revisions}),
        # whole means: every eligible section examined, AND no document of this
        # jurisdiction still waiting to be captured. A corpus missing a document
        # cannot carry an absence claim about the jurisdiction, only about the
        # documents it does hold.
        "complete": bool(eligible) and not omissions,
        "corpus_whole": bool(eligible) and not omissions and not plan.uncaptured_revisions,
    }


def section_population_fingerprint(repo: Any, jurisdiction: str = "") -> str:
    """A hash over the section population the index is a projection OF.

    ``projections.canonical_fingerprint`` hashes ``section_id || role``, which
    does not change when a section's TEXT changes. The retrieval manifest needs
    the stronger statement: this covers each section's identity, its span and
    its revision, so a re-capture that moves a boundary marks the index STALE.

    Fingerprinted **per jurisdiction** by default, because the corpora are
    projected independently. A store-wide hash makes writing one operator note
    mark the regulatory index stale, which is false and trains people to ignore
    the signal. Pass no jurisdiction for the whole population.
    """
    import hashlib
    import json

    clause = "WHERE d.jurisdiction = ?" if jurisdiction else ""
    params = (jurisdiction,) if jurisdiction else ()
    rows = repo._conn.execute(
        f"""SELECT s.section_id, s.revision_id, s.char_start, s.char_end, s.unit_kind
            FROM source_sections s
            JOIN document_revisions r ON r.revision_id = s.revision_id
            JOIN source_documents d ON d.logical_id = r.logical_id
            {clause}
            ORDER BY s.section_id""",  # noqa: S608 - fixed clause, parameterised value
        params,
    ).fetchall()
    digest = hashlib.sha256()
    digest.update(json.dumps([list(map(str, r)) for r in rows], separators=(",", ":")).encode())
    return digest.hexdigest()


# ── resolution: a section id back to its verbatim text and provenance ───────


def resolve_sections(repo: Any, section_ids: list[str]) -> dict[str, dict[str, Any]]:
    """``section_id -> verbatim text plus everything needed to cite it``.

    This is the other half of one identity space: a search hit, a boundary
    receipt entry, a stored answer's citation and an operator's note all name a
    ``section_id``, and all of them resolve here. A sub-unit id
    (``<section_id>#<n>``) resolves to its parent section — splitting is a
    projection detail.

    An id that does not resolve is simply absent from the result. The caller
    reports it as unresolvable; this function never invents a row.
    """
    wanted = {parent_section_id(str(s)) for s in section_ids if s}
    if not wanted:
        return {}
    out: dict[str, dict[str, Any]] = {}
    texts: dict[str, str] = {}
    marks = ",".join("?" for _ in wanted)
    rows = repo._conn.execute(
        f"""SELECT s.section_id, s.revision_id, s.path, s.title, s.heading_path, s.role,
                   s.unit_kind, s.ordinal, s.page_start, s.page_end, s.char_start, s.char_end,
                   s.table_ref, s.extractor,
                   r.alias_path, r.logical_id, r.effective_date, r.approved_date,
                   r.inactive_date, r.version, r.document_number, r.lifecycle_status,
                   r.recorded_from, r.recorded_to,
                   d.title AS document_title, d.source_kind, d.jurisdiction, d.issuer
            FROM source_sections s
            JOIN document_revisions r ON r.revision_id = s.revision_id
            JOIN source_documents d ON d.logical_id = r.logical_id
            WHERE s.section_id IN ({marks})""",  # noqa: S608 - placeholders only
        tuple(sorted(wanted)),
    ).fetchall()
    for row in rows:
        entry = dict(row)
        revision_id = str(entry["revision_id"])
        if revision_id not in texts:
            texts[revision_id] = repo.get_document_text(revision_id) or ""
        full = texts[revision_id]
        start, end = _span_of(entry)
        entry["text"] = full[start:end] if full and 0 <= start < end <= len(full) else ""
        entry["headings"] = _heading_of(entry)
        entry["resolvable"] = bool(entry["text"])
        # P4: a section always arrives labelled with its authority — "" is
        # untiered and stays visible as untiered.
        from portal.modules.compliance.core.tiers import recorded_tier

        entry["authority_tier"] = recorded_tier(
            str(entry["logical_id"] or ""), str(entry["source_kind"] or "")
        )
        out[str(entry["section_id"])] = entry
    return out


def sections_in_scope(
    repo: Any,
    *,
    jurisdiction: str = "",
    logical_id: str = "",
    revision_id: str = "",
    path_prefix: str = "",
) -> list[str]:
    """Every section id matching a declared scope, in reading order.

    This is what makes a boundary receipt a claim about something: the scope is
    stated as a query over the store, the population is whatever that query
    returns, and the receipt says so.
    """
    clauses, params = ["s.char_start >= 0"], []
    if jurisdiction:
        clauses.append("d.jurisdiction = ?")
        params.append(jurisdiction)
    if logical_id:
        clauses.append("d.logical_id = ?")
        params.append(logical_id)
    if revision_id:
        clauses.append("s.revision_id = ?")
        params.append(revision_id)
    if path_prefix:
        clauses.append("(s.path LIKE ? OR s.heading_path LIKE ? OR s.title LIKE ?)")
        params.extend([f"%{path_prefix}%"] * 3)
    rows = repo._conn.execute(
        f"""SELECT s.section_id FROM source_sections s
            JOIN document_revisions r ON r.revision_id = s.revision_id
            JOIN source_documents d ON d.logical_id = r.logical_id
            WHERE {" AND ".join(clauses)}
            ORDER BY d.logical_id, s.revision_id, s.ordinal, s.section_id""",  # noqa: S608
        tuple(params),
    ).fetchall()
    return [str(r[0]) for r in rows]
