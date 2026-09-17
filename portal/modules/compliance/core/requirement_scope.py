"""One requirement scope, shared by the assembly, the links and the closure.

ONE_REGULATORY_EXTRACTION_V1 P4.3.

A product question is asked at the identity an analyst uses — ``CIP-007-6 R2``
— and the store keys its anchors and its operator edges to the identities the
standard itself numbers: ``R2 Part 2.1`` through ``Part 2.4``. Measured on the
live store the day this module was written: the parent carried **0**
``requirement_sections`` rows and **0** ``relationship_assertions`` rows, while
its four Parts carried 14 anchors each and 66 proposed operator edges between
them.

An exact lookup on the parent therefore produced an EMPTY eligible population,
and a closure receipt computed from it read ``eligible=[] examined=[]
unread=[]`` with the answer's five regulatory citations classified ``outside``.
That is worse than an error: an empty population makes ``complete`` and
``unread`` both look satisfied, so a reading over no evidence at all reports
like a reading that read everything. No prompt and no seat can repair it,
because nothing was ever offered to read.

The scope comes from ``requirement_nodes`` — the standard's own numbering —
never from a string prefix: ``'CIP-007-6 R2'`` is a prefix of
``'CIP-007-6 R20'`` exactly as readily as of ``'CIP-007-6 R2 Part 2.1'``.

**The parent stays in its own scope.** Some standards in this store anchor
material to the bare requirement as well as to its Parts (``CIP-003-9 R2``
carries three anchors and three edges on the parent and has no Parts at all),
so dropping it would trade one empty population for another.

:func:`population` is the one call both the assembly and the closure make, so a
reading cannot be assembled over one scope and then judged against a different
one — which is the defect this module exists to close.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Scope:
    """A requirement identity and the leaf identities it stands for."""

    ref: str
    leaves: list[str] = field(default_factory=list)
    method: str = "self"
    detail: str = ""

    @property
    def is_parent(self) -> bool:
        return bool(self.leaves)

    @property
    def refs(self) -> list[str]:
        """Every identity this scope answers for — the ref as asked, then its
        leaves, in the standard's own numbering order."""
        return list(dict.fromkeys([self.ref, *self.leaves]))

    def as_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "leaves": list(self.leaves),
            "method": self.method,
            "detail": self.detail,
        }


def _part_key(part: str) -> tuple[int, ...]:
    """``2.10`` sorts after ``2.9``, which string order does not do."""
    return tuple(int(piece) if piece.isdigit() else 0 for piece in str(part).split("."))


def resolve(repo: Any, ref: str) -> Scope:
    """The scope of one reference: a parent requirement expands to its Parts, a
    Part is its own leaf, and anything that is not a regulatory address is
    returned unchanged rather than guessed at."""
    from portal.modules.compliance.core.reading_assembly import parse_ref

    parsed = parse_ref(ref)
    if parsed is None:
        return Scope(ref=ref, detail=f"{ref!r} is not a regulatory address; it stands for itself")
    canonical = str(parsed)
    if parsed.part:
        return Scope(ref=canonical, detail="a Part is a leaf: it stands for itself")
    if not parsed.requirement:
        return Scope(ref=canonical, detail="a whole standard stands for itself")
    rows = repo._conn.execute(
        """SELECT node_id, part FROM requirement_nodes
           WHERE standard_revision_id = ? AND requirement = ? AND part <> ''""",
        (parsed.standard, f"R{parsed.requirement}"),
    ).fetchall()
    leaves = [str(row[0]) for row in sorted(rows, key=lambda row: _part_key(row[1]))]
    if not leaves:
        return Scope(
            ref=canonical,
            detail=f"{canonical} numbers no Parts in this store; it stands for itself",
        )
    return Scope(
        ref=canonical,
        leaves=leaves,
        method="parts",
        detail=f"{canonical} stands for {len(leaves)} Part(s): " + ", ".join(leaves),
    )


def population(
    repo: Any,
    ref: str,
    *,
    relations: tuple[str, ...] | None = None,
    valid_at: str = "",
    proximity_fallback: Any = None,
    include_operator: bool = True,
    include_notes: bool = True,
) -> dict[str, Any]:
    """The sections constituting a requirement across its whole scope.

    Three kinds of material, each entry keeping the leaf identity it came from
    and its standing: a regulatory anchor keeps its ``relation``, an operator
    edge keeps its ``link_status``, so a population containing only ``proposed``
    edges cannot be mistaken for one built from approved ones.

    **Operator notes are in the population.** They are neither an anchor nor an
    edge, so a population built from those two alone left them out — and a
    reading that cited the operator's own recorded decision about the very
    requirement it was reading had that citation classified ``outside`` scope.
    Measured on the live Part 2.2 reading: the answer correctly engaged the
    note saying *we evaluate every 30 days, not the 35 the Part allows, and the
    extra strictness is deliberate*, and the receipt called it out-of-scope. The
    note travels in the assembly already; it is eligible material by the
    module's own reckoning.

    The regulatory side is the join wherever any leaf is anchored;
    ``proximity_fallback`` runs only when no leaf resolves, and the method says
    ``proximity`` when it does — named, never silently substituted.
    """
    from portal.modules.compliance.core import enumeration, reading_assembly

    # The primitive's own default — every relation a section can bear to a
    # requirement. A closure narrowed to `governing` would call a reading
    # complete that never opened the Measures it was anchored to.
    relations = relations or enumeration.ALL_RELATIONS
    scope = resolve(repo, ref)
    regulatory: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    unanchored: list[dict[str, Any]] = []
    for identity in scope.refs:
        found = enumeration.population_for_requirement(
            repo, identity, relations=relations, valid_at=valid_at
        )
        if found["population_method"] == "join":
            for row in found["rows"]:
                rows.append(row)
                regulatory.append(
                    {
                        "section_id": str(row["section_id"]),
                        "requirement_id": identity,
                        "relation": str(row.get("relation", "")),
                        "side": "regulatory",
                    }
                )
        else:
            unanchored.extend(found.get("unanchored", []))

    method = "join"
    if not rows:
        method = "proximity"
        rows = list(proximity_fallback() or []) if proximity_fallback else []
        regulatory = [
            {
                "section_id": str(row.get("section_id", "")),
                "requirement_id": scope.ref,
                "relation": "governing",
                "side": "regulatory",
            }
            for row in rows
        ]

    operator: list[dict[str, Any]] = []
    if include_operator:
        operator = [
            {
                "section_id": str(entry.get("section_id", "")),
                "requirement_id": str(entry.get("link_requirement") or scope.ref),
                "link_status": str(entry.get("link_status", "")),
                "side": "operator",
            }
            for entry in reading_assembly.linked_internal(repo, ref, scope=scope)
            if entry.get("section_id")
        ]

    # One section legitimately serves several Parts — the operator's single
    # patch procedure answers 2.1 through 2.4 — so the union keeps every
    # identity it answers for rather than the first one seen.
    notes: list[dict[str, Any]] = []
    if include_notes:
        from portal.modules.compliance.core.notes import notes_for

        for identity in scope.refs:
            notes.extend(
                {
                    "section_id": str(note["section_id"]),
                    "requirement_id": identity,
                    "kind": str(note.get("kind", "")),
                    "side": "operator_note",
                }
                for note in notes_for(repo, identity)
                if note.get("section_id")
            )

    by_section: dict[str, dict[str, Any]] = {}
    for entry in [*regulatory, *operator, *notes]:
        kept = by_section.setdefault(
            entry["section_id"], {**entry, "requirement_ids": [entry["requirement_id"]]}
        )
        if entry["requirement_id"] not in kept["requirement_ids"]:
            kept["requirement_ids"].append(entry["requirement_id"])
    detail = (
        f"{len(regulatory)} regulatory section(s) by {method}, {len(operator)} operator "
        f"section(s) by recorded edge and {len(notes)} operator note(s), over "
        f"{len(scope.refs)} identity(ies): {', '.join(scope.refs)}"
    )
    if method == "proximity":
        # The disclosure `enumeration` attaches to a single unanchored identity,
        # kept at scope level: an absence claim resting on a structural guess has
        # to stay visibly weaker than one resting on the join, or the two get
        # treated as the same evidence.
        detail += (
            " — no identity in this scope is anchored into the captured revision, so the "
            "regulatory side was gathered by heading-path proximity, which is a weaker "
            "basis than the join and is reported as such"
        )
    return {
        "ref": scope.ref,
        "scope": scope.as_dict(),
        "population_method": method,
        "relations": list(relations),
        "regulatory": regulatory,
        "operator": operator,
        "notes": notes,
        "sections": by_section,
        "section_ids": list(by_section),
        "rows": rows,
        "unanchored": unanchored,
        "detail": detail,
    }


__all__ = ["Scope", "population", "resolve"]
