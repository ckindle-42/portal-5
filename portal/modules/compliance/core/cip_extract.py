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
# three-level leaves "1.2.6" (CIP-003-9 R1, CIP-013-2 R1). A bare integer
# ("1", "2") is a section header, never a Part.
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
    r"[-‐–—]\s*[A-Z][A-Za-z ]+?\s+(?:Page\s+)?\d+(?:\s+of\s+\d+)?\s*"
)
# page / attachment markers pymupdf splices into a string across a page break
_PAGE_MARK_RE = re.compile(r"\s*(?:Attachment\s+\d+\s+\d+|Page\s+\d+\s+of\s+\d+)\s*")


def _norm(s: str) -> str:
    """Collapse PDF whitespace + normalise the bullet glyph, and strip a spliced
    running header / page marker. Verbatim content, reflowed — the words and
    their order are exactly the source's."""
    s = s.replace(_BULLET, "- ").replace("\xa0", " ")
    s = _RUNHDR_RE.sub(" ", s)
    s = _PAGE_MARK_RE.sub(" ", s)
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


# ── prose numbered lists (CIP-002/003/012/013/014) ──────────────────────────
# Several standards lay a requirement's Parts out as a colon-terminated lead-in
# followed by a numbered list ("R1. … for purposes of parts 1.1 through 1.3: …
# 1.1. Identify … 1.2. Identify …") rather than a `Table R<n>`. One general
# extractor covers them; CIP-003 R1 keeps a thin wrapper (see `_cip003_r1_parts`).
_PROSE_ITEM_RE = re.compile(
    r"(?ms)^[ \t]*(\d+(?:\.\d+)+)\.?[ \t]*\r?\n?[ \t]*(\S.*?)"
    r"(?=^[ \t]*\d+(?:\.\d+)+\.?[ \t\r\n]|^[ \t]*M\d+\.[ \t]|^[ \t]*R\d+\.[ \t]|\Z)"
)


def _requirement_block(full: str, n: int) -> str:
    """The text of requirement R<n> — from its lead-in to its measure M<n>. The
    numbered list lives here; neither the Compliance section's own `1.1.`
    numbering nor the VSL table's `R1.` cells do, so the search is bounded to the
    'Requirements and Measures' section and anchored on the R<n> that is actually
    followed by a `shall`."""
    body_start = re.search(r"Requirements and Measures", full)
    hay = full[body_start.end() :] if body_start else full
    end = re.search(r"(?m)^[ \tC]*\.?\s*Compliance\s*$|\bViolation Severity Level", hay)
    if end:
        hay = hay[: end.start()]
    cand = None
    for m in re.finditer(rf"(?m)^[ \t]*R{n}\.[ \t\r\n]", hay):
        window = _norm(hay[m.start() : m.start() + 400])
        if re.search(r"\bshall\b|\bdeveloped\b|\breview\b", window, re.I):
            cand = m.start()
            break
    if cand is None:
        return ""
    me = re.search(rf"(?m)^[ \t]*M{n}\.[ \t\r\n]", hay[cand:])
    return hay[cand : cand + me.start()] if me else hay[cand : cand + 8000]


def _prose_items(block: str, req_num: int) -> list[tuple[str, str]]:
    """[(part_id, verbatim_body)] for every numbered item under requirement
    ``req_num`` in ``block``. Items nested deeper are returned too — the register
    is Part-granular and a deeper leaf is still addressable."""
    out: list[tuple[str, str]] = []
    for m in _PROSE_ITEM_RE.finditer(block):
        pid = m.group(1)
        if pid.split(".")[0] != str(req_num):
            continue
        body = _norm(m.group(2))
        if body:
            out.append((pid, body))
    return out


def _prose_list_parts(
    standard: str,
    version: str,
    req: str,
    lead: tuple[str, str, str],
    full: str,
    pdf: Path,
) -> list[RequirementPart]:
    """Parts of a colon-terminated prose requirement (CIP-002 R1/R2, CIP-012 R1,
    CIP-013 R1, CIP-014 R4/R5/R6)."""
    n = int(req[1:])
    out = []
    for pid, body in _prose_items(_requirement_block(full, n), n):
        out.append(
            RequirementPart(
                standard=standard,
                version=version,
                requirement=req,
                part=pid,
                verbatim_text=body,
                measure_text="",
                applicable_systems="",
                table_name="",
                vrf=lead[1],
                time_horizon=lead[2],
                source_pdf=pdf.name,
                source_pages=[],
            )
        )
    return out


def _cip003_r1_parts(
    standard: str, version: str, lead: tuple[str, str, str], full: str, pdf: Path
) -> list[RequirementPart]:
    """CIP-003 R1's policy-topic list. Bespoke for two reasons the general prose
    path does not cover: (1) only the leaves (1.1.1 … 1.2.7) are obligation-
    bearing — the 1.1 / 1.2 level is applicability scoping, not a topic; (2) each
    leaf's `applicable_systems` is derived from which sub-list it sits in (high +
    medium vs. low impact). Uses `_prose_items` for the raw grab, then filters
    and enriches."""
    parts = []
    for pid, topic in _prose_items(_requirement_block(full, 1), 1):
        if pid.count(".") != 2:  # keep leaves only; drop the 1.1 / 1.2 scoping level
            continue
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
                verbatim_text=topic.rstrip(" ;"),
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


# ── CIP-002 Attachment 1 — Impact Rating Criteria ───────────────────────────
_ATT1_SECTION_RE = re.compile(
    r"(?m)^[ \t]*([123])\.[ \t]+((?:High|Medium|Low) Impact Rating[^\n]*)"
)


def _cip002_attachment1(standard: str, version: str, full: str, pdf: Path) -> list[RequirementPart]:
    """The bright-line criteria (1.1–1.4 High, 2.x Medium, 3.x Low) that *define*
    the impact ratings the whole CIP suite gates on. Not a compliance
    requirement in itself, but the authoritative source for the register's
    applicability dimension (TASK §1.4)."""
    i = full.find("Attachment 1")
    if i < 0:
        return []
    j = full.find("Appendix 1", i)
    region = full[i : j if j > i else len(full)]
    secs = list(_ATT1_SECTION_RE.finditer(region))
    out: list[RequirementPart] = []
    for k, sm in enumerate(secs):
        tier = _norm(sm.group(2))  # "High Impact Rating (H)"
        end = secs[k + 1].start() if k + 1 < len(secs) else len(region)
        seg = region[sm.end() : end]
        lead_m = re.match(r"\s*(.+?:)\s*\n", seg)
        section_leadin = _norm(lead_m.group(1)) if lead_m else ""
        # section parent node — verbatim text is the section lead-in sentence
        # (a real sentence from the PDF), falling back to the tier heading.
        out.append(
            RequirementPart(
                standard=standard,
                version=version,
                requirement=f"Attachment 1 Section {sm.group(1)}",
                part="",
                verbatim_text=section_leadin or tier,
                measure_text="",
                applicable_systems=tier,
                table_name="Impact Rating Criteria",
                vrf="",
                time_horizon="",
                source_pdf=pdf.name,
                source_pages=[],
            )
        )
        for pid, body in _prose_items(seg, int(sm.group(1))):
            out.append(
                RequirementPart(
                    standard=standard,
                    version=version,
                    requirement="Attachment 1",
                    part=pid,
                    verbatim_text=body,
                    measure_text="",
                    applicable_systems=f"{tier} — {section_leadin}".rstrip(" —"),
                    table_name="Impact Rating Criteria",
                    vrf="",
                    time_horizon="",
                    source_pdf=pdf.name,
                    source_pages=[],
                )
            )
    return out


# CIP-003 Attachment 1 — the low-impact cyber security plan sections R2 requires
# ("Section 1. Cyber Security Awareness: …"). Section 6 (vendor electronic remote
# access) is new in CIP-003-9 and is the T4-documented diff false negative.
_CIP003_ATT_SEC_RE = re.compile(r"(?m)^[ \t]*Section[ \t]+(\d+)\.[ \t]+([^\n:]+):[ \t]*")


def _cip003_attachment1(standard: str, version: str, full: str, pdf: Path) -> list[RequirementPart]:
    i = full.find("Required Sections for Cyber Security Plan")
    if i < 0:
        return []
    j = full.find("Attachment 2", i)
    region = full[i : j if j > i else len(full)]
    secs = list(_CIP003_ATT_SEC_RE.finditer(region))
    out: list[RequirementPart] = []
    for k, sm in enumerate(secs):
        n = sm.group(1)
        title = _norm(sm.group(2))
        end = secs[k + 1].start() if k + 1 < len(secs) else len(region)
        seg = region[sm.start() : end]
        # the section node's verbatim text is its lead-in only — up to the first
        # numbered sub-item, or the whole section when it has none. A section-
        # sized blob otherwise accumulates hyphen re-encodings across a version
        # bump and the diff misreads them as substantive.
        first_item = _PROSE_ITEM_RE.search(seg)
        body = _norm(seg[: first_item.start()] if first_item else seg)
        out.append(
            RequirementPart(
                standard=standard,
                version=version,
                requirement="Attachment 1",
                part=n,
                verbatim_text=body,
                measure_text="",
                applicable_systems="assets containing low impact BES Cyber Systems",
                table_name=f"Required Sections for Cyber Security Plan(s) — {title}",
                vrf="Lower",
                time_horizon="Operations Planning",
                source_pdf=pdf.name,
                source_pages=[],
            )
        )
        for pid, sub in _prose_items(seg, int(n)):
            out.append(
                RequirementPart(
                    standard=standard,
                    version=version,
                    requirement="Attachment 1",
                    part=pid,
                    verbatim_text=sub,
                    measure_text="",
                    applicable_systems="assets containing low impact BES Cyber Systems",
                    table_name=f"Required Sections for Cyber Security Plan(s) — {title}",
                    vrf="Lower",
                    time_horizon="Operations Planning",
                    source_pdf=pdf.name,
                    source_pages=[],
                )
            )
    return out


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


def extract_standard(  # noqa: PLR0912 - one pass over table + prose + attachment + R-level, sequential by design
    pdf_path: str | Path,
) -> tuple[list[RequirementPart], dict]:
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

    # CIP-003 R1 policy-topic leaves (bespoke: leaves-only + impact enrichment).
    if standard == "CIP-003" and not any(p.requirement == "R1" and p.part for p in parts):
        parts.extend(
            _cip003_r1_parts(standard, version, leadins.get("R1", ("", "", "")), full, pdf)
        )
        seen.update((standard, p.part) for p in parts if p.requirement == "R1")

    # General prose numbered lists — any requirement the table pass left part-less
    # whose lead-in ends in ':' (it is declaring that a list follows).
    table_reqs = {p.requirement for p in parts if p.part}
    for req, (lead, vrf, th) in leadins.items():
        if req in table_reqs or (standard == "CIP-003" and req == "R1"):
            continue
        # a colon lead-in *declares* a list; a period lead-in may still carry one
        # (CIP-014 R6). Run the extractor either way — the block is bounded, so a
        # dry requirement simply yields nothing.
        prose = _prose_list_parts(standard, version, req, (lead, vrf, th), full, pdf)
        parts.extend(prose)
        seen.update((standard, p.part) for p in prose)

    # CIP-002 Attachment 1 — the impact-rating criteria the whole suite gates on.
    if standard == "CIP-002":
        parts.extend(_cip002_attachment1(standard, version, full, pdf))
    # CIP-003 Attachment 1 — the low-impact plan sections R2 requires (incl. the
    # -9 Section 6 vendor-remote-access program, the T4 diff false negative).
    if standard == "CIP-003":
        parts.extend(_cip003_attachment1(standard, version, full, pdf))

    # R-level bookkeeping: which requirements produced obligation-bearing parts.
    parts_by_req: dict[str, list[str]] = {}
    for p in parts:
        if not re.fullmatch(r"R\d+", p.requirement):
            continue  # Attachment nodes are not requirement-numbered
        if p.standard.startswith("CIP-003") and p.requirement == "R1":
            continue  # topic leaves don't count as covering R1
        if p.part:
            parts_by_req.setdefault(p.requirement, []).append(p.part)
    partless = []
    for req, (lead, vrf, th) in leadins.items():
        has_parts = req in parts_by_req
        colon = lead.rstrip().endswith(":")
        # emit an R-level node when the requirement is genuinely part-less OR
        # when a colon lead-in needs its parent retained above its new Parts.
        if not has_parts or colon or (standard == "CIP-003" and req == "R1"):
            if not has_parts:
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
        if not re.fullmatch(r"R\d+", p.requirement):
            continue  # completeness is assessed per numbered requirement only
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
