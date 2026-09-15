"""Complete regulatory bundle extraction (foundation task P3).

One module owns the *whole* semantic content of one official standard
revision, not just its requirement tables: requirement Parts with lead-ins and
applicable-system columns, the Measures column and the M<n> measure
statements, the Guidelines and Technical Basis section, and the definitions
disposition. Every span is an exact, hash-anchored slice of the normalized
revision text, so ``verify`` can prove — from the immutable revision bytes —
that a component was not truncated, reordered, or mixed across revisions.

Roles follow ``result_contract.SOURCE_ROLES``: a Measure is evidence context
(``MEASURE``), Guidelines and Technical Basis is interpretive context
(``TECHNICAL_BASIS``) — neither is ever concatenated into the mandatory duty
text, which keeps its ``REGULATORY_REQUIREMENT`` role.

Readiness is component-shaped (lesson L13): a table-shaped Part needs its
lead-in, verbatim text, applicable systems, Measures, requirement Technical
Basis, a recorded definitions disposition, and hash-verified spans. A missing
or truncated component is a named ``U14_INCOMPLETE_SOURCE_BUNDLE`` failure,
never a silent empty string.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from portal.modules.compliance.core.cip_extract import (
    RequirementPart,
    _leadins,
    _norm,
    extract_standard,
)

U14_INCOMPLETE_SOURCE_BUNDLE = "U14_INCOMPLETE_SOURCE_BUNDLE"

#: section heading whose body carries the per-requirement Technical Basis.
_TECH_BASIS_HEADING = "Guidelines and Technical Basis"
#: One marker regex covering the header variants across revisions:
#: "Requirement R2:" and "Rationale for Requirement R2:" (CIP-007-6),
#: "Rationale for R2:" (CIP-002). A single scan cannot re-match the inner
#: text of a rationale header, and the trailing Interpretations listing's
#: bare "R2" mentions never carry the colon+space header shape.
_GTB_MARKER_RE = re.compile(r"(Rationale\s+for\s+)?(?:Requirement\s+)?R(\d+):\s")
_GTB_PART_RE = re.compile(r"(?<![A-Za-z0-9.])(\d+(?:\.\d+)+)\.\s")
_MEASURE_LEADIN_RE = re.compile(
    r"(?<![A-Za-z0-9])M(\d+)\.\s+(.+?)(?=(?<![A-Za-z0-9])M\d+\.|\Z)",
    re.DOTALL,
)
#: the closing sections that follow the Technical Basis in a CIP standard
_GTB_END_RE = re.compile(r"(?<![A-Za-z])(?:[A-E]\.\s+)?(?:Regional Variances|Interpretations)\b")
#: an inline definitions section (some standards carry one; CIP-007 does not).
_DEFINITIONS_HEADING_RE = re.compile(r"(?m)^\s*\d*\.?\s*Definitions\s*$")
_TERM_RE = re.compile(r"(?m)^([A-Z][A-Za-z0-9][A-Za-z0-9 /()&,'-]{1,60}):\s+")


@dataclass
class RegulatorySpan:
    """An exact, hash-anchored slice of one revision's normalized text.

    ``doc_char_start``/``doc_char_end`` are half-open offsets into the
    normalized full-document text (per-page ``cip_extract._norm`` output
    joined with newlines, page numbers in order). ``sha256`` is the hash of
    the slice text. ``verify`` recomputes both from revision bytes, so a
    stale or foreign span cannot pass.
    """

    text: str
    sha256: str
    doc_char_start: int
    doc_char_end: int
    page_start: int
    page_end: int
    role: str
    locator: str

    def to_record(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "sha256": self.sha256,
            "doc_char_start": self.doc_char_start,
            "doc_char_end": self.doc_char_end,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "role": self.role,
            "locator": self.locator,
        }

    def verify(self, normalized_pages: dict[int, str]) -> bool:
        doc = "\n".join(normalized_pages[p] for p in sorted(normalized_pages))
        if self.doc_char_start < 0 or self.doc_char_end > len(doc):
            return False
        body = doc[self.doc_char_start : self.doc_char_end]
        return body == self.text and hashlib.sha256(body.encode()).hexdigest() == self.sha256


@dataclass
class RevisionBundle:
    """The complete extracted semantics of one official standard revision."""

    standard: str  # "CIP-007"
    version: str  # "6" or "7.1"
    source_sha256: str
    normalized_pages: dict[int, str] = field(default_factory=dict)
    leadins: dict[str, tuple[str, str, str]] = field(default_factory=dict)
    parts: list[RequirementPart] = field(default_factory=list)
    #: requirement-level Technical Basis spans, keyed "R2" -> spans
    technical_basis: dict[str, list[RegulatorySpan]] = field(default_factory=dict)
    #: per-Part Technical Basis sub-spans, keyed "R2 Part 2.1" -> spans
    technical_basis_parts: dict[str, list[RegulatorySpan]] = field(default_factory=dict)
    #: NERC rationale boxes carried in the same section, keyed "R2" -> spans
    technical_basis_rationale: dict[str, list[RegulatorySpan]] = field(default_factory=dict)
    #: "present" | "absent" — a recorded revision shape fact. CIP-007-7.1's
    #: 2024 edition carries no Guidelines and Technical Basis section; its
    #: interpretive context lives in the separately acquired technical
    #: rationale document. Absence is recorded, never silently tolerated.
    technical_basis_section: str = ""
    #: requirement-level measure statements M<n>, keyed "R2" -> text
    measures_leadins: dict[str, str] = field(default_factory=dict)
    #: verbatim inline definitions, when the standard carries its own section
    definitions: list[dict[str, Any]] = field(default_factory=list)
    #: "inline" | "external_glossary" — an explicit disposition either way
    definitions_disposition: str = ""

    @property
    def revision_id(self) -> str:
        return self.source_sha256

    def part_id(self, part: RequirementPart) -> str:
        suffix = f" Part {part.part}" if part.part else ""
        return f"{part.standard}-{part.version} {part.requirement}{suffix}"

    def parts_for_requirement(self, requirement: str) -> list[RequirementPart]:
        return [p for p in self.parts if p.requirement == requirement and p.part]

    def technical_basis_for(self, requirement: str) -> list[RegulatorySpan]:
        return self.technical_basis.get(requirement, [])


def normalized_pages_from_bytes(source: bytes) -> dict[int, str]:
    import pymupdf

    with pymupdf.open(stream=source, filetype="pdf") as document:  # type: ignore[no-untyped-call]
        return {i + 1: _norm(page.get_text()) for i, page in enumerate(document)}


def sha256_of(source: bytes) -> str:
    return hashlib.sha256(source).hexdigest()


# ── section extraction ──────────────────────────────────────────────────────


def _doc_text(pages: dict[int, str]) -> str:
    return "\n".join(pages[p] for p in sorted(pages))


def _page_of(pages: dict[int, str], doc_offset: int) -> int:
    acc = 0
    for p in sorted(pages):
        acc += len(pages[p]) + 1
        if doc_offset < acc:
            return p
    return max(pages) if pages else 0


def _tech_basis_markers(doc: str) -> list[tuple[int, int, str]]:
    """Every Guidelines / Rationale requirement marker inside the Technical
    Basis section: [(abs_offset, num, kind)] with kind in {guidelines,
    rationale}.

    A marker only counts when a real section heading precedes it — CIP-013-2
    carries no Guidelines and Technical Basis section at all, and its duty
    prose contains a "Requirement R2:" phrase that must not fabricate a
    span. The section ends where the closing Regional Variances /
    Interpretations blocks begin, when they follow."""
    headings = [m.start() for m in re.finditer(re.escape(_TECH_BASIS_HEADING), doc)]
    raw = [
        (m.start(), int(m.group(2)), "rationale" if m.group(1) else "guidelines")
        for m in _GTB_MARKER_RE.finditer(doc)
    ]
    if not headings or not raw:
        return []
    first = raw[0][0]
    preceding = [h for h in headings if h < first]
    if not preceding:
        return []
    section_start = max(preceding)
    in_section = [t for t in raw if t[0] >= section_start]
    end_m = _GTB_END_RE.search(doc[section_start:])
    if end_m:
        limit = section_start + end_m.start()
        in_section = [t for t in in_section if t[0] < limit]
    return in_section


def _extract_technical_basis(
    bundle: RevisionBundle,
    doc: str,
    span_role: str = "TECHNICAL_BASIS",
) -> None:
    markers = _tech_basis_markers(doc)
    if not markers:
        bundle.technical_basis_section = "absent"
        return
    bundle.technical_basis_section = "present"
    for i, (pos, num, kind) in enumerate(markers):
        end = markers[i + 1][0] if i + 1 < len(markers) else _region_end(doc, pos)
        body = doc[pos:end].rstrip()
        if not body.strip():
            continue
        req = f"R{num}"
        span = RegulatorySpan(
            text=body,
            sha256=hashlib.sha256(body.encode()).hexdigest(),
            doc_char_start=pos,
            doc_char_end=pos + len(body),
            page_start=_page_of(bundle.normalized_pages, pos),
            page_end=_page_of(bundle.normalized_pages, pos + len(body)),
            role=span_role,
            locator=f"{_TECH_BASIS_HEADING} {'Rationale ' if kind == 'rationale' else ''}{req}",
        )
        if kind == "rationale":
            bundle.technical_basis_rationale.setdefault(req, []).append(span)
        else:
            bundle.technical_basis.setdefault(req, []).append(span)
            # per-Part sub-spans inside the Guidelines text only
            parts = [(m.start(), m.group(1)) for m in _GTB_PART_RE.finditer(body)]
            for j, (ppos, pid) in enumerate(parts):
                pend = parts[j + 1][0] if j + 1 < len(parts) else len(body)
                pbody = body[ppos:pend].rstrip()
                if len(pbody) < 40:  # a cross-reference, not a sub-section
                    continue
                pstart_abs = pos + ppos
                bundle.technical_basis_parts.setdefault(f"{req} Part {pid}", []).append(
                    RegulatorySpan(
                        text=pbody,
                        sha256=hashlib.sha256(pbody.encode()).hexdigest(),
                        doc_char_start=pstart_abs,
                        doc_char_end=pstart_abs + len(pbody),
                        page_start=_page_of(bundle.normalized_pages, pstart_abs),
                        page_end=_page_of(bundle.normalized_pages, pstart_abs + len(pbody)),
                        role=span_role,
                        locator=f"{_TECH_BASIS_HEADING} {req} {pid}",
                    )
                )


def _region_end(doc: str, from_pos: int) -> int:
    end_m = _GTB_END_RE.search(doc[from_pos:])
    return from_pos + end_m.start() if end_m else len(doc)


def _extract_measure_leadins(bundle: RevisionBundle, doc: str) -> None:
    for m in _MEASURE_LEADIN_RE.finditer(doc):
        req = f"R{m.group(1)}"
        bundle.measures_leadins.setdefault(req, _norm(m.group(2)))


def _extract_definitions(bundle: RevisionBundle, doc: str) -> None:
    """Verbatim inline definitions, or the explicit external-glossary
    disposition. A standard without its own definitions section — CIP-007
    defers to the NERC Glossary of Terms — gets the explicit result, never a
    placeholder body."""
    m = _DEFINITIONS_HEADING_RE.search(doc)
    entries: list[dict[str, Any]] = []
    if m:
        region_end = len(doc)
        next_heading = re.search(
            r"(?m)^\s*\d*\.?\s*(Introduction|Requirements and Measures)\s*$", doc[m.end() :]
        )
        if next_heading:
            region_end = m.end() + next_heading.start()
        region = doc[m.end() : region_end]
        terms = [(t.start(), t.end(), t.group(1).strip()) for t in _TERM_RE.finditer(region)]
        for i, (_s, e, term) in enumerate(terms):
            body_end = terms[i + 1][0] if i + 1 < len(terms) else len(region)
            body = _norm(region[e:body_end])
            if body:
                entries.append(
                    {
                        "term": term,
                        "body": body,
                        "role": "DEFINITION",
                        "doc_char_start": m.end() + e,
                        "doc_char_end": m.end() + body_end,
                    }
                )
    if entries:
        bundle.definitions = entries
        bundle.definitions_disposition = "inline"
    else:
        bundle.definitions = []
        bundle.definitions_disposition = "external_glossary"


def extract_revision_bundle(
    source: bytes | Path,
    *,
    expected_sha256: str = "",
    source_name: str = "",
) -> RevisionBundle:
    """Extract the complete bundle for one official revision.

    ``expected_sha256`` is the mixed-fingerprint guard: when the caller pins
    a revision identity (the store's content-hash revision id, the acquisition
    manifest), bytes that do not match fail loudly instead of silently
    producing a bundle stitched from the wrong revision. ``source_name`` is
    the canonical file name recorded on extracted parts (defaults to the
    standards' own naming).
    """
    if isinstance(source, (Path, str)):
        source_name = source_name or Path(source).name
        source = Path(source).read_bytes()
    digest = sha256_of(source)
    if expected_sha256 and digest != expected_sha256:
        raise ValueError(
            f"source revision mismatch: expected {expected_sha256[:12]}…, got {digest[:12]}…"
        )
    import pymupdf

    with pymupdf.open(stream=source, filetype="pdf") as document:  # type: ignore[no-untyped-call]
        standard, version = _standard_and_version_from_doc(document, digest, source_name)
    pages = normalized_pages_from_bytes(source)
    doc = _doc_text(pages)

    parts = _extract_parts(source, source_name)
    default_name = source_name or f"{standard.lower()}-{version}.pdf"
    for part in parts:
        part.source_pdf = default_name
    bundle = RevisionBundle(
        standard=standard,
        version=version,
        source_sha256=digest,
        normalized_pages=pages,
        leadins=_leadins(doc),
        parts=parts,
    )
    _extract_technical_basis(bundle, doc)
    _extract_measure_leadins(bundle, doc)
    _extract_definitions(bundle, doc)
    return bundle


def _standard_and_version_from_doc(
    document: Any, digest: str, source_name: str = ""
) -> tuple[str, str]:
    head = document[0].get_text()[:400] + document[min(2, len(document) - 1)].get_text()[:400]
    m = re.search(r"(CIP-\d{3})-([\w.]+)\b", head.replace("\n", " "))
    if m:
        return m.group(1), m.group(2)
    fm = re.match(r"(cip-\d{3})-([\w.]+?)(?:\.pdf)?$", source_name, re.I)
    if fm:
        return fm.group(1).upper(), fm.group(2)
    raise ValueError(f"cannot determine standard id (sha256 {digest[:12]}…)")


# ── per-part bundle + readiness ─────────────────────────────────────────────


def part_bundle(bundle: RevisionBundle, requirement: str, part: str) -> dict[str, Any]:
    """Every component the governing side offers for one duty, role-labelled."""
    pid = f"{bundle.standard}-{bundle.version} {requirement}" + (f" Part {part}" if part else "")
    node = next(
        (p for p in bundle.parts if bundle.part_id(p) == pid),
        None,
    )
    lead = bundle.leadins.get(requirement, ("", "", ""))
    measures: list[dict[str, Any]] = []
    if node is not None and node.measure_text:
        measures.append(
            {
                "ref": pid,
                "text": node.measure_text,
                "role": "MEASURE",
                "locator": f"Table {requirement} Measures column",
            }
        )
    if bundle.measures_leadins.get(requirement):
        measures.append(
            {
                "ref": requirement,
                "text": bundle.measures_leadins[requirement],
                "role": "MEASURE",
                "locator": f"M{requirement[1:]} lead-in",
            }
        )
    tb = bundle.technical_basis_for(requirement)
    tb_key = f"{requirement} Part {part}" if part else ""
    tb_parts = bundle.technical_basis_parts.get(tb_key, []) if part else []
    rationale = bundle.technical_basis_rationale.get(requirement, [])
    is_attachment = requirement.startswith("Attachment")
    if is_attachment:
        shape = "attachment"
    elif node is not None and node.table_name:
        shape = "table"
    else:
        shape = "prose"
    return {
        "ref": pid,
        "shape": shape,
        "standard": bundle.standard,
        "version": bundle.version,
        "revision_id": bundle.revision_id,
        "part_text": node.verbatim_text if node is not None else "",
        "lead_in": lead[0],
        "vrf": lead[1],
        "time_horizon": lead[2],
        "applicable_systems": node.applicable_systems if node is not None else "",
        "measures": measures,
        "technical_basis": [s.to_record() for s in tb],
        "technical_basis_parts": [s.to_record() for s in tb_parts],
        "technical_basis_rationale": [s.to_record() for s in rationale],
        "technical_basis_section": bundle.technical_basis_section,
        "definitions": list(bundle.definitions),
        "definitions_disposition": bundle.definitions_disposition,
    }


#: components required of a table-shaped duty (a `Table Rn` row)
_TABLE_COMPONENTS: tuple[str, ...] = (
    "lead_in",
    "part_text",
    "applicable_systems",
    "measures",
    "technical_basis",
    "definitions_disposition",
)
#: components required of a prose-shaped duty (a numbered list item)
_PROSE_COMPONENTS: tuple[str, ...] = (
    "lead_in",
    "part_text",
    "measures",
    "technical_basis",
    "definitions_disposition",
)
#: attachment criteria tables (CIP-002 impact ratings, CIP-003 plan sections)
#: carry no Measures column and no per-requirement Technical Basis — the
#: source shape is the criterion text itself. Under-required components are a
#: recorded shape fact, never a silent waiver.
_ATTACHMENT_COMPONENTS: tuple[str, ...] = ("part_text", "definitions_disposition")


def required_components(shape: str) -> tuple[str, ...]:
    if shape == "table":
        return _TABLE_COMPONENTS
    if shape == "attachment":
        return _ATTACHMENT_COMPONENTS
    return _PROSE_COMPONENTS


def _required_component_failures(pb: dict[str, Any]) -> list[dict[str, str]]:
    """Component checks for the bundle's source shape (lesson L13): a
    component absent where the shape requires one is a named failure."""
    failures: list[dict[str, str]] = []
    ref = pb.get("ref")
    required = required_components(pb.get("shape", "prose"))

    if not pb.get("revision_id"):
        failures.append(_u14("revision_id", "bundle is not pinned to a source revision"))
    if not pb.get("part_text"):
        failures.append(_u14("part_text", f"no verbatim duty text for {ref}"))
    if "lead_in" in required and not pb.get("lead_in"):
        failures.append(_u14("lead_in", f"no verified requirement lead-in for {ref}"))
    if "applicable_systems" in required and not pb.get("applicable_systems"):
        failures.append(_u14("applicable_systems", f"empty Applicable Systems column for {ref}"))
    if "measures" in required:
        failures.extend(_measure_failures(pb))
    if "technical_basis" in required:
        failures.extend(_technical_basis_failures(pb))
    if "definitions_disposition" in required and pb.get("definitions_disposition", "") not in (
        "inline",
        "external_glossary",
    ):
        failures.append(
            _u14(
                "definitions_disposition",
                f"definitions disposition unresolved for {ref}: "
                f"{pb.get('definitions_disposition', '')!r}",
            )
        )
    return failures


def _u14(component: str, detail: str) -> dict[str, str]:
    return {"component": component, "detail": detail, "code": U14_INCOMPLETE_SOURCE_BUNDLE}


def _measure_failures(pb: dict[str, Any]) -> list[dict[str, str]]:
    if not pb.get("measures"):
        return [_u14("measures", f"no Measures column or M-lead-in for {pb.get('ref')}")]
    truncated = [m for m in pb["measures"] if len(str(m.get("text", "")).strip()) < 20]
    if truncated:
        return [_u14("measures", f"Measures component truncated or empty for {pb.get('ref')}")]
    return []


def _technical_basis_failures(pb: dict[str, Any]) -> list[dict[str, str]]:
    present = bool(
        pb.get("technical_basis")
        or pb.get("technical_basis_parts")
        or pb.get("technical_basis_rationale")
    )
    state = pb.get("technical_basis_section", "")
    if state == "present" and not present:
        return [
            _u14(
                "technical_basis",
                f"Technical Basis section is present but {pb.get('ref')} has no span "
                "(truncated extraction)",
            )
        ]
    if state not in ("present", "absent"):
        return [
            _u14(
                "technical_basis",
                f"Technical Basis section fact not recorded for {pb.get('ref')}: {state!r}",
            )
        ]
    return []


def readiness_failures(
    pb: dict[str, Any],
    *,
    atoms: list[Any] | None = None,
    expression: dict[str, Any] | None = None,
    text: str = "",
) -> list[dict[str, str]]:
    """Every ``U14`` failure for one duty's bundle; empty means ready.

    Components are required by source shape (lesson L13). ``atoms``/
    ``expression``/``text`` add the decomposition checks when the caller has
    materialized them — the logical expression must represent the text (no
    one-child placeholder, no collapsed alternatives, verbatim clauses).
    """
    failures = _required_component_failures(pb)
    for span in pb.get("technical_basis", []) + pb.get("technical_basis_parts", []):
        if span.get("doc_char_end", 0) <= span.get("doc_char_start", 0):
            failures.append(
                _u14("span_offsets", f"empty or inverted span offsets in {span.get('locator')}")
            )

    if atoms is not None and expression is not None:
        from portal.modules.compliance.core.obligations import decomposition_defects

        for defect in decomposition_defects(atoms, expression, text):
            failures.append(_u14("decomposition", defect))

    return failures


def verify_bundle_spans(
    bundle: RevisionBundle,
    *,
    source: bytes | None = None,
) -> list[str]:
    """Re-locate every extracted span against the revision bytes. Returns the
    list of locators that fail; empty means every span hash-verifies.

    Supplying ``source`` bytes that are not the pinned revision is the
    mixed-fingerprint case — it raises instead of silently verifying against
    cached pages.
    """
    if source is not None and sha256_of(source) != bundle.source_sha256:
        raise ValueError(
            "span verification bytes are not the pinned revision: "
            f"{sha256_of(source)[:12]}… != {bundle.source_sha256[:12]}…"
        )
    pages = normalized_pages_from_bytes(source) if source is not None else bundle.normalized_pages
    failed: list[str] = []
    all_spans: list[RegulatorySpan] = [
        *[s for spans in bundle.technical_basis.values() for s in spans],
        *[s for spans in bundle.technical_basis_parts.values() for s in spans],
        *[s for spans in bundle.technical_basis_rationale.values() for s in spans],
    ]
    for span in all_spans:
        if not span.verify(pages):
            failed.append(span.locator)
    return failed


def require_ready(failures: list[dict[str, str]], *, ref: str = "") -> None:
    """Raise the controlled U14 error when a bundle is not ready."""
    if failures:
        raise SourceBundleIncompleteError(ref=ref, failures=failures)


class SourceBundleIncompleteError(ValueError):
    """A required bundle component is missing/truncated/foreign (U14).

    This is an engineering stop, not an SME question: the payload names the
    requirement, each failed component, and what would settle it.
    """

    def __init__(self, ref: str, failures: list[dict[str, str]]) -> None:
        self.ref = ref
        self.failures = failures
        detail = "; ".join(f"{f['component']}: {f['detail']}" for f in failures)
        super().__init__(
            f"{U14_INCOMPLETE_SOURCE_BUNDLE} for {ref or 'unpinned bundle'} — {detail}"
        )

    @property
    def missing_fact(self) -> dict[str, Any]:
        return {
            "requirement_id": self.ref,
            "components": self.failures,
        }


def _extract_parts(source: bytes, source_name: str) -> list[RequirementPart]:
    """extract_standard works on a path and derives identities from the file
    name — hand it a temp dir containing the revision under its real name."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / (source_name or "standard.pdf")
        path.write_bytes(source)
        parts, _meta = extract_standard(path)
    return parts
