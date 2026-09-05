from __future__ import annotations

import pytest

from portal.modules.compliance.core.assessment import assess_atom
from portal.modules.compliance.core.boundary import BoundarySearch


def _atom(case_id: str) -> dict:
    return {
        "atom_id": f"TEST-{case_id}",
        "actor": "Responsible Entity",
        "modality": "SHALL",
        "action": "evaluate security patches",
        "object": "applicable cyber assets",
        "deadline_cadence": "within 35 calendar days",
        "source_anchor_ids": [f"gov-{case_id}"],
    }


def _candidate(case_id: str, *, deadline: str = "within 35 calendar days") -> dict:
    return {
        "actor": "Responsible Entity",
        "modality": "SHALL",
        "action": "evaluate security patches",
        "object": "applicable cyber assets",
        "deadline_cadence": deadline,
        "anchor_id": f"int-{case_id}",
    }


@pytest.mark.parametrize(
    "case_id", [f"A{i:02d}" for i in range(1, 31)], ids=[f"A{i:02d}" for i in range(1, 31)]
)
def test_adversarial_a_matrix(case_id):
    atom = _atom(case_id)
    mode = (int(case_id[1:]) - 1) % 4
    boundary = BoundarySearch(
        atom["atom_id"], [case_id, "patch evaluation cyber assets"], "test-index", "manifest", 1
    )
    if mode == 0:
        result = assess_atom(atom, [_candidate(case_id)], {"boundary": boundary})
        expected, forbidden, finding = "SUPPORTED", "ABSENT", None
    elif mode == 1:
        result = assess_atom(
            atom, [_candidate(case_id, deadline="within 60 calendar days")], {"boundary": boundary}
        )
        expected, forbidden, finding = "CONTRADICTED", "SUPPORTED", "CONTRADICTION"
    elif mode == 2:
        result = assess_atom(atom, [], {"boundary": boundary})
        expected, forbidden, finding = "ABSENT", "SUPPORTED", "GAP_ABSENT"
    else:
        result = assess_atom(
            atom, [], {"boundary": boundary, "truncated": True, "index_generation": "test-index"}
        )
        expected, forbidden, finding = "UNRESOLVED", "ABSENT", None
    assert result.determination == expected
    assert result.determination != forbidden
    assert result.governing_anchor_ids == [f"gov-{case_id}"]
    if expected in {"SUPPORTED", "CONTRADICTED"}:
        assert result.internal_anchor_ids == [f"int-{case_id}"]
    if expected == "ABSENT":
        assert result.boundary_proof_id.startswith("boundary-")
    if finding:
        assert finding in {"CONTRADICTION", "GAP_ABSENT"}


_Q_IDS = [
    f"Q{i:02d}-{variant}" for i in range(1, 13) for variant in ("complete", "counter", "missing")
]


@pytest.mark.parametrize("case_id", _Q_IDS, ids=_Q_IDS)
def test_q01_q12_three_variants(case_id):
    question, variant = case_id.split("-")
    atom = _atom(question)
    boundary = BoundarySearch(
        atom["atom_id"], [question, "patch evaluation cyber assets"], "test-index", "manifest", 1
    )
    if variant == "complete":
        result = assess_atom(atom, [_candidate(question)], {"boundary": boundary})
        claim = f"{question}: implementation satisfies the governing atom"
        assert result.determination == "SUPPORTED"
        assert result.internal_anchor_ids == [f"int-{question}"]
    elif variant == "counter":
        result = assess_atom(
            atom, [_candidate(question, deadline="within 60 calendar days")], {"boundary": boundary}
        )
        claim = f"{question}: internal deadline exceeds the governing maximum"
        assert result.determination == "CONTRADICTED"
        assert result.counterevidence_anchor_ids == [f"int-{question}"]
    else:
        result = assess_atom(
            atom, [], {"boundary": boundary, "truncated": True, "index_generation": "test-index"}
        )
        claim = f"{question}: retrieval did not reach its declared boundary"
        assert result.determination == "UNRESOLVED"
        assert result.unresolved_code == "U04_RETRIEVAL_INCOMPLETE"
        assert result.missing_fact["index_generation"] == "test-index"
    assert claim.startswith(question)
    assert result.governing_anchor_ids == [f"gov-{question}"]
