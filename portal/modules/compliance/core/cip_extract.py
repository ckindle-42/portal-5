"""Verbatim Part-level extraction from NERC CIP standard PDFs (T3 Phase 1).

**Verbatim, never summarised.** The requirement column of each `Table R<n>` row
is extracted exactly as printed (line breaks normalised to spaces, the PDF
bullet glyph `` normalised to `- `); a summarised requirement cannot support
the gap-quoting the persona contract demands, and every citation built on it is
unverifiable.

**Verified, not trusted.** ``verify_parts`` re-locates every extracted verbatim
string in the raw page text; a Part that does not round-trip is reported
``missing`` so a hole is visible as a hole rather than producing a false
"no gap".

Structure this relies on (regular for CIP-004/005/006/007/008/009/010/011):

    R<n>. <lead-in> [Violation Risk Factor: <VRF>] [Time Horizon: <TH>]
    M<n>. <measure lead-in>
    CIP-XXX-Y Table R<n> - <table name>
    <table: Part | Applicable Systems | Requirements | Measures>

CIP-002 (categorisation + Attachment 1), CIP-003 (Attachment 1 for low impact),
CIP-012, CIP-013, CIP-014 diverge; ``extract_standard`` returns what it can and
the caller reports the shortfall per standard against that standard's own
numbering.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_BULLET = ""
_PART_RE = re.compile(r"^\d+\.\d+$")
_STANDARD_RE = re.compile(r"^(CIP-\d{3})-([\w.]+)\b")
_R_LEADIN_RE = re.compile(
    r"\bR(\d+)\.\s+((?:Each|The|Responsible)\b.+?\bshall\b.+?)"
    r"\[Violation\s+Risk\s+Factor:\s*([^\]]+?)\s*\]\s*"
    r"\[Time\s+Horizon:\s*([^\]]+?)\s*\]"
)
# CIP-014 uses a compact bracket: "[VRF: Medium; Time-Horizon: Long-term Planning]"
_R_LEADIN_ALT_RE = re.compile(
    r"\bR(\d+)\.\s+((?:Each|The)\b.+?\bshall\b.+?)"
    r"\[VRF:\s*([^;\]]+?)\s*;\s*Time-?\s*Horizon:\s*([^\]]+?)\s*\]"
)
_TABLE_CAP_RE = re.compile(r"Table\s+R(\d+)\s*[–-]\s*([A-Za-z][A-Za-z /,&-]+?)(?:\.|\n|$)")


def _norm(s: str) -> str:
    """Collapse PDF whitespace + normalise the bullet glyph. Verbatim content,
    reflowed — the words and their order are exactly the source's."""
    s = s.replace(_BULLET, "- ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class RequirementPart:
    standard: str  # "CIP-007"
    version: str  # "6"
    requirement: str  # "R2"
    part: str  # "2.2" — "" for a requirement with no parts table
    verbatim_text: str
    measure_text: str
    applicable_systems: str
    table_name: str
    vrf: str
    time_horizon: str
    source_pdf: str
    source_pages: list[int] = field(default_factory=list)

    @property
    def full_id(self) -> str:
        p = f" Part {self.part}" if self.part else ""
        return f"{self.standard}-{self.version} {self.requirement}{p}"


def _standard_and_version(pdf: Path) -> tuple[str, str]:
    """From the running header 'CIP-007-6 — Cyber Security ...'."""
    import pymupdf

    with pymupdf.open(str(pdf)) as d:
        head = d[0].get_text()[:400] + d[min(2, len(d) - 1)].get_text()[:400]
    m = _STANDARD_RE.search(head.replace("\n", " ").strip())
    if m:
        return m.group(1), m.group(2)
    # fall back to the filename: cip-007-6.pdf
    fm = re.match(r"(cip-\d{3})-([\w.]+)", pdf.stem, re.I)
    if fm:
        return fm.group(1).upper(), fm.group(2)
    raise ValueError(f"cannot determine standard id from {pdf}")


def _leadins(full_text: str) -> dict[str, tuple[str, str, str]]:
    """R<n> -> (lead-in, VRF, Time Horizon), from the requirement statements."""
    norm = _norm(full_text)
    out: dict[str, tuple[str, str, str]] = {}
    for rx in (_R_LEADIN_RE, _R_LEADIN_ALT_RE):
        for m in rx.finditer(norm):
            rn = f"R{m.group(1)}"
            if rn in out:
                continue
            out[rn] = (_norm(m.group(2)), _norm(m.group(3)), _norm(m.group(4)))
    return dict(sorted(out.items(), key=lambda kv: int(kv[0][1:])))


def _cells(row: list) -> list[str]:
    return [c.strip() for c in row if c and c.strip()]


def extract_standard(pdf_path: str | Path) -> tuple[list[RequirementPart], dict]:
    """Return (parts, meta). ``meta`` carries per-requirement R->parts counts and
    the requirements with no parts table (extracted at R granularity)."""
    import pymupdf

    pdf = Path(pdf_path)
    standard, version = _standard_and_version(pdf)
    with pymupdf.open(str(pdf)) as d:
        pages = [p.get_text() for p in d]
        full = "\n".join(pages)
        leadins = _leadins(full)
        parts: list[RequirementPart] = []
        seen: set[tuple[str, str]] = set()
        for pi, page in enumerate(d):
            for tab in page.find_tables().tables:
                rows = tab.extract()
                if len(rows) < 2:
                    continue
                header = " ".join(_cells(rows[1]))
                if "Applicable Systems" not in header or "Requirements" not in header:
                    continue
                cap = " ".join(_cells(rows[0]))
                cm = _TABLE_CAP_RE.search(cap)
                if not cm:
                    continue
                req = f"R{cm.group(1)}"
                table_name = _norm(cm.group(2))
                lead = leadins.get(req, ("", "", ""))
                for r in rows[2:]:
                    cc = _cells(r)
                    if len(cc) < 3 or not _PART_RE.match(cc[0]):
                        continue
                    key = (standard, cc[0])
                    if key in seen:
                        continue
                    seen.add(key)
                    appsys = _norm(cc[1]) if len(cc) >= 4 else ""
                    reqtext = _norm(cc[2] if len(cc) >= 4 else cc[1])
                    meastext = _norm(cc[3] if len(cc) >= 4 else (cc[2] if len(cc) > 2 else ""))
                    parts.append(
                        RequirementPart(
                            standard=standard,
                            version=version,
                            requirement=req,
                            part=cc[0],
                            verbatim_text=reqtext,
                            measure_text=meastext,
                            applicable_systems=appsys,
                            table_name=table_name,
                            vrf=lead[1],
                            time_horizon=lead[2],
                            source_pdf=pdf.name,
                            source_pages=[pi + 1],
                        )
                    )

    # requirements that have a lead-in but produced no parts (part-less R, or a
    # table layout this extractor did not recognise)
    parts_by_req: dict[str, list[str]] = {}
    for p in parts:
        parts_by_req.setdefault(p.requirement, []).append(p.part)
    partless = []
    for req, (lead, vrf, th) in leadins.items():
        if req not in parts_by_req:
            partless.append(req)
            parts.append(
                RequirementPart(
                    standard=standard,
                    version=version,
                    requirement=req,
                    part="",
                    verbatim_text=lead,
                    measure_text="",
                    applicable_systems="",
                    table_name="",
                    vrf=vrf,
                    time_horizon=th,
                    source_pdf=pdf.name,
                    source_pages=[],
                )
            )
    meta = {
        "standard": standard,
        "version": version,
        "requirements": sorted(leadins, key=lambda r: int(r[1:])),
        "parts_by_requirement": {k: sorted(v) for k, v in sorted(parts_by_req.items())},
        "partless_requirements": sorted(partless, key=lambda r: int(r[1:])),
        "n_parts": sum(1 for p in parts if p.part),
    }
    return parts, meta


def verify_parts(pdf_path: str | Path, parts: list[RequirementPart]) -> dict:
    """Round-trip every extracted verbatim string back against the raw page text.
    Returns found / verified / missing, per requirement."""
    import pymupdf

    with pymupdf.open(str(pdf_path)) as d:
        norm_pages = [_norm(p.get_text()) for p in d]
    blob = " ".join(norm_pages)

    verified, missing = [], []
    for p in parts:
        # part-less R lead-ins are matched a little more loosely (80 chars)
        probe = p.verbatim_text[: 80 if not p.part else 120]
        (verified if probe and probe in blob else missing).append(p.full_id)
    return {
        "n_total": len(parts),
        "n_verified": len(verified),
        "n_missing": len(missing),
        "missing": missing,
    }
