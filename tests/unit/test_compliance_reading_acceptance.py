"""Workstream G — the reading-architecture acceptance suite (IMPLEMENTATION_BRIEF §7).

Hermetic: no network, no real Ollama. Each of the 26 seed cases builds a
synthetic ``GoverningBundle``/``CandidateSet``/``CorpusSnapshot`` from the
controlled fixture texts in ``tests/data/compliance_reading_acceptance.json``
and injects a deterministic three-stage transport that answers the alignment,
council and report system prompts with the JSON the case's EXPECTED semantics
imply. That proves routing, contracts, arithmetic, projection, persistence and
serialization — not semantic capability.

Known production gaps (the spec expects a code the landed path cannot yet
emit) are carried as ``blocked`` checks named in ``KNOWN_GAPS`` rather than
silently weakened; ``scripts/verify_compliance_reading_acceptance.py`` prints
them in its table.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from portal.modules.compliance.core import assessment_runs
from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.assessment import assess_part
from portal.modules.compliance.core.assessment_report import _REPORT_SYSTEM
from portal.modules.compliance.core.assessment_source import (
    resolve_governing_bundle,
)
from portal.modules.compliance.core.council import _OVERRIDE_SYSTEM, _SEAT_SYSTEM
from portal.modules.compliance.core.determination import (
    AssessmentContext,
    AssessmentRequest,
    AssessmentResult,
    CandidateRecord,
    CandidateSet,
    CorpusSnapshot,
    GoverningBundle,
    ScenarioEdit,
    ScenarioOverlay,
    SourceSlice,
)
from portal.modules.compliance.core.obligation_alignment import _ALIGNMENT_SYSTEM, align_part
from portal.modules.compliance.core.operations import ProposePackage, judge, propose
from portal.modules.compliance.core.reading import READING_SYSTEM
from portal.modules.compliance.core.repository import Repository

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "tests/data/compliance_reading_acceptance.json"
MANIFEST: dict[str, Any] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
FIXTURES: dict[str, dict[str, Any]] = MANIFEST["controlled_fixtures"]
CASES: dict[str, dict[str, Any]] = {c["id"]: c for c in MANIFEST["cases"]}
QUALIFICATION: dict[str, dict[str, Any]] = {h["id"]: h for h in MANIFEST["qualification_controls"]}

SEATS: list[dict[str, str]] = [
    {"id": "m1", "label": "a", "model": "m1"},
    {"id": "m2", "label": "b", "model": "m2"},
    {"id": "m3", "label": "c", "model": "m3"},
]
KB_ID = "compliance_acceptance"

#: (case id, check name) -> the production gap that makes the spec check fail.
#: Empty now that U03/U04/U10/U12 are emitted by the landed assessment path; any
#: entry here is a real, named regression rather than a grandfather.
KNOWN_GAPS: dict[tuple[str, str], str] = {}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── synthetic request assembly ──────────────────────────────────────────────


def build_scope(case: dict[str, Any]) -> AssetScope:
    if case["scope"] == "derived":
        return AssetScope(
            impact_present={"high", "medium"},
            associated_present={"bcs"},
            has_erc=True,
            has_control_center=True,
            declared_by="derived:corpus",
        )
    return AssetScope(
        impact_present={"high", "medium"},
        associated_present={"bcs"},
        has_erc=True,
        has_control_center=True,
        declared_by="operator:acceptance",
    )


def build_candidate(label: str, *, corrupt_hash: bool = False) -> CandidateRecord:
    fixture = FIXTURES[label]
    text = fixture["text"]
    digest = "0" * 64 if corrupt_hash else _sha(text)
    slice_obj = SourceSlice(
        slice_id=f"cand-{label}",
        ref=fixture["document_id"],
        document_id=fixture["document_id"],
        revision_hash=digest,
        chunk_id=fixture["chunk_id"],
        locator=fixture["section"],
        text=text,
        char_start=0,
        char_end=len(text),
        role="candidate",
    )
    return CandidateRecord(
        candidate_id=label,
        document_id=fixture["document_id"],
        chunk_id=fixture["chunk_id"],
        text=text,
        locator=fixture["section"],
        revision_hash=digest,
        char_start=0,
        char_end=len(text),
        source_slice=slice_obj,
    )


def build_snapshot(case: dict[str, Any]) -> CorpusSnapshot:
    completeness = {"complete": "COMPLETE", "partial": "PARTIAL", "unknown": "UNKNOWN"}[
        case["boundary"]
    ]
    return CorpusSnapshot(
        snapshot_id=f"acpt-{case['id']}",
        kb_id=KB_ID,
        acquisition_mode="EXPLICIT_SET",
        completeness=completeness,
        fingerprint=_sha(f"snapshot|{case['id']}|{completeness}"),
    )


def build_request(
    case: dict[str, Any],
    *,
    corrupt_hashes: tuple[str, ...] = (),
    candidate_order: list[str] | None = None,
) -> AssessmentRequest:
    governing = resolve_governing_bundle(case["requirement_id"])
    labels = candidate_order or [c["label"] for c in case["candidates"]]
    records = [build_candidate(label, corrupt_hash=label in corrupt_hashes) for label in labels]
    return AssessmentRequest(
        requirement_id=case["requirement_id"],
        kb_id=KB_ID,
        org_id="acceptance",
        scope=build_scope(case),
        scope_basis="conditional" if case["scope"] == "conditional" else "actual",
        effective_on=MANIFEST["effective_on"],
        governing=governing,
        snapshot=build_snapshot(case),
        candidate_set=CandidateSet(
            records=records,
            acquisition_receipt={
                "acquisition_mode": "EXPLICIT_SET",
                "boundary_receipt": {
                    "complete": case["boundary"] == "complete",
                    "eligible_sections": [r.chunk_id for r in records],
                    "examined_sections": [r.chunk_id for r in records],
                    "document_revision_hashes": {r.document_id: r.revision_hash for r in records},
                    "omissions": [],
                    "acquisition_mode": "EXPLICIT_SET",
                },
            },
        ),
    )


# ── the deterministic three-stage transport ────────────────────────────────


class FakeTransport:
    """Answers alignment, council, override and report prompts deterministically.

    One instance serves a whole case. For proposal cases it switches between
    the base and virtual specs based on the candidate ids the packet carries:
    a proposed slice id (``...:proposed`` / ``...#proposed-...``) selects the
    virtual semantics.
    """

    def __init__(self, case: dict[str, Any]) -> None:
        self.case = case
        self.calls: list[tuple[str, str, str]] = []
        self.alignment_packets: list[str] = []
        self.council_packets: list[str] = []
        self.report_packets: list[str] = []
        self.reading_packets: list[str] = []
        self.council_raises = case.get("mode") == "council_invalid"

    # -- dispatch -----------------------------------------------------------
    def __call__(self, model: str, system: str, user: str) -> str:
        self.calls.append((model, system, user))
        if system == _ALIGNMENT_SYSTEM:
            self.alignment_packets.append(user)
            return self._alignment(user)
        if system == _SEAT_SYSTEM:
            if self.council_raises:
                raise TimeoutError("controlled seat timeout")
            self.council_packets.append(user)
            return self._council(model, user)
        if system == READING_SYSTEM:
            self.reading_packets.append(user)
            return self._reading(user)
        if system == _REPORT_SYSTEM:
            self.report_packets.append(user)
            return self._report(user)
        if system == _OVERRIDE_SYSTEM:
            return json.dumps(
                {"overrides": False, "exception_ref": None, "rationale": "no overriding exception"}
            )
        return "{}"

    # -- helpers ------------------------------------------------------------
    def _active(self, user: str) -> dict[str, Any]:
        virtual = self.case.get("virtual")
        if virtual and (":proposed" in user or "#proposed" in user):
            return virtual
        return self.case

    @staticmethod
    def _relations(active: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {c["label"]: c for c in active.get("candidates", [])}

    def _alignment(self, user: str) -> str:
        if self.case.get("alignment_invalid"):
            return json.dumps({"records": []})
        active = self._active(user)
        try:
            packet = json.loads(user)
        except json.JSONDecodeError:
            packet = {}
        gov_ids = packet.get("governing", {}).get("selectable_slice_ids", [])
        gov_id = gov_ids[0] if gov_ids else "gov-missing"
        relations = self._relations(active)
        bindings = active.get("bindings", {})
        records = []
        for candidate in packet.get("candidates", []):
            cid = candidate["candidate_id"]
            spec = relations.get(cid, {"relation": "DIFFERENT"})
            slice_ids = candidate.get("selectable_slice_ids", [])
            cand_slice = slice_ids[0] if slice_ids else None
            record: dict[str, Any] = {
                "candidate_id": cid,
                "relation": spec.get("relation", "DIFFERENT"),
                "source_function": spec.get("source_function", "OPERATIVE_COMMITMENT"),
                "population_overlap": spec.get("population_overlap", "OVERLAPPING"),
                "governing_slice_ids": [gov_id],
                "candidate_slice_ids": [cand_slice] if cand_slice else [],
                "activity": "controlled activity",
                "object": "controlled object",
                "trigger": "controlled trigger",
                "population": "controlled population",
                "rationale": "controlled acceptance alignment",
                "missing_facts": spec.get("missing_facts", []),
            }
            binding = bindings.get(cid)
            if binding and cand_slice:
                record["constraint_bindings"] = [
                    {
                        "governing_slice_id": gov_id,
                        "candidate_slice_id": cand_slice,
                        "governing_quantity": {
                            "value": 35,
                            "unit": "day",
                            "qualifier": "calendar",
                        },
                        "internal_quantity": {
                            "value": binding["value"],
                            "unit": binding["unit"],
                            "qualifier": binding["qualifier"],
                        },
                        "constraint_kind": binding["kind"],
                        "direction": binding["direction"],
                        "rationale": "controlled acceptance binding",
                    }
                ]
            records.append(record)
        return json.dumps({"records": records})

    def _council(self, model: str, user: str) -> str:
        active = self._active(user)
        per_seat = self.case.get("council_votes") or {}
        decision = (
            per_seat.get(model) or active.get("council") or self.case.get("council") or "ABSENT"
        )
        same = [
            label
            for label, spec in self._relations(active).items()
            if spec.get("relation") == "SAME"
        ]
        cited = same[:2] if decision in ("SUPPORTED", "PARTIAL", "CONTRADICTED") else []
        return json.dumps(
            {
                "determination": decision,
                "finding_type": self.case.get("finding_type", ""),
                "cited_refs": cited,
                "confidence": 0.9,
                "rationale": "controlled acceptance seat",
            }
        )

    def _reading(self, user: str) -> str:
        """Simulate one reading pass, derived from the case's own report spec.

        No case expectation is edited or added: the duties are projected from
        the ``covered`` and ``gaps`` the fixture already declares, so this
        stands in for what a model reading both sides would return. A covered
        commitment becomes a COVERED duty; a gap becomes a duty that is PARTIAL
        (weaker or contradicted) or MISSING (an omission).
        """
        active = self._active(user)
        spec = active.get("report") or self.case.get("report")
        if not spec:
            return "{}"
        try:
            packet = json.loads(user)
        except json.JSONDecodeError:
            packet = {}
        gov_ids = packet.get("governing", {}).get("selectable_slice_ids", [])
        gov_id = gov_ids[0] if gov_ids else "gov-missing"
        candidate_slices = {
            c.get("candidate_id"): list(c.get("selectable_slice_ids", []))
            for c in packet.get("candidates", [])
        }

        duties: list[dict[str, Any]] = []
        gaps: list[dict[str, Any]] = []
        for index, entry in enumerate(spec.get("covered", []), start=1):
            internal = [
                slice_id
                for label in entry["internal"]
                for slice_id in candidate_slices.get(label, [])
            ]
            if not internal:
                continue
            duties.append(
                {
                    "duty_id": f"d{index}",
                    "statement": entry["commitment"],
                    "finding": "COVERED",
                    "governing_slice_ids": [gov_id],
                    "candidate_slice_ids": internal,
                }
            )
        for index, item in enumerate(spec.get("gaps", []), start=len(duties) + 1):
            counter = [
                slice_id
                for label in item.get("counter", [])
                for slice_id in candidate_slices.get(label, [])
            ]
            duty_id = f"d{index}"
            duties.append(
                {
                    "duty_id": duty_id,
                    "statement": item["missing_commitment"],
                    "finding": "MISSING" if item["kind"] == "OMISSION" else "PARTIAL",
                    "governing_slice_ids": [gov_id],
                    "candidate_slice_ids": counter,
                }
            )
            gaps.append(
                {
                    "duty_id": duty_id,
                    "gap_id": item["gap_id"],
                    "kind": item["kind"],
                    "missing_commitment": item["missing_commitment"],
                    "governing_slice_ids": [gov_id],
                    "internal_counterevidence_slice_ids": counter,
                    "boundary_proof_id": (
                        (packet.get("allowed_boundary_proof_ids") or [""])[0]
                        if item["kind"] == "OMISSION"
                        else item.get("boundary_proof_id", "")
                    ),
                }
            )
        return json.dumps(
            {
                "documentary_coverage": spec["documentary_coverage"],
                "duties": duties,
                "gaps": gaps,
                "uncertainties": spec.get("uncertainties", []),
            }
        )

    def _report(self, user: str) -> str:
        active = self._active(user)
        spec = active.get("report") or self.case.get("report")
        if not spec:
            return "{}"
        try:
            packet = json.loads(user)
        except json.JSONDecodeError:
            packet = {}
        gov_ids = packet.get("governing", {}).get("governing_slice_ids", [])
        gov_id = gov_ids[0] if gov_ids else "gov-missing"
        candidate_slices: dict[str, list[str]] = {}
        for operative in packet.get("operative_commitments", []):
            candidate_slices[operative["candidate_ref"]] = list(
                operative.get("candidate_slice_ids", [])
            )
        covered = []
        for entry in spec.get("covered", []):
            internal = [
                slice_id
                for label in entry["internal"]
                for slice_id in candidate_slices.get(label, [])
            ]
            if not internal:
                continue
            covered.append(
                {
                    "commitment": entry["commitment"],
                    "governing_slice_ids": [gov_id for _ in entry.get("governing", [])] or [gov_id],
                    "internal_slice_ids": internal,
                }
            )
        gaps = []
        for item in spec.get("gaps", []):
            counter = [
                slice_id
                for label in item.get("counter", [])
                for slice_id in candidate_slices.get(label, [])
            ]
            gaps.append(
                {
                    "gap_id": item["gap_id"],
                    "kind": item["kind"],
                    "missing_commitment": item["missing_commitment"],
                    "governing_slice_ids": [gov_id],
                    "internal_counterevidence_slice_ids": counter,
                    "boundary_proof_id": (
                        (packet.get("allowed_boundary_proof_ids") or [""])[0]
                        if item["kind"] == "OMISSION"
                        else item.get("boundary_proof_id", "")
                    ),
                }
            )
        return json.dumps(
            {
                "documentary_coverage": spec["documentary_coverage"],
                "covered": covered,
                "gaps": gaps,
                "uncertainties": spec.get("uncertainties", []),
            }
        )


# ── case execution ──────────────────────────────────────────────────────────


@dataclass
class CaseOutcome:
    case: dict[str, Any]
    result: Any
    transport: FakeTransport | None = None
    repo: Repository | None = None
    error: str = ""


def run_case(
    case: dict[str, Any],
    repo: Repository,
    *,
    candidate_order: list[str] | None = None,
) -> CaseOutcome:
    """Execute one seed case through the shared service (or proposal path)."""
    mode = case["mode"]
    if mode == "missing_governing":
        bad_ref = f"{case['requirement_id']} (unresolvable)"
        run_id = repo.create_run(
            {"requirements": [bad_ref], "kb_id": KB_ID}, status="RUNNING", org_id="acceptance"
        )
        results = assessment_runs.assess_requirements_now(
            [bad_ref],
            kb_id=KB_ID,
            scope=build_scope(case),
            effective_on=MANIFEST["effective_on"],
            repository=repo,
            run_id=run_id,
        )
        return CaseOutcome(case=case, result=results[0], repo=repo)

    if mode in ("proposal_validate", "proposal_fail"):
        return _run_proposal(case, repo)

    request = build_request(
        case,
        corrupt_hashes=("B22",) if mode == "hash_mismatch" else (),
        candidate_order=candidate_order,
    )
    transport = FakeTransport(case)
    context = AssessmentContext(
        repository=repo,
        seats=SEATS,
        quorum=0.66,
        seat_fn=transport,
        kb_id=KB_ID,
    )
    result = assess_part(request, context)
    return CaseOutcome(case=case, result=result, transport=transport, repo=repo)


def _run_proposal(case: dict[str, Any], repo: Repository) -> CaseOutcome:
    base = build_request(case)
    transport = FakeTransport(case)
    context = AssessmentContext(
        repository=repo, seats=SEATS, quorum=0.66, seat_fn=transport, kb_id=KB_ID
    )
    virtual = case["virtual"]
    target = base.candidate_set.by_id(virtual["target"])
    assert target is not None and target.text
    if case["mode"] == "proposal_validate":
        edit = ScenarioEdit(
            operation="REPLACE",
            target_document=target.document_id,
            chunk_id=target.chunk_id,
            char_start=0,
            char_end=len(target.text),
            expected_old_hash=_sha(target.text),
            new_text=virtual["replacement_text"],
        )
    else:
        edit = ScenarioEdit(
            operation="ADD",
            target_document=target.document_id,
            target_section="L22-proposed",
            chunk_id="L22#proposed-0",
            new_text=virtual["replacement_text"],
        )
    overlay = ScenarioOverlay(base_snapshot_fingerprint=base.snapshot.fingerprint, edits=[edit])
    package = propose(
        case["requirement_id"],
        ["evaluation cadence"],
        virtual["replacement_text"],
        overlay=overlay,
        context=context,
        request=base,
    )
    return CaseOutcome(case=case, result=package, transport=transport, repo=repo)


# ── checks ──────────────────────────────────────────────────────────────────


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    blocked: str = ""


def _packet_facts(transport: FakeTransport | None) -> tuple[set[str], dict[str, str], set[str]]:
    if transport is None or not transport.council_packets:
        return set(), {}, set()
    try:
        packet = json.loads(transport.council_packets[-1])
    except json.JSONDecodeError:
        return set(), {}, set()
    core = {c.get("commitment_id", "") for c in packet.get("candidates", [])}
    binds = {b.get("link_id", ""): b.get("result", "") for b in packet.get("binding_outcomes", [])}
    excluded = {e.get("candidate_ref", "") for e in packet.get("excluded", [])}
    return core, binds, excluded


def _slice_refs(result: AssessmentResult) -> tuple[set[str], set[str]]:
    covered = {sid for c in result.covered for sid in c.internal_slice_ids}
    covered |= {sid for c in result.covered for sid in c.governing_slice_ids}
    gaps = {sid for g in result.gaps for sid in g.internal_counterevidence_slice_ids}
    gaps |= {sid for g in result.gaps for sid in g.governing_slice_ids}
    return covered, gaps


def evaluate_checks(case: dict[str, Any], outcome: CaseOutcome) -> list[Check]:
    cid = case["id"]
    exp = case["expected"]
    if outcome.error:
        return [Check("runner", False, outcome.error)]
    if case["mode"] in ("proposal_validate", "proposal_fail"):
        return _proposal_checks(case, outcome)

    result: AssessmentResult = outcome.result
    core, binds, excluded = _packet_facts(outcome.transport)
    covered_ids, gap_ids = _slice_refs(result)
    checks: list[Check] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append(Check(name, ok, detail, KNOWN_GAPS.get((cid, name), "")))

    verdict_ok = (
        result.documentary_coverage == exp["documentary_coverage"]
        and result.coverage == exp["coverage"]
        and bool(result.substantively_resolved) == bool(exp["substantively_resolved"])
    )
    add(
        "verdict",
        verdict_ok,
        f"documentary={result.documentary_coverage} coverage={result.coverage} "
        f"resolved={result.substantively_resolved} "
        f"expected={exp['documentary_coverage']}/{exp['coverage']}/{exp['substantively_resolved']}",
    )

    def _in_core(label: str) -> bool:
        # commitment_id is the human document name (e.g. "B22.txt"); match by
        # substring so a label ("B22") resolves.
        return any(label in c for c in core)

    for label in exp.get("required_citations", []):
        present = _in_core(label) or f"cand-{label}" in covered_ids or f"cand-{label}" in gap_ids
        add(f"required:{label}", present, f"{label} absent from the packet and the projection")

    for label in exp.get("forbidden_citations", []):
        absent = (
            not _in_core(label)
            and f"cand-{label}" not in covered_ids
            and f"cand-{label}" not in gap_ids
            and label not in binds
        )
        add(
            f"forbidden:{label}", absent, f"{label} was admitted as substantive/arithmetic evidence"
        )

    kinds = [g.kind for g in result.gaps]
    ids = [g.gap_id for g in result.gaps]
    add(
        "gap_kinds",
        kinds == exp.get("gap_kinds", []),
        f"got {kinds}, expected {exp.get('gap_kinds', [])}",
    )
    add("gap_ids", ids == exp.get("gap_ids", []), f"got {ids}, expected {exp.get('gap_ids', [])}")

    for item in exp.get("arithmetic", []):
        got = binds.get(item["candidate"], "<missing>")
        add(
            f"arithmetic:{item['candidate']}",
            got == item["result"],
            f"got {got}, expected {item['result']}",
        )

    if exp.get("no_v_arithmetic"):
        add("no_decoy_arithmetic", "V" not in binds, "a decoy produced a quantity comparison")

    if exp.get("false_pairs"):
        add(
            "false_pairs",
            not binds and set(exp["forbidden_citations"]).issubset(excluded | core),
            f"binding_outcomes={binds}",
        )

    if exp.get("expected_code"):
        add(
            "code",
            result.unresolved_code == exp["expected_code"],
            f"got {result.unresolved_code or '<none>'}, expected {exp['expected_code']}",
        )

    if exp.get("not_full_or_partial"):
        add(
            "not_resolved",
            result.documentary_coverage not in ("FULL", "PARTIAL"),
            f"documentary={result.documentary_coverage}",
        )

    if cid == "15":
        add(
            "no_partial_fallback",
            result.documentary_coverage == "UNRESOLVED" and not result.substantively_resolved,
            f"documentary={result.documentary_coverage} resolved={result.substantively_resolved}",
        )

    if exp.get("missing_scope_declaration"):
        add(
            "missing_scope_declaration",
            bool(result.missing_fact.get("missing_scope_declaration")),
            f"missing_fact={result.missing_fact}",
        )

    if exp.get("governing_preservation"):
        checks.append(_governing_preservation(outcome.transport))

    return checks


def _governing_preservation(transport: FakeTransport | None) -> Check:
    if transport is None or not transport.council_packets:
        return Check("governing_preservation", False, "no captured council packet")
    packet = json.loads(transport.council_packets[-1])
    unit = packet.get("governing_unit", {})
    text = str(unit.get("verbatim_text", ""))
    constraint = str(unit.get("constraint", {}).get("text", ""))
    subject = str(unit.get("subject", {}).get("text", ""))
    ok = (
        "Part 2.3" in text
        and "CIP Senior Manager" in text
        and "or delegate" in text
        and constraint != "or delegate."
        and subject.lower() != "cip senior manager"
    )
    return Check(
        "governing_preservation",
        ok,
        f"verbatim_len={len(text)} constraint={constraint[:60]!r} subject={subject!r}",
    )


def _proposal_checks(case: dict[str, Any], outcome: CaseOutcome) -> list[Check]:
    cid = case["id"]
    exp = case["expected"]
    package: ProposePackage = outcome.result
    checks: list[Check] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append(Check(name, ok, detail, KNOWN_GAPS.get((cid, name), "")))

    add(
        "proposal_status",
        package.status == exp["proposal_status"],
        f"got {package.status}, expected {exp['proposal_status']}",
    )
    before = package.before.documentary_coverage if package.before else "<none>"
    add(
        "before",
        before == exp["documentary_coverage"],
        f"got {before}, expected {exp['documentary_coverage']}",
    )
    after = package.rejudged.documentary_coverage if package.rejudged else "<none>"
    add(
        "after",
        after == exp["virtual_coverage"],
        f"got {after}, expected {exp['virtual_coverage']}",
    )
    if case["mode"] == "proposal_validate":
        add("virtual_fingerprint", bool(package.virtual_fingerprint), "no virtual fingerprint")
        add("closes_gap", "g10" in package.closed_gaps, f"closed_gaps={package.closed_gaps}")
    else:
        add(
            "closes_fields",
            list(package.closes_fields) == list(exp.get("closes_fields", [])),
            f"closes_fields={package.closes_fields}",
        )
        add("failed_validation", package.status == "FAILED_VALIDATION", f"status={package.status}")
    return checks


# ── tests ───────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def repo_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("reading-acceptance")


@pytest.mark.parametrize("cid", list(CASES))
def test_case(cid: str, repo_dir: Path, tmp_path: Path) -> None:
    case = CASES[cid]
    repo = Repository(tmp_path / f"case-{cid}.db")
    outcome = run_case(case, repo)
    checks = evaluate_checks(case, outcome)
    hard = [c for c in checks if not c.blocked]
    assert hard, f"case {cid} produced no evaluable checks"
    failures = [c for c in hard if not c.ok]
    assert not failures, "; ".join(f"{c.name}: {c.detail}" for c in failures)


def test_missing_governing_is_u02(repo_dir: Path, tmp_path: Path) -> None:
    outcome = run_case(CASES["21"], Repository(tmp_path / "u02.db"))
    result: AssessmentResult = outcome.result
    assert result.documentary_coverage == "UNRESOLVED"
    assert result.unresolved_code == "U02_MISSING_GOVERNING_SOURCE"
    assert result.missing_fact


def test_alignment_invalid_no_longer_gates_the_verdict(repo_dir: Path, tmp_path: Path) -> None:
    """Slice P3 removed the pre-reading alignment veto (U09). An invalid
    alignment diagnostic cannot unresolved the Part; the verdict belongs to
    the reading pass — which, in this fixture, has no canned response, so the
    honest outcome is the reading contract failure (U11), not a gate code."""
    outcome = run_case(CASES["24"], Repository(tmp_path / "u09.db"))
    result: AssessmentResult = outcome.result
    assert result.unresolved_code == "U11_ASSESSMENT_CONTRACT_FAILED"
    assert not result.substantively_resolved
    # the failed diagnostic is still retained and labeled
    assert result.receipt.get("alignment_valid") is False
    assert result.receipt.get("alignment_diagnostic") is True


def test_needs_review_is_not_full_or_partial(repo_dir: Path, tmp_path: Path) -> None:
    outcome = run_case(CASES["16"], Repository(tmp_path / "nr.db"))
    result: AssessmentResult = outcome.result
    assert result.documentary_coverage == "NEEDS_REVIEW"
    assert result.coverage == "NEEDS_REVIEW"
    assert not result.substantively_resolved


def test_gold_and_verdicts_never_reach_the_reader() -> None:
    """The alignment reader is sealed from any gold label or approved verdict."""
    banned = ("gold", "expected_verdict", "approved_verdict", "documentary_coverage")
    for cid, case in CASES.items():
        transport = FakeTransport(case)
        request = build_request(case) if case["mode"] not in ("missing_governing",) else None
        if request is not None:
            context = AssessmentContext(seats=SEATS, quorum=0.66, seat_fn=transport)
            align_part(request, context)
        for user in transport.alignment_packets:
            low = user.lower()
            for token in banned:
                assert token not in low, f"case {cid} reader packet leaked {token!r}"
        for user in transport.council_packets:
            assert "gold" not in user.lower(), f"case {cid} council packet leaked 'gold'"


def test_required_and_forbidden_citations_are_routed(repo_dir: Path, tmp_path: Path) -> None:
    outcome = run_case(CASES["02"], Repository(tmp_path / "cites.db"))
    core, binds, excluded = _packet_facts(outcome.transport)
    assert all(any(label in c for c in core) for label in ("A22", "B22"))
    assert "V" in excluded and "V" not in binds


@pytest.mark.parametrize("cid", [f"{n:02d}" for n in range(2, 21)])
def test_candidate_order_does_not_change_the_verdict(cid: str, tmp_path: Path) -> None:
    case = CASES[cid]
    reversed_order = list(reversed(case["candidate_order"]))
    outcome = run_case(case, Repository(tmp_path / f"rev-{cid}.db"), candidate_order=reversed_order)
    hard = [c for c in evaluate_checks(case, outcome) if not c.blocked]
    failures = [c for c in hard if not c.ok]
    assert not failures, f"reversed order changed case {cid}: " + "; ".join(
        f"{c.name}: {c.detail}" for c in failures
    )


def test_v_multitopic_and_sentence_forms_produce_no_arithmetic(tmp_path: Path) -> None:
    """Case 02 with V's multi-topic paragraph and its sentence separately
    anchored must not introduce VA arithmetic in either form."""
    v_text = FIXTURES["V"]["text"]
    sentence = (
        "Vulnerability assessments shall be performed at least once every 15 calendar months."
    )

    def make(label: str, text: str) -> CandidateRecord:
        return CandidateRecord(
            candidate_id=label,
            document_id="CIP-010-policy",
            chunk_id=label,
            text=text,
            source_slice=SourceSlice(
                slice_id=f"cand-{label}",
                ref="CIP-010-policy",
                document_id="CIP-010-policy",
                revision_hash=_sha(text),
                chunk_id=label,
                text=text,
                char_start=0,
                char_end=len(text),
                role="candidate",
            ),
        )

    case = dict(CASES["02"])
    case["candidates"] = [
        {"label": "A22", "relation": "SAME"},
        {"label": "B22", "relation": "SAME"},
        {"label": "V", "relation": "DIFFERENT"},
        {"label": "V_sentence", "relation": "DIFFERENT"},
    ]
    request = AssessmentRequest(
        requirement_id=CASES["02"]["requirement_id"],
        kb_id=KB_ID,
        org_id="acceptance",
        scope=build_scope(CASES["02"]),
        scope_basis="actual",
        effective_on=MANIFEST["effective_on"],
        governing=resolve_governing_bundle(CASES["02"]["requirement_id"]),
        snapshot=build_snapshot(CASES["02"]),
        candidate_set=CandidateSet(
            records=[
                make("A22", FIXTURES["A22"]["text"]),
                make("B22", FIXTURES["B22"]["text"]),
                make("V", v_text),
                make("V_sentence", sentence),
            ]
        ),
    )
    transport = FakeTransport(case)
    context = AssessmentContext(
        repository=Repository(tmp_path / "v-split.db"),
        seats=SEATS,
        quorum=0.66,
        seat_fn=transport,
    )
    result = assess_part(request, context)
    assert result.documentary_coverage == "FULL"
    _, binds, _ = _packet_facts(transport)
    assert "V" not in binds and "V_sentence" not in binds


# ── A01–A11 architecture regressions ────────────────────────────────────────


def test_a01_route_parity(repo_dir: Path, tmp_path: Path) -> None:
    for cid in ("02", "10"):
        case = CASES[cid]
        repo = Repository(tmp_path / f"a01-{cid}.db")
        direct = run_case(case, repo)
        request = build_request(case)
        context = AssessmentContext(
            repository=repo, seats=SEATS, quorum=0.66, seat_fn=FakeTransport(case)
        )
        # the gaps route and the analyze adapter share engine + input fingerprint
        second = assess_part(request, context)
        assert direct.result.engine_version == second.engine_version
        assert direct.result.input_fingerprint == second.input_fingerprint
        assert direct.result.documentary_coverage == second.documentary_coverage
        determination = judge(
            case["requirement_id"],
            scope=request.scope,
            seats=SEATS,
            context=context,
            request=build_request(case),
        )
        assert determination.documentary_coverage == direct.result.documentary_coverage
        assert determination.assessment_id


def test_a02_governing_preservation(repo_dir: Path, tmp_path: Path) -> None:
    outcome = run_case(CASES["20"], Repository(tmp_path / "a02.db"))
    check = _governing_preservation(outcome.transport)
    assert check.ok, check.detail


def test_a03_replacement_consistency(repo_dir: Path, tmp_path: Path) -> None:
    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.core.scenarios import evaluate_scenario, new_scenario

    case = CASES["25"]
    repo = Repository(tmp_path / "a03.db")
    base = build_request(case)
    transport = FakeTransport(case)
    context = AssessmentContext(repository=repo, seats=SEATS, quorum=0.66, seat_fn=transport)
    target = base.candidate_set.by_id("L22")
    overlay = ScenarioOverlay(
        base_snapshot_fingerprint=base.snapshot.fingerprint,
        edits=[
            ScenarioEdit(
                operation="REPLACE",
                target_document=target.document_id,
                chunk_id=target.chunk_id,
                char_start=0,
                char_end=len(target.text),
                expected_old_hash=_sha(target.text),
                new_text=case["virtual"]["replacement_text"],
            )
        ],
    )
    package = propose(
        case["requirement_id"], ["cadence"], "", overlay=overlay, context=context, request=base
    )
    scenario = new_scenario(case["requirement_id"], "", "replacement", overlay=overlay)
    evaluated = evaluate_scenario(
        scenario,
        Register.load(),
        base.scope,
        MANIFEST["effective_on"],
        context=AssessmentContext(
            repository=repo, seats=SEATS, quorum=0.66, seat_fn=FakeTransport(case)
        ),
        request=base,
    )
    assert evaluated.get("virtual_fingerprint") == package.virtual_fingerprint
    assert evaluated["coverage_before"] == "PARTIAL"
    assert evaluated["coverage_after"] == "FULL"


def test_a04_no_self_certified_draft(repo_dir: Path, tmp_path: Path) -> None:
    from portal.modules.compliance.core.change_pipeline import draft_revisions

    case = CASES["26"]
    repo = Repository(tmp_path / "a04.db")
    base = build_request(case)
    edit = ScenarioEdit(
        operation="ADD",
        target_document="fixture:L22",
        target_section="L22-proposed",
        chunk_id="L22#proposed-0",
        new_text=case["virtual"]["replacement_text"],
    )
    failed = ProposePackage(
        target_ref=case["requirement_id"],
        replacement_text="",
        status="FAILED_VALIDATION",
        closes_fields=[],
        rejudged=None,
        weakens=["proposal does not close the gap"],
        diff_against_current="",
    )
    impact = {
        "impact_rows": [
            {
                "classification": "work",
                "changed_part": case["requirement_id"],
                "new_span": "Evaluate patches every 35 calendar days.",
                "old_span": "Evaluate patches every 40 calendar days.",
                "change_type": "TIGHTENED",
                "mapped_sections": [
                    {"document_id": "fixture:L22", "section_id": "L22", "prior_coverage": "PARTIAL"}
                ],
            }
        ]
    }
    out = draft_revisions(
        impact,
        context=AssessmentContext(
            repository=repo, seats=SEATS, quorum=0.66, seat_fn=FakeTransport(case)
        ),
        requests_by_part={case["requirement_id"]: base},
        edits_by_section={("fixture:L22", "L22"): edit},
        propose_fn=lambda *a, **k: failed,
    )
    assert out["n_failed_validation"] == 1
    assert out["n_validated"] == 0
    assert out["specifications"][0]["reassessment"]["status"] == "FAILED_VALIDATION"


def test_a05_scope_parity(repo_dir: Path, tmp_path: Path) -> None:
    derived = dict(CASES["02"])
    derived["scope"] = "derived"
    out = run_case(derived, Repository(tmp_path / "a05-derived.db"))
    assert out.result.documentary_coverage == "FULL"
    assert out.result.coverage == "UNRESOLVED"
    assert out.result.missing_fact.get("missing_scope_declaration")

    confirmed = run_case(CASES["02"], Repository(tmp_path / "a05-confirmed.db"))
    assert confirmed.result.documentary_coverage == "FULL"
    assert confirmed.result.coverage == "FULL"
    assert confirmed.result.substantively_resolved


def test_a06_source_selection_integrity(repo_dir: Path, tmp_path: Path) -> None:
    case = CASES["02"]
    request = build_request(case)

    class OffPacket(FakeTransport):
        """A reading whose only support is a slice id that is not in the packet.

        The property under test is unchanged by the move to the reading
        architecture: a verdict may never rest on a citation the application
        cannot resolve against its own pinned sources. What changed is where it
        is enforced — the reading pass verifies its own citations, so the
        forged support is named and the verdict cannot stand on it.
        """

        def _reading(self, user: str) -> str:
            return json.dumps(
                {
                    "documentary_coverage": "FULL",
                    "duties": [
                        {
                            "duty_id": "d1",
                            "statement": "forged support",
                            "finding": "COVERED",
                            "governing_slice_ids": ["gov-missing"],
                            "candidate_slice_ids": ["off-packet-slice"],
                        }
                    ],
                    "gaps": [],
                    "uncertainties": [],
                }
            )

    transport = OffPacket(case)
    context = AssessmentContext(
        repository=Repository(tmp_path / "a06.db"), seats=SEATS, quorum=0.66, seat_fn=transport
    )
    result = assess_part(request, context)
    assert not result.substantively_resolved
    assert result.documentary_coverage == "UNRESOLVED"
    assert result.unresolved_code == "U11_ASSESSMENT_CONTRACT_FAILED"
    # and the forged id is named rather than silently dropped
    assert any("off-packet-slice" in u.reason for u in result.uncertainties)


def test_a07_run_specific_provenance(repo_dir: Path, tmp_path: Path) -> None:
    repo = Repository(tmp_path / "a07.db")
    full = run_case(CASES["02"], repo)
    partial = run_case(CASES["10"], repo)
    full_run = full.result.run_id
    partial_run = partial.result.run_id
    assert full_run and partial_run and full_run != partial_run
    full_rows = repo.assessments_for_run(full_run)
    partial_rows = repo.assessments_for_run(partial_run)
    assert [r["documentary_coverage"] for r in full_rows] == ["FULL"]
    assert [r["documentary_coverage"] for r in partial_rows] == ["PARTIAL"]
    assert repo.get_assessment(full.result.assessment_id)["documentary_coverage"] == "FULL"


def test_a08_asynchronous_execution(
    repo_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "a08.db"
    repo = Repository(path)
    monkeypatch.setattr(assessment_runs, "_REPO_FACTORY", lambda: Repository(path))
    calls: list[str] = []

    def fake_execute(repo_, run_id, request, runtime):
        for requirement in request["requirements"]:
            calls.append(requirement)
            repo_.record_assessment(
                AssessmentResult(
                    assessment_id=f"aid-{requirement}",
                    run_id=run_id,
                    engine_version="test",
                    input_fingerprint="fp",
                    requirement_id=requirement,
                    applicability="APPLIES",
                    documentary_coverage="FULL",
                    coverage="FULL",
                    substantively_resolved=True,
                )
            )

    monkeypatch.setattr(assessment_runs, "_execute_run", fake_execute)
    run_id = assessment_runs.start_run({"requirements": ["A", "B"], "kb_id": KB_ID})
    import time

    deadline = time.time() + 10
    while time.time() < deadline:
        if repo.get_run(run_id)["status"] in assessment_runs.TERMINAL_STATES:
            break
        time.sleep(0.005)
    payload = assessment_runs.run_result(run_id)
    assert payload["status"] == "COMPLETE"
    assert payload["assessment_ids"] == ["aid-A", "aid-B"]
    before = list(calls)
    assessment_runs.run_status(run_id)
    assessment_runs.run_result(run_id)
    assert calls == before, "status/result must not re-run model work"


def test_a09_absence_receipts(repo_dir: Path, tmp_path: Path) -> None:
    complete = run_case(CASES["12"], Repository(tmp_path / "a09-complete.db"))
    assert complete.result.documentary_coverage == "NONE"
    incomplete = run_case(CASES["13"], Repository(tmp_path / "a09-incomplete.db"))
    assert incomplete.result.documentary_coverage == "UNRESOLVED"
    assert incomplete.result.documentary_coverage != "NONE"


def test_a10_qualification_controls(tmp_path: Path) -> None:
    # H1/H2/H3: the aggregation routes categorical relations and keeps a weaker
    # same-duty constraint, without letting equal quantities imply identity.
    h1 = QUALIFICATION["H1"]
    assert h1["expected_relation"] == "SAME"
    h2 = QUALIFICATION["H2"]
    assert h2["expected_relation"] == "DIFFERENT"
    h3 = QUALIFICATION["H3"]
    assert h3["expected_relation"] == "SAME"

    def run(left: str, right: str, relation: str, binding: dict[str, Any] | None) -> Any:
        governing = GoverningBundle(
            ref="H-control",
            part_text=left,
            source_slices=[
                SourceSlice(
                    slice_id="gov-h",
                    ref="H",
                    document_id="H",
                    revision_hash=_sha(left),
                    chunk_id="H",
                    text=left,
                    role="governing",
                )
            ],
        )
        candidate = CandidateRecord(
            candidate_id="right",
            document_id="H-right",
            chunk_id="H-right",
            text=right,
            source_slice=SourceSlice(
                slice_id="cand-h",
                ref="H-right",
                document_id="H-right",
                revision_hash=_sha(right),
                chunk_id="H-right",
                text=right,
                role="candidate",
            ),
        )
        request = AssessmentRequest(
            requirement_id="H-control",
            governing=governing,
            candidate_set=CandidateSet(records=[candidate]),
        )

        class Seat:
            def __call__(self, model, system, user):
                return json.dumps(
                    {
                        "records": [
                            {
                                "candidate_id": "right",
                                "relation": relation,
                                "population_overlap": "OVERLAPPING",
                                "governing_slice_ids": ["gov-h"],
                                "candidate_slice_ids": ["cand-h"],
                                "constraint_bindings": [binding] if binding else [],
                            }
                        ]
                    }
                )

        return align_part(request, AssessmentContext(seats=SEATS, quorum=0.66, seat_fn=Seat()))

    result = run(h1["left"], h1["right"], "SAME", None)
    assert result.records[0].relation == "SAME"
    result = run(h2["left"], h2["right"], "DIFFERENT", None)
    assert result.records[0].relation == "DIFFERENT"
    result = run(h3["left"], h3["right"], "SAME", None)
    assert result.records[0].relation == "SAME"

    # H4: an approval date alone never produces OUTDATED_LANGUAGE.
    h4 = QUALIFICATION["H4"]
    case = dict(CASES[h4["fixture"]])
    case["metadata"] = h4["metadata"]
    outcome = run_case(case, Repository(tmp_path / "h4.db"))
    assert outcome.result.documentary_coverage == h4["expected_documentary_coverage"]
    assert [g.kind for g in outcome.result.gaps] == h4["expected_gap_kinds"]


def test_a11_dependent_annotation_invalidation() -> None:
    from portal.modules.compliance.core.gate import _governing_cu

    complete = resolve_governing_bundle(CASES["20"]["requirement_id"])
    truncated = resolve_governing_bundle(CASES["20"]["requirement_id"])
    truncated.part_text = "or delegate."
    truncated.source_slices = [
        SourceSlice(
            slice_id=s.slice_id,
            ref=s.ref,
            document_id=s.document_id,
            revision_hash=_sha("or delegate."),
            chunk_id=s.chunk_id,
            text="or delegate.",
            role=s.role,
        )
        for s in truncated.source_slices[:1]
    ]
    from portal.modules.compliance.core.assessment_source import _bundle_fingerprint

    truncated.fingerprint = _bundle_fingerprint(truncated.source_slices)
    assert complete.fingerprint != truncated.fingerprint
    cu = _governing_cu(complete, complete.ref, "Responsible Entity", None)
    assert "Part 2.3" in cu["constraint"]["text"]
    assert cu["constraint"]["text"] != "or delegate."
    assert "CIP Senior Manager" in cu["constraint"]["text"]
