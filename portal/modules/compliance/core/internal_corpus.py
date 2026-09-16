"""Internal controlled-corpus inventory, control-block metadata, and
section-function classification (END_TO_END Phase 4 / foundation P4).

Everything here is deterministic and text-in: ``parse_document_control`` and
``sectionize`` consume page texts (the extraction recipe lives in
``extract_pages``), so every rule is hermetically testable without the
operator's private PDFs.

The honesty rules that make this the truthful revision layer:

* a metadata field the document does not state stays ``None`` / ``''`` — a
  filename version token or a guessed date never fills it (P4: "Do not guess
  absent metadata");
* section roles come from the controlled ``SOURCE_ROLES`` vocabulary, so a
  copied regulation row inside a traceability appendix is a
  ``TRACEABILITY_ASSERTION`` end to end and can never read as operative
  implementation (lesson L18);
* parent/sibling closure: numbered headings carry their full dotted path, so
  a duty split across sibling clauses resolves to the same parent document
  section tree.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from portal.modules.compliance.core.provenance import text_hash

# ── document kinds ──────────────────────────────────────────────────────────
# Sourced from the document's own "Document Type:" line; the filename is only
# a fallback and is recorded as such in ``kind_evidence``.

#: document-kind -> (source_documents.source_kind, document_revisions.binding_effect,
#:                    document-level SOURCE_ROLE for its operative text)
KIND_TABLE: dict[str, tuple[str, str, str]] = {
    "policy": ("policy", "internally_mandatory", "INTERNAL_POLICY"),
    "standard": ("standard", "internally_mandatory", "INTERNAL_POLICY"),
    "procedure": ("procedure", "internally_mandatory", "OPERATIVE_PROCEDURE"),
    "process": ("process", "internally_mandatory", "OPERATIVE_PROCEDURE"),
    "plan": ("plan", "internally_mandatory", "OPERATIVE_PROCEDURE"),
    "work instruction": ("work_instruction", "internally_mandatory", "WORK_INSTRUCTION"),
    "evidence specification": ("evidence_specification", "descriptive", "EVIDENCE_SPECIFICATION"),
    "evidence artifact": ("evidence_artifact", "descriptive", "EVIDENCE_ARTIFACT"),
}

#: document kinds whose text records what must be retained/demonstrated but
#: which are completed records rather than instructions.
_EVIDENCE_KINDS = ("form", "report", "attestation", "log", "list", "record")

#: section roles whose text can carry an operative internal commitment. Every
#: other role (traceability rows, ToC, control pages, commentary, definitions,
#: evidence) must never manufacture an IMPLEMENTS-style commitment.
OPERATIVE_ROLES: frozenset[str] = frozenset(
    {"INTERNAL_POLICY", "OPERATIVE_PROCEDURE", "WORK_INSTRUCTION"}
)


def classify_kind(stated_type: str | None, filename: str = "") -> tuple[str, str, str, str]:
    """Map a document to ``(source_kind, binding_effect, source_role, evidence)``.

    ``stated_type`` (the document's own "Document Type:" line, lowercased)
    wins; the filename is a recorded fallback; no signal at all yields
    ``unknown`` everywhere rather than a plausible guess.
    """
    if stated_type:
        lowered_type = stated_type.strip().lower()
        for key, mapped in KIND_TABLE.items():
            if key in lowered_type:
                return (*mapped, f"document states 'Document Type: {stated_type.strip()}'")
        if any(k in lowered_type for k in _EVIDENCE_KINDS):
            return (
                "evidence_specification",
                "descriptive",
                "EVIDENCE_SPECIFICATION",
                f"document states 'Document Type: {stated_type.strip()}'",
            )
    lowered = filename.lower()
    for cue, mapped in (
        ("work instruction", ("work_instruction", "internally_mandatory", "WORK_INSTRUCTION")),
        ("wi v", ("work_instruction", "internally_mandatory", "WORK_INSTRUCTION")),
        ("procedure", ("procedure", "internally_mandatory", "OPERATIVE_PROCEDURE")),
        ("process", ("process", "internally_mandatory", "OPERATIVE_PROCEDURE")),
        ("policy", ("policy", "internally_mandatory", "INTERNAL_POLICY")),
        ("plan", ("plan", "internally_mandatory", "OPERATIVE_PROCEDURE")),
    ):
        if cue in lowered:
            return (*mapped, f"filename contains {cue!r}")
    for cue in _EVIDENCE_KINDS:
        if re.search(rf"\b{cue}\b", lowered):
            return (
                "evidence_specification",
                "descriptive",
                "EVIDENCE_SPECIFICATION",
                f"filename contains {cue!r}",
            )
    return ("unknown", "unknown", "", "no stated document type and no filename signal")


# ── dates ───────────────────────────────────────────────────────────────────

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

_SLASH_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_MONTH_DATE = re.compile(r"\b(" + "|".join(_MONTHS) + r")\.?\s+(\d{1,2}),?\s+(\d{4})\b", re.I)
_DASH_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def parse_date(text: str) -> str | None:
    """First date found in ``text`` as ISO-8601, else ``None``. Handles the
    corpus's observed shapes (``July 31, 2026``, ``7/24/2026``, ``2026-07-31``).
    Ambiguous or partial text yields ``None`` — never a guess."""
    m = _DASH_DATE.search(text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = _MONTH_DATE.search(text)
    if m:
        return f"{m.group(3)}-{_MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    m = _SLASH_DATE.search(text)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year}-{month:02d}-{day:02d}"
    return None


# ── control block ───────────────────────────────────────────────────────────

_BANNER_RE = re.compile(r"private\s*[–-]\s*for internal use|confidential", re.I)
_PAGE_MARK_RE = re.compile(r"^\s*page \d+ of \d+\s*$", re.I)


@dataclass
class DocumentControl:
    """Sourced controlled-document metadata. ``None`` = the document does not
    state it; provenance for every sourced field is in ``sources``."""

    title: str | None = None
    document_number: str | None = None
    stated_type: str | None = None
    nerc_standard: str | None = None
    effective_date: str | None = None
    approval_date: str | None = None
    approver: str | None = None
    approver_title: str | None = None
    owner: str | None = None
    owner_title: str | None = None
    version: str | None = None
    authored_date: str | None = None
    last_reviewed_date: str | None = None
    #: field -> where it was read from (page number and the matched line)
    sources: dict[str, str] = field(default_factory=dict)


_CONTROL_LINE = re.compile(
    r"^(document (?:number|id)|document type|nerc standard|effective date)\s*:\s*(.+)$", re.I
)


def _sourced(control: DocumentControl, name: str, value: object, where: str) -> None:
    """Record a field value and its page provenance in one step."""
    control.sources[name] = where
    setattr(control, name, value)


def _parse_labelled_fields(pages: list[str], control: DocumentControl) -> None:
    """Front-matter labelled fields (page 1 in the observed corpus,
    tolerated through page 3)."""
    for page_no, page in enumerate(pages[:3], start=1):
        for line in page.splitlines():
            if _BANNER_RE.search(line) or _PAGE_MARK_RE.match(line):
                continue
            m = _CONTROL_LINE.match(line.strip())
            if not m:
                continue
            where = f"page {page_no}: {line.strip()}"
            field, value = m.group(1).lower(), m.group(2).strip()
            if field in ("document number", "document id"):
                _sourced(control, "document_number", value, where)
            elif field == "document type" and control.stated_type is None:
                _sourced(control, "stated_type", value, where)
            elif field == "nerc standard":
                _sourced(control, "nerc_standard", value, where)
            elif field == "effective date" and control.effective_date is None:
                parsed = parse_date(value)
                if parsed:
                    _sourced(control, "effective_date", parsed, where)


def _parse_title_block(first_page: str, control: DocumentControl) -> None:
    """Title: non-banner lines before the first labelled field on page 1."""
    title_lines: list[str] = []
    for line in first_page.splitlines():
        stripped = line.strip()
        if not stripped or _BANNER_RE.search(stripped) or _PAGE_MARK_RE.match(stripped):
            continue
        if _CONTROL_LINE.match(stripped):
            break
        title_lines.append(stripped)
    if title_lines:
        _sourced(control, "title", " ".join(title_lines), "page 1: title block")


def _parse_owner_line(page_no: int, line: str, control: DocumentControl) -> bool:
    """One DOCUMENT OWNER line; returns whether the block stays active."""
    low = line.lower()
    if low.startswith("name") or low.startswith("title"):
        return True  # the column header row
    where = f"page {page_no}: DOCUMENT OWNER"
    if control.owner is None:
        _sourced(control, "owner", line, where)
        return True
    if control.owner_title is None:
        _sourced(control, "owner_title", line, where)
        return False
    return True


def _parse_approval_line(page_no: int, line: str, control: DocumentControl) -> bool:
    """One APPROVALS line: 'Name: X' / 'Title: Y' or the date line (the
    approval event). Returns whether the block stays active."""
    low = line.lower()
    where = f"page {page_no}: APPROVALS"
    if low.startswith("name:"):
        _sourced(control, "approver", line.split(":", 1)[1].strip(), where)
        return True
    if low.startswith("title:"):
        _sourced(control, "approver_title", line.split(":", 1)[1].strip(), where)
        return True
    parsed = parse_date(line)
    if parsed:
        _sourced(control, "approval_date", parsed, where)
        return False
    return True


def _parse_owner_approval_blocks(pages: list[str], control: DocumentControl) -> None:
    """DOCUMENT OWNER (Name/Title rows) and APPROVALS (Name:/Title:/date)
    blocks. A field the block does not state stays None."""
    owner_section = approvals_section = False
    for page_no, page in enumerate(pages, start=1):
        owner_section = False
        for raw_line in page.splitlines():
            line = raw_line.strip()
            if not line or _PAGE_MARK_RE.match(line) or _BANNER_RE.search(line):
                continue
            upper = line.upper()
            if upper.startswith("DOCUMENT OWNER"):
                owner_section, approvals_section = True, False
                continue
            if upper.startswith("APPROVAL"):
                owner_section, approvals_section = False, True
                continue
            if upper.startswith("REVISION HISTORY"):
                owner_section = approvals_section = False
                continue
            if owner_section:
                owner_section = _parse_owner_line(page_no, line, control)
            elif approvals_section:
                approvals_section = _parse_approval_line(page_no, line, control)


def parse_document_control(pages: list[str]) -> DocumentControl:
    """Read the document's own control block: labelled front-matter fields,
    the page-1 title, DOCUMENT OWNER / APPROVALS blocks, and the REVISION
    HISTORY table wherever it lives. Fields the document does not state stay
    ``None`` — a filename never invents a value."""
    control = DocumentControl()
    _parse_labelled_fields(pages, control)
    if pages:
        _parse_title_block(pages[0], control)
    _parse_owner_approval_blocks(pages, control)
    for page_no, page in enumerate(pages, start=1):
        if (
            page.strip().upper().startswith("REVISION HISTORY")
            or "REVISION HISTORY" in page.upper()
        ):
            _parse_revision_history(pages, page_no, page, control)
            break
    return control


def _parse_revision_history(
    pages: list[str], start_page_no: int, start_page: str, control: DocumentControl
) -> None:
    """Latest revision-history row sources ``version`` and ``authored_date``;
    the latest row whose comments mention a review sources
    ``last_reviewed_date``. Row shape in the corpus:
    ``<date> <version> <revised by> <comments>`` flowing as wrapped text."""
    body = [start_page]
    # The table can continue past its heading page; take through the next
    # ALL-CAPS heading or end of document.
    for page in pages[start_page_no:]:
        body.append(page)
    text = "\n".join(body)
    rows: list[tuple[str, str]] = []
    for m in _SLASH_DATE.finditer(text):
        tail = text[m.end() : m.end() + 40]
        vm = re.match(r"\s*\n?\s*(\d+(?:\.\d+)?)\s", tail)
        if vm:
            rows.append((m.group(0), vm.group(1)))
    if not rows:
        return
    date, version = rows[-1]
    control.version = version
    control.authored_date = parse_date(date)
    control.sources["version"] = f"page {start_page_no}: REVISION HISTORY latest row {version}"
    control.sources["authored_date"] = f"page {start_page_no}: REVISION HISTORY {date}"
    review_dates = [
        parse_date(m.group(0))
        for m in _SLASH_DATE.finditer(text)
        if re.search(r"review", text[m.end() : m.end() + 120], re.I)
    ]
    dated = [d for d in review_dates if d]
    if dated:
        control.last_reviewed_date = max(dated)
        control.sources["last_reviewed_date"] = f"page {start_page_no}: REVISION HISTORY review row"


# ── sectioning ──────────────────────────────────────────────────────────────

_NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\s+(\S.*)$")
_BARE_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)$")
_CAPS_HEADING = re.compile(r"^[A-Z][A-Z &:/,'()\-–—]+$")
_TOC_MARK = re.compile(r"\.{4,}\s*\d+\s*$")
_SENTENCE_MODAL = re.compile(r"\b(shall|must|may |will |required to)\b", re.I)


@dataclass
class InternalSection:
    """One classified section of an internal document revision. ``path`` is
    the full dotted heading path (parent/sibling closure), ``role`` a
    SOURCE_ROLES value, and the span anchors into the document's extracted
    text so every claim back to this section hash-verifies."""

    path: str
    title: str
    role: str
    page_start: int
    page_end: int
    char_start: int
    char_end: int
    revision_id: str = ""
    text: str = ""
    #: matched heading text ("5.1 Appendix 1: Requirements Traceability")
    heading: str = ""

    @property
    def section_id(self) -> str:
        # revision-scoped: two documents may both have a '1.0' on page 1 —
        # their sections must never share an id.
        return (
            "isection-"
            + hashlib.sha256(
                f"{self.revision_id}|{self.path}|{self.page_start}|{self.role}".encode()
            ).hexdigest()[:20]
        )

    def span_sha256(self) -> str:
        return text_hash(self.text)


def _is_toc_page(page: str) -> bool:
    head = page[:600].lower()
    if "table of contents" in head:
        return True
    lines = [ln for ln in page.splitlines() if ln.strip()]
    if len(lines) < 3:
        return False
    dotted = sum(1 for ln in lines if _TOC_MARK.search(ln))
    return dotted >= max(3, len(lines) // 2)


def _is_title_like(text: str, *, relaxed: bool = False) -> bool:
    """A plausible heading title: short, no terminal punctuation, not a
    sentence (no modals). Numbered content items ('Carries out tasks ...
    activities.') fail this and stay inside their parent section's text.
    Same-line numbered headings may run long ('3.2 Software Security Patch
    Device, Application, and Source Inventories'); the next-line shape stays
    strict because a wrapped sentence begins exactly like a title."""
    stripped = text.strip()
    max_chars, max_words = (90, 14) if relaxed else (60, 8)
    if not stripped or len(stripped) > max_chars:
        return False
    if stripped.endswith((".", ",", ";", ":")):
        return False
    if _SENTENCE_MODAL.search(stripped):
        return False
    return len(stripped.split()) <= max_words


def _detect_headings(pages: list[str], toc_pages: set[int]) -> list[tuple[int, int, str, str]]:
    """Headings in document order as (page, line, number, title).

    Three guards keep numbered CONTENT and table rows from becoming
    sections:

    * a heading number must continue the document's own numbering (a
      '3.1' row inside the '5.1 Requirements Traceability' table does not
      extend the running '5.x' path and stays table text);
    * after a REVISION HISTORY heading no numbered heading is accepted (its
      date/version/author rows re-use section-shaped numbers);
    * a bare number line heads a section only when the next line is
      title-like — sentence lines after a number are numbered content items.
    """
    raw: list[tuple[int, int, str, str]] = []
    stack: list[str] = []  # accepted number per depth, e.g. ['1.0', '1.4']
    after_revision_history = False
    for i, page in enumerate(pages):
        if i in toc_pages:
            continue
        lines = page.splitlines()
        j = 0
        while j < len(lines):
            line = lines[j].strip()
            j += 1
            if not line or _BANNER_RE.search(line) or _PAGE_MARK_RE.match(line):
                continue
            m = _NUMBERED_HEADING.match(line)
            if m and len(line) <= 120 and _is_title_like(m.group(2), relaxed=True):
                number, title = m.group(1), m.group(2).strip()
                if after_revision_history or not _continues_numbering(number, stack):
                    continue
                stack = _push_number(number, stack)
            elif _BARE_NUMBER.match(line) and j < len(lines):
                nxt = lines[j].strip()
                if not (nxt and _is_title_like(nxt) and not _BARE_NUMBER.match(nxt)):
                    continue
                number, title = line, nxt
                if after_revision_history or not _continues_numbering(number, stack):
                    continue
                stack = _push_number(number, stack)
                j += 1
            elif _CAPS_HEADING.match(line) and _is_control_heading(line):
                number, title = "", line
                if "revision history" in line.lower():
                    after_revision_history = True
            else:
                continue
            raw.append((i, _line_index_of_heading(pages[i], number, title), number, title))
    return raw


def _norm(number: str) -> str:
    """'5.0' and '5' are the same top-level section in the corpus numbering."""
    return number[:-2] if number.endswith(".0") else number


def _depth(number: str) -> int:
    """Nesting depth of a corpus number: 'X.0' is top-level (depth 1),
    'X.Y' depth 2, 'X.Y.Z' depth 3, ..."""
    return _norm(number).count(".") + 1


def _continues_numbering(number: str, stack: list[str]) -> bool:
    """True when ``number`` extends, siblings, or closes the running path —
    i.e. its parent equals the running stack at depth-1 ('5.1' under
    '5.0'/'5'; '1.4.2' under '1.4'). A top-level number always continues."""
    depth = _depth(number)
    if depth == 1:
        return True
    if depth - 2 >= len(stack):
        return False  # an orphan deeper number after shallower content
    return _norm(stack[depth - 2]) == _norm(number.rsplit(".", 1)[0])


def _push_number(number: str, stack: list[str]) -> list[str]:
    return stack[: _depth(number) - 1] + [number]


def _is_control_heading(line: str) -> bool:
    """ALL-CAPS structural headings ('DOCUMENT OWNER', 'REVISION HISTORY');
    short caps tokens ('TFE') and trailing-colon table labels ('CAUTION:')
    are table/content text, not headings."""
    stripped = line.strip()
    return len(stripped) >= 6 and not stripped.endswith(":")


def _classify_headings(
    raw: list[tuple[int, int, str, str]], operative_role: str
) -> list[tuple[int, int, str, str, str]]:
    """Assign each heading (page, line, path, title, role). A heading inside
    a traceability subtree ('5.1 Appendix 1: Requirements Traceability' under
    '5.0 Appendix') inherits the traceability role, so copied regulation rows
    can never read operative."""
    trace_roots: list[str] = []
    out: list[tuple[int, int, str, str, str]] = []
    for page_no, line_idx, number, title in raw:
        path = number if number else title
        if "traceabilit" in title.lower():
            trace_roots.append(path)
        in_trace = any(path == r or path.startswith(r + ".") for r in trace_roots)
        role = "TRACEABILITY_ASSERTION" if in_trace else _role_for(number, title, operative_role)
        out.append((page_no, line_idx, path, title, role))
    return out


def _span_sections(
    headings: list[tuple[int, int, str, str, str]],
    pages: list[str],
    page_offsets: list[int],
    toc_pages: set[int],
    full_text: str,
) -> list[InternalSection]:
    """One section per heading, spanning to the next heading or the start of
    a ToC page (whichever comes first); leading matter is the cover/control
    block."""
    starts = sorted(
        (
            page_offsets[p] + sum(len(x) + 1 for x in pages[p].splitlines()[:ln]),
            p,
            path,
            title,
            role,
        )
        for p, ln, path, title, role in headings
    )
    toc_starts = sorted(page_offsets[i] for i in toc_pages)
    total_chars = page_offsets[-1] - 1
    sections: list[InternalSection] = []
    if starts and starts[0][0] > 0:
        first_start = starts[0][0]
        sections.append(
            InternalSection(
                path="front",
                title="",
                role="DOCUMENT_CONTROL",
                page_start=1,
                page_end=_page_of_offset(page_offsets, first_start - 1) + 1,
                char_start=0,
                char_end=first_start,
                text=full_text[:first_start],
            )
        )
    for idx, (start, hp, path, title, role) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else total_chars
        later_toc = [t for t in toc_starts if t > start]
        if later_toc:
            end = min(end, later_toc[0])
        if end <= start:
            end = min(start + 1, total_chars)
        sections.append(
            InternalSection(
                path=path,
                title=title,
                role=role,
                page_start=hp + 1,
                page_end=_page_of_offset(page_offsets, end - 1) + 1,
                char_start=start,
                char_end=end,
                text=full_text[start:end],
                heading=f"{path} {title}".strip(),
            )
        )
    return sections


def _fallback_page_sections(
    pages: list[str], page_offsets: list[int], operative_role: str
) -> list[InternalSection]:
    """No headings at all (forms, contact lists): per-page sections at the
    document-level role so the whole document remains addressable."""
    end_of_text = page_offsets[-1] - 1
    return [
        InternalSection(
            path=f"page.{i + 1}",
            title="",
            role=operative_role,
            page_start=i + 1,
            page_end=i + 1,
            char_start=page_offsets[i],
            # to the NEXT page's start, so the join newline belongs to the page
            # it follows and the pages tile the document with no 1-char gaps.
            char_end=min(page_offsets[i + 1], end_of_text),
            text=page,
        )
        for i, page in enumerate(pages)
        if page.strip()
    ]


def _toc_sections(
    pages: list[str], page_offsets: list[int], toc_pages: set[int]
) -> list[InternalSection]:
    """ToC pages become their own sections wherever they sit."""
    return [
        InternalSection(
            path=f"toc.p{i + 1}",
            title="Table of Contents",
            role="TABLE_OF_CONTENTS",
            page_start=i + 1,
            page_end=i + 1,
            char_start=page_offsets[i],
            char_end=min(page_offsets[i + 1], page_offsets[-1] - 1),
            text=pages[i],
            heading="Table of Contents",
        )
        for i in sorted(toc_pages)
    ]


def sectionize(pages: list[str], *, operative_role: str = "") -> list[InternalSection]:
    """Split a document into role-classified sections.

    ``operative_role`` is the document-level role from :func:`classify_kind`
    (e.g. ``OPERATIVE_PROCEDURE``); body sections receive it. Traceability
    appendix subtrees, the ToC, document-control pages, definitions and
    revision history receive their own roles. Evidence documents without
    headings fall back to per-page sections at the document-level role
    (or ``EVIDENCE_SPECIFICATION`` when unspecified).
    """
    operative_role = operative_role or "EVIDENCE_SPECIFICATION"
    page_offsets = [0]
    for page in pages:
        page_offsets.append(page_offsets[-1] + len(page) + 1)  # +1 join newline
    toc_pages = {i for i, page in enumerate(pages) if _is_toc_page(page)}
    headings = _classify_headings(_detect_headings(pages, toc_pages), operative_role)
    if headings:
        sections = _span_sections(headings, pages, page_offsets, toc_pages, "\n".join(pages))
    else:
        sections = _fallback_page_sections(pages, page_offsets, operative_role)
    sections.extend(_toc_sections(pages, page_offsets, toc_pages))
    sections.sort(key=lambda s: s.char_start)
    return _complete_tiling(sections, "\n".join(pages), page_offsets, operative_role)


def _complete_tiling(
    sections: list[InternalSection],
    full_text: str,
    page_offsets: list[int],
    operative_role: str,
) -> list[InternalSection]:
    """Close every gap the heading/ToC split leaves, so the sections tile the
    document's whole text.

    Measured on the 68-document operator corpus before this pass: 63 documents
    lost material at a section boundary — the char between a ToC page's end and
    the next heading's line, and the tail after the last heading. Small, but a
    corpus that silently drops text cannot support an absence claim
    (BILATERAL_CORPUS_V1 P1.7). Filler carries the document's own operative
    role — it is ordinary body text nobody gave a heading, not a lesser class of
    passage, and no code path may use its role to withhold it.
    """
    ordered = sorted(sections, key=lambda s: (s.char_start, s.char_end))
    out: list[InternalSection] = []
    cursor = 0
    for idx, section in enumerate(ordered):
        # a section never reaches into the next one: the cover/control block
        # spans to the first heading, which may be on the far side of a ToC page
        # the ToC pass also claims.
        limit = ordered[idx + 1].char_start if idx + 1 < len(ordered) else len(full_text)
        start = max(section.char_start, cursor)
        end = min(section.char_end, max(limit, start))
        if end <= start:
            continue  # wholly inside a section already emitted
        if start > cursor:
            out.append(_filler(cursor, start, full_text, page_offsets, operative_role))
        if (start, end) != (section.char_start, section.char_end):
            section.char_start, section.char_end = start, end
            section.page_end = _page_of_offset(page_offsets, max(start, end - 1)) + 1
        # one invariant, enforced in one place: a section's text IS its span.
        section.text = full_text[start:end]
        out.append(section)
        cursor = end
    if cursor < len(full_text):
        out.append(_filler(cursor, len(full_text), full_text, page_offsets, operative_role))
    return out


def _filler(
    start: int, end: int, full_text: str, page_offsets: list[int], operative_role: str
) -> InternalSection:
    return InternalSection(
        path=f"unsectioned.{start}",
        title="",
        role=operative_role,
        page_start=_page_of_offset(page_offsets, start) + 1,
        page_end=_page_of_offset(page_offsets, max(start, end - 1)) + 1,
        char_start=start,
        char_end=end,
        text=full_text[start:end],
    )


def _page_of_offset(page_offsets: list[int], offset: int) -> int:
    """The page index a char offset falls in (page_offsets[i] is page i's
    start offset in the joined text)."""
    lo, hi = 0, len(page_offsets) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if page_offsets[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _role_for(number: str, title: str, operative_role: str) -> str:
    low = title.lower()
    if "traceabilit" in low:
        return "TRACEABILITY_ASSERTION"
    if not number and "PRIVATE" not in title and _CAPS_HEADING.match(title):
        if any(k in low for k in ("revision history", "document owner", "approval")):
            return "DOCUMENT_CONTROL"
        return "COMMENTARY"
    if re.search(r"\bdefinitions?\b", low):
        return "DEFINITION"
    return operative_role


def _line_index_of_heading(page: str, number: str, title: str) -> int:
    """The line a heading starts on. Prefers the exact 'number + title'
    same-line shape, then the bare-number + next-line-title corpus shape,
    then a bare title line."""
    lines = page.splitlines()
    same_line = f"{number} {title}".strip()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped == same_line:
            return idx
        if (
            number
            and stripped == number
            and idx + 1 < len(lines)
            and lines[idx + 1].strip() == title
        ):
            return idx
    for idx, line in enumerate(lines):
        if line.strip() == title:
            return idx
    return 0


# ── extraction adapter ──────────────────────────────────────────────────────

EXTRACTOR = "pymupdf"


def extract_pages(path: Path) -> tuple[list[str], str]:
    """Deterministic page texts for a PDF plus the joined full text. The
    joined text is the span coordinate space: char offsets from sectionize
    resolve against ``full_text`` and hash-verify against section text."""
    import pymupdf

    with pymupdf.open(path) as document:
        pages = [page.get_text("text") for page in document]
    return pages, "\n".join(pages)


def inventory_file(path: Path) -> dict:
    """Classify one controlled document: sourced control metadata, kind, and
    section functions. No store access — the pure inventory half of P4."""
    pages, full_text = extract_pages(path)
    control = parse_document_control(pages)
    source_kind, binding_effect, doc_role, evidence = classify_kind(control.stated_type, path.name)
    sections = sectionize(pages, operative_role=doc_role)
    return {
        "path": path,
        "pages": len(pages),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "control": control,
        "source_kind": source_kind,
        "binding_effect": binding_effect,
        "document_role": doc_role,
        "kind_evidence": evidence,
        "sections": sections,
        "full_text": full_text,
    }
