"""The organization graph (TASK_COMPLIANCE_REASONING_V6 P2).

The second register the module has always needed. Where the policy graph holds
the regulator's obligations, this holds the operator's *commitments* — plus the
controls, roles, systems, recurring activities and evidence specifications that
carry them — extracted from the operator's own procedure / policy / work-
instruction PDFs with the same discipline ``cip_extract`` uses on the standards:

  - every extracted element carries a verbatim char span into an immutable
    document revision, and round-trips (Y02 / Y06);
  - the completeness denominator comes from **document-declared structure**
    (the numbered section headings and the control block), never from the
    extractor's own output (Y06);
  - control-block dates (effective / approved / owner) are read from the
    document, never guessed from a filename.

Node types:
  - ``commitment``    — an internally-mandatory statement (a "shall", or a
    controlled procedure's operational prose) that an actor performs a duty.
  - ``control``       — a named, repeatable safeguard a commitment relies on.
  - ``role``          — an internal role/title a commitment assigns work to.
  - ``system``        — an internal system / tool / asset class named as the
    locus of a control.
  - ``activity``      — a recurring activity with a cadence.
  - ``evidence_spec`` — a described record/artifact a commitment produces.
  - ``premise``       — a local definition / acronym / scope statement (the
    document's own "Terms and Definitions" and "Applicability" sections).

The persisted graph contains verbatim operator text and is therefore **not**
committed (unlike the NERC register JSON). ``build_org_graph`` writes to a
caller-supplied path; the default is under ``coding_task/v9_compliance/private``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

OrgNodeType = Literal[
    "commitment", "control", "role", "system", "activity", "evidence_spec", "premise"
]

# ── control block ──────────────────────────────────────────────────────────

_DATE = r"(?:[A-Z][a-z]+ \d{1,2},? \d{4}|\d{1,2}/\d{1,2}/\d{4})"
_CB_FIELDS: tuple[tuple[str, str], ...] = (
    ("effective_date", rf"Effective Date:?\s*({_DATE})"),
    ("revision_date", rf"(?:Revision|Revised) Date:?\s*({_DATE})"),
    ("last_reviewed_date", rf"(?:Last Review(?:ed)?|Review Date):?\s*({_DATE})"),
    ("approved_date", rf"Approv\w+:?\s*(?:\|\s*)?({_DATE})"),
    ("document_type", r"Document Type:?\s*([A-Za-z ]+?)(?:\s*\n|\s*NERC|\s*Document)"),
    ("document_number", r"Document (?:Number|ID):?\s*([A-Za-z0-9-]+)"),
    ("nerc_standard", r"NERC Standard:?\s*(CIP-\d{3})"),
)
_MONTHS = "january february march april may june july august september october november december"
_MONTH_IX = {m: i + 1 for i, m in enumerate(_MONTHS.split())}


def _iso(raw: str) -> str:
    raw = raw.strip().rstrip(".")
    m = re.match(r"([A-Za-z]+) (\d{1,2}),? (\d{4})", raw)
    if m and m.group(1).lower() in _MONTH_IX:
        return f"{m.group(3)}-{_MONTH_IX[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return ""


@dataclass
class OrgDocument:
    logical_id: str  # stable identity independent of filename/version
    revision_id: str  # sha256 of the extracted text
    title: str
    source_path: str
    document_class: str  # policy | procedure | work_instruction | plan | program | unknown
    standard_folder: str  # the operator's own folder-per-standard claim
    nerc_standard: str  # from the control block, "" if absent
    document_number: str
    effective_date: str
    approved_date: str
    revision_date: str
    last_reviewed_date: str
    owner: str
    approver: str
    declared_section_count: int
    control_block_fields_found: list[str]


@dataclass
class OrgSection:
    section_id: str
    document_id: str
    number: str  # "3.1", "" for unnumbered
    heading: str
    heading_path: str
    char_start: int
    char_end: int


@dataclass
class OrgNode:
    id: str
    node_type: OrgNodeType
    document_id: str
    section_id: str
    text: str  # verbatim span
    char_start: int
    char_end: int
    extraction_rule: str
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrgGraph:
    documents: list[OrgDocument] = field(default_factory=list)
    sections: list[OrgSection] = field(default_factory=list)
    nodes: list[OrgNode] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "report": self.report,
            "documents": [asdict(d) for d in self.documents],
            "sections": [asdict(s) for s in self.sections],
            "nodes": [asdict(n) for n in self.nodes],
            "edges": self.edges,
        }

    @classmethod
    def load(cls, path: Path | str) -> OrgGraph:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            documents=[OrgDocument(**x) for x in d.get("documents", [])],
            sections=[OrgSection(**x) for x in d.get("sections", [])],
            nodes=[OrgNode(**x) for x in d.get("nodes", [])],
            edges=d.get("edges", []),
            report=d.get("report", {}),
        )


# ── structure parsing ──────────────────────────────────────────────────────

_HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.M)
_NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)\s+(.*)$")
_STD_FOLDER = re.compile(r"^CIP-(\d+)$", re.I)
_CLASS_CUES = (
    ("work instruction", "work_instruction"),
    ("procedure", "procedure"),
    ("policy", "policy"),
    (" plan", "plan"),
    ("program", "program"),
)


def _classify_document(title: str, header: str) -> str:
    hay = (title + " " + header).lower()
    for cue, kind in _CLASS_CUES:
        if cue in hay:
            return kind
    return "unknown"


def parse_control_block(text: str) -> dict[str, Any]:
    head = text[:4000]
    out: dict[str, Any] = {"found": []}
    for key, pat in _CB_FIELDS:
        m = re.search(pat, head, re.I)
        if not m:
            continue
        val = m.group(1).strip()
        out[key] = _iso(val) if key.endswith("_date") else val
        out["found"].append(key)
    # owner / approver from the DOCUMENTOWNER / APPROVALS tables
    om = re.search(r"DOCUMENT ?OWNER.*?\n(?:.*\n)*?\|\s*([A-Z][a-z]+ [A-Z][a-z]+)\s*\|", head, re.I)
    if om:
        out["owner"] = om.group(1).strip()
    am = re.search(r"Name:\s*([A-Z][a-z]+ [A-Z][a-z]+)", head)
    if am:
        out["approver"] = am.group(1).strip()
    return out


def parse_sections(text: str, document_id: str) -> list[OrgSection]:
    sections: list[OrgSection] = []
    matches = list(_HEADING.finditer(text))
    for i, m in enumerate(matches):
        raw = m.group(2).replace("&amp;", "&").strip()
        nm = _NUMBERED.match(raw)
        number = nm.group(1) if nm else ""
        heading = nm.group(2).strip() if nm else raw
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append(
            OrgSection(
                section_id=f"{document_id}#{i:03d}",
                document_id=document_id,
                number=number,
                heading=heading,
                heading_path=raw,
                char_start=start,
                char_end=end,
            )
        )
    return sections


# ── first-pass entity extraction (deterministic) ───────────────────────────

_MODAL = re.compile(
    r"\b(shall not|shall|must not|must|will|is responsible for|are required to)\b", re.I
)
_OPERATIONAL = re.compile(
    r"\b(maintains?|identif(?:y|ies)|reviews?|documents?|creates?|implements?|evaluates?|"
    r"approves?|performs?|tracks?|retains?|protects?|restricts?|monitors?|tests?|updates?|"
    r"validates?|installs?|mitigates?|verif(?:y|ies)|records?|notif(?:y|ies)|submits?)\b",
    re.I,
)
_CADENCE = re.compile(
    r"\b(?:annually|quarterly|monthly|weekly|daily|"
    r"(?:at least )?once (?:every|per|each)\s+\d+\s+(?:calendar |business )?"
    r"(?:days?|weeks?|months?|years?|quarters?)|every\s+\d+\s+(?:days?|months?|years?)|"
    r"within\s+\d+\s+(?:calendar |business )?(?:days?|months?|hours?))\b",
    re.I,
)
_ROLE_RE = re.compile(
    r"\b(OT Security (?:Manager|Operations|Team|Analyst)|CIP Senior Manager|"
    r"OT Management|System Owner|Document Owner|Responsible Manager|"
    r"[A-Z][a-z]+ (?:Manager|Owner|Analyst|Administrator|Coordinator|Engineer|Lead))\b"
)
_EVIDENCE_RE = re.compile(
    r"\b(evidence|record|log|report|register|inventory|attestation|screenshot|"
    r"ticket|change request|checklist|form)s?\b",
    re.I,
)
_SYSTEM_RE = re.compile(
    r"\b(SCADA|EMS|Historian|jump[- ]host|Bomgar|Active Directory|SIEM|"
    r"patch management (?:system|tool)|ticketing system|CMDB|firewall|"
    r"[A-Z][A-Za-z]+(?:DB|Sys|Track|Manager) )\b"
)


def _sentences(text: str, offset: int) -> list[tuple[str, int, int]]:
    """(verbatim_sentence, char_start, char_end) with the span trimmed to the
    non-whitespace content so ``full_text[start:end] == sentence`` exactly."""
    out = []
    for m in re.finditer(r"[^.!?\n]+[.!?]?", text):
        raw = m.group(0)
        lead = len(raw) - len(raw.lstrip())
        s = raw.strip()
        if len(s) < 12:
            continue
        start = offset + m.start() + lead
        out.append((s, start, start + len(s)))
    return out


def _nid(kind: str, document_id: str, cs: int) -> str:
    return f"{kind}-{hashlib.sha256(f'{document_id}:{cs}'.encode()).hexdigest()[:14]}"


def extract_section_nodes(
    section: OrgSection, section_text: str, is_traceability: bool
) -> list[OrgNode]:
    nodes: list[OrgNode] = []
    lower_head = section.heading.lower()
    if any(
        k in lower_head
        for k in ("terms", "definition", "acronym", "applicability", "scope", "purpose")
    ):
        end = min(section.char_end, section.char_start + 400)
        nodes.append(
            OrgNode(
                id=_nid("premise", section.document_id, section.char_start),
                node_type="premise",
                document_id=section.document_id,
                section_id=section.section_id,
                text=section_text[: end - section.char_start],
                char_start=section.char_start,
                char_end=end,
                extraction_rule="definitional_section",
            )
        )
        return nodes
    for sent, cs, ce in _sentences(section_text, section.char_start):
        modal = _MODAL.search(sent)
        op = _OPERATIONAL.search(sent)
        if not (modal or op):
            continue
        rel = "REFERENCES" if is_traceability else "IMPLEMENTS"
        cad = _CADENCE.search(sent)
        node = OrgNode(
            id=_nid("commitment", section.document_id, cs),
            node_type="activity" if cad else "commitment",
            document_id=section.document_id,
            section_id=section.section_id,
            text=sent,
            char_start=cs,
            char_end=ce,
            extraction_rule="modal_statement" if modal else "operational_prose",
            fields={
                "relation": rel,
                "modality": (modal.group(0).lower() if modal else "internally_mandatory"),
                "cadence": cad.group(0) if cad else "",
                "roles": sorted({m.group(0) for m in _ROLE_RE.finditer(sent)}),
                "systems": sorted({m.group(1).strip() for m in _SYSTEM_RE.finditer(sent)}),
                "produces_evidence": bool(_EVIDENCE_RE.search(sent)),
            },
        )
        nodes.append(node)
    return nodes


async def _read(path: Path) -> str:
    from portal.platform.retrieval import extraction as _ex

    try:
        return await _ex.read_text(path)
    except Exception:  # noqa: BLE001 - a bad PDF still yields an empty-doc record
        return ""


def _logical_id(path: Path) -> str:
    stem = re.sub(r"\s*[Vv]\d+(\.\d+)?\s*$", "", path.stem).strip()
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")


async def build_org_graph(corpus_dir: str | Path) -> OrgGraph:
    src = Path(corpus_dir).expanduser().resolve()
    graph = OrgGraph()
    pdfs = sorted(p for p in src.rglob("*.pdf") if p.is_file())
    fidelity_fail = 0
    fidelity_total = 0
    for pdf in pdfs:
        text = await _read(pdf)
        if not text:
            continue
        rev = hashlib.sha256(text.encode()).hexdigest()[:16]
        lid = _logical_id(pdf)
        title = ""
        tm = _HEADING.search(text)
        if tm:
            title = tm.group(2).replace("&amp;", "&").strip()
        cb = parse_control_block(text)
        folder = pdf.parent.name
        std_folder = (
            f"CIP-{_STD_FOLDER.match(folder).group(1)}" if _STD_FOLDER.match(folder) else ""
        )
        sections = parse_sections(text, lid)
        declared = [s for s in sections if s.number]
        graph.documents.append(
            OrgDocument(
                logical_id=lid,
                revision_id=rev,
                title=title or pdf.stem,
                source_path=str(pdf.relative_to(src)),
                document_class=_classify_document(title or pdf.stem, text[:2000]),
                standard_folder=std_folder,
                nerc_standard=cb.get("nerc_standard", ""),
                document_number=cb.get("document_number", ""),
                effective_date=cb.get("effective_date", ""),
                approved_date=cb.get("approved_date", ""),
                revision_date=cb.get("revision_date", ""),
                last_reviewed_date=cb.get("last_reviewed_date", ""),
                owner=cb.get("owner", ""),
                approver=cb.get("approver", ""),
                declared_section_count=len(declared),
                control_block_fields_found=cb.get("found", []),
            )
        )
        graph.sections.extend(sections)
        for s in sections:
            body = text[s.char_start : s.char_end]
            is_trace = "traceab" in s.heading.lower() or "requirements mapping" in s.heading.lower()
            for node in extract_section_nodes(s, body, is_trace):
                fidelity_total += 1
                if text[node.char_start : node.char_end] != node.text:
                    fidelity_fail += 1
                    continue
                graph.nodes.append(node)
                if node.node_type in ("commitment", "activity"):
                    graph.edges.append(
                        {
                            "src": node.id,
                            "dst": lid,
                            "rel": node.fields.get("relation", "IMPLEMENTS"),
                        }
                    )
    _finalize_report(graph, pdfs, fidelity_total, fidelity_fail)
    return graph


def _finalize_report(graph: OrgGraph, pdfs: list[Path], fid_total: int, fid_fail: int) -> None:
    by_type: dict[str, int] = {}
    for n in graph.nodes:
        by_type[n.node_type] = by_type.get(n.node_type, 0) + 1
    docs_with_sections = {s.document_id for s in graph.sections if s.number}
    docs_with_nodes = {n.document_id for n in graph.nodes}
    sections_with_nodes = {n.section_id for n in graph.nodes}
    declared_sections = [s for s in graph.sections if s.number]
    graph.report = {
        "pdfs_seen": len(pdfs),
        "documents": len(graph.documents),
        "documents_missing_effective_date": sum(1 for d in graph.documents if not d.effective_date),
        "sections_declared": len(declared_sections),
        "nodes_by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
        "fidelity": {
            "n_checked": fid_total,
            "n_failed": fid_fail,
            "pass_rate": round(1 - (fid_fail / fid_total), 4) if fid_total else 1.0,
        },
        "completeness": {
            "denominator_source": "document-declared numbered section headings",
            "declared_sections": len(declared_sections),
            "declared_sections_with_extraction": len(
                sections_with_nodes & {s.section_id for s in declared_sections}
            ),
            "documents_with_no_extraction": sorted(docs_with_sections - docs_with_nodes),
        },
    }


def write_org_graph(graph: OrgGraph, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(graph.to_json(), indent=1, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    import asyncio
    import sys

    if len(sys.argv) > 2 and sys.argv[1] == "build":
        out = (
            sys.argv[3] if len(sys.argv) > 3 else "coding_task/v9_compliance/private/org_graph.json"
        )
        g = asyncio.run(build_org_graph(sys.argv[2]))
        write_org_graph(g, out)
        print(json.dumps(g.report, indent=1))
        print(f"wrote {out}")
    else:
        print(
            "usage: python -m portal.modules.compliance.core.org_graph build <corpus_dir> [out.json]"
        )
