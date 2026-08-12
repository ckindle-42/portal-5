import json

from scripts import intent_eval


def test_security_loader_uses_only_comparable_scenarios(tmp_path, monkeypatch):
    monkeypatch.setattr(intent_eval, "SECURITY_CANDIDATES_DIR", tmp_path)
    payload = {
        "candidate": "candidate",
        "candidate_results": [
            {"scenario": "ok", "unique_coverage": 0.5, "lab_success": True},
            {"scenario": "blocked", "unique_coverage": 1.0, "lab_success": False},
        ],
        "incumbent_results": [
            {"scenario": "ok", "unique_coverage": 0.5},
            {"scenario": "blocked", "unique_coverage": 0.0},
        ],
        "deltas": [
            {"scenario": "ok", "unique_coverage_delta": 0.0},
            {"scenario": "__aggregate__", "unique_coverage_delta": 0.0},
        ],
    }
    (tmp_path / "cand_candidate_solo_20260812T000000Z.json").write_text(json.dumps(payload))

    [row] = intent_eval._load_candidate_eval_results()

    assert row["quality_score"] == 0.5
    assert row["incumbent_quality"] == 0.5
    assert row["native_delta"]["unique_coverage_delta"] == 0.0


def test_blocked_security_candidate_has_explicit_reason():
    candidate = next(iter(intent_eval.SECURITY_TOOL_TEMPLATE_BLOCKED))

    assert intent_eval._missing_result_note("security", candidate).startswith("BLOCKED")
    assert intent_eval._missing_result_note("general", candidate) == "no result row"
