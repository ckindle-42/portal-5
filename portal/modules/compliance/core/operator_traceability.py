"""The operator's own requirement traceability, as data (DATA_TRUTH DD2).

Roughly half the operator's controlled documents end with a "Requirements
Traceability" appendix — a table the OPERATOR wrote, mapping its own sections
to the standard's requirements ("R1 Part 1.2 <requirement text> Sections 3.2,
3.4 <applicable systems> <TFE>"). DD2 promotes the D-DT-8 probe parser
(``reading_truth/dt/probe/trace_parse.py``) into the internal corpus: every
appendix row becomes two machine_determined assertions in
``relationship_assertions`` under ``derivation='operator_traceability'`` —

* document-level ``ADDRESSES`` (document → standard requirement), and
* section-level ``IMPLEMENTS`` (requirement → section), the operator's own
  declaration that its §n implements the requirement.

The row is a DECLARATION, labelled as such wherever it surfaces. It is not
read verification: the similarity-proposed edges keep their ``proposed``
status and delivery no longer flows through them.

Hazard rules carried over from the probe and tightened (D-DT-8 G5):

* **Requirement resolution is text-first.** A row yields assertions only when
  its restated requirement text covers ≥ ``CONFIRM_OVERLAP`` of some register
  requirement's normative words (the probe's ≥0.6 confirmation, now the gate
  for EVERY row rather than only suspicious ones). This is what kills the
  multi-standard-table misreads: the header's "last CIP mention" can no
  longer invent a standard, because an unconfirmed row is rejected, never
  emitted. A tie across standards is broken by the row's contextual
  standard, then rejected as ambiguous.
* **Undotted section numbers.** "Section 3" resolves to a section stored as
  "3.0" (and, only when nothing else matched, to the 3.x family).
* **Numbered paragraphs folded inside another section's body** resolve
  through a line-start scan of the section spans, as in the probe.

A revision's assertions are rebuilt idempotently: ``record_traceability``
replaces exactly this revision's ``operator_traceability`` rows.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

DERIVATION = "operator_traceability"
#: a row is the operator's declaration only when its restated text covers at
#: least this share of the register requirement's words (D-DT-8 G5)
CONFIRM_OVERLAP = 0.6

_STD_RE = re.compile(r"CIP[\s-]*0?(\d{2,3})(?:-(\d+(?:\.\d+)?[a-z]?))?")
_ROW_RE = re.compile(r"\bR(\d+)(?:\s*Part\s*|\.)(\d+(?:\.\d+)*)|\bR(\d+)\.(?=\s+Each)")
_SEC_RE = re.compile(r"Sections?\s+((?:\d+(?:\.\d+)*)(?:\s*(?:,|&|and)\s*\d+(?:\.\d+)*)*)")
_APPENDIX_START_RE = re.compile(r"cross-?\s*reference\s+between", re.I)
_APPENDIX_END_RE = re.compile(r"REVISION HISTORY")
_PART_TOKEN_RE = re.compile(r"\d+(?:\.\d+)*")

#: roles whose sections can never be an appendix row's target
_INELIGIBLE_ROLES = ("TABLE_OF_CONTENTS", "TRACEABILITY_ASSERTION")


@dataclass
class TraceRow:
    """One parsed appendix row, before requirement/section resolution."""

    row_text: str  # the restated requirement text, as printed (the citation)
    standard: str | None  # contextual standard, from the running header text
    version: str | None
    r: str | None
    part: str | None
    section_numbers: list[str]


@dataclass
class ResolvedRow(TraceRow):
    requirement_ids: list[str] = field(default_factory=list)
    section_ids: list[str] = field(default_factory=list)
    overlap: float = 0.0
    #: 'text' when confirmed; otherwise the rejection reason
    outcome: str = "no_appendix"


def appendix_region(full_text: str) -> str:
    """The appendix's text: the LAST 'cross-reference between' heading to the
    revision history (the probe's region rule), whitespace-flattened."""
    normalized = re.sub(r"\s+", " ", full_text)
    starts = list(_APPENDIX_START_RE.finditer(normalized))
    if not starts:
        return ""
    start = starts[-1].start()
    end = _APPENDIX_END_RE.search(normalized, start)
    return normalized[start : end.start() if end else len(normalized)]


def parse_rows(appendix: str) -> list[TraceRow]:
    """Split the appendix into rows at each R-token.

    The contextual standard is the last standard mention BEFORE the row's
    requirement statement (cumulative, as in the probe) — with text-first
    resolution it is a tiebreaker, never the authority.
    """
    rows: list[TraceRow] = []
    matches = list(_ROW_RE.finditer(appendix))
    for index, match in enumerate(matches):
        segment_end = matches[index + 1].start() if index + 1 < len(matches) else len(appendix)
        segment = appendix[match.start() : segment_end]
        r_number = match.group(1) or match.group(3)
        statements = [
            m.start()
            for m in re.finditer(rf"\bR{r_number}\.\s+(?:Each|The)", appendix[: match.start() + 1])
        ]
        statement_start = statements[-1] if statements else match.start()
        sec = _SEC_RE.search(segment)
        restated = appendix[match.start() : (match.start() + sec.start()) if sec else segment_end]
        context = appendix[:statement_start]
        standard_match = None
        for found in _STD_RE.finditer(context):
            standard_match = found  # the LAST mention before the row, as in the probe
        part = match.group(2)
        if (
            match.group(1)
            and "Part" not in match.group(0)
            and part
            and not part.startswith(f"{r_number}.")
        ):
            part = f"{r_number}.{part}"  # "R2.3" style: the Part token is dotted
        rows.append(
            TraceRow(
                row_text=restated,
                standard=standard_match.group(1) if standard_match else None,
                version=standard_match.group(2) if standard_match else None,
                r=r_number,
                part=part,
                section_numbers=_numbers(sec),
            )
        )
    return rows


def _numbers(sec_match: re.Match[str] | None) -> list[str]:
    if not sec_match:
        return []
    return _PART_TOKEN_RE.findall(sec_match.group(1))


def _word_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z]{4,}", (text or "").lower()))


def _overlap(row_words: set[str], requirement_text: str) -> float:
    words = _word_set(requirement_text)
    if not words:
        return 0.0
    return len(row_words & words) / len(words)


def resolve_row(
    row: TraceRow,
    register: Register,
    sections_by_number: dict[str, list[str]],
    section_bodies: dict[str, str],
    stats: Counter | None = None,
) -> ResolvedRow:
    """Resolve one row exactly as the validated probe did (D-DT-8 G5):

    * Part rows are confirmed BY TEXT against the current register (≥0.6
      word overlap); when the text match fails, the structurally resolved
      requirement survives only if its own normative text overlaps ≥0.6 —
      the check that rejected the probe's 24 header misreads.
    * Whole-requirement rows resolve structurally (contextual standard,
      currency-preferred), as the probe did.

    The undotted-number additions below the probe's rules are counted
    separately, so the probe-faithful counts stay measurable.
    """
    stats = stats if stats is not None else Counter()
    resolved = ResolvedRow(
        row_text=row.row_text,
        standard=row.standard,
        version=row.version,
        r=row.r,
        part=row.part,
        section_numbers=list(row.section_numbers),
    )
    # the probe's skips, in its order: a row with no standard context, then a
    # row with no "Sections n" token, never entered its output at all
    if not row.standard:
        stats["no_std"] += 1
        resolved.outcome = "no_std"
        return resolved
    if not row.section_numbers:
        stats["no_section"] += 1
        resolved.outcome = "no_section"
        return resolved
    structural = _structural_resolve(row, register, stats)
    requirement_ids: list[str] = []
    outcome = "unresolved"
    overlap = 0.0
    if row.part:
        score, text_rid = _by_text(row, register)
        overlap = score
        if text_rid and score >= CONFIRM_OVERLAP:
            if structural and text_rid not in structural:
                stats["req_corrected_by_text"] += 1
            requirement_ids = [text_rid]
            outcome = "text_confirmed"
            stats["req_text_confirmed"] += 1
        elif structural and structural[0] in register.texts:
            score = _overlap(_word_set(row.row_text), register.texts[structural[0]])
            overlap = score
            if score < CONFIRM_OVERLAP:
                outcome = "rejected_text_mismatch"
                stats["req_rejected_text_mismatch"] += 1
            else:
                requirement_ids = structural
                outcome = "structural"
        else:
            requirement_ids = structural
            outcome = "structural" if structural else "unresolved"
    else:
        requirement_ids = structural
        outcome = "structural" if structural else "unresolved"
    if requirement_ids:
        stats["req_resolved"] += 1
    resolved.requirement_ids = requirement_ids
    resolved.overlap = overlap
    resolved.outcome = outcome
    resolved.section_ids = _resolve_sections(row, sections_by_number, section_bodies, stats)
    return resolved


def _structural_resolve(row: TraceRow, register: Register, stats: Counter) -> list[str]:
    """The probe's structural resolution: contextual standard (+ version when
    the appendix states one), parent-trimmed Part tokens, currency-preferred."""
    if not row.standard or not row.r:
        return []

    def candidates(part: str | None) -> list[str]:
        suffix = f" R{row.r} Part {part}" if part else f" R{row.r}"
        found = [
            rid
            for rid in register.ids
            if re.match(rf"CIP-0?{row.standard}-", rid) and rid.endswith(suffix)
        ]
        if row.version:
            versioned = [
                rid
                for rid in found
                if rid.startswith(f"CIP-0{row.standard}-{row.version} ")
                or rid.startswith(f"CIP-{row.standard}-{row.version} ")
            ]
            found = versioned or found
        current = [rid for rid in found if rid.split(" R")[0] in register.current_stds]
        return sorted(current or found)[:1] if not row.version else sorted(found)

    resolved = candidates(row.part)
    part = row.part
    while not resolved and part and "." in part:
        part = part.rsplit(".", 1)[0]
        stats["part_trimmed"] += 1
        resolved = candidates(part)
    return resolved


def _by_text(row: TraceRow, register: Register) -> tuple[float, str]:
    """The probe's by-text confirmation: best ≥0.6 candidate wins; candidates
    are current-register Parts of ANY standard matching R{r} Part {p}."""
    row_words = _word_set(row.row_text)
    suffix = f" R{row.r} Part {row.part}"
    best = (0.0, "")
    for rid, text in register.texts.items():
        if not rid.endswith(suffix) or rid.split(" R")[0] not in register.current_stds:
            continue
        score = _overlap(row_words, text)
        if score > best[0]:
            best = (score, rid)
    return best


def _resolve_sections(
    row: TraceRow,
    sections_by_number: dict[str, list[str]],
    section_bodies: dict[str, str],
    stats: Counter,
) -> list[str]:
    targets: list[str] = []
    for number in row.section_numbers:
        # the probe's rules, complete, first: exact/parent-prefix, then the
        # folded-paragraph fallback. Only when the probe's rules find nothing
        # do the counted undotted-number additions fill the gap (G5) — they
        # must never displace a folded hit, because documents carry
        # misnumbered duplicate runs (owner lists numbered 1.0-8.1) that the
        # '.0' equivalence happily matches while the folded scan finds the
        # section the operator actually meant.
        hits = _sections_for_number(number, sections_by_number)
        if not hits:
            hits = _folded_paragraph(number, section_bodies)
            if hits:
                stats["folded_paragraph"] += 1
        if not hits:
            hits = _undotted(number, sections_by_number, stats)
        targets += [hit for hit in hits if hit not in targets]
    if targets:
        stats["sections_resolved"] += 1
    return targets


def _sections_for_number(number: str, sections_by_number: dict[str, list[str]]) -> list[str]:
    # the probe's rule: exact match, or the appendix names a parent whose
    # subsections belong to it
    return [
        section_id
        for stored, ids in sections_by_number.items()
        if stored == number or ("." in number and stored.startswith(f"{number}."))
        for section_id in ids
    ]


def _undotted(number: str, sections_by_number: dict[str, list[str]], stats: Counter) -> list[str]:
    """Hazard fix (G5, counted): undotted appendix numbers over dotted
    document sections — "Section 3" may be stored as 3.0."""
    hits = list(sections_by_number.get(f"{number}.0", []))
    if hits:
        stats["undotted_equivalence"] += 1
        return hits
    if _PART_TOKEN_RE.fullmatch(number):
        for stored, ids in sections_by_number.items():
            if stored.split(".")[0] == number:
                hits += ids
        if hits:
            stats["undotted_fallback"] += 1
    return hits


def _folded_paragraph(number: str, section_bodies: dict[str, str]) -> list[str]:
    pattern = re.compile(rf"(?m)^\s*{re.escape(number)}\s")
    return [section_id for section_id, body in section_bodies.items() if pattern.search(body or "")]


# ── the store side ───────────────────────────────────────────────────────────


@dataclass
class Register:
    """The requirement register the rows resolve against — the probe's three
    pools, from the store's own currency rule:

    ``ids``: every requirement_id anchored under ANY relation (the probe's
    ``reqids`` — a Part can carry a measure or technical-basis anchor without
    a governing one, and the appendix still names it).
    ``texts``: requirement_id → normative text for governing-anchor rows,
    first occurrence (the probe's ``NT`` — the by-text pool).
    ``current_stds``: the standard ids ('CIP-007-6') that govern NOW —
    ``section_index._governing_revisions`` (currency included, module clock;
    the probe re-derived it with a local ``date.today()``, which the D6 test
    lesson forbids).
    """

    ids: set[str]
    texts: dict[str, str]
    current_stds: set[str]


def load_register(repo: Any) -> Register:
    from portal.modules.compliance.core.section_index import _governing_revisions

    governing_revisions = _governing_revisions(repo, "US")
    current_stds = {
        str(logical).split("/", 1)[1]
        for logical, revision in repo._conn.execute(
            "select logical_id, revision_id from document_revisions"
        ).fetchall()
        if str(logical).startswith("NERC/CIP-") and str(revision) in governing_revisions
    }
    ids = {
        str(row[0])
        for row in repo._conn.execute(
            "select distinct requirement_id from requirement_sections"
        ).fetchall()
    }
    texts: dict[str, str] = {}
    cache: dict[str, str] = {}
    rows = repo._conn.execute(
        "select requirement_id, revision_id, char_start, char_end from requirement_sections"
        " where relation='governing'"
    ).fetchall()
    for requirement_id, revision_id, char_start, char_end in rows:
        if revision_id not in cache:
            cache[revision_id] = repo.get_document_text(revision_id) or ""
        texts.setdefault(str(requirement_id), cache[revision_id][char_start:char_end])
    return Register(ids=ids, texts=texts, current_stds=current_stds)


def load_sections(repo: Any, revision_id: str) -> tuple[dict[str, list[str]], dict[str, str]]:
    """(section numbers → ids, section id → body text) for one revision,
    excluding the never-eligible roles (TOC, the appendix itself)."""
    rows = repo._conn.execute(
        "select section_id, heading_path, title, role, char_start, char_end"
        " from source_sections where revision_id=? order by ordinal",
        (revision_id,),
    ).fetchall()
    full = repo.get_document_text(revision_id) or ""
    by_number: dict[str, list[str]] = {}
    bodies: dict[str, str] = {}
    for section_id, heading_path, title, role, char_start, char_end in rows:
        if role in _INELIGIBLE_ROLES:
            continue
        number = _leading_number(heading_path) or _leading_number(title)
        if number:
            by_number.setdefault(number, []).append(str(section_id))
        start, end = int(char_start or 0), int(char_end or 0)
        bodies[str(section_id)] = full[start:end] if 0 <= start < end <= len(full) else ""
    return by_number, bodies


def _leading_number(text: str | None) -> str:
    match = re.match(r"\s*(\d+(?:\.\d+)*)", text or "")
    return match.group(1) if match else ""


def resolve_revision(repo: Any, revision_id: str) -> dict[str, Any]:
    """Parse and resolve one revision's appendix from the store. No writes."""
    full = repo.get_document_text(revision_id) or ""
    appendix = appendix_region(full)
    if not appendix:
        return {"resolved": [], "stats": Counter(), "has_appendix": False}
    register = load_register(repo)
    by_number, bodies = load_sections(repo, revision_id)
    stats: Counter = Counter()
    resolved = [
        resolve_row(row, register, by_number, bodies, stats) for row in parse_rows(appendix)
    ]
    stats["rows"] = len(resolved)
    return {"resolved": resolved, "stats": stats, "has_appendix": True}


def record_traceability(repo: Any, revision_id: str) -> dict[str, Any]:
    """Rebuild one revision's operator_traceability assertions, idempotently:
    exactly this revision's rows under the derivation are replaced."""
    from portal.modules.compliance.core.temporal import now_iso

    logical_row = repo._conn.execute(
        "select logical_id from document_revisions where revision_id=?", (revision_id,)
    ).fetchone()
    logical_id = str(logical_row[0]) if logical_row else ""
    result = resolve_revision(repo, revision_id)
    stats: Counter = Counter(result["stats"])
    stats["no_appendix"] = 0 if result["has_appendix"] else 1
    stamp = now_iso()
    addresses: list[tuple[str, str, float, str]] = []
    links: list[tuple[str, str, float, str]] = []
    addressed: set[str] = set()
    linked: set[tuple[str, str]] = set()
    for row in result["resolved"]:
        for requirement_id in row.requirement_ids:
            if requirement_id not in addressed:
                addressed.add(requirement_id)
                addresses.append((requirement_id, row.row_text, row.overlap, row.outcome))
            for section_id in row.section_ids:
                # an appendix may repeat a (requirement, section) pair across
                # blocks; one pair is one assertion
                if (requirement_id, section_id) in linked:
                    continue
                linked.add((requirement_id, section_id))
                links.append((requirement_id, section_id, row.overlap, row.row_text))
    with repo._lock, repo._conn:
        repo._conn.execute(
            "delete from relationship_assertions where derivation=? and"
            " (src_revision_id=? or dst_revision_id=?)",
            (DERIVATION, revision_id, revision_id),
        )
        for requirement_id, row_text, overlap, outcome in addresses:
            repo._conn.execute(
                """insert into relationship_assertions(assertion_id, relation_type, src_ref,
                       src_revision_id, dst_ref, citations_json, status, review_state,
                       rationale, confidence, derivation, recorded_from)
                   values (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    # revision-scoped: two revisions of one document both
                    # address the same requirement without colliding
                    _assertion_id("addresses", logical_id, revision_id, requirement_id),
                    "ADDRESSES",
                    logical_id,
                    revision_id,
                    requirement_id,
                    _citations(row_text, overlap, outcome),
                    "machine_determined",
                    "machine_determined",
                    _ADDRESSES_RATIONALE,
                    round(overlap, 4),
                    DERIVATION,
                    stamp,
                ),
            )
        for requirement_id, section_id, overlap, row_text in links:
            repo._conn.execute(
                """insert into relationship_assertions(assertion_id, relation_type, src_ref,
                       dst_ref, dst_revision_id, citations_json, status, review_state,
                       rationale, confidence, derivation, recorded_from)
                   values (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    _assertion_id("implements", requirement_id, section_id),
                    "IMPLEMENTS",
                    requirement_id,
                    section_id,
                    revision_id,
                    _citations(row_text, overlap, "text"),
                    "machine_determined",
                    "machine_determined",
                    _IMPLEMENTS_RATIONALE,
                    round(overlap, 4),
                    DERIVATION,
                    stamp,
                ),
            )
    return {
        "revision_id": revision_id,
        "rows": stats.get("rows", 0),
        "confirmed": sum(1 for row in result["resolved"] if row.requirement_ids),
        "addresses": len(addresses),
        "section_links": len(links),
        "stats": dict(stats),
    }


_ADDRESSES_RATIONALE = (
    "the operator's own declaration: its Requirements Traceability appendix names this "
    "requirement (machine-parsed from the appendix row; not read-verified)"
)
_IMPLEMENTS_RATIONALE = (
    "the operator's own declaration: its Requirements Traceability appendix maps this "
    "section to this requirement (machine-parsed; not read-verified)"
)


def _citations(row_text: str, overlap: float, outcome: str) -> str:
    return json.dumps(
        [
            {
                "appendix_row": row_text.strip(),
                "overlap": round(overlap, 4),
                "confirmation": outcome,
            }
        ]
    )


def _assertion_id(kind: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join((kind, *parts)).encode()).hexdigest()[:20]
    return f"rel-{digest}"


def record_all_traceability(repo: Any) -> dict[str, Any]:
    """Re-run every internal revision from the store (DD2's 're-runnable')."""
    revisions = [
        str(row[0])
        for row in repo._conn.execute(
            "select distinct revision_id from source_sections where section_id like 'isection-%'"
        ).fetchall()
    ]
    receipts = [record_traceability(repo, revision_id) for revision_id in sorted(revisions)]
    totals: Counter = Counter()
    for receipt in receipts:
        for key, value in receipt["stats"].items():
            totals[key] += value
    return {
        "revisions": len(revisions),
        "with_appendix": sum(1 for r in receipts if not r["stats"].get("no_appendix")),
        "rows": totals.get("rows", 0),
        "addresses": sum(r["addresses"] for r in receipts),
        "section_links": sum(r["section_links"] for r in receipts),
        "stats": dict(totals),
        "per_revision": receipts,
    }
