"""The planted compliance corpus + its scorer (T3 Phase 7, Tier 2).

You cannot verify gap detection against data whose gaps you do not know. The
corpus is synthetic policies/procedures written **against the public NERC CIP
PDFs**, committable; the operator's private documents stay out entirely.

Each planted document declares, in a ``<!-- PLANT ... -->`` header, the register
Part it targets and its **control class** — one of:

    covered · hole · aspirational · lexical · applicability · temporal ·
    future_effective · implicit_change · tier_conflict · deontic · cross_reference

and the ground-truth coverage the engine SHOULD produce. The scorer reports
**Full-Gap recall** as the headline (a missed gap is what destroys trust);
false-covered and false-gap separately (never averaged); citation resolution
(must be 1.000); conflict / temporal / applicability precision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from portal.modules.compliance.core.text_signals import is_aspirational as _is_aspirational
from portal.modules.compliance.core.text_signals import keywords as _keywords

CORPUS_DIR = Path(__file__).resolve().parents[1] / "data" / "planted_corpus"

CONTROL_CLASSES = (
    "covered",
    "hole",
    "aspirational",
    "lexical",
    "applicability",
    "temporal",
    "future_effective",
    "implicit_change",
    "tier_conflict",
    "deontic",
    "cross_reference",
)

_PLANT_RE = re.compile(r"<!--\s*PLANT\s+(\{.*?\})\s*-->", re.S)


@dataclass
class PlantedDoc:
    path: Path
    doc_id: str
    doc_class: str  # policy | procedure | evidence
    targets: str  # register Part id
    control_class: str
    expected_coverage: str  # FULL | PARTIAL | NONE | NOT_APPLICABLE
    expected_signal: str  # "" | COMPLIANCE_CONFLICT | STALE
    sections: dict[str, str]  # section_id -> verbatim body

    @property
    def text(self) -> str:
        return self.path.read_text(encoding="utf-8")


def load_corpus(corpus_dir: Path | str = CORPUS_DIR) -> list[PlantedDoc]:
    import json

    out = []
    for p in sorted(Path(corpus_dir).glob("*.md")):
        body = p.read_text(encoding="utf-8")
        m = _PLANT_RE.search(body)
        if not m:
            continue
        meta = json.loads(m.group(1))
        sections = {
            sm.group(1): sm.group(2).strip()
            for sm in re.finditer(r"(?m)^##\s+(\S+)\s*\n(.*?)(?=^##\s|\Z)", body, re.S)
        }
        out.append(
            PlantedDoc(
                path=p,
                doc_id=meta["doc_id"],
                doc_class=meta.get("doc_class", "policy"),
                targets=meta["targets"],
                control_class=meta["control_class"],
                expected_coverage=meta.get("expected_coverage", "NONE"),
                expected_signal=meta.get("expected_signal", ""),
                sections=sections,
            )
        )
    return out


# ── deterministic proposer over the planted corpus ──────────────────────────
# _keywords / _is_aspirational moved to text_signals.py (TASK_COMPLIANCE_ENGINE_
# LANDING_V1 P2) so the real retrieval proposer shares the same substantive-
# overlap check instead of a drifting copy.


def make_proposer(corpus: list[PlantedDoc], *, threshold: int = 3):
    """A ``propose(node, side)`` that keyword-matches planted docs of the right
    class to a register node, and marks a span ``locatable`` when the section
    body substantively overlaps the requirement (not just names it)."""
    by_side = {"policy": "policy", "procedure": "procedure", "evidence": "evidence"}

    def propose(node, side: str) -> list[dict]:
        want_class = by_side[side]
        hits = []
        req_kw = _keywords(node.verbatim_text)
        for d in corpus:
            if d.doc_class != want_class or d.targets != node.id:
                continue
            for sec_id, body in d.sections.items():
                overlap = len(req_kw & _keywords(body))
                # substantive == the section actually restates the obligation,
                # not just names it and not aspirational hand-waving
                substantive = overlap >= threshold and not _is_aspirational(body)
                hits.append(
                    {
                        "document_id": d.doc_id,
                        "section_id": sec_id,
                        "span": body[:200],
                        "locatable": substantive,
                        "control_class": d.control_class,
                    }
                )
        return hits

    return propose


# ── scorer ─────────────────────────────────────────────────────────────────
_SIDE_FIELD = {
    "policy": "policy_spans",
    "procedure": "procedure_spans",
    "evidence": "evidence_spans",
}

# "temporal" plants a span that DOES substantively restate the obligation
# (it should qualify at the anchor/relevance layer) but cites a SUPERSEDED
# standard id — a different, separately-tested mechanism (cell.stale_citations)
# is what disqualifies it as CURRENT coverage, not the anchor/relevance layer.
# expected_coverage=="NONE" for this class describes the citation-staleness
# outcome, not "the text never qualified".
_CITATION_STALE_CLASSES = {"temporal"}


@dataclass
class PlantedScore:
    n_controls: int
    qualified_signal_recall: float  # headline (P1 replaces the old full_gap_recall)
    false_covered: int
    false_gap: int
    citation_resolution: float  # must be 1.000
    per_control: list[dict]

    def to_dict(self) -> dict:
        return {
            "n_controls": self.n_controls,
            "qualified_signal_recall": round(self.qualified_signal_recall, 3),
            "false_covered": self.false_covered,
            "false_gap": self.false_gap,
            "citation_resolution": round(self.citation_resolution, 3),
            "per_control": self.per_control,
        }


def score(corpus: list[PlantedDoc], matrix_cells: list) -> PlantedScore:
    """Compare the coverage matrix against each planted doc's declared truth.

    TASK_COMPLIANCE_REASONING_V2 P1: the automated classifier can no longer
    certify a ``FULL``/``NONE`` compliance VERDICT from textual presence or
    absence alone (F03) — obligation-atom comparison is P5 work. Every
    planted control now resolves ``UNRESOLVED``/``NEEDS_REVIEW`` regardless of
    ``expected_coverage``. What this suite still verifies mechanically is the
    signal a future P5 assessment will consume: did the retrieval/anchor/
    relevance layer correctly qualify (or correctly reject) THIS document's
    own span for its target Part — ``qualified_signal_recall`` replaces the
    old ``full_gap_recall`` as the headline for that reason. It is a
    retrieval-quality measure, not a compliance determination.

    ``false_covered``/``false_gap`` keep their original meaning and are now
    hard invariants rather than headline metrics: the classifier structurally
    cannot emit FULL/PARTIAL from automated candidates (false_covered), nor
    NONE from empty/unqualified ones (false_gap) — both must read 0, and a
    nonzero value here means the P1 protections regressed.
    """
    cell_by_req: dict[str, object] = {}
    for c in matrix_cells:
        cell_by_req.setdefault(c.requirement_id, c)

    signal_expected = signal_correct = 0
    false_covered = false_gap = 0
    cite_total = cite_ok = 0
    per: list[dict] = []

    for d in corpus:
        cell = cell_by_req.get(d.targets)
        got = cell.coverage if cell else "MISSING_FROM_MATRIX"
        exp = d.expected_coverage
        expect_qualified = exp in ("FULL", "PARTIAL") or d.control_class in _CITATION_STALE_CLASSES
        own_spans = (
            [
                s
                for s in getattr(cell, _SIDE_FIELD.get(d.doc_class, "policy_spans"), [])
                if s.get("document_id") == d.doc_id
            ]
            if cell
            else []
        )
        actually_qualified = any(s.get("locatable") for s in own_spans)

        signal_expected += 1
        signal_ok = actually_qualified == expect_qualified
        if signal_ok:
            signal_correct += 1

        if not expect_qualified and got in ("FULL", "PARTIAL"):
            false_covered += 1
        if expect_qualified and got == "NONE":
            false_gap += 1

        if cell:
            for s in own_spans:
                if not s.get("locatable"):
                    continue
                cite_total += 1
                cite_ok += int(
                    any(s["section_id"] in pd.sections for pd in corpus if pd.doc_id == d.doc_id)
                )

        per.append(
            {
                "doc": d.doc_id,
                "control_class": d.control_class,
                "targets": d.targets,
                "expected_coverage_legacy": exp,
                "expected_qualified_signal": expect_qualified,
                "actually_qualified_signal": actually_qualified,
                "got_coverage": got,
                "pass": signal_ok,
            }
        )

    return PlantedScore(
        n_controls=len(corpus),
        qualified_signal_recall=(signal_correct / signal_expected) if signal_expected else 1.0,
        false_covered=false_covered,
        false_gap=false_gap,
        citation_resolution=(cite_ok / cite_total) if cite_total else 1.0,
        per_control=per,
    )
