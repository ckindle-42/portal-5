"""The bitemporal NERC CIP requirement register (T3 Phase 1).

Nodes are requirement **Parts** (or R-level statements where a standard's
obligations live in prose / an Attachment). The temporal model is
**validity-time**, not observation-time: `valid_from` / `valid_to` are when a
requirement *is enforceable*, true independent of when we ingested it —
`graph_memory`'s `first_seen` / `last_seen` schema is deliberately NOT reused.

`nerc_cip_map.json` is rebuilt as a *derived* crosswalk from this register plus
the pre-existing advisory `related_800_53` seed. `nerc_cip_requirement()` keeps
its signature and answers at Part granularity.

Serialised to `portal/modules/compliance/data/nerc_cip_register.json` — NERC
standards are public record, so the verbatim register is committable (unlike the
operator's private policy PDFs).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from portal.modules.compliance.core.cip_extract import (
    assess_completeness,
    extract_standard,
    verify_fidelity,
)

_DATA = Path(__file__).resolve().parent.parent / "data"
REGISTER_PATH = _DATA / "nerc_cip_register.json"
DERIVED_MAP_PATH = _DATA / "nerc_cip_map.json"

# FERC-approved effective dates — public record (nerc.com/pa/Stand, "Reliability
# Standards Under Development" / "Enforcement Dates"). The standard PDFs
# themselves defer to a separate Implementation Plan, so these are maintained
# here with an explicit source and re-checked by the Phase 8 currency probe
# (`honest-BLOCKED` when nerc.com is unreachable — never inferred).
_LIFECYCLE: dict[str, dict] = {
    "CIP-002-5.1a": {"state": "EFFECTIVE", "valid_from": "2016-07-01", "valid_to": None},
    "CIP-003-8": {
        "state": "RETIRED",
        "valid_from": "2020-01-01",
        "valid_to": "2024-04-01",
        "superseded_by": "CIP-003-9",
    },
    "CIP-003-9": {
        "state": "EFFECTIVE",
        "valid_from": "2024-04-01",
        "valid_to": None,
        "supersedes": "CIP-003-8",
    },
    "CIP-004-7": {"state": "EFFECTIVE", "valid_from": "2024-04-01", "valid_to": None},
    "CIP-005-7": {"state": "EFFECTIVE", "valid_from": "2024-04-01", "valid_to": None},
    "CIP-006-6": {"state": "EFFECTIVE", "valid_from": "2017-07-01", "valid_to": None},
    "CIP-007-6": {"state": "EFFECTIVE", "valid_from": "2016-07-01", "valid_to": None},
    "CIP-008-6": {"state": "EFFECTIVE", "valid_from": "2021-01-01", "valid_to": None},
    "CIP-009-6": {"state": "EFFECTIVE", "valid_from": "2016-07-01", "valid_to": None},
    "CIP-010-4": {"state": "EFFECTIVE", "valid_from": "2024-04-01", "valid_to": None},
    "CIP-011-3": {"state": "EFFECTIVE", "valid_from": "2024-04-01", "valid_to": None},
    "CIP-012-1": {
        "state": "RETIRED",
        "valid_from": "2022-07-01",
        "valid_to": "2025-07-01",
        "superseded_by": "CIP-012-2",
    },
    "CIP-012-2": {
        "state": "EFFECTIVE",
        "valid_from": "2025-07-01",
        "valid_to": None,
        "supersedes": "CIP-012-1",
    },
    "CIP-013-2": {"state": "EFFECTIVE", "valid_from": "2024-04-01", "valid_to": None},
    "CIP-014-3": {"state": "EFFECTIVE", "valid_from": "2022-01-01", "valid_to": None},
}
_LIFECYCLE_SOURCE = "nerc.com/pa/Stand — FERC-approved enforcement dates (public record)"

# Authority tier: standard text is Tier 0 (Phase 3 assigns Tier 1-4 to the other
# document classes).
TIER_STANDARD = 0


@dataclass
class RegisterNode:
    id: str  # "CIP-007-6 R2 Part 2.2"
    standard: str  # "CIP-007-6"
    version: str
    requirement: str  # "R2"
    part: str  # "2.2" or ""
    verbatim_text: str
    measure_text: str
    applicable_systems: str
    table_name: str
    vrf: str
    time_horizon: str
    lifecycle_state: str
    valid_from: str | None
    valid_to: str | None
    supersedes: str | None
    superseded_by: str | None
    authority_tier: int
    source_pdf: str
    source_pages: list[int]
    recorded_at: float
    granularity: str  # "part" | "requirement"


@dataclass
class Register:
    nodes: list[RegisterNode] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    extraction_report: dict = field(default_factory=dict)
    lifecycle_source: str = _LIFECYCLE_SOURCE
    built_at: str = ""  # ISO-8601 UTC — an auditable artifact carries a real header
    source_pdfs: dict = field(default_factory=dict)  # {"cip-007-6.pdf": "<sha256[:12]>"}
    extractor_commit: str = ""  # git HEAD of cip_extract.py at build time

    def to_json(self) -> dict:
        return {
            "built_at": self.built_at,
            "extractor_commit": self.extractor_commit,
            "source_pdfs": self.source_pdfs,
            "lifecycle_source": self.lifecycle_source,
            "extraction_report": self.extraction_report,
            "nodes": [asdict(n) for n in self.nodes],
            "edges": self.edges,
        }

    @classmethod
    def load(cls, path: Path | str = REGISTER_PATH) -> Register:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            nodes=[RegisterNode(**n) for n in d["nodes"]],
            edges=d.get("edges", []),
            extraction_report=d.get("extraction_report", {}),
            lifecycle_source=d.get("lifecycle_source", _LIFECYCLE_SOURCE),
            built_at=d.get("built_at", ""),
            source_pdfs=d.get("source_pdfs", {}),
            extractor_commit=d.get("extractor_commit", ""),
        )


_XREF_RE = re.compile(r"\bCIP-\d{3}(?:-[\w.]+)?\b")

_NERC_BASE = "https://www.nerc.com/globalassets/standards/reliability-standards/cip"
_STANDARDS = [
    "cip-002-5.1a",
    "cip-003-9",
    "cip-004-7",
    "cip-005-7",
    "cip-006-6",
    "cip-007-6",
    "cip-008-6",
    "cip-009-6",
    "cip-010-4",
    "cip-011-3",
    "cip-012-2",
    "cip-013-2",
    "cip-014-3",
]


def fetch_pdfs(dest: str | Path) -> tuple[list[str], list[str]]:
    """Download the 13 current CIP standard PDFs. Public record; not committed
    (the register JSON is the committed artifact). Returns (ok, failed)."""
    import urllib.error
    import urllib.request

    d = Path(dest)
    d.mkdir(parents=True, exist_ok=True)
    ok, failed = [], []
    for s in _STANDARDS:
        out = d / f"{s}.pdf"
        if out.exists() and out.stat().st_size > 50_000:
            ok.append(s)
            continue
        try:
            req = urllib.request.Request(f"{_NERC_BASE}/{s}.pdf", headers={"User-Agent": "portal5"})
            with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - fixed host
                out.write_bytes(r.read())
            ok.append(s)
        except (urllib.error.URLError, TimeoutError, OSError):
            failed.append(s)
    return ok, failed


def _extractor_commit() -> str:
    import subprocess

    src = Path(__file__).with_name("cip_extract.py")
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", str(src)],
            capture_output=True,
            text=True,
            cwd=src.parent,
            timeout=10,
            check=False,
        )
        sha = (out.stdout.strip() or "unknown")[:12]
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", str(src)],
            capture_output=True,
            text=True,
            cwd=src.parent,
            timeout=10,
            check=False,
        )
        return sha + ("-dirty" if dirty.stdout.strip() else "")
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def build_register(pdf_dir: str | Path) -> Register:
    """Extract every downloaded standard, check fidelity AND completeness, attach
    lifecycle, derive cross-reference edges. Deterministic given the same PDFs
    apart from the ``built_at`` header."""
    import datetime
    import hashlib

    pdf_dir = Path(pdf_dir)
    src_pdfs = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:12]
        for p in sorted(pdf_dir.glob("cip-*.pdf"))
    }
    reg = Register(
        built_at=datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        source_pdfs=src_pdfs,
        extractor_commit=_extractor_commit(),
    )
    report: dict = {}
    now = 0.0  # deterministic per-node stamp; the live store stamps real recorded_at

    for pdf in sorted(pdf_dir.glob("cip-*.pdf")):
        parts, meta = extract_standard(pdf)
        fid = verify_fidelity(pdf, parts)
        comp = assess_completeness(parts)
        std = meta["standard"]  # "CIP-007"
        ver = meta["version"]
        full = f"{std}-{ver}"
        life = _LIFECYCLE.get(full, {"state": "EFFECTIVE", "valid_from": None, "valid_to": None})
        report[full] = {
            "requirements": meta["requirements"],
            "n_parts": meta["n_parts"],
            "partless_requirements": meta["partless_requirements"],
            "lifecycle": life,
            "fidelity": fid,
            "completeness": comp,
        }
        for p in parts:
            node_id = p.full_id
            reg.nodes.append(
                RegisterNode(
                    id=node_id,
                    standard=full,
                    version=ver,
                    requirement=p.requirement,
                    part=p.part,
                    verbatim_text=p.verbatim_text,
                    measure_text=p.measure_text,
                    applicable_systems=p.applicable_systems,
                    table_name=p.table_name,
                    vrf=p.vrf,
                    time_horizon=p.time_horizon,
                    lifecycle_state=life["state"],
                    valid_from=life.get("valid_from"),
                    valid_to=life.get("valid_to"),
                    supersedes=life.get("supersedes"),
                    superseded_by=life.get("superseded_by"),
                    authority_tier=TIER_STANDARD,
                    source_pdf=p.source_pdf,
                    source_pages=p.source_pages,
                    recorded_at=now,
                    granularity="part" if p.part else "requirement",
                )
            )
            reg.edges.append({"src": full, "dst": node_id, "rel": "HAS_REQUIREMENT"})
            for ref in sorted(
                set(_XREF_RE.findall(p.verbatim_text + " " + p.measure_text))
                - {full, std, f"{std}-"}
            ):
                if ref in (std, full):
                    continue
                reg.edges.append(
                    {
                        "src": node_id,
                        "dst": ref,
                        "rel": "CROSS_REFERENCES",
                        "valid_from": life.get("valid_from"),
                    }
                )
        sup = life.get("supersedes")
        if sup:
            reg.edges.append(
                {"src": full, "dst": sup, "rel": "SUPERSEDES", "valid_from": life.get("valid_from")}
            )
            reg.edges.append(
                {
                    "src": sup,
                    "dst": full,
                    "rel": "SUPERSEDED_BY",
                    "valid_to": life.get("valid_from"),
                }
            )

    reg.extraction_report = {
        "n_standards": len(report),
        "n_nodes": len(reg.nodes),
        "n_parts": sum(1 for n in reg.nodes if n.granularity == "part"),
        "n_requirement_level": sum(1 for n in reg.nodes if n.granularity == "requirement"),
        "fidelity": {
            "n_extracted": sum(r["fidelity"]["n_extracted"] for r in report.values()),
            "n_fidelity_verified": sum(
                r["fidelity"]["n_fidelity_verified"] for r in report.values()
            ),
            "n_fidelity_failed": sum(r["fidelity"]["n_fidelity_failed"] for r in report.values()),
            "fidelity_failed": sorted(
                fid for r in report.values() for fid in r["fidelity"]["fidelity_failed"]
            ),
        },
        "completeness": {
            "n_missing": sum(r["completeness"]["n_missing"] for r in report.values()),
            "incomplete_standards": sorted(
                std for std, r in report.items() if not r["completeness"]["complete"]
            ),
            "denominator_source_by_standard": {
                std: r["completeness"]["denominator_source"] for std, r in report.items()
            },
        },
        "per_standard": report,
    }
    return reg


def write_register(reg: Register, path: Path | str = REGISTER_PATH) -> None:
    Path(path).write_text(json.dumps(reg.to_json(), indent=1, ensure_ascii=False), encoding="utf-8")


def derive_crosswalk(reg: Register, path: Path | str = DERIVED_MAP_PATH) -> dict:
    """Rebuild nerc_cip_map.json as a *derived* view: one entry per register
    node, carrying the verbatim text and (where the pre-existing seed had one)
    the advisory 800-53 crosswalk. The seed's superseded versions (CIP-003-8,
    CIP-012-1) are dropped — the register is the source of truth for versions."""
    seed = {}
    p = Path(path)
    if p.exists():
        with __import__("contextlib").suppress(Exception):
            seed = json.loads(p.read_text(encoding="utf-8")).get("requirements", {})
    # seed keys are "CIP-007-6 R2" — map R-level 800-53 hints onto our nodes
    seed_by_r = {}
    for k, val in seed.items():
        m = re.match(r"(CIP-\d{3}-[\w.]+)\s+(R\d+)", k)
        if m:
            seed_by_r[(m.group(1).upper().replace("5.1A", "5.1a"), m.group(2))] = val.get(
                "related_800_53", []
            )

    out: dict[str, dict] = {}
    for n in reg.nodes:
        out[n.id] = {
            "standard": n.standard,
            "requirement": n.requirement,
            "part": n.part,
            "verbatim_text": n.verbatim_text,
            "lifecycle_state": n.lifecycle_state,
            "valid_from": n.valid_from,
            "valid_to": n.valid_to,
            "related_800_53": seed_by_r.get((n.standard, n.requirement), []),
        }
    payload = {
        "source": "DERIVED from portal/modules/compliance/data/nerc_cip_register.json "
        "(NERC CIP standards, verbatim). Do not hand-edit — run "
        "`python -m portal.modules.compliance.core.cip_register build`.",
        "note": "related_800_53 is the pre-existing advisory crosswalk seed, "
        "R-level, not an official OLIR. Verify against the current enforceable "
        "version on nerc.com for audit use.",
        "lifecycle_source": reg.lifecycle_source,
        "requirements": out,
    }
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in ("build", "fetch"):
        src = sys.argv[2] if len(sys.argv) > 2 else str(_DATA / "cip_pdfs")
        okp, badp = fetch_pdfs(src)
        if badp:
            print(f"honest-BLOCKED: could not fetch {badp} from nerc.com")
            if sys.argv[1] == "fetch":
                sys.exit(1)
        if sys.argv[1] == "fetch":
            print(f"fetched {len(okp)}/13 CIP PDFs to {src}")
            sys.exit(0)
        r = build_register(src)
        write_register(r)
        derive_crosswalk(r)
        rep = r.extraction_report
        print(
            f"register: {rep['n_nodes']} nodes ({rep['n_parts']} parts, "
            f"{rep['n_requirement_level']} R-level), "
            f"{rep['fidelity']['n_fidelity_verified']}/{rep['fidelity']['n_extracted']} fidelity-verified, "
            f"{rep['completeness']['n_missing']} completeness holes"
        )
        for std, s in rep["per_standard"].items():
            c = s["completeness"]
            holes = ",".join(
                i["requirement"] + ":" + i["signal"] for i in c["incomplete_requirements"]
            )
            print(
                f"  {std:<14} R={len(s['requirements']):2d} parts={s['n_parts']:3d} "
                f"fidelity_fail={s['fidelity']['n_fidelity_failed']} "
                f"holes=[{holes}] src={c['denominator_source']}"
            )
