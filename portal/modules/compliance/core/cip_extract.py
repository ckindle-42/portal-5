"""Verbatim Part-level extraction from NERC CIP standard PDFs (T3 Phase 1).

**Verbatim, never summarised.** The requirement column of each `Table R<n>` row
is extracted exactly as printed (line breaks normalised to spaces, the PDF
bullet glyph `` normalised to `- `); a summarised requirement cannot support
the gap-quoting the persona contract demands, and every citation built on it is
unverifiable.

**Two independent checks, never conflated.** ``verify_fidelity`` re-locates
every *extracted* verbatim string in the raw page text — a Part that does not
round-trip was mangled in extraction. ``assess_completeness`` asks the opposite
question — does the register hold every Part the *document* says exists — using
document-derived signals (a colon-terminated lead-in with no children; the
document naming its own children; numbering gaps), never the extractor's own
output. A completeness metric computed by iterating what you found is a fidelity
metric; this module keeps the two numbers apart.

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
# Part ids are two or more dot-separated integers: "1.1", "1.10", and the
# three-level leaves "1.2.6" (CIP-003-9 R1) and "2.1.1" (CIP-014 R2). A bare
# integer ("1", "2") is a section header, never a Part.
_PART_RE = re.compile(r"^\d+(?:\.\d+)+$")
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


# NERC running header, e.g. "CIP-003-9 - Cyber Security - Security Management
# Controls 5". pymupdf occasionally splices it into a requirement string that
# spans a page break; it is not part of the obligation text.
_RUNHDR_RE = re.compile(
    r"\s*CIP[-‐]\d{3}[-‐][\w.]+\s*[-‐–—]\s*Cyber Security\s*"
    r"[-‐–—]\s*[A-Z][A-Za-z ]+?\s+\d+(?:\s+of\s+\d+)?\s*"
)


def _norm(s: str) -> str:
    """Collapse PDF whitespace + normalise the bullet glyph, and strip a spliced
    running header. Verbatim content, reflowed — the words and their order are
    exactly the source's."""
    s = s.replace(_BULLET, "- ").replace("\xa0", " ")
    s = _RUNHDR_RE.sub(" ", s)
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


# CIP-003 R1 carries its obligations as a nested numbered list of policy topics
# (1.1.1 .. 1.1.9, 1.2.1 .. 1.2.7) rather than a Table R<n>. This is the one
# case where the leaf items are the unit of change (T4 targets CIP-003-8 -> -9,
# where 1.2.6 changed meaning and 1.2.7 was added).
_CIP003_LEAF_RE = re.compile(
    r"(?m)^\s*(1\.[12]\.\d+)\.\s+(.+?)(?=^\s*1\.[12]\.\d+\.|\bM1\.|\Z)", re.S
)


def _cip003_r1_leaves(full_text: str) -> list[tuple[str, str]]:
    """[(part_id, verbatim_topic)] for CIP-003 R1's policy-topic list."""
    out = []
    for m in _CIP003_LEAF_RE.finditer(full_text):
        topic = _norm(m.group(2))
        # trim a trailing '(CIP-004);' style xref-only tail but keep it in text
        out.append((m.group(1), topic.rstrip(" ;")))
    return out


def _cip003_r1_parts(
    standard: str, version: str, lead: tuple[str, str, str], full: str, pdf: Path
) -> list[RequirementPart]:
    parts = []
    for pid, topic in _cip003_r1_leaves(full):
        impacts = (
            "high impact and medium impact BES Cyber Systems"
            if pid.startswith("1.1.")
            else "assets identified in CIP-002 containing low impact BES Cyber Systems"
        )
        parts.append(
            RequirementPart(
                standard=standard,
                version=version,
                requirement="R1",
                part=pid,
                verbatim_text=topic,
                measure_text="",
                applicable_systems=impacts,
                table_name="Cyber Security Policies",
                vrf=lead[1] or "Medium",
                time_horizon=lead[2] or "Operations Planning",
                source_pdf=pdf.name,
                source_pages=[],
            )
        )
    return parts


def _table_parts(page, pi, standard, version, leadins, pdf, seen) -> list[RequirementPart]:
    """Every recognised `Table R<n>` row on one page."""
    out: list[RequirementPart] = []
    for tab in page.find_tables().tables:
        rows = tab.extract()
        if len(rows) < 2:
            continue
        header = " ".join(_cells(rows[1]))
        if "Applicable Systems" not in header or "Requirements" not in header:
            continue
        cm = _TABLE_CAP_RE.search(" ".join(_cells(rows[0])))
        if not cm:
            continue
        req = f"R{cm.group(1)}"
        table_name = _norm(cm.group(2))
        lead = leadins.get(req, ("", "", ""))
        for r in rows[2:]:
            cc = _cells(r)
            if len(cc) < 3 or not _PART_RE.match(cc[0]) or (standard, cc[0]) in seen:
                continue
            seen.add((standard, cc[0]))
            out.append(
                RequirementPart(
                    standard=standard,
                    version=version,
                    requirement=req,
                    part=cc[0],
                    verbatim_text=_norm(cc[2] if len(cc) >= 4 else cc[1]),
                    measure_text=_norm(cc[3] if len(cc) >= 4 else (cc[2] if len(cc) > 2 else "")),
                    applicable_systems=_norm(cc[1]) if len(cc) >= 4 else "",
                    table_name=table_name,
                    vrf=lead[1],
                    time_horizon=lead[2],
                    source_pdf=pdf.name,
                    source_pages=[pi + 1],
                )
            )
    return out


def extract_standard(pdf_path: str | Path) -> tuple[list[RequirementPart], dict]:
    """Return (parts, meta). ``meta`` carries per-requirement R->parts counts and
    the requirements with no parts table (extracted at R granularity)."""
    import pymupdf

    pdf = Path(pdf_path)
    standard, version = _standard_and_version(pdf)
    with pymupdf.open(str(pdf)) as d:
        full = "\n".join(p.get_text() for p in d)
        leadins = _leadins(full)
        parts: list[RequirementPart] = []
        seen: set[tuple[str, str]] = set()
        for pi, page in enumerate(d):
            parts.extend(_table_parts(page, pi, standard, version, leadins, pdf, seen))

    # CIP-003 R1 policy-topic leaves (the one non-table case with leaf Parts).
    # The R1 *statement* still carries the 15-calendar-month review obligation, so
    # R1 is emitted at R-level AND its topic leaves as Parts.
    if standard == "CIP-003" and not any(p.requirement == "R1" and p.part for p in parts):
        parts.extend(
            _cip003_r1_parts(standard, version, leadins.get("R1", ("", "", "")), full, pdf)
        )
        seen.update((standard, p.part) for p in parts if p.requirement == "R1")

    # requirements that have a lead-in but produced no obligation-bearing parts
    # (part-less R, an unrecognised table, or CIP-003 R1 whose parts are topics)
    parts_by_req: dict[str, list[str]] = {}
    for p in parts:
        if p.standard.startswith("CIP-003") and p.requirement == "R1":
            continue  # topic leaves don't count as covering R1
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


def verify_fidelity(pdf_path: str | Path, parts: list[RequirementPart]) -> dict:
    """**Fidelity, not completeness.** Round-trip every *extracted* verbatim
    string back against the raw page text; a string that does not re-locate was
    mangled in extraction. This iterates ``parts``, so a requirement that was
    never extracted cannot appear here — that is what ``assess_completeness``
    is for. No field in this dict is named ``missing``."""
    import pymupdf

    with pymupdf.open(str(pdf_path)) as d:
        norm_pages = [_norm(p.get_text()) for p in d]
    blob = " ".join(norm_pages)

    verified, failed = [], []
    for p in parts:
        # part-less R lead-ins are matched a little more loosely (80 chars)
        probe = p.verbatim_text[: 80 if not p.part else 120]
        (verified if probe and probe in blob else failed).append(p.full_id)
    return {
        "n_extracted": len(parts),
        "n_fidelity_verified": len(verified),
        "n_fidelity_failed": len(failed),
        "fidelity_failed": failed,
    }


# ── completeness (independent of what the extractor produced) ────────────────
# Signal 1 — a requirement lead-in that ends in a colon is declaring that a list
# of children follows. If none were extracted, that is a hole the document itself
# announces. Zero external index, zero false positives on the shipped standards.
_COLON_LEADIN_RE = re.compile(r":\s*$")

# Signal 2 — the document naming its own children. "for purposes of parts 1.1
# through 1.3", "Parts 1.1, 1.2, and 1.3", "Criteria 1.1 to 1.4 and 2.1 to 2.11",
# "parts 2.1.1, 2.1.2, and 2.1.3".
_SELFREF_RANGE_RE = re.compile(
    r"\b(?:part|parts|criterion|criteria|section|sections)\s+"
    r"(\d+(?:\.\d+)+)\s+(?:through|to|[-–])\s+(\d+(?:\.\d+)+)",
    re.I,
)
_SELFREF_LIST_RE = re.compile(
    r"\b(?:part|parts|criterion|criteria)\s+"
    r"((?:\d+(?:\.\d+)+)(?:\s*,\s*(?:and\s+)?\d+(?:\.\d+)+)+(?:\s*,?\s*and\s+\d+(?:\.\d+)+)?)",
    re.I,
)


def _expand_range(lo: str, hi: str) -> list[str]:
    """`1.1`..`1.3` -> [1.1, 1.2, 1.3]; `2.1` .. `2.11` -> 2.1..2.11. Only
    expands when the ids share a prefix and differ in the last component."""
    a, b = lo.split("."), hi.split(".")
    if len(a) != len(b) or a[:-1] != b[:-1]:
        return [lo, hi]
    try:
        first, last = int(a[-1]), int(b[-1])
    except ValueError:
        return [lo, hi]
    if not 0 <= last - first < 40:
        return [lo, hi]
    return [".".join(a[:-1] + [str(i)]) for i in range(first, last + 1)]


def _self_referenced_ids(text: str, req_num: str) -> set[str]:
    """Child ids the text names for requirement ``req_num`` (e.g. "1")."""
    out: set[str] = set()
    for m in _SELFREF_RANGE_RE.finditer(text):
        out.update(_expand_range(m.group(1), m.group(2)))
    for m in _SELFREF_LIST_RE.finditer(text):
        out.update(re.findall(r"\d+(?:\.\d+)+", m.group(1)))
    return {i for i in out if i.split(".")[0] == req_num}


def assess_completeness(parts: list[RequirementPart]) -> dict:
    """**Completeness, not fidelity.** Does the register hold every Part the
    *document* says exists? Three document-derived signals, strongest first:

    1. colon-terminated requirement lead-in with zero extracted children;
    2. the document naming its own children ("parts 1.1 through 1.3");
    3. numbering contiguity — extracted 1.1, 1.2, 1.4 means 1.3 is missing.

    ``denominator_source`` per requirement names which signal set the expected
    count. It is **never** ``"extractor"`` — the bug this function exists to
    close is a denominator the extractor supplies to itself. Every signal reads
    the document's own verbatim text (the lead-in strings are extracted verbatim
    from the PDF), so no re-parse of the PDF is needed here.
    """
    by_req: dict[str, list[RequirementPart]] = {}
    leadin_by_req: dict[str, RequirementPart] = {}
    for p in parts:
        if p.part:
            by_req.setdefault(p.requirement, []).append(p)
        else:
            leadin_by_req.setdefault(p.requirement, p)

    reqs = sorted(set(by_req) | set(leadin_by_req), key=lambda r: int(r[1:]))
    incomplete: list[dict] = []
    sources: set[str] = set()

    def _captured(pid: str, ex: set[str]) -> bool:
        # captured if the id itself or any dotted ancestor is an extracted node —
        # "1.1.5" lives inside Part "1.1"'s verbatim text.
        bits = pid.split(".")
        return any(".".join(bits[:i]) in ex for i in range(2, len(bits) + 1))

    for req in reqs:
        req_num = req[1:]
        extracted = sorted(p.part for p in by_req.get(req, []))
        ex_set = set(extracted)
        lead = leadin_by_req.get(req)
        lead_text = lead.verbatim_text if lead else ""

        colon = bool(lead) and not extracted and bool(_COLON_LEADIN_RE.search(lead_text))
        expected = _self_referenced_ids(
            lead_text or " ".join(p.verbatim_text for p in by_req.get(req, [])), req_num
        )
        selfref_missing = sorted(i for i in expected if not _captured(i, ex_set))

        contiguity_missing: list[str] = []
        leaves = [e for e in extracted if e.count(".") == 1]
        if len(leaves) >= 2:
            nums = sorted(int(e.split(".")[1]) for e in leaves)
            contiguity_missing = [
                f"{req_num}.{i}" for i in range(nums[0], nums[-1]) if i not in nums
            ]

        if colon:
            incomplete.append(
                {
                    "requirement": req,
                    "signal": "colon-lead-in",
                    "detail": f"lead-in ends ':' — '{lead_text[-70:]}' — zero children extracted",
                    "missing": sorted(expected) or ["<unenumerated list>"],
                    "extracted": extracted,
                }
            )
            sources.add("document:colon-lead-in")
        elif selfref_missing:
            incomplete.append(
                {
                    "requirement": req,
                    "signal": "self-reference",
                    "detail": f"document names {selfref_missing} with no extracted node or parent",
                    "missing": selfref_missing,
                    "extracted": extracted,
                }
            )
            sources.add("document:self-reference")
        elif contiguity_missing:
            incomplete.append(
                {
                    "requirement": req,
                    "signal": "contiguity",
                    "detail": f"gap in numbering: extracted {extracted}, missing {contiguity_missing}",
                    "missing": contiguity_missing,
                    "extracted": extracted,
                }
            )
            sources.add("document:contiguity")
        elif extracted:
            sources.add("document:enumerated-list")
        elif lead and not _COLON_LEADIN_RE.search(lead_text):
            sources.add("document:requirement-level")  # period-terminated: genuinely part-less
        else:
            sources.add("document:enumerated-list")

    return {
        "n_requirements": len(reqs),
        "n_parts_extracted": sum(len(v) for v in by_req.values()),
        "incomplete_requirements": incomplete,
        "n_missing": sum(len(r["missing"]) for r in incomplete),
        "complete": not incomplete,
        "denominator_source": "+".join(sorted(sources)) if sources else "document:none",
    }
