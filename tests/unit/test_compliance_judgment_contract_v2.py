from __future__ import annotations

import json
from pathlib import Path

from tests.benchmarks.compliance_judgment_contract_v2 import (
    aggregate_v2,
    packet_ref_ids,
    packet_v2,
    parse_contract_object,
    parse_final_json,
    score_case_v2,
)


def _case(gold: str = "CONTRADICTED") -> dict:
    return {
        "id": "HOLD-1",
        "category": gold,
        "governing_ref": "CIP-007-6 R2 Part 2.2",
        "governing_text": "Evaluate security patches at least once every 35 days.",
        "premises": ["packet is complete"],
        "candidate_text": "The OT team evaluates patches every 21 days.",
        "packet_complete": True,
        "gold_label": gold,
        "gold_citation": ["CIP-007-6 R2 Part 2.2"],
    }


def _answer(determination: str, cited_refs: list[str] | None = None) -> str:
    return json.dumps(
        {
            "determination": determination,
            "finding_type": None,
            "cited_refs": cited_refs or ["CIP-007-6 R2 Part 2.2"],
            "rationale": "The packet says the schedule is within the stated maximum.",
        }
    )


def test_final_json_parser_rejects_reasoning_or_prose_wrapped_objects():
    valid = _answer("SUPPORTED")
    assert parse_final_json(valid) is not None
    assert parse_final_json("Let me think.\n" + valid) is None
    assert parse_final_json(valid + "\nThat is my answer.") is None
    assert parse_final_json("<think>" + valid + "</think>") is None


def test_contract_packet_exposes_exact_reference_ids_from_visible_fields():
    case = _case()
    packet = packet_v2(case)
    assert packet["source_refs"] == ["CIP-007-6 R2 Part 2.2"]
    assert packet_ref_ids(case) == packet["source_refs"]


def test_contract_preserves_exact_non_regulatory_slice_ids():
    case = _case()
    case["source_ref_ids"] = ["REQ-HOLD-01", "EVID-HOLD-01-A"]
    packet = packet_v2(case)
    assert packet["source_refs"] == [
        "CIP-007-6 R2 Part 2.2",
        "EVID-HOLD-01-A",
        "REQ-HOLD-01",
    ]


def test_contract_schema_rejects_string_null_and_missing_citations():
    bad_finding = json.loads(_answer("SUPPORTED"))
    bad_finding["finding_type"] = "null"
    assert not parse_contract_object(json.dumps(bad_finding))[1]
    bad_refs = json.loads(_answer("SUPPORTED"))
    bad_refs["cited_refs"] = "CIP-007-6 R2 Part 2.2"
    assert not parse_contract_object(json.dumps(bad_refs))[1]
    bad_determination = json.loads(_answer("SUPPORTED"))
    bad_determination["determination"] = 1
    assert not parse_contract_object(json.dumps(bad_determination))[1]


def test_literal_false_support_is_separate_from_invalid_output_penalty():
    case = _case("CONTRADICTED")
    literal = score_case_v2(case, _answer("SUPPORTED"))
    malformed_literal = json.loads(_answer("SUPPORTED"))
    malformed_literal["finding_type"] = "null"
    malformed_literal_score = score_case_v2(case, json.dumps(malformed_literal))
    invalid = score_case_v2(case, "not a JSON verdict")
    assert literal["literal_false_supported"]
    assert not literal["conservative_unresolved_penalty"]
    assert not malformed_literal_score["schema_ok"]
    assert malformed_literal_score["literal_false_supported"]
    assert not malformed_literal_score["conservative_unresolved_penalty"]
    assert not invalid["literal_false_supported"]
    assert invalid["conservative_unresolved_penalty"]


def test_insufficient_maps_to_abstain_but_invalid_packet_citation_does_not_pass():
    case = _case("ABSTAIN")
    abstain = score_case_v2(case, _answer("INSUFFICIENT"))
    assert abstain["pred"] == "ABSTAIN"
    assert abstain["correct"]
    invalid_citation = score_case_v2(
        _case("SUPPORTED"), _answer("SUPPORTED", ["premise mentioning CIP-007-6 R2 Part 2.2"])
    )
    assert not invalid_citation["citation_ok"]
    assert invalid_citation["off_packet_citations"]


def test_v2_aggregate_keeps_errors_conservative_without_calling_them_false_support():
    cases = [_case("CONTRADICTED"), _case("ABSTAIN")]
    rows = [
        score_case_v2(cases[0], "failed call"),
        score_case_v2(cases[1], _answer("INSUFFICIENT")),
    ]
    aggregate = aggregate_v2(cases, rows)
    assert aggregate["conservative_unresolved_penalty_count"] == 1
    assert aggregate["literal_false_supported_count"] == 0
    assert aggregate["confusion"]["fn"] == 1


def test_frozen_holdout_has_checkable_labels_and_exact_packet_citations():
    path = Path(__file__).parents[1] / "compliance_probe" / "judgment_probe_holdout_v1.jsonl"
    cases = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert len(cases) == 21
    assert len({case["id"] for case in cases}) == len(cases)
    assert {case["category"] for case in cases} == {
        "missing_applicability",
        "incomplete_packet",
        "complete_absence",
        "conflicting_evidence",
        "stricter_adequate",
        "counterevidence",
        "resolvable_slice_citation",
    }
    scores = []
    for case in cases:
        assert set(case["gold_citation"]).issubset(packet_ref_ids(case))
        answer = json.dumps(
            {
                "determination": case["gold_label"],
                "finding_type": "CONTRADICTION" if case["gold_label"] == "CONTRADICTED" else None,
                "cited_refs": case["gold_citation"],
                "rationale": case["gold_rationale"],
            }
        )
        score = score_case_v2(case, answer)
        assert score["schema_ok"] and score["correct"] and score["citation_ok"]
        scores.append(score)
    aggregate = aggregate_v2(cases, scores)
    assert aggregate["schema_valid_rate"] == 1.0
    assert aggregate["citation_ok_rate"] == 1.0
