"""The NERC Glossary of Terms as a resolvable corpus (BILATERAL_CORPUS_V1 P2).

A CIP standard that carries no definitions section defers to the *Glossary of
Terms Used in NERC Reliability Standards*. Before this module,
``regulatory_bundle._extract_definitions`` recorded that deferral honestly as
``definitions_disposition = "external_glossary"`` — and then nothing ever
fetched the Glossary, so every capitalised defined term in a requirement
(``BES Cyber System``, ``EACMS``, ``External Routable Connectivity``) resolved
to nothing at all. A requirement whose defined terms are unreadable cannot be
read.

**Source.** NERC serves the Glossary at https://www.nerc.com/glossary-of-terms
as a page whose ``window._model`` payload carries one structured record per
term: the term, its acronym, the verbatim ``definitionHtml``, its status,
region, docket number, Board-adoption date, effective date and inactive date.
That payload is the authority; the acquired bytes are hashed into the same
append-only manifest as the standards, with the same UNCHANGED semantics.

**Honesty rules this module owns.**

* A term's definition is the Glossary's own words, never paraphrased and never
  assembled from a standard's inline text.
* Both clocks apply: a term carries its effective and inactive dates, so a
  resolution at a ``valid_at`` outside that window is reported as not yet
  effective or retired — not silently served.
* A term the Glossary does not carry resolves to an explicit ``unresolved``
  entry naming the term. It is never guessed, never silently empty, and never
  filled from a similar term.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GLOSSARY_URL = "https://www.nerc.com/glossary-of-terms"
GLOSSARY_ARTIFACT = "glossary-of-terms.html"
GLOSSARY_LOGICAL_ID = "NERC/glossary-of-terms"
GLOSSARY_SOURCE_KIND = "glossary"

EXTRACTOR = "nerc_glossary"
EXTRACTOR_VERSION = "1"

_MODEL_MARKER = "window._model = "
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class GlossaryTerm:
    """One Glossary entry, verbatim, with its own effectivity."""

    term: str
    definition: str
    acronym: str = ""
    status: str = ""
    region: str = ""
    docket: str = ""
    footnote: str = ""
    adopted_date: str = ""
    effective_date: str = ""
    inactive_date: str = ""
    ordinal: int = 0

    @property
    def heading(self) -> str:
        return f"{self.term} ({self.acronym})" if self.acronym else self.term

    def text(self) -> str:
        """The unit's verbatim body: the heading line, then the definition, then
        the footnote if the Glossary carries one."""
        parts = [self.heading, self.definition]
        if self.footnote:
            parts.append(self.footnote)
        return "\n".join(parts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "term": self.term,
            "acronym": self.acronym,
            "definition": self.definition,
            "footnote": self.footnote,
            "status": self.status,
            "region": self.region,
            "docket": self.docket,
            "adopted_date": self.adopted_date,
            "effective_date": self.effective_date,
            "inactive_date": self.inactive_date,
        }


def _plain(value: Any) -> str:
    """Glossary HTML → text. Verbatim words; only markup and entity escapes go."""
    if not value:
        return ""
    text = _TAG_RE.sub(" ", str(value))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _iso(value: Any) -> str:
    """An ISO timestamp cell → ``YYYY-MM-DD``. An absent cell stays ''."""
    if not value:
        return ""
    return str(value)[:10]


def _find_term_records(node: Any) -> list[dict[str, Any]]:
    """The first list of term records in the page model, wherever it sits.

    Located by shape rather than by path, so a CMS reshuffle that moves
    ``pageModel.searchResults.items`` does not silently yield zero terms.
    """
    if (
        isinstance(node, list)
        and node
        and isinstance(node[0], dict)
        and "term" in node[0]
        and "definitionHtml" in node[0]
    ):
        return [r for r in node if isinstance(r, dict)]
    if isinstance(node, dict):
        for value in node.values():
            found = _find_term_records(value)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_term_records(value)
            if found:
                return found
    return []


def parse_glossary(payload: bytes) -> list[GlossaryTerm]:
    """Parse the acquired Glossary page into verbatim terms.

    Raises when the page carries no recognisable term records — an empty
    Glossary must fail loudly, because "no terms" and "the page changed shape"
    are indistinguishable downstream and one of them is a silent outage.
    """
    text = payload.decode("utf-8", errors="ignore")
    start = text.find(_MODEL_MARKER)
    if start < 0:
        raise ValueError(f"{GLOSSARY_URL}: no window._model payload in the acquired page")
    model, _end = json.JSONDecoder().raw_decode(text[start + len(_MODEL_MARKER) :])
    records = _find_term_records(model)
    if not records:
        raise ValueError(f"{GLOSSARY_URL}: page model carries no term records")
    terms: list[GlossaryTerm] = []
    for idx, record in enumerate(sorted(records, key=lambda r: str(r.get("term", "")).lower())):
        term = _plain(record.get("term"))
        definition = _plain(record.get("definitionHtml"))
        if not term or not definition:
            continue
        terms.append(
            GlossaryTerm(
                term=term,
                definition=definition,
                acronym=_plain(record.get("acronym") or record.get("acronymHtml")),
                status=_plain(record.get("status")),
                region=_plain(record.get("region")),
                docket=_plain(record.get("docketNumber")),
                footnote=_plain(record.get("footnoteHtml")),
                adopted_date=_iso(record.get("botAdoptionDate")),
                effective_date=_iso(record.get("effectiveDate")),
                inactive_date=_iso(record.get("inactiveDate")),
                ordinal=idx,
            )
        )
    return terms


# ── capture ─────────────────────────────────────────────────────────────────


def capture_glossary(terms: list[GlossaryTerm], path: Path) -> Any:
    """The Glossary as a :class:`~core.capture.CapturedDocument`.

    One unit per term, tiling one coordinate space, so a Glossary entry is the
    same kind of addressable thing as a requirement Part or an operator
    procedure section and lands in the same tables.
    """
    from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit

    units: list[CapturedUnit] = []
    buf: list[str] = []
    cursor = 0
    for term in terms:
        piece = term.text() + "\n"
        units.append(
            CapturedUnit(
                ordinal=term.ordinal,
                unit_kind="prose",
                heading_path=term.heading,
                title=term.term,
                page_start=1,
                page_end=1,
                char_start=cursor,
                char_end=cursor + len(piece),
                text=piece,
            )
        )
        buf.append(piece)
        cursor += len(piece)
    return CapturedDocument(
        path=path,
        page_count=1,
        full_text="".join(buf),
        units=units,
        extractor=EXTRACTOR,
        extractor_version=EXTRACTOR_VERSION,
        reader_strings=tuple(t.definition for t in terms),
    )


def register_glossary(repo: Any, payload: bytes, alias_path: str) -> dict[str, Any]:
    """Acquire → parse → register → capture, in one step. Idempotent on bytes."""
    from portal.modules.compliance.core.capture import store_capture
    from portal.modules.compliance.core.models import SourceDocument

    terms = parse_glossary(payload)
    repo.upsert_source_document(
        SourceDocument(
            logical_id=GLOSSARY_LOGICAL_ID,
            title="Glossary of Terms Used in NERC Reliability Standards",
            issuer="NERC",
            source_kind=GLOSSARY_SOURCE_KIND,
            jurisdiction="US",
        )
    )
    revision = repo.add_document_revision(
        GLOSSARY_LOGICAL_ID, alias_path, payload, binding_effect="regulatory"
    )
    report = store_capture(repo, revision.revision_id, capture_glossary(terms, Path(alias_path)))
    report["terms"] = len(terms)
    report["revision_id"] = revision.revision_id
    return report


# ── resolution ──────────────────────────────────────────────────────────────


@dataclass
class TermResolution:
    """One term's resolution attempt. ``resolved`` is False for a term the
    Glossary does not carry — the entry still exists and still names the term."""

    term: str
    resolved: bool = False
    definition: str = ""
    acronym: str = ""
    effective_date: str = ""
    inactive_date: str = ""
    status: str = ""
    docket: str = ""
    section_id: str = ""
    revision_id: str = ""
    as_of: str = ""
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _glossary_revision(repo: Any) -> str:
    row = repo._conn.execute(
        """SELECT revision_id FROM document_revisions
           WHERE logical_id = ? ORDER BY retrieved_at DESC LIMIT 1""",
        (GLOSSARY_LOGICAL_ID,),
    ).fetchone()
    return str(row[0]) if row else ""


def normalise_term(term: str) -> str:
    """The lookup key for a term.

    Lowercased, whitespace-collapsed, and a trailing plural ``s`` dropped. The
    inflection rule exists because NERC renames headwords between revisions —
    the enforceable definition is under *Protected Cyber Assets* and its
    2028 successor under *Protected Cyber Asset*, and a requirement written in
    the singular must still reach its own definition. Verified against the live
    Glossary: exactly one bucket collapses two spellings, and their effectivity
    windows are sequential, so no two distinct concepts are merged.
    """
    key = re.sub(r"\s+", " ", term.strip().lower())
    return key[:-1] if key.endswith("s") and not key.endswith("ss") else key


def glossary_index(repo: Any) -> dict[str, list[dict[str, Any]]]:
    """``normalised term -> every revision of it``, newest window last.

    A term is reachable by its headword (either inflection) and by its acronym
    — a requirement says ``EACMS``, not *Electronic Access Control or Monitoring
    Systems*. An acronym is only indexed when every entry carrying it belongs to
    the same term; an ambiguous acronym resolves to nothing rather than to a
    guess.
    """
    revision_id = _glossary_revision(repo)
    if not revision_id:
        return {}
    full_text = repo.get_document_text(revision_id) or ""
    rows = repo._conn.execute(
        """SELECT section_id, title, heading_path, char_start, char_end
           FROM source_sections WHERE revision_id = ? AND extractor = ?
           ORDER BY ordinal""",
        (revision_id, EXTRACTOR),
    ).fetchall()
    dates = _term_dates(repo)
    index: dict[str, list[dict[str, Any]]] = {}
    acronyms: dict[str, list[dict[str, Any]]] = {}
    for section_id, title, heading_path, char_start, char_end in rows:
        body = full_text[char_start:char_end]
        lines = body.split("\n")
        acronym = ""
        m = re.search(r"\(([^)]+)\)\s*$", str(heading_path))
        if m:
            acronym = m.group(1)
        meta = _meta_for(dates, str(title), lines[1] if len(lines) > 1 else "")
        entry = {
            "term": str(title),
            "acronym": acronym,
            "definition": lines[1] if len(lines) > 1 else "",
            "footnote": "\n".join(lines[2:]).strip(),
            "section_id": str(section_id),
            "revision_id": revision_id,
            "effective_date": str(meta.get("effective_date", "") or ""),
            "inactive_date": str(meta.get("inactive_date", "") or ""),
            "status": str(meta.get("status", "") or ""),
            "docket": str(meta.get("docket", "") or ""),
        }
        index.setdefault(normalise_term(str(title)), []).append(entry)
        if acronym:
            acronyms.setdefault(normalise_term(acronym), []).append(entry)
    for key, entries in acronyms.items():
        if key in index:
            continue
        if len({normalise_term(e["term"]) for e in entries}) == 1:
            index[key] = entries
    for entries in index.values():
        entries.sort(key=lambda e: (e["effective_date"] or "", e["inactive_date"] or "9999-12-31"))
    return index


def _meta_for(dates: dict[str, list[dict[str, Any]]], term: str, definition: str) -> dict[str, Any]:
    """The acquisition-time record for one captured term unit. Two revisions
    share a headword, so the definition text is what tells them apart."""
    candidates = dates.get(term.lower(), [])
    for record in candidates:
        if str(record.get("definition", "")) == definition:
            return record
    return candidates[0] if candidates else {}


def _select_revision(
    entries: list[dict[str, Any]], valid_at: str
) -> tuple[dict[str, Any] | None, str]:
    """The revision in force at ``valid_at``, or the honest reason there is none."""
    for entry in entries:
        effective = entry["effective_date"]
        inactive = entry["inactive_date"]
        if (not effective or effective <= valid_at) and (not inactive or valid_at < inactive):
            return entry, ""
    future = [e for e in entries if e["effective_date"] and e["effective_date"] > valid_at]
    if future:
        return future[0], (f"not effective at {valid_at}; effective {future[0]['effective_date']}")
    retired = entries[-1] if entries else None
    if retired is not None:
        return retired, (
            f"retired at {valid_at}; inactive from {retired['inactive_date']}"
            if retired["inactive_date"]
            else f"no revision in force at {valid_at}"
        )
    return None, "no revision recorded"


def resolve_terms(repo: Any, terms: list[str], *, valid_at: str = "") -> list[dict[str, Any]]:
    """Resolve defined terms against the registered Glossary.

    Every requested term comes back, resolved or not. ``valid_at`` defaults to
    today: the Glossary carries a term's future successor beside its
    enforceable revision, and serving the wrong one silently is exactly the
    failure the two clocks exist to prevent. A revision outside its window at
    ``valid_at`` is still returned — labelled ``resolved=False`` with the clock
    that excluded it — never silently served and never silently dropped.
    """
    index = glossary_index(repo)
    as_of = valid_at or _today()
    out: list[dict[str, Any]] = []
    for raw in terms:
        term = str(raw).strip()
        entries = index.get(normalise_term(term))
        if not entries:
            out.append(
                TermResolution(
                    term=term,
                    as_of=as_of,
                    detail=(
                        "not a NERC Glossary term"
                        if index
                        else "the NERC Glossary is not registered in this store"
                    ),
                ).as_dict()
            )
            continue
        entry, detail = _select_revision(entries, as_of)
        assert entry is not None  # entries is non-empty
        resolution = TermResolution(
            term=term,
            resolved=not detail,
            definition=entry["definition"],
            acronym=entry["acronym"],
            effective_date=entry["effective_date"],
            inactive_date=entry["inactive_date"],
            status=entry["status"],
            docket=entry["docket"],
            section_id=entry["section_id"],
            revision_id=entry["revision_id"],
            as_of=as_of,
            detail=detail,
        ).as_dict()
        resolution["matched_as"] = entry["term"]
        resolution["other_revisions"] = [
            {
                "term": e["term"],
                "effective_date": e["effective_date"],
                "inactive_date": e["inactive_date"],
                "status": e["status"],
                "section_id": e["section_id"],
            }
            for e in entries
            if e["section_id"] != entry["section_id"]
        ]
        out.append(resolution)
    return out


def _today() -> str:
    from portal.modules.compliance.core.temporal import now_iso

    return now_iso()[:10]


#: the parsed term metadata, kept beside the store because effectivity dates
#: are the Glossary's own facts and the captured text is verbatim prose.
_DATES_SIDECAR = "glossary_terms.json"


def write_term_dates(directory: Path, terms: list[GlossaryTerm]) -> Path:
    target = Path(directory) / _DATES_SIDECAR
    target.write_text(json.dumps([t.as_dict() for t in terms], indent=2), encoding="utf-8")
    return target


def _term_dates(repo: Any) -> dict[str, list[dict[str, Any]]]:
    """Per-term effectivity, read from the sidecar written at acquisition. A
    headword has one entry per revision, so the value is a list."""
    row = repo._conn.execute(
        """SELECT alias_path FROM document_revisions
           WHERE logical_id = ? ORDER BY retrieved_at DESC LIMIT 1""",
        (GLOSSARY_LOGICAL_ID,),
    ).fetchone()
    if not row:
        return {}
    sidecar = Path(str(row[0])).parent / _DATES_SIDECAR
    if not sidecar.is_file():
        return {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for record in data:
        if isinstance(record, dict):
            out.setdefault(str(record.get("term", "")).lower(), []).append(record)
    return out


# ── the deferral, resolved ──────────────────────────────────────────────────

#: capitalised multi-word terms a CIP requirement is likely to defer on. Used
#: only to CHOOSE what to look up, never to decide what a term means.
_CANDIDATE_RE = re.compile(r"\b(?:[A-Z][A-Za-z]*\s+){1,4}[A-Z][A-Za-z]*\b|\b[A-Z]{3,6}\b")


def terms_in(text: str, index: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Glossary terms that literally appear in ``text``.

    Membership is decided by the Glossary, not by a vocabulary in this file:
    a candidate span is kept only when it is a term the Glossary carries.
    """
    found: dict[str, None] = {}
    for match in _CANDIDATE_RE.finditer(text):
        for candidate in _shrink(match.group(0)):
            entries = index.get(normalise_term(candidate))
            if entries:
                found.setdefault(entries[0]["term"], None)
                break
    return list(found)


def _shrink(span: str) -> list[str]:
    """Longest-first prefixes and suffixes of a capitalised span, so
    ``Each BES Cyber System`` finds ``BES Cyber System``."""
    words = span.split()
    out: list[str] = []
    for size in range(len(words), 0, -1):
        for start in range(0, len(words) - size + 1):
            out.append(" ".join(words[start : start + size]))
    return out


def resolve_bundle_definitions(
    repo: Any, bundle_text: str, *, valid_at: str = ""
) -> dict[str, Any]:
    """The ``external_glossary`` disposition, actually resolved.

    A bundle that defers to the Glossary now carries the resolved terms its own
    text depends on, each with its own provenance and effectivity. Terms that do
    not resolve stay in the payload, explicitly unresolved.
    """
    index = glossary_index(repo)
    names = terms_in(bundle_text, index)
    resolved = resolve_terms(repo, names, valid_at=valid_at)
    return {
        "disposition": "external_glossary",
        "glossary_registered": bool(index),
        "glossary_revision_id": _glossary_revision(repo),
        "terms": resolved,
        "resolved": sum(1 for r in resolved if r["resolved"]),
        "unresolved": [r["term"] for r in resolved if not r["resolved"]],
    }


__all__ = [
    "EXTRACTOR",
    "GLOSSARY_ARTIFACT",
    "GLOSSARY_LOGICAL_ID",
    "GLOSSARY_SOURCE_KIND",
    "GLOSSARY_URL",
    "GlossaryTerm",
    "TermResolution",
    "capture_glossary",
    "glossary_index",
    "normalise_term",
    "parse_glossary",
    "register_glossary",
    "resolve_bundle_definitions",
    "resolve_terms",
    "terms_in",
    "write_term_dates",
]
