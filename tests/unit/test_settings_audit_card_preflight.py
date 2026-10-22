"""Regression tests for seat screening's card-conformance audit rows."""

from tests.wfe import settings_audit as audit


def _card() -> dict:
    return {
        "qwen3.8": {
            "harness_policy": {"think": "false"},
            "recommended_sampling_modes": {
                "thinking": {"temperature": 1.0, "top_p": 0.95, "top_k": 20},
                "instruct": {"temperature": 0.7, "top_p": 0.8, "top_k": 20},
            },
            "recommended_max_output": 32768,
        }
    }


def test_think_policy_mismatch_warns_without_a_variant_override() -> None:
    rows: list[dict] = []

    audit._audit_think_vs_card_policy(
        "seat", {"think": True}, "qwen3.8-test", _card(), {"seat": {}}, rows
    )

    assert [(row["kind"], row["severity"]) for row in rows] == [("think_vs_card_policy", "WARN")]


def test_reasoned_variant_think_override_is_info() -> None:
    workspaces = {
        "seat": {"variants": {"think-on": {"think": True, "think_override_reason": "screen arm"}}}
    }
    rows: list[dict] = []

    audit._audit_think_vs_card_policy(
        "seat::think-on", {"think": True}, "qwen3.8-test", _card(), workspaces, rows
    )

    assert [(row["kind"], row["severity"]) for row in rows] == [("think_vs_card_policy", "INFO")]


def test_sampling_mode_mismatch_warns_for_the_opposite_think_mode() -> None:
    rows: list[dict] = []

    audit._audit_sampling_mode_mismatch(
        "seat",
        {"think": True, "temperature": 0.7, "top_p": 0.8, "top_k": 20},
        "qwen3.8-test",
        {},
        _card(),
        rows,
    )

    assert [(row["kind"], row["severity"]) for row in rows] == [("sampling_mode_mismatch", "WARN")]
    assert "instruct" in rows[0]["detail"]


def test_sampling_mode_matching_think_setting_is_clean() -> None:
    rows: list[dict] = []

    audit._audit_sampling_mode_mismatch(
        "seat",
        {"think": False, "temperature": 0.7, "top_p": 0.8, "top_k": 20},
        "qwen3.8-test",
        {},
        _card(),
        rows,
    )

    assert rows == []


def test_think_true_without_predict_limit_warns_when_card_has_output_budget() -> None:
    rows: list[dict] = []

    audit._audit_thinking_unbounded("seat", {"think": True}, "qwen3.8-test", _card(), rows)

    assert [(row["kind"], row["severity"]) for row in rows] == [("thinking_unbounded", "WARN")]
    assert "predict_limit" in rows[0]["detail"]


def test_explicit_predict_limit_or_missing_card_budget_is_clean() -> None:
    rows: list[dict] = []
    registry = _card()

    audit._audit_thinking_unbounded(
        "seat", {"think": True, "predict_limit": 32768}, "qwen3.8-test", registry, rows
    )
    audit._audit_thinking_unbounded("other", {"think": True}, "uncatalogued-model", registry, rows)

    assert rows == []
