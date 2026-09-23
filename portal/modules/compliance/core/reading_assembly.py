"""The reading assembly (BILATERAL_CORPUS_V1 P5).

What replaces the top-k keyhole. Fifteen chunks out of two thousand, each
truncated at 180 characters, under a prompt claiming the operator's material is
present in full, is not a reading — it is a guess with citations attached. For a
51-page standard a requirement's neighbourhood is a handful of pages. That is
affordable, and assembling it is arithmetic, not judgement.

**Deterministic.** Everything here is gathered by *document structure* and by
*recorded graph edges*. No relevance score decides what a requirement's
neighbourhood contains, and no model call happens in this module.

**Addressing is not interpretation.** Selecting the sections that sit under
``Guidelines and Technical Basis > Requirement R2:``, or the compliance-table
rows whose first cell is ``R2``, reads the document's **own outline and own
numbering**. It does not decide what any passage means; that is read at question
time by a model that has been handed all of it.

**Nothing is marked ineligible to cite.** The Guidelines and Technical Basis is
in the assembly on the same terms as the requirement text, labelled with what it
is and where it came from. Weight is the reader's call, stated in the answer.

**Omissions are named.** When the budget cannot hold a component, the component
is listed in ``omitted`` with its size, so the reader knows what it has not seen
rather than silently believing it saw everything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: Characters per token, for budgeting. Deliberately crude and stated: a real
#: tokenizer would make the budget exact for one model and wrong for the next.
#:
#: **Measured, not assumed.** The obvious 4.0 — fine for ordinary English — is
#: wrong for this material by nearly 2x, and the error is dangerous in one
#: direction only: it under-counts, so a window sized from it is too SMALL and
#: the material is silently truncated, which is the top-k keyhole returning
#: through the back door. Measured on the live CIP-007-6 R2 Part 2.2 assembly
#: against the runner's own ``prompt_eval_count``: 63,500 characters tokenised
#: to 29,353 tokens = **2.16 chars/token**. Dense regulatory prose is part of
#: it; the larger part is that every passage carries a section id, and
#: ``csection-7afa10cdad0b38ae102e`` is 29 characters and about 12 tokens.
#:
#: 2.1 is used rather than 2.16 so the estimate errs HIGH — over-reserving a
#: window costs memory, under-reserving costs the answer.
#:
#: :func:`core.reader.read` checks the estimate against the runner's real
#: ``prompt_eval_count`` on every call and reports a mismatch, so this constant
#: cannot quietly drift away from the corpus it was measured on.
CHARS_PER_TOKEN = 2.1

DEFAULT_BUDGET_TOKENS = 60_000

_REF_RE = re.compile(
    r"^(?P<standard>CIP-\d{3}-[\w.]+)"
    r"(?:\s+R(?P<requirement>\d+))?"
    r"(?:\s+Attachment\s+(?P<attachment>\d+))?"
    r"(?:\s+(?:Part\s+(?P<part>\d+(?:\.\d+)*)|Section\s+(?P<section>\d+)))?\s*$",
    re.I,
)

#: The standard's own shorthand: ``R2.4`` for ``R2 Part 2.4``. CIP-007-6 R2.4
#: is written that way in the standard's own text — ``parse_ref`` rejected it
#: as "not a regulatory address" for the life of the module, which is how a
#: well-formed address became 30 of the sites' worth of "invalid" refusals.
_SHORTHAND_RE = re.compile(
    r"^(?P<standard>CIP-\d{3}-[\w.]+)\s+R(?P<requirement>\d+)\.(?P<part>\d+(?:\.\d+)*)\s*$",
    re.I,
)


@dataclass
class Ref:
    """A parsed regulatory address. ``requirement`` and ``part`` may be empty —
    a whole standard is a legitimate thing to read. ``attachment`` carries the
    CIP-002-style Attachment structure the register tracks as requirement nodes
    (COMPLIANCE_FAMILY_CENSUS_V1 §5 / A5): the categorisation method every other
    standard's applicability derives from is Attachment 1 Part N.N text, and a
    grammar that refused it left 26 of 33 CIP-002-5.1a nodes unreadable by the
    sweep — measured: every one skipped with "not a regulatory address"."""

    standard: str
    requirement: str = ""
    part: str = ""
    attachment: str = ""
    section: str = ""

    @property
    def logical_id(self) -> str:
        return f"NERC/{self.standard}"

    def __str__(self) -> str:
        tail = f" R{self.requirement}" if self.requirement else ""
        tail += f" Attachment {self.attachment}" if self.attachment else ""
        tail += f" Part {self.part}" if self.part else ""
        tail += f" Section {self.section}" if self.section else ""
        return f"{self.standard}{tail}"


def parse_ref(ref: str) -> Ref | None:
    """``CIP-007-6 R2 Part 2.2`` -> a :class:`Ref`. ``None`` when the string is
    not a regulatory address (it may still be a section id or a document).
    Attachment addresses parse too: ``CIP-002-5.1a Attachment 1 Part 2.3`` and
    ``CIP-002-5.1a Attachment 1 Section 1`` — the register carries them as
    requirement nodes, and ``str(Ref)`` round-trips to exactly those ids."""
    text = str(ref).strip()
    m = _REF_RE.match(text)
    if not m:
        shorthand = _SHORTHAND_RE.match(text)
        if shorthand is None:
            return None
        # Rewrite the shorthand into the canonical spelling and re-parse, so
        # there is exactly one place ("Part N.M") that constructs a Ref.
        m = _REF_RE.match(
            f"{shorthand.group('standard')} R{shorthand.group('requirement')} "
            f"Part {shorthand.group('requirement')}.{shorthand.group('part')}"
        )
        if m is None:
            return None
    # Normalise the FAMILY prefix (cip-007-6 -> CIP-007-6) and nothing else.
    # Uppercasing the whole id broke revision suffixes that carry case: the
    # register's `CIP-002-5.1a` became `CIP-002-5.1A`, which matches no
    # requirement_nodes row and no document revision — a whole standard
    # silently resolved to nothing (measured live, PROVE_THEN_SCALE_V1 §P7).
    standard = re.sub(
        r"^(cip-\d{3})", lambda match: match.group(1).upper(), m.group("standard"), flags=re.I
    )
    return Ref(
        standard=standard,
        requirement=m.group("requirement") or "",
        part=m.group("part") or "",
        attachment=m.group("attachment") or "",
        section=m.group("section") or "",
    )


@dataclass
class Component:
    """One named part of the assembly, with the sections that make it up."""

    name: str
    why: str
    sections: list[dict[str, Any]] = field(default_factory=list)

    @property
    def characters(self) -> int:
        return sum(len(str(s.get("text", ""))) for s in self.sections)

    @property
    def tokens(self) -> int:
        return int(self.characters / CHARS_PER_TOKEN)


# ── structural selection ────────────────────────────────────────────────────


def _revision_for(repo: Any, logical_id: str, valid_at: str = "") -> dict[str, Any] | None:
    """The revision of a document in force at ``valid_at`` (default: the latest
    effective one). Never a filename guess; the lifecycle is the workbook's."""
    rows = repo._conn.execute(
        """SELECT revision_id, effective_date, inactive_date, version, alias_path,
                  lifecycle_status
           FROM document_revisions WHERE logical_id = ?
           ORDER BY COALESCE(effective_date, ''), retrieved_at""",
        (logical_id,),
    ).fetchall()
    if not rows:
        return None
    candidates = [dict(r) for r in rows]
    if valid_at:
        for entry in candidates:
            effective = entry["effective_date"] or ""
            inactive = entry["inactive_date"] or ""
            if (not effective or effective <= valid_at) and (not inactive or valid_at < inactive):
                return entry
    live = [
        e
        for e in candidates
        if (e["effective_date"] or "") and not (e["inactive_date"] or "") <= _today()
    ]
    return (live or candidates)[-1]


def _today() -> str:
    from portal.modules.compliance.core.temporal import now_iso

    return now_iso()[:10]


def _sections(repo: Any, revision_id: str) -> list[dict[str, Any]]:
    from portal.modules.compliance.core.section_index import _heading_of, _span_of

    rows = repo._conn.execute(
        """SELECT section_id, path, title, heading_path, role, unit_kind, ordinal,
                  page_start, page_end, char_start, char_end, table_ref
           FROM source_sections WHERE revision_id = ? AND char_start >= 0
           ORDER BY ordinal""",
        (revision_id,),
    ).fetchall()
    full = repo.get_document_text(revision_id) or ""
    out: list[dict[str, Any]] = []
    for row in rows:
        entry = dict(row)
        start, end = _span_of(entry)
        entry["text"] = full[start:end] if 0 <= start < end <= len(full) else ""
        entry["headings"] = _heading_of(entry)
        entry["revision_id"] = revision_id
        out.append(entry)
    return out


def _under(sections: list[dict[str, Any]], *needles: str) -> list[dict[str, Any]]:
    """Sections whose heading lineage contains one of ``needles`` — the
    document's own outline, matched literally."""
    lowered = [n.lower() for n in needles]
    return [
        s for s in sections if any(n in str(s.get("heading_path", "")).lower() for n in lowered)
    ]


def _requirement_rows(
    sections: list[dict[str, Any]], requirement: str, part: str
) -> list[dict[str, Any]]:
    """The requirement's own table rows and prose, by the standard's numbering.

    A requirements table row's first cell is the Part number; a prose
    requirement's text opens with ``R<n>.``. Both are the document's own
    addressing.
    """
    if not requirement:
        return sections
    prefix = f"{requirement}."
    out: list[dict[str, Any]] = []
    for section in sections:
        text = str(section.get("text", ""))
        first_cell = text.split("|", 1)[0].strip()
        is_row = section.get("unit_kind") == "table_row" and first_cell.startswith(prefix)
        is_lead = bool(re.match(rf"^\s*R{requirement}\.", text))
        is_table = section.get("unit_kind") == "table" and re.search(
            rf"\bTable\s+R{requirement}\b", text
        )
        if is_row and part and first_cell != part:
            continue
        if is_row or is_lead or is_table:
            out.append(section)
    return out


def _vsl_rows(sections: list[dict[str, Any]], requirement: str) -> list[dict[str, Any]]:
    """Violation Severity Level rows for one requirement, from the compliance
    table. Selected by the row's own ``R<n>`` cell."""
    rows = _under(sections, "table of compliance elements", "violation severity")
    if not requirement:
        return rows
    wanted = f"r{requirement}"
    return [
        s
        for s in rows
        if s.get("unit_kind") != "table_row"
        or str(s.get("text", "")).split("|", 1)[0].strip().lower() in (wanted, requirement)
    ]


def linked_internal(repo: Any, ref: str, *, scope: Any = None) -> list[dict[str, Any]]:
    """Internal sections recorded as related to this requirement, in full.

    Read from ``relationship_assertions``; a proposed edge travels labelled as
    proposed, because an analyst asking *does what we do achieve this* needs to
    see the candidates as well as the confirmed ones, and needs to know which
    is which.

    **Across the whole scope.** The edges live on the identities the standard
    numbers, so an exact match on a parent requirement returns nothing while its
    Parts hold every edge there is (``CIP-007-6 R2``: 0 against 66). Each entry
    carries ``link_requirement`` — the leaf the edge was recorded against — so
    expanding the query never blurs which Part the operator's section answers.

    An edge's endpoint arrives in two recorded shapes: a bare ``section_id``
    and ``mapping_store``'s ``{document}::{section_id}`` — one identity space
    (BILATERAL_CORPUS_V1 P4) with two spellings. The tail after ``::`` is the
    section; on the live store every ``::``-shaped edge resolves through the
    tail and none through the raw value.
    """
    from portal.modules.compliance.core import requirement_scope
    from portal.modules.compliance.core.section_index import resolve_sections

    refs = (scope or requirement_scope.resolve(repo, ref)).refs
    marks = ",".join("?" for _ in refs)
    rows = repo._conn.execute(
        f"""SELECT src_ref, dst_ref, status, derivation, confidence, rationale
           FROM relationship_assertions
           WHERE src_ref IN ({marks}) AND status IN ('approved', 'proposed')""",  # noqa: S608
        tuple(refs),
    ).fetchall()
    edges = [dict(r) for r in rows]
    for edge in edges:
        _doc, sep, section = str(edge["dst_ref"]).partition("::")
        if sep and section:
            edge["dst_ref"] = section
    resolved = resolve_sections(repo, [str(e["dst_ref"]) for e in edges])
    out: list[dict[str, Any]] = []
    for edge in edges:
        entry = resolved.get(str(edge["dst_ref"]))
        if entry is None:
            continue
        out.append(
            {
                **entry,
                "link_requirement": edge["src_ref"],
                "link_status": edge["status"],
                "link_derivation": edge["derivation"],
                "link_derivations": [
                    part for part in str(edge.get("derivation") or "").split("|") if part
                ],
                "link_confidence": edge["confidence"],
            }
        )
    return out


# ── contradiction is a retrievable fact (SUBSTRATE_PROPERTIES_V1 P4) ────────

# A duration/modal mismatch is only a real COMPLIANCE_CONFLICT when the two
# compared spans are actually about the same obligation. Carried from
# ``coverage.py`` (whose verdict-engine cell file D retires — the guard itself
# must survive it): live on the real corpus, ``detect_conflicts`` flagged a
# password-rotation cadence against an unrelated sub-item's access-revocation
# deadline mentioned in the same paragraph of a genuinely relevant, locatable
# procedure chunk. Requiring the two spans to share this much topical
# vocabulary is a cheap, disclosed proxy for "same obligation" — not semantic
# understanding, but it closes the specific false-positive class observed live.
_CONFLICT_TOPIC_OVERLAP = 3


def _shares_topic(conflict: Any) -> bool:
    from portal.modules.compliance.core.text_signals import keywords

    overlap = keywords(conflict.higher.text) & keywords(conflict.lower.text)
    return len(overlap) >= _CONFLICT_TOPIC_OVERLAP


def conflicts_for_requirement(repo: Any, ref: str, *, valid_at: str = "") -> dict[str, Any]:
    """The cross-tier contradictions touching one requirement's neighbourhood.

    The detection logic is ``tiers.detect_conflicts``, unchanged — both spans,
    both tiers, both citations, emitted and **never reconciled**. What changed
    (SUBSTRATE_PROPERTIES_V1 P4) is where the result lives: not inside the
    coverage cell (retired in file D), but here, where the reader can reach it
    — a tool on its own and a component of every full assembly.

    The standard side of every comparison is the requirement's OWN table rows
    — never the Measures, never the Guidelines and Technical Basis. Both of
    those quote the standard's other Parts; comparing them against an operator
    procedure produced FALSE ``COMPLIANCE_CONFLICT``s live (a policy-review
    cadence flagged against an unrelated delegation deadline, and the standard
    appearing to disagree with itself). The Measures are example evidence, not
    duty text; a conflict detector that fires on the standard quoting itself is
    worse than none.

    An untiered operator document cannot take part in a CROSS-tier ruling —
    ranking it would fabricate the very authority the property refuses to
    invent — so it is listed under ``untiered_sections``, visibly, instead.
    """
    from portal.modules.compliance.core.tiers import Span, detect_conflicts

    parsed = parse_ref(ref)
    if parsed is None:
        return {"ref": ref, "error": f"{ref!r} is not a regulatory address"}
    revision = _revision_for(repo, parsed.logical_id, valid_at)
    if revision is None:
        return {"ref": ref, "error": f"{parsed.logical_id} is not in the store"}
    sections = _sections(repo, str(revision["revision_id"]))
    body = _under(sections, "requirements and measures") or sections
    req_sections = _requirement_rows(body, parsed.requirement, parsed.part)
    linked = linked_internal(repo, str(parsed))

    spans: list[Span] = [
        Span(
            str(s.get("text", "")),
            tier=0,
            citation=str(s.get("section_id", "")),
            doc_class="standard",
        )
        for s in req_sections
        if str(s.get("text", "")).strip()
    ]
    untiered: list[str] = []
    for entry in linked:
        tier = str(entry.get("authority_tier", ""))
        text = str(entry.get("text", ""))
        if not text.strip():
            continue
        if tier == "":
            untiered.append(str(entry.get("section_id", "")))
            continue
        spans.append(
            Span(
                text,
                tier=int(tier),
                citation=str(entry.get("section_id", "")),
                doc_class=str(entry.get("source_kind", "")),
            )
        )

    conflicts = [c for c in detect_conflicts(spans, obligation=str(parsed)) if _shares_topic(c)]
    payload: list[dict[str, Any]] = []
    for c in conflicts:
        entry = c.to_dict()
        # both sides addressable: the citation IS the section id on each side
        higher_key = "higher_authority" if not c.same_tier else "span_a"
        lower_key = "lower_authority" if not c.same_tier else "span_b"
        entry["sections"] = {
            higher_key.split("_")[0] if not c.same_tier else "a": c.higher.citation,
            lower_key.split("_")[0] if not c.same_tier else "b": c.lower.citation,
        }
        payload.append(entry)
    return {
        "ref": str(parsed),
        "obligation": str(parsed),
        "standard_sections": [str(s.get("section_id", "")) for s in req_sections],
        "operator_sections": [str(e.get("section_id", "")) for e in linked if e.get("section_id")],
        "untiered_sections": sorted(set(untiered)),
        "conflicts": payload,
    }


# ── the assembly ────────────────────────────────────────────────────────────

#: assembly order. Earlier components survive a tight budget; the requirement
#: itself is never dropped. Stated here so the priority is reviewable rather
#: than buried in control flow.
COMPONENT_ORDER = (
    "requirement",
    "measures",
    "applicable_systems",
    "technical_basis",
    "rationale",
    "glossary",
    "linked_internal",
    "conflicts",
    "vsl",
    "applicability",
    "background",
    "effective_dates",
    "compliance_and_evidence_retention",
    "version_history",
    "implementation_plan",
    "technical_rationale_document",
)


#: Question-scoped packets. Measured on CIP-007-6 R2 Part 2.2, the full
#: neighbourhood is ~29,900 tokens, of which the implementation plan is 33% and
#: the compliance/evidence-retention section 22% — while the requirement itself
#: is 2%. Handing all of it to every question is not thoroughness, it is ballast:
#: it costs minutes of prefill, it forces a large seat, and it buries the two
#: hundred words that answer the question.
#:
#: A profile is NOT a classifier and nothing infers one from the question — that
#: would be the prescriptive move in a new place. The caller names it, ``full``
#: is the default, and **whatever a profile leaves out is named in `omitted`**
#: and repeated to the reader, so the honest response to a question a profile
#: cannot answer is "I would need the implementation plan for that" — which is a
#: conversation, not a silent gap.
PROFILES: dict[str, tuple[str, ...]] = {
    "intent": (
        "requirement",
        "measures",
        "technical_basis",
        "rationale",
        "glossary",
        "background",
    ),
    "conformance": (
        "requirement",
        "measures",
        "glossary",
        "applicability",
        "linked_internal",
    ),
    "audit": (
        "requirement",
        "measures",
        "vsl",
        "compliance_and_evidence_retention",
        "applicability",
        "linked_internal",
    ),
    "timeline": (
        "requirement",
        "effective_dates",
        "implementation_plan",
        "technical_rationale_document",
        "version_history",
    ),
}


def assemble(
    repo: Any,
    ref: str,
    *,
    budget_tokens: int = DEFAULT_BUDGET_TOKENS,
    include: list[str] | None = None,
    profile: str = "",
    valid_at: str = "",
) -> dict[str, Any]:
    """Everything a reader needs for one requirement, sized to a budget.

    Returns the components in :data:`COMPONENT_ORDER`, each with its sections'
    verbatim text and provenance, plus ``omitted`` naming anything the budget
    could not hold.
    """
    parsed = parse_ref(ref)
    if parsed is None:
        return {"ref": ref, "error": f"{ref!r} is not a regulatory address"}
    revision = _revision_for(repo, parsed.logical_id, valid_at)
    if revision is None:
        return {
            "ref": str(parsed),
            "error": f"{parsed.logical_id} is not in the store",
        }
    revision_id = str(revision["revision_id"])
    sections = _sections(repo, revision_id)
    requirement, part = parsed.requirement, parsed.part

    # P4.2: the requirement's own sections come from the JOIN where one exists.
    # Heading-path proximity was never a principle here — with no
    # requirement→section key there was no way to retrieve *the sections
    # constituting R2 Part 2.2*, so proximity was the only option available. It
    # stays as a NAMED fallback for an unanchored requirement, never a silent
    # substitute: an absence claim resting on a guess must be visibly weaker.
    #
    # P4.3: over the whole SCOPE. A parent requirement is anchored through its
    # Parts, so asking the join for `CIP-007-6 R2` exactly returned nothing and
    # fell through to proximity on every parent-level reading — the same
    # identity mismatch that emptied the closure population.
    from portal.modules.compliance.core import requirement_scope

    population = requirement_scope.population(
        repo,
        str(parsed),
        relations=("governing",),
        valid_at=valid_at,
        include_operator=False,
        proximity_fallback=lambda: _requirement_rows(
            _under(sections, "requirements and measures") or sections, requirement, part
        ),
    )
    by_id = {str(s["section_id"]): s for s in sections}
    req_sections = (
        # reading order, not join order: a scope spanning four Parts concatenates
        # four anchor sets, and the reader is handed the document, not the query.
        sorted(
            (by_id[sid] for sid in population["section_ids"] if sid in by_id),
            key=lambda s: s.get("ordinal", 0),
        )
        if population["population_method"] == "join"
        else population["rows"]
    )
    if population["population_method"] == "join" and not req_sections:
        # the join resolved into a revision these sections do not come from.
        # Say so by falling back rather than returning an empty requirement.
        population["population_method"] = "proximity"
        population["detail"] = (
            f"{str(parsed)!r} is anchored, but into a revision other than "
            f"{revision_id[:12]} — gathered by heading-path proximity instead"
        )
        req_sections = _requirement_rows(
            _under(sections, "requirements and measures") or sections, requirement, part
        )
    gtb = _under(sections, f"requirement r{requirement}:") if requirement else []
    rationale = (
        _under(sections, f"rationale for requirement r{requirement}:") if requirement else []
    )

    components: list[Component] = [
        Component(
            "requirement",
            "the requirement and its Parts, from the standard's own requirements table",
            req_sections,
        ),
        Component(
            "measures",
            "the Measures — what the standard offers as example evidence, not an "
            "additional duty. Empty for a table-shaped requirement, where the "
            "Measures cell travels inside its own Part row rather than separately",
            [
                s
                for s in _under(sections, "requirements and measures")
                if s.get("unit_kind") != "table_row"
                and re.match(rf"^\s*M{requirement}\.", str(s.get("text", "")))
            ]
            if requirement
            else [],
        ),
        Component(
            "technical_basis",
            "Guidelines and Technical Basis for this requirement — the standard's "
            "own statement of what it is for",
            gtb,
        ),
        Component("rationale", "the drafting team's recorded rationale", rationale),
        Component(
            "vsl",
            "Violation Severity Levels — what a shortfall is graded as",
            _vsl_rows(sections, requirement),
        ),
        Component(
            "applicability",
            "Section 4 applicability and exemptions — who and what this standard reaches",
            _under(sections, "applicability", "exemptions"),
        ),
        Component(
            "background",
            "Section 6 background, including the standard's own reading conventions",
            _under(sections, "background"),
        ),
        Component(
            "effective_dates", "Section 5 effective dates", _under(sections, "effective dates")
        ),
        Component(
            "compliance_and_evidence_retention",
            "Section C — evidence retention and the compliance monitoring process",
            _under(sections, "compliance"),
        ),
        Component(
            "version_history",
            "the revision history, including why the standard was last rewritten",
            _under(sections, "version history"),
        ),
    ]

    duty_text = "\n".join(str(s.get("text", "")) for s in req_sections)
    components.append(_glossary_component(repo, duty_text, valid_at))
    components.append(
        Component(
            "linked_internal",
            "operator sections recorded as related to this requirement, in full",
            linked_internal(repo, str(parsed)),
        )
    )
    # P4: contradiction is a retrievable fact that rides with the reading — a
    # reading that never looked at a known cross-tier contradiction between the
    # standard and the operator's own documents should be visible as one.
    conflicts = conflicts_for_requirement(repo, str(parsed), valid_at=valid_at)
    conflict_sections = [
        {
            "section_id": (c.get("sections", {}) or {}).get("higher", "")
            + " / "
            + (c.get("sections", {}) or {}).get("lower", ""),
            "title": f"{c.get('signal')} — {c.get('kind')}",
            "headings": "cross-tier contradiction, emitted and never reconciled",
            "text": str(c.get("detail", "")),
            "conflict": c,
        }
        for c in conflicts.get("conflicts", [])
    ]
    components.append(
        Component(
            "conflicts",
            "known contradictions between the standard and the operator's own "
            "documents touching this requirement — both sides, both tiers, never "
            "reconciled",
            conflict_sections,
        )
    )
    components.extend(_companion_documents(repo, parsed, valid_at))

    ordered = sorted(
        (c for c in components if c.sections),
        key=lambda c: COMPONENT_ORDER.index(c.name) if c.name in COMPONENT_ORDER else 99,
    )
    wanted = {i.lower() for i in include} if include else set()
    if profile and profile.lower() != "full":
        if profile.lower() not in PROFILES:
            return {
                "ref": ref,
                "error": f"unknown profile {profile!r}; choose one of "
                f"{sorted(['full', *PROFILES])}",
            }
        wanted |= set(PROFILES[profile.lower()])
    profile_omitted: list[dict[str, Any]] = []
    if wanted:
        profile_omitted = [
            {
                "component": c.name,
                "why": c.why,
                "sections": len(c.sections),
                "tokens": c.tokens,
                "reason": (
                    f"outside the {profile or 'requested'} profile — ask for it and it "
                    "will be assembled"
                ),
            }
            for c in ordered
            if c.name not in wanted
        ]
        ordered = [c for c in ordered if c.name in wanted]

    cells = _cells_for(repo, [s for c in components for s in c.sections])
    kept: list[Component] = []
    omitted: list[dict[str, Any]] = list(profile_omitted)
    spent = 0
    for component in ordered:
        if kept and spent + component.tokens > budget_tokens:
            omitted.append(
                {
                    "component": component.name,
                    "why": component.why,
                    "sections": len(component.sections),
                    "tokens": component.tokens,
                    "reason": f"exceeds the remaining budget ({budget_tokens - spent} tokens)",
                }
            )
            continue
        kept.append(component)
        spent += component.tokens

    return {
        "ref": str(parsed),
        "standard": parsed.standard,
        "revision_id": revision_id,
        "revision": {
            "version": revision["version"],
            "effective_date": revision["effective_date"],
            "inactive_date": revision["inactive_date"],
            "lifecycle_status": revision["lifecycle_status"],
            "alias_path": revision["alias_path"],
        },
        "valid_at": valid_at or _today(),
        "profile": profile or "full",
        "budget_tokens": budget_tokens,
        "tokens_used": spent,
        "components": [
            {
                "component": c.name,
                "why": c.why,
                "sections": [_cite(s, cells) for s in c.sections],
                "tokens": c.tokens,
            }
            for c in kept
        ],
        "omitted": omitted,
        # P4.2: how the requirement's own population was derived. "join" is the
        # exact anchor; "proximity" is the weaker structural walk, and it is
        # named here so a reader never mistakes one for the other.
        "population_method": population["population_method"],
        "population_detail": population["detail"],
        # P4.3: the identities this assembly answers for. A parent requirement
        # reads as its Parts, and the reading says which ones.
        "scope": population["scope"],
        "assembly": "deterministic — document structure and recorded edges, no relevance score",
    }


def _glossary_component(repo: Any, duty_text: str, valid_at: str) -> Component:
    from portal.modules.compliance.core.glossary import resolve_bundle_definitions

    resolution = resolve_bundle_definitions(repo, duty_text, valid_at=valid_at)
    return Component(
        "glossary",
        "NERC Glossary terms the duty text depends on, with their own effectivity",
        [
            {
                "section_id": term["section_id"],
                "title": term.get("matched_as") or term["term"],
                "headings": "NERC Glossary of Terms",
                "text": term["definition"] or f"[unresolved: {term['detail']}]",
                "effective_date": term["effective_date"],
                "inactive_date": term["inactive_date"],
                "resolved": term["resolved"],
                "revision_id": term["revision_id"],
            }
            for term in resolution["terms"]
        ],
    )


def _companion_documents(repo: Any, parsed: Ref, valid_at: str) -> list[Component]:
    """The implementation plan, technical rationale and RSAW for this standard,
    whole. They are short and they answer 'when does this bite' and 'why'."""
    out: list[Component] = []
    for suffix, name, why in (
        (
            " implementation plan",
            "implementation_plan",
            "the implementation plan the standard defers to for effective dates",
        ),
        (
            " technical rationale",
            "technical_rationale_document",
            "the drafting team's published technical rationale",
        ),
        (" RSAW", "rsaw", "the Reliability Standard Audit Worksheet"),
    ):
        revision = _revision_for(repo, parsed.logical_id + suffix, valid_at)
        if revision is None:
            continue
        if name == "technical_rationale_document" and _anchored_per_requirement(
            repo, str(revision["revision_id"])
        ):
            # Placed on its requirements, it reaches each reading as that
            # requirement's `technical_basis` sections, the same way the GTB
            # inside an older standard does. Whole, it repeated every
            # requirement's rationale in every reading of the standard and put
            # CIP-004-7 and CIP-010-4 material at ~100k chars against a 32k-token
            # seat (measured 2026-09-22).
            continue
        out.append(Component(name, why, _sections(repo, str(revision["revision_id"]))))
    return out


def _anchored_per_requirement(repo: Any, revision_id: str) -> bool:
    """True when any requirement carries ``technical_basis`` sections from this revision."""
    return (
        repo._conn.execute(
            """SELECT 1 FROM requirement_sections
                WHERE revision_id = ? AND relation = 'technical_basis' LIMIT 1""",
            (revision_id,),
        ).fetchone()
        is not None
    )


def _cells_for(repo: Any, sections: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """``section_id -> [{column, text}]`` for every table row in the assembly."""
    ids = [
        str(s["section_id"])
        for s in sections
        if s.get("unit_kind") == "table_row" and s.get("section_id")
    ]
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    rows = repo._conn.execute(
        f"""SELECT section_id, col_index, column_name, text FROM source_table_cells
            WHERE section_id IN ({marks}) ORDER BY section_id, row_index, col_index""",  # noqa: S608
        tuple(ids),
    ).fetchall()
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(str(row[0]), []).append({"column": str(row[2]), "text": str(row[3])})
    return out


def _cite(
    section: dict[str, Any], cells: dict[str, list[dict[str, Any]]] | None = None
) -> dict[str, Any]:
    """One section, with enough provenance to cite it and nothing invented.

    A table row also carries its cells under their column names, so a Measure
    stays attached to the Part it belongs to and an Applicable Systems value
    stays attached to the requirement it governs — the shape that flattening a
    requirements table destroys.
    """
    row_cells = (cells or {}).get(str(section.get("section_id", "")))
    extra = {"cells": row_cells} if row_cells else {}
    return {
        **extra,
        "section_id": section.get("section_id", ""),
        "text": section.get("text", ""),
        "headings": section.get("headings", ""),
        "title": section.get("title", ""),
        "path": section.get("path", ""),
        "unit_kind": section.get("unit_kind", ""),
        "page": section.get("page_start"),
        "revision_id": section.get("revision_id", ""),
        **{
            key: section[key]
            for key in (
                "effective_date",
                "inactive_date",
                "resolved",
                "link_status",
                "link_derivation",
                "link_confidence",
                "logical_id",
                "document_title",
                "jurisdiction",
                "source_kind",
                "authority_tier",
                "conflict",
                "version",
            )
            if key in section
        },
    }
