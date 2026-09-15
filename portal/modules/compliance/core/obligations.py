"""Symmetric, source-anchored obligation decomposition.

Foundation task P3: revision-specific duties carry their real logical shape —
``AND``/``OR``, alternatives, conditions, exceptions, deadlines and
dependencies — and the logical expression must represent the source text. Two
failures this module is written to never reproduce:

* A **one-child placeholder expression** claiming decomposition readiness. An
  ``ALL_OF``/``ANY_OF`` container with a single child says nothing; a part with
  one indivisible duty is ``SINGLE``, and an empty decomposition is ``EMPTY``.
* An **incidental "or"** flipping a duty into an alternative group
  ("a source or sources" is not a three-way choice). ``ANY_OF`` is produced
  only by an explicit declared list ("take one of the following actions:"),
  never by scanning for the word "or".

Every atom carries its verbatim clause text and the offsets of that clause in
the normalized source text, so a consumer can prove the atom came from the
duty rather than from the decomposer's imagination. Modality is never
invented: an explicit modal is used as printed, a modal-free clause under a
``shall`` requirement lead-in inherits that modality (recorded as
``inherited_lead_in``), and a fragment with no modality anywhere stays
``proposed``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

_MODAL = re.compile(r"\b(shall not|must not|shall|must|may not|required to)\b", re.I)
_CADENCE = re.compile(
    r"\b(?:within|at least once every|no less than)\s+\d+\s+(?:calendar\s+|business\s+)?(?:hours?|days?|months?|years?)"
    r"(?:\s+of\s+[^,;.]+)?",
    re.I,
)
# An explicitly declared alternative list: "take one of the following actions:",
# "do one of the following:". The trigger for ANY_OF — nothing else is.
_ALT_LIST_RE = re.compile(r"\b(?:one|any)\s+of\s+the\s+following[a-z ]{0,30}:", re.I)
_BULLET_SPLIT_RE = re.compile(r"\s*-\s+")
# A cross-reference to a sibling Part ("identified in Part 2.1").
_PART_REF_RE = re.compile(r"\bPart\s+(\d+(?:\.\d+)+)")
# Sentence boundary: . ! ? followed by whitespace and a capital / bullet —
# abbreviations like "e.g.," do not match the capital requirement.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=(?:[A-Z“\"'-]))")

EXPRESSION_KINDS: tuple[str, ...] = ("ALL_OF", "ANY_OF", "SINGLE", "EMPTY")


@dataclass
class ObligationAtom:
    atom_id: str
    node_id: str
    actor: str = ""
    modality: str = ""
    action: str = ""
    object: str = ""
    population: str = ""
    trigger: str = ""
    deadline_cadence: str = ""
    conditions: list[str] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)
    evidence_expectation: str = ""
    source_anchor_ids: list[str] = field(default_factory=list)
    interpretation_status: str = "accepted"
    # ── P3: the verbatim clause this atom was derived from, and where it sits ──
    text: str = ""
    clause_start: int = -1  # offsets into the normalized duty text
    clause_end: int = -1
    clause_kind: str = "duty"  # duty | alternative
    alt_group: int = -1  # >=0 only for alternatives of one declared list
    alt_group_kind: str = ""  # ANY_OF | ALL_OF — the declared list's logic
    modality_basis: str = ""  # explicit | inherited_lead_in | none
    depends_on: list[str] = field(default_factory=list)

    def to_record(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _norm(text: str) -> str:
    """Whitespace fold + bullet-glyph normalization (7.1-era layouts print
    '•' where the -6 register carries '- '), so declared lists split the
    same way regardless of which glyph the PDF used."""
    return " ".join(text.replace("•", "- ").split())


def _atom_id(node_id: str, clause: str, index: int) -> str:
    basis = f"{node_id}||{index}||{clause}"
    return f"atom-{hashlib.sha256(basis.encode()).hexdigest()[:16]}"


def _leadin_modality(lead_in: str) -> str:
    m = _MODAL.search(lead_in)
    return m.group(0).upper() if m else ""


def _leadin_actor(lead_in: str) -> str:
    m = _MODAL.search(lead_in)
    return lead_in[: m.start()].strip(" ,:;") if m else ""


def _split_sentences(text: str) -> list[tuple[int, int, str]]:
    """[(start, end, sentence)] over the normalized text, order-preserving.
    Offsets bound the sentence exactly (whitespace trimmed on both edges)."""
    out: list[tuple[int, int, str]] = []

    def _emit(seg: str, base: int) -> None:
        s = base + (len(seg) - len(seg.lstrip()))
        e = base + len(seg.rstrip())
        if e > s:
            out.append((s, e, text[s:e]))

    pos = 0
    for m in _SENTENCE_SPLIT_RE.finditer(text):
        _emit(text[pos : m.start()], pos)
        pos = m.start()
    _emit(text[pos:], pos)
    return out


_ITEM_TAIL_RE = re.compile(r";\s*(?:or|and)\s*$", re.I)


def _split_alternative_list(list_text: str, group_kind: str) -> list[str]:
    """The items of one declared list, verbatim. Bullets win; a plain
    '; or' / '; and' separated run without bullet glyphs is split on the
    separators."""
    body = list_text.strip()
    if _BULLET_SPLIT_RE.search(body):
        parts = [p.strip() for p in _BULLET_SPLIT_RE.split(body) if p.strip()]
    else:
        sep = r";\s*and\s+" if group_kind == "ALL_OF" else r";\s*or\s+"
        parts = [p.strip() for p in re.split(sep, body, flags=re.I) if p.strip()]

    def _clean(item: str) -> str:
        return _ITEM_TAIL_RE.sub("", item).rstrip(";. ").strip()

    return [c for p in parts if (c := _clean(p))]


@dataclass
class _ListRegion:
    start: int
    end: int
    kind: str  # ANY_OF | ALL_OF
    head_start: int  # the duty clause that introduces the list


def _find_list_regions(text: str) -> list[_ListRegion]:
    """Declared alternative/conjunction lists with their span. The list runs
    from the intro's trailing ':' to the sentence end after its last item."""
    regions: list[_ListRegion] = []
    for m in _ALT_LIST_RE.finditer(text):
        # the head clause begins at the start of the sentence that introduces
        # the list — the previous boundary position, or the start of the text
        prior = list(_SENTENCE_SPLIT_RE.finditer(text[: m.start()]))
        head_start = prior[-1].start() if prior else 0
        rest = text[m.end() :]
        # the list ends at the first sentence boundary that follows the last
        # '; or' / '; and' separator (or the whole rest when unseparated)
        sep_iter = list(re.finditer(r";\s*(?:or|and)\s+", rest, re.I))
        if sep_iter:
            tail = rest[sep_iter[-1].end() :]
            stop = _SENTENCE_SPLIT_RE.search(tail)
            end = m.end() + sep_iter[-1].end() + (stop.start() if stop else len(tail))
        else:
            stop = _SENTENCE_SPLIT_RE.search(rest)
            end = m.end() + (stop.start() if stop else len(rest))
        body = text[m.end() : end]
        kind = "ALL_OF" if re.search(r";\s*and\s+", body, re.I) else "ANY_OF"
        regions.append(_ListRegion(m.start(), end, kind, head_start))
    return regions


def _first_modal_pos(text: str) -> re.Match[str] | None:
    return _MODAL.search(text)


def _make_atom(
    *,
    node_id: str,
    index: int,
    clause: str,
    start: int,
    end: int,
    lead_in: str,
    lead_modal: str,
    lead_actor: str,
    anchor_ids: list[str],
    clause_kind: str = "duty",
    alt_group: int = -1,
    alt_group_kind: str = "",
    inherited_conditions: list[str] | None = None,
    inherited_cadence: str = "",
) -> ObligationAtom:
    norm_clause = _norm(clause)
    modal = _first_modal_pos(norm_clause)
    if modal:
        modality = modal.group(0).upper()
        modality_basis = "explicit"
        actor = norm_clause[: modal.start()].strip(" ,:;") or lead_actor
        remainder = norm_clause[modal.end() :].strip(" ,:;")
        interpretation_status = "accepted"
    elif lead_modal:
        modality = lead_modal
        modality_basis = "inherited_lead_in"
        actor = lead_actor
        remainder = norm_clause
        interpretation_status = "accepted"
    else:
        modality = ""
        modality_basis = "none"
        actor = lead_actor
        remainder = norm_clause
        interpretation_status = "proposed"

    words = remainder.split()
    action = " ".join(words[: min(4, len(words))])
    obj = " ".join(words[min(4, len(words)) :])

    conditions = list(inherited_conditions or [])
    exceptions: list[str] = []
    for cue, target in (
        (" if ", conditions),
        (" when ", conditions),
        (" unless ", exceptions),
        (" except ", exceptions),
    ):
        match = re.search(rf"\b{re.escape(cue.strip())}\b", remainder, re.I)
        if match:
            target.append(remainder[match.start() :].strip())

    cadence_m = _CADENCE.search(remainder) or (
        _CADENCE.search(norm_clause) if not inherited_cadence else None
    )
    cadence = cadence_m.group(0) if cadence_m else inherited_cadence

    depends_on = [f"Part {ref}" for ref in _PART_REF_RE.findall(norm_clause)]

    return ObligationAtom(
        atom_id=_atom_id(node_id, norm_clause, index),
        node_id=node_id,
        actor=actor,
        modality=modality,
        action=action,
        object=obj,
        deadline_cadence=cadence,
        conditions=conditions,
        exceptions=exceptions,
        evidence_expectation="documented evidence"
        if re.search(r"\b(document|record|retain|evidence)\b", norm_clause, re.I)
        else "",
        source_anchor_ids=anchor_ids,
        interpretation_status=interpretation_status,
        text=norm_clause,
        clause_start=start,
        clause_end=end,
        clause_kind=clause_kind,
        alt_group=alt_group,
        alt_group_kind=alt_group_kind,
        modality_basis=modality_basis,
        depends_on=depends_on,
    )


def decompose(
    node_id: str, text: str, *, lead_in: str = "", anchor_ids: list[str] | None = None
) -> list[ObligationAtom]:
    """Decompose one duty's text into its verbatim clauses.

    Declared alternative lists become one atom per item sharing the
    introducing clause's conditions/cadence; remaining sentences become one
    atom each. Modality is explicit, inherited from the requirement lead-in,
    or absent with ``interpretation_status="proposed"`` — never invented.
    """
    source = _norm(text)
    if not source:
        return []
    anchors = anchor_ids or []
    lead_modal = _leadin_modality(lead_in)
    lead_actor = _leadin_actor(lead_in)

    atoms: list[ObligationAtom] = []
    regions = _find_list_regions(source)
    consumed = [(r.head_start, r.end) for r in regions]

    def _outside(span: tuple[int, int]) -> bool:
        return all(e <= span[0] or s >= span[1] for s, e in consumed)

    index = 0
    for region in regions:
        head = _norm(source[region.head_start : region.start])
        intro = re.search(_ALT_LIST_RE, source[region.head_start : region.end])
        body_start = region.head_start + (intro.end() if intro else 0)
        items = _split_alternative_list(source[body_start : region.end], region.kind)
        head_conditions = _leading_conditions(head)
        head_cadence = _CADENCE.search(head).group(0) if _CADENCE.search(head) else ""
        head_depends = [f"Part {r}" for r in _PART_REF_RE.findall(head)]
        if not items:
            continue
        for item in items:
            pos = source.find(item, body_start)
            span = (pos, pos + len(item)) if pos >= 0 else (body_start, body_start + len(item))
            atom = _make_atom(
                node_id=node_id,
                index=index,
                clause=item,
                start=span[0],
                end=span[1],
                lead_in=lead_in,
                lead_modal=lead_modal,
                lead_actor=lead_actor,
                anchor_ids=anchors,
                clause_kind="alternative",
                alt_group=len([r for r in regions if r is region]),
                alt_group_kind=region.kind,
                inherited_conditions=head_conditions,
                inherited_cadence=head_cadence,
            )
            if head_depends:
                atom.depends_on = sorted(set(atom.depends_on) | set(head_depends))
            atoms.append(atom)
            index += 1

    for start, end, sentence in _split_sentences(source):
        if not _outside((start, end)):
            continue
        atoms.append(
            _make_atom(
                node_id=node_id,
                index=index,
                clause=sentence,
                start=start,
                end=end,
                lead_in=lead_in,
                lead_modal=lead_modal,
                lead_actor=lead_actor,
                anchor_ids=anchors,
            )
        )
        index += 1
    return atoms


def _leading_conditions(head: str) -> list[str]:
    """A leading 'For X,' / 'For each X,' scoping phrase is a condition. The
    phrase runs to its own comma and may contain dotted Part references
    ('identified in Part 2.2')."""
    m = re.match(r"^((?:For|For each)\b[^,]{3,200},)", head, re.I)
    return [m.group(1)] if m else []


def expression_for(atoms: list[ObligationAtom], text: str = "") -> dict[str, Any]:
    """The logical expression the atoms actually form.

    Declared alternative lists group as ``ANY_OF`` (or ``ALL_OF`` for an
    '; and' list); a duty with one indivisible clause is ``SINGLE``; an empty
    decomposition is ``EMPTY``. ``ALL_OF``/``ANY_OF`` never carry a single
    child — that shape is the false-complete placeholder this module exists
    to kill.
    """
    del text  # logic comes from the declared-list structure, not keyword scans
    if not atoms:
        return {"kind": "EMPTY", "children": []}
    groups: list[tuple[tuple[int, str], list[ObligationAtom]]] = []
    for order, atom in enumerate(atoms):
        if atom.clause_kind == "alternative" and atom.alt_group >= 0:
            key = (atom.alt_group, atom.alt_group_kind)
        else:
            key = (-1 - order, "duty")  # duty atoms never share a group
        if groups and groups[-1][0] == key:
            groups[-1][1].append(atom)
        else:
            groups.append((key, [atom]))

    def _child(atom: ObligationAtom) -> dict[str, Any]:
        return {"kind": "ATOM", "atom_id": atom.atom_id}

    if len(groups) == 1:
        (_, gk), atoms_in_group = groups[0]
        if gk == "duty":
            return {
                "kind": "SINGLE" if len(atoms_in_group) == 1 else "ALL_OF",
                "children": [_child(a) for a in atoms_in_group],
            }
        return {"kind": gk, "children": [_child(a) for a in atoms_in_group]}

    children: list[dict[str, Any]] = []
    for (_, gk), atoms_in_group in groups:
        if gk == "duty":
            children.extend(_child(a) for a in atoms_in_group)
        else:
            children.append({"kind": gk, "children": [_child(a) for a in atoms_in_group]})
    return {"kind": "ALL_OF", "children": children}


def _anchored_atom_defects(atoms: list[ObligationAtom], source: str) -> list[str]:
    defects: list[str] = []
    for atom in atoms:
        if not atom.text:
            defects.append(f"{atom.atom_id}: atom without verbatim clause text")
        elif atom.text not in source:
            defects.append(f"{atom.atom_id}: clause text not present in the duty text")
        if atom.clause_start < 0 or atom.clause_end <= atom.clause_start:
            defects.append(f"{atom.atom_id}: clause offsets not anchored")
        elif source[atom.clause_start : atom.clause_end] != atom.text:
            defects.append(f"{atom.atom_id}: clause offsets do not resolve to the clause text")
    return defects


def _declared_list_defects(atoms: list[ObligationAtom], source: str) -> list[str]:
    """A declared list must appear as a >=2-child group whose items are the
    verbatim list items."""
    defects: list[str] = []
    for region in _find_list_regions(source):
        intro = re.search(_ALT_LIST_RE, source[region.head_start : region.end])
        body_start = region.head_start + (intro.end() if intro else 0)
        items = _split_alternative_list(source[body_start : region.end], region.kind)
        if len(items) < 2:
            continue
        group_atoms = [a for a in atoms if a.clause_kind == "alternative" and a.text in items]
        if len(group_atoms) < 2:
            defects.append("declared alternative list did not become a >=2-child group")
        elif len(group_atoms) != len(items):
            defects.append(
                f"declared list has {len(items)} items but {len(group_atoms)} alternative atoms"
            )
    return defects


def decomposition_defects(
    atoms: list[ObligationAtom], expression: dict[str, Any], text: str
) -> list[str]:
    """Readiness defects for one decomposition — every way the expression can
    fail to represent the text. Empty list means the decomposition is sound."""
    defects: list[str] = []
    source = _norm(text)
    kind = expression.get("kind", "")

    if not source:
        if atoms or kind != "EMPTY":
            defects.append("expression over empty text is not EMPTY")
        return defects
    if not atoms:
        defects.append("no atoms derived from non-empty duty text")
        return defects
    if kind == "EMPTY":
        defects.append("EMPTY expression over non-empty duty text")
        return defects
    if kind in ("ALL_OF", "ANY_OF") and len(expression.get("children", [])) < 2:
        defects.append(f"one-child {kind} expression claims a decomposition it does not have")

    defects.extend(_anchored_atom_defects(atoms, source))
    defects.extend(_declared_list_defects(atoms, source))
    return defects
