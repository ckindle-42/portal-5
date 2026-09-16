"""Faithful whole-document capture (BILATERAL_CORPUS_V1 P1).

Extraction's only job here is **fidelity**. A captured document is the whole
document — front matter to final page — laid out as an ordered tiling of units
over one character coordinate space. Nothing is dropped because nothing is
selected: there is no requirement parser, no VSL parser, no rationale parser and
no keyword classifier in this module, and there must never be one.

What a unit records is *where it is*:

* ``ordinal`` — reading order, 0-based;
* ``heading_path`` — from the document's own outline, never invented;
* ``page_start`` / ``page_end`` — from the reader's own provenance;
* ``char_start`` / ``char_end`` — a half-open span in :attr:`CapturedDocument.full_text`;
* ``unit_kind`` — ``prose`` | ``table`` | ``table_row`` | ``list_item`` | ``figure_caption``.

What a unit **means** is not recorded, because meaning is read by a model at
question time, not decided by a regex at ingest.

Three properties hold by construction and are asserted by
:func:`fidelity_report`:

1. **total character coverage** — the units tile ``full_text`` exactly: no gap,
   no overlap, every character in exactly one unit;
2. **total page coverage** — every page ``1..N`` carries at least one unit (a
   page the layout reader returns nothing for is captured verbatim from the
   page's own text rather than skipped);
3. **empty reconstruction diff** — concatenating the units in ordinal order
   reproduces ``full_text`` byte for byte.

Tables are kept **as tables**. A ``table`` unit carries the caption and the
header row; each body row is its own ``table_row`` unit with its cells and the
column names they sit under, so a CIP requirements table's
``Part | Applicable Systems | Requirements | Measures`` shape survives and a
Measure stays attached to the Part it belongs to.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EXTRACTOR = "docling"
EXTRACTOR_VERSION = "capture-v1"

#: the tiling separator. Belongs to the unit it follows, so the spans remain a
#: gapless partition of ``full_text``.
_SEP = "\n"

UNIT_KINDS = ("prose", "table", "table_row", "list_item", "figure_caption")


@dataclass(frozen=True)
class CapturedUnit:
    """One positional unit of a captured document."""

    ordinal: int
    unit_kind: str
    heading_path: str
    title: str
    page_start: int
    page_end: int
    char_start: int
    char_end: int
    text: str
    #: the reader's own reference for the enclosing table (``#/tables/2``), on
    #: both the ``table`` unit and each of its ``table_row`` units; '' otherwise.
    table_ref: str = ""
    row_index: int = -1
    columns: list[str] = field(default_factory=list)
    cells: list[str] = field(default_factory=list)

    @property
    def path(self) -> str:
        """The addressable structural path: heading lineage plus the unit's own
        position under it."""
        tail = f"row {self.row_index}" if self.unit_kind == "table_row" else f"#{self.ordinal}"
        return f"{self.heading_path} / {tail}" if self.heading_path else tail


@dataclass(frozen=True)
class CapturedDocument:
    path: Path
    page_count: int
    full_text: str
    units: list[CapturedUnit]
    extractor: str = EXTRACTOR
    extractor_version: str = EXTRACTOR_VERSION
    #: every distinct normalised string the layout reader produced — items and
    #: table cells alike. Kept so the fidelity gate can be checked against the
    #: READER rather than only against the capture's own coordinate space; a
    #: tiling is trivially 100% of itself, which proves nothing.
    reader_strings: tuple[str, ...] = ()

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


# ── heading lineage ─────────────────────────────────────────────────────────


def _normalise(text: str) -> str:
    """Collapse the reader's whitespace. The words and their order are the
    source's; only runs of whitespace change."""
    return re.sub(r"[ \t]*\n[ \t]*", "\n", text.replace("\xa0", " ")).strip()


class _Outline:
    """The document's own heading stack, keyed by the reader's heading level."""

    def __init__(self) -> None:
        self._stack: list[tuple[int, str]] = []

    def push(self, level: int, title: str) -> None:
        self._stack = [(lv, t) for lv, t in self._stack if lv < level]
        self._stack.append((level, title))

    @property
    def path(self) -> str:
        return " > ".join(t for _lv, t in self._stack)

    @property
    def top(self) -> str:
        return self._stack[0][1] if self._stack else ""


def positional_role(heading_path: str) -> str:
    """A role read off the document's own outline — a positional fact, not a
    judgement about the passage.

    The value is the top-level heading, upper-cased and punctuation-stripped.
    It is a label for *where the passage sits*. **No code path may use it to
    bar a passage from retrieval, return or citation** (P1.3).
    """
    top = heading_path.split(" > ", 1)[0] if heading_path else ""
    slug = re.sub(r"[^A-Za-z0-9]+", "_", top).strip("_").upper()
    return slug or "FRONT_MATTER"


# ── the reader ──────────────────────────────────────────────────────────────


def _page_of(item: Any) -> tuple[int, int]:
    prov = getattr(item, "prov", None) or []
    pages = [int(p.page_no) for p in prov if getattr(p, "page_no", None)]
    return (min(pages), max(pages)) if pages else (0, 0)


def _table_rows(item: Any) -> tuple[list[str], list[list[str]], list[list[str]]]:
    """``(columns, header_rows, body_rows)`` for one table item.

    A row is a header row while every cell in it is flagged as one by the
    reader; the LAST header row carries the column names and everything after
    it is a body row. Header rows above it (a CIP requirements table spans its
    caption across all four columns as row 0) are kept on the ``table`` unit —
    dropping them would lose which requirement the table belongs to.
    """
    data = getattr(item, "data", None)
    grid = list(getattr(data, "grid", []) or [])
    if not grid:
        return [], [], []
    text_grid = [[_normalise(str(getattr(c, "text", "") or "")) for c in row] for row in grid]
    header_n = 0
    for row, trow in zip(grid, text_grid, strict=True):
        flagged = all(bool(getattr(c, "column_header", False)) for c in row) and any(trow)
        if not flagged:
            break
        header_n += 1
    if header_n == 0:
        header_n = 1  # a reader that flags nothing still has a first row of names
    columns = text_grid[header_n - 1]
    return columns, text_grid[:header_n], text_grid[header_n:]


def _units_from_document(doc: Any) -> list[dict[str, Any]]:
    """Every reader item in reading order, as raw unit dicts (no offsets yet)."""
    outline = _Outline()
    raw: list[dict[str, Any]] = []
    for item, level in doc.iterate_items():
        kind = type(item).__name__
        page_start, page_end = _page_of(item)
        if kind == "SectionHeaderItem":
            title = _normalise(str(getattr(item, "text", "") or ""))
            if not title:
                continue
            outline.push(int(getattr(item, "level", level) or level), title)
            raw.append(
                {
                    "unit_kind": "prose",
                    "heading_path": outline.path,
                    "title": title,
                    "page_start": page_start,
                    "page_end": page_end,
                    "text": title,
                }
            )
            continue
        if kind == "TableItem":
            columns, header_rows, body = _table_rows(item)
            ref = str(getattr(item, "self_ref", "") or "")
            caption = ""
            with_caption = getattr(item, "caption_text", None)
            if callable(with_caption):
                try:
                    caption = _normalise(str(with_caption(doc) or ""))
                except Exception:  # noqa: BLE001 — a caption is optional metadata
                    caption = ""
            # every header row, in order — a caption row spanning all columns
            # collapses to its single distinct value rather than repeating it.
            header_lines = [
                " | ".join(dict.fromkeys(row)) if len(set(row)) == 1 else " | ".join(row)
                for row in header_rows
            ]
            raw.append(
                {
                    "unit_kind": "table",
                    "heading_path": outline.path,
                    "title": caption or (header_lines[0] if header_lines else ""),
                    "page_start": page_start,
                    "page_end": page_end,
                    "text": "\n".join(t for t in ([caption] + header_lines) if t),
                    "table_ref": ref,
                    "columns": columns,
                }
            )
            for idx, cells in enumerate(body):
                raw.append(
                    {
                        "unit_kind": "table_row",
                        "heading_path": outline.path,
                        "title": cells[0] if cells else "",
                        "page_start": page_start,
                        "page_end": page_end,
                        "text": " | ".join(cells),
                        "table_ref": ref,
                        "row_index": idx,
                        "columns": columns,
                        "cells": cells,
                    }
                )
            continue
        if kind == "PictureItem":
            caption = ""
            fn = getattr(item, "caption_text", None)
            if callable(fn):
                try:
                    caption = _normalise(str(fn(doc) or ""))
                except Exception:  # noqa: BLE001 — a caption is optional metadata
                    caption = ""
            if not caption:
                continue
            raw.append(
                {
                    "unit_kind": "figure_caption",
                    "heading_path": outline.path,
                    "title": caption,
                    "page_start": page_start,
                    "page_end": page_end,
                    "text": caption,
                }
            )
            continue
        text = _normalise(str(getattr(item, "text", "") or ""))
        if not text:
            continue
        raw.append(
            {
                "unit_kind": "list_item" if kind == "ListItem" else "prose",
                "heading_path": outline.path,
                "title": "",
                "page_start": page_start,
                "page_end": page_end,
                "text": text,
            }
        )
    return raw


def reader_strings(doc: Any) -> tuple[str, ...]:
    """Every distinct non-empty normalised string the layout reader produced —
    each item's text and each table cell's text. This is the independent
    reference the fidelity gate checks the capture against."""
    out: list[str] = []
    for item, _level in doc.iterate_items():
        if type(item).__name__ == "TableItem":
            data = getattr(item, "data", None)
            for row in list(getattr(data, "grid", []) or []):
                out.extend(_normalise(str(getattr(c, "text", "") or "")) for c in row)
            continue
        out.append(_normalise(str(getattr(item, "text", "") or "")))
    return tuple(dict.fromkeys(s for s in out if s))


def _page_texts(path: Path) -> list[str]:
    import pymupdf

    with pymupdf.open(path) as document:  # type: ignore[no-untyped-call]  # pymupdf open() is untyped
        return [str(page.get_text("text")) for page in document]


def _fill_uncovered_pages(
    raw: list[dict[str, Any]], page_count: int, path: Path
) -> list[dict[str, Any]]:
    """A page the layout reader returned nothing for is captured verbatim from
    the page's own text, inserted in page order. Silence about a page is the one
    thing a fidelity capture may not do."""
    covered = {u["page_start"] for u in raw if u["page_start"]}
    missing = [p for p in range(1, page_count + 1) if p not in covered]
    if not missing:
        return raw
    try:
        pages = _page_texts(path)
    except Exception:  # noqa: BLE001 — an unreadable page is recorded as such
        pages = []
    out = list(raw)
    for page_no in missing:
        body = _normalise(pages[page_no - 1]) if page_no <= len(pages) else ""
        unit = {
            "unit_kind": "prose",
            "heading_path": "",
            "title": "",
            "page_start": page_no,
            "page_end": page_no,
            "text": body or f"[page {page_no}: no extractable text]",
        }
        insert_at = len(out)
        for idx, existing in enumerate(out):
            if existing["page_start"] and existing["page_start"] > page_no:
                insert_at = idx
                break
        out.insert(insert_at, unit)
    return out


def capture_document(path: Path, *, doc: Any = None, page_count: int = 0) -> CapturedDocument:
    """Capture one document whole.

    ``doc`` / ``page_count`` let a caller that has already run the layout reader
    (the acquisition pipeline converts once and captures once) pass it in; the
    default converts here.
    """
    if doc is None:
        import asyncio

        from portal.platform.retrieval.extraction import read_document

        _md, doc = asyncio.run(read_document(path))
        if doc is None:
            raise ValueError(f"the layout reader could not convert {path}")
    page_count = page_count or len(getattr(doc, "pages", {}) or {})
    raw = _fill_uncovered_pages(_units_from_document(doc), page_count, path)

    units: list[CapturedUnit] = []
    buf: list[str] = []
    cursor = 0
    for ordinal, entry in enumerate(raw):
        body = str(entry["text"])
        piece = body + _SEP
        start, end = cursor, cursor + len(piece)
        buf.append(piece)
        cursor = end
        units.append(
            CapturedUnit(
                ordinal=ordinal,
                unit_kind=str(entry["unit_kind"]),
                heading_path=str(entry["heading_path"]),
                title=str(entry["title"]),
                page_start=int(entry["page_start"]),
                page_end=int(entry["page_end"]),
                char_start=start,
                char_end=end,
                text=piece,
                table_ref=str(entry.get("table_ref", "")),
                row_index=int(entry.get("row_index", -1)),
                columns=list(entry.get("columns", [])),
                cells=list(entry.get("cells", [])),
            )
        )
    return CapturedDocument(
        path=path,
        page_count=page_count,
        full_text="".join(buf),
        units=units,
        reader_strings=reader_strings(doc),
    )


# ── the fidelity gates ──────────────────────────────────────────────────────


def fidelity_report(captured: CapturedDocument) -> dict[str, Any]:
    """The three capture properties, measured rather than asserted."""
    full = captured.full_text
    units = captured.units
    covered = 0
    gaps: list[tuple[int, int]] = []
    overlaps: list[tuple[int, int]] = []
    cursor = 0
    for unit in sorted(units, key=lambda u: u.char_start):
        if unit.char_start > cursor:
            gaps.append((cursor, unit.char_start))
        elif unit.char_start < cursor:
            overlaps.append((unit.char_start, cursor))
        covered += max(0, unit.char_end - max(unit.char_start, cursor))
        cursor = max(cursor, unit.char_end)
    if cursor < len(full):
        gaps.append((cursor, len(full)))

    reconstruction = "".join(u.text for u in sorted(units, key=lambda u: u.ordinal))
    pages = {p for u in units for p in range(u.page_start, u.page_end + 1) if p}
    missing_pages = [p for p in range(1, captured.page_count + 1) if p not in pages]

    kinds: dict[str, int] = {}
    for unit in units:
        kinds[unit.unit_kind] = kinds.get(unit.unit_kind, 0) + 1

    absent = [s for s in captured.reader_strings if s and s not in full]

    return {
        "document": captured.path.name,
        "pages": captured.page_count,
        "characters": len(full),
        "sections": len(units),
        "sections_by_unit_kind": kinds,
        "character_coverage_pct": round(100.0 * covered / len(full), 4) if full else 0.0,
        "gaps": gaps,
        "overlaps": overlaps,
        "missing_pages": missing_pages,
        "reconstruction_diff": "" if reconstruction == full else "MISMATCH",
        "reconstruction_delta_chars": len(reconstruction) - len(full),
        "tables": len({u.table_ref for u in units if u.table_ref}),
        "table_rows": sum(1 for u in units if u.unit_kind == "table_row"),
        "reader_strings": len(captured.reader_strings),
        "reader_strings_absent": len(absent),
        "reader_strings_absent_sample": absent[:5],
    }


def assert_faithful(captured: CapturedDocument) -> dict[str, Any]:
    """Raise unless the capture is total. Used by the ingest path, so a
    lossy capture can never reach the store."""
    report = fidelity_report(captured)
    failures = []
    if report["character_coverage_pct"] != 100.0:
        failures.append(f"character coverage {report['character_coverage_pct']}%")
    if report["gaps"]:
        failures.append(f"{len(report['gaps'])} coverage gaps")
    if report["overlaps"]:
        failures.append(f"{len(report['overlaps'])} overlapping spans")
    if report["missing_pages"]:
        failures.append(f"pages with no unit: {report['missing_pages']}")
    if report["reconstruction_diff"]:
        failures.append("reconstruction diff is not empty")
    if report["reader_strings_absent"]:
        failures.append(
            f"{report['reader_strings_absent']} reader strings are absent from the capture: "
            f"{report['reader_strings_absent_sample']}"
        )
    if failures:
        raise ValueError(f"{captured.path.name}: capture is not faithful — {'; '.join(failures)}")
    return report


def table_shape(captured: CapturedDocument, table_ref: str) -> dict[str, Any]:
    """The round-tripped shape of one captured table."""
    rows = [u for u in captured.units if u.table_ref == table_ref and u.unit_kind == "table_row"]
    head = next(
        (u for u in captured.units if u.table_ref == table_ref and u.unit_kind == "table"), None
    )
    return {
        "table_ref": table_ref,
        "columns": list(head.columns) if head else [],
        "rows": len(rows),
        "cells_per_row": sorted({len(r.cells) for r in rows}),
        "row_cells": [list(r.cells) for r in rows],
    }


# ── the store write path ────────────────────────────────────────────────────


def section_id_for(revision_id: str, unit: CapturedUnit) -> str:
    """Revision-scoped, ordinal-scoped section id. Two units may share a
    heading path; their ordinal never collides."""
    body = f"{revision_id}|{unit.ordinal}|{unit.unit_kind}|{unit.path}"
    return "csection-" + hashlib.sha256(body.encode()).hexdigest()[:20]


def store_capture(
    repo: Any,
    revision_id: str,
    captured: CapturedDocument,
    *,
    org_id: str = "default",
) -> dict[str, Any]:
    """Write one faithful capture into the canonical store.

    Same-fingerprint rebuild: sections written by THIS extractor for this
    revision are replaced wholesale, so a re-capture never leaves stale units
    beside fresh ones. Sections written by another extractor are untouched.

    Refuses to write a capture that is not faithful — a lossy capture must not
    reach the store, because everything downstream reads absence off it.
    """
    from portal.modules.compliance.core.models import SourceSection
    from portal.modules.compliance.core.provenance import text_hash

    report = assert_faithful(captured)
    conn = repo._conn
    # scoped to THIS capture's own extractor, not the module default: the
    # Glossary capture declares its own extractor, and deleting by the default
    # would leave its previous units in place beside the fresh ones.
    extractor = captured.extractor
    with repo._lock, conn:
        conn.execute(
            """DELETE FROM source_table_cells WHERE section_id IN (
                   SELECT section_id FROM source_sections
                   WHERE revision_id = ? AND extractor = ?)""",
            (revision_id, extractor),
        )
        conn.execute(
            """DELETE FROM source_spans WHERE section_id IN (
                   SELECT section_id FROM source_sections
                   WHERE revision_id = ? AND extractor = ?)""",
            (revision_id, extractor),
        )
        conn.execute(
            "DELETE FROM source_sections WHERE revision_id = ? AND extractor = ?",
            (revision_id, extractor),
        )
    repo.put_document_text(
        revision_id,
        captured.full_text,
        page_count=captured.page_count,
        extractor=captured.extractor,
        extractor_version=captured.extractor_version,
        org_id=org_id,
    )
    for unit in captured.units:
        section_id = section_id_for(revision_id, unit)
        repo.add_source_section(
            SourceSection(
                section_id=section_id,
                revision_id=revision_id,
                path=unit.path,
                page_start=unit.page_start or None,
                page_end=unit.page_end or None,
                table_ref=unit.table_ref or None,
                extractor=captured.extractor,
                extractor_version=captured.extractor_version,
                org_id=org_id,
                role=positional_role(unit.heading_path),
                title=unit.title,
                unit_kind=unit.unit_kind,
                ordinal=unit.ordinal,
                char_start=unit.char_start,
                char_end=unit.char_end,
                heading_path=unit.heading_path,
            )
        )
        repo.add_source_span(
            "cspan-" + section_id[len("csection-") :],
            section_id,
            unit.char_start,
            unit.char_end,
            text_hash(unit.text),
            org_id=org_id,
        )
        if unit.unit_kind == "table_row" and unit.cells:
            repo.add_table_cells(
                section_id, unit.row_index, unit.cells, unit.columns, org_id=org_id
            )
    report["revision_id"] = revision_id
    return report
