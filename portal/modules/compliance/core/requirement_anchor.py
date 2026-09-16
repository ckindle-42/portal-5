"""Anchor requirement identity into the captured character space.

The graph and the corpus were both built and never joined. `RegisterNode`
carries no `section_id`; `source_sections` carries no requirement reference.
The only overlap is `source_pdf` + `source_pages`, which is page granularity —
a page holds many sections and a Part can span pages.

So `reading_assembly` had to gather by heading-path proximity (with no join
there is no way to retrieve *the sections constituting R2 Part 2.2*) and
`resolve_governing_bundle` had to re-parse the PDF at call time to get text for
an identity it already held. This module supplies the missing key.

**The method is exact, not fuzzy, and that is the point.** The Register carries
each requirement's `verbatim_text`. `document_texts.full_text` is the captured
revision's character space with a byte-exact reconstruction guarantee, and
every section carries `char_start`/`char_end` in it. Locate the verbatim text
in that space by exact match after one normalisation whose only licensed
transformations are NFKC, the PDF-rendering substitutions below, and
whitespace collapse; the sections whose half-open span overlaps the located
range ARE that requirement's sections.

**Two renderings of the same bytes.** The Register's text comes from pymupdf
reading the PDF as flowing text. The capture's `full_text` is the byte-exact
concatenation of docling units, and a ``table_row`` unit is
``" | ".join(cells)``. A ``verbatim_text`` inside one cell matches as a
substring — the normal case, since a Part's requirement text is one cell. One
spanning cells will not anchor. That is recorded as `UNANCHORED`, never
approximated: a fuzzy match would produce citations that look correct, cannot
be checked afterwards, and would be built on by everything downstream.

**This module writes nothing to `source_sections`.** `capture.assert_faithful`
raises on overlapping spans, so the join lives in its own table and the
capture is never edited.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

#: The ONLY licensed substitutions. Each is a rendering artefact between the
#: two readers, not a semantic change. §P1.3 states the test any addition to
#: this tuple must pass.
_SUBSTITUTIONS = (
    ("‘", "'"),
    ("’", "'"),
    ("“", '"'),
    ("”", '"'),
    ("–", "-"),
    ("—", "-"),
    ("‐", "-"),
    (" ", " "),
    ("ﬁ", "fi"),
    ("ﬂ", "fl"),
    ("­", ""),  # soft hyphen
    # Symbol-font list bullet in the PUA. docling keeps the codepoint; pymupdf
    # renders the same glyph as "-", so the Register's text carries a hyphen
    # where the capture carries this. Admitted under the §P1.3 test: zero
    # change to any already-anchored range, 9 UNANCHORED converted (see the
    # report). It is a rendering reconciliation, not a text edit.
    ("", "-"),
    # The same typographic double quote, read two ways: pymupdf gives U+201C /
    # U+201D, docling gives ASCII "'". The pair above already folds the curly
    # doubles to '"', so this last step folds the quote glyphs into ONE form.
    # Which quote mark a reader chose is typography, not what a requirement
    # says. Admitted under the §P1.3 test: zero change to any already-anchored
    # range, 7 UNANCHORED converted.
    ('"', "'"),
    # A list bullet. docling folds the marker into structure (the unit becomes a
    # ``list_item``) and drops the glyph; pymupdf renders it inline, so the
    # Register's text carries a bullet the capture does not. Same class as the
    # soft hyphen above -- a marker, not a word. Admitted under the same test:
    # zero change to any already-anchored range, 7 UNANCHORED converted.
    ("•", ""),
)

_WS = re.compile(r"\s+")

UNANCHORED = "UNANCHORED"

#: Below this, a fragment can match inside an unrelated sentence. Refused
#: rather than risked.
MIN_ANCHOR_CHARS = 24

#: Relations a section can bear to a requirement. `governing` is the
#: requirement's own text; the rest are the material the Register and the
#: revision bundle attach to it. A relation narrows WHICH of a requirement's
#: material is asked for — it must never bar a passage from a general search
#: (`capture.positional_role`'s P1.3 rule).
RELATIONS = ("governing", "measure", "applicable_systems", "technical_basis")


def normalise(text: str) -> str:
    """NFKC, licensed substitutions, whitespace collapse. Nothing else.

    Deliberately not a "cleaner". Every transformation must be meaning-
    preserving; anything that could change what a requirement SAYS does not
    belong, because the whole value of the anchor is that it is exact.
    """
    out = unicodedata.normalize("NFKC", text or "")
    for src, dst in _SUBSTITUTIONS:
        out = out.replace(src, dst)
    return _WS.sub(" ", out).strip()


@dataclass
class OffsetMap:
    """Normalised text plus the original index of each normalised character.

    Needed because the located range must be reported in ORIGINAL coordinates:
    `source_sections.char_start`/`char_end` live in the original space, and an
    overlap test across two coordinate systems is silently wrong.
    """

    normalised: str
    origin: list[int] = field(default_factory=list)

    @classmethod
    def build(cls, text: str) -> OffsetMap:
        chars: list[str] = []
        origin: list[int] = []
        pending_space = False
        started = False
        for index, raw in enumerate(text or ""):
            piece = unicodedata.normalize("NFKC", raw)
            for src, dst in _SUBSTITUTIONS:
                piece = piece.replace(src, dst)
            if not piece:
                continue
            if piece.isspace():
                if started:
                    pending_space = True
                continue
            if pending_space:
                chars.append(" ")
                origin.append(index)
                pending_space = False
            for ch in piece:
                chars.append(ch)
                origin.append(index)
            started = True
        return cls(normalised="".join(chars), origin=origin)

    def to_original(self, start: int, end: int) -> tuple[int, int]:
        if not self.origin:
            return (0, 0)
        first = self.origin[max(0, min(start, len(self.origin) - 1))]
        last = self.origin[max(0, min(end - 1, len(self.origin) - 1))]
        return (first, last + 1)


@dataclass
class Anchor:
    """One requirement located in one captured revision, or not."""

    requirement_id: str
    revision_id: str
    relation: str
    anchored: bool
    char_start: int = -1
    char_end: int = -1
    section_ids: list[str] = field(default_factory=list)
    occurrences: int = 0
    reason: str = ""


def locate(needle_text: str, offsets: OffsetMap) -> tuple[int, int, int, str]:
    """Find ``needle_text`` in the captured space. Returns (start, end, count, reason).

    Multiple occurrences are NOT an error — a requirement's text recurs where
    the Guidelines quote it. The first occurrence in reading order is the
    governing one (requirement tables precede Guidelines in every CIP PDF) and
    the count is recorded so a reader can see the text recurs. Zero is
    `UNANCHORED`.
    """
    needle = normalise(needle_text)
    if not needle:
        return (-1, -1, 0, "no text to anchor")
    if len(needle) < MIN_ANCHOR_CHARS:
        return (-1, -1, 0, f"text too short to anchor safely ({len(needle)} chars)")
    hay = offsets.normalised
    first = hay.find(needle)
    if first < 0:
        return (-1, -1, 0, "text does not occur in the captured revision")
    count = hay.count(needle)
    start, end = offsets.to_original(first, first + len(needle))
    return (start, end, count, "")


def sections_overlapping(repo: Any, revision_id: str, start: int, end: int) -> list[str]:
    """Sections of ``revision_id`` whose half-open span overlaps [start, end)."""
    rows = repo._conn.execute(
        """SELECT section_id FROM source_sections
            WHERE revision_id = ? AND char_end > ? AND char_start < ?
            ORDER BY ordinal""",
        (revision_id, start, end),
    ).fetchall()
    return [str(r[0]) for r in rows]


def _anchor_one(
    repo: Any, revision_id: str, offsets: OffsetMap, req_id: str, text: str, relation: str
) -> Anchor:
    start, end, count, reason = locate(text, offsets)
    if start < 0:
        return Anchor(req_id, revision_id, relation, False, reason=reason)
    section_ids = sections_overlapping(repo, revision_id, start, end)
    return Anchor(
        requirement_id=req_id,
        revision_id=revision_id,
        relation=relation,
        anchored=bool(section_ids),
        char_start=start,
        char_end=end,
        section_ids=section_ids,
        occurrences=count,
        reason="" if section_ids else "located in text but no section span overlaps it",
    )


def anchor_revision(repo: Any, revision_id: str, nodes: list[Any]) -> list[Anchor]:
    """Anchor every requirement node of one standard into one captured revision.

    Emits a `governing` anchor per node, plus `measure` and
    `applicable_systems` anchors where the Register carries that text. In a CIP
    requirements table all three usually land on the SAME ``table_row``
    section, because a row is one unit — that is expected and correct, and it
    is why the relation is a column on the join rather than a new section.
    """
    full = repo.get_document_text(revision_id) or ""
    if not full:
        return [
            Anchor(
                str(getattr(n, "id", "")),
                revision_id,
                "governing",
                False,
                reason="captured revision has no stored full_text",
            )
            for n in nodes
        ]
    offsets = OffsetMap.build(full)
    out: list[Anchor] = []
    for node in nodes:
        req_id = str(node.id)
        out.append(
            _anchor_one(
                repo, revision_id, offsets, req_id, str(node.verbatim_text or ""), "governing"
            )
        )
        for attr, relation in (
            ("measure_text", "measure"),
            ("applicable_systems", "applicable_systems"),
        ):
            text = str(getattr(node, attr, "") or "")
            if normalise(text):
                out.append(_anchor_one(repo, revision_id, offsets, req_id, text, relation))
    return out


def anchor_report(anchors: list[Anchor]) -> dict[str, Any]:
    """The honest census, per relation. Every miss named, never rounded away.

    An unanchored `governing` requirement is one the reading path cannot
    retrieve at all; an unanchored `measure` is a smaller loss. Reporting one
    rate over both would hide the difference.
    """
    by_relation: dict[str, dict[str, Any]] = {}
    for relation in RELATIONS:
        rows = [a for a in anchors if a.relation == relation]
        if not rows:
            continue
        hit = [a for a in rows if a.anchored]
        by_relation[relation] = {
            "attempted": len(rows),
            "anchored": len(hit),
            "rate": round(len(hit) / len(rows), 4),
            "recurring_text": sum(1 for a in hit if a.occurrences > 1),
            "sections_joined": sum(len(a.section_ids) for a in hit),
            "unanchored": [
                {"requirement_id": a.requirement_id, "reason": a.reason}
                for a in rows
                if not a.anchored
            ],
        }
    governing = by_relation.get("governing", {})
    return {
        "by_relation": by_relation,
        "governing_rate": governing.get("rate", 0.0),
        "signal": UNANCHORED if governing.get("unanchored") else "",
    }
