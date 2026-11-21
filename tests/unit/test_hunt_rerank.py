from __future__ import annotations

from pathlib import Path
from typing import Any

from portal.modules.security.core.hunt.notables.judge_notables import CaseFacts, judge_cases
from portal.modules.security.core.hunt.notables.rerank import (
    _council_adjust,
    _council_budget,
    _fusion_order,
    _recall,
    _rule_name,
    case_order,
    judged_only_cases,
)
from portal.modules.security.core.hunt.notables.scoreboard import Notable


def _notable(index: int, p_yes: float | None, key: str = "") -> Notable:
    return Notable(index, "peer_rare", None, p_yes, key or f"k{index}")


def test_fusion_weight_zero_is_the_stage1_order():
    notables = [_notable(0, 0.1), _notable(1, 0.9), _notable(2, None)]
    assert _fusion_order(notables, 0.0) == [0, 1, 2]


def test_fusion_weight_one_is_p_yes_desc_with_unjudged_last():
    notables = [_notable(0, 0.1), _notable(1, 0.9), _notable(2, None), _notable(3, 0.5)]
    assert _fusion_order(notables, 1.0) == [1, 3, 0, 2]


def test_intermediate_fusion_pulls_high_p_yes_up_but_keeps_stage1_weight():
    notables = [_notable(i, 0.5) for i in range(4)]
    notables[3].p_yes = 0.99
    order = _fusion_order(notables, 0.5)
    assert order.index(3) < 3
    assert _rule_name(0.0) == "stage1" and _rule_name(1.0) == "p_yes"
    assert _rule_name(0.25) == "fusion_w0.25"


def test_recall_counts_steps_under_the_new_rank():
    cmap = {"stepA": {0, 5}, "stepB": {40}}
    rank_of = {0: 60, 5: 10, 40: 20}
    recall = _recall(cmap, rank_of)
    assert recall[50] == 2  # stepA via 5@10, stepB via 40@20
    assert recall[100] == 2
    rank_of = {0: 0, 5: 10, 40: 200}
    assert _recall(cmap, rank_of)[50] == 1


def test_council_adjust_support_rises_reject_sinks_within_k_only():
    notables = [_notable(i, 0.5, key=f"k{i}") for i in range(5)]
    order = [0, 1, 2, 3, 4]
    decisions = {"k0": "REJECT", "k1": "SUPPORT", "k2": "REVISE", "k3": "SUPPORT"}
    final, moved = _council_adjust(order, notables, decisions, 4)
    # within top4: SUPPORT (1,3) first, abstain (2) next, REJECT (0) last; index4 untouched
    assert final == [1, 3, 2, 0, 4]
    assert moved > 0
    assert final[4] == 4


def test_council_adjust_without_decisions_keeps_order():
    notables = [_notable(i, 0.5, key=f"k{i}") for i in range(3)]
    final, moved = _council_adjust([0, 1, 2], notables, {}, 3)
    assert final == [0, 1, 2] and moved == 0


def test_council_budget_is_what_the_deadline_buys_at_the_measured_rate():
    # 720 s at the live council rate (22.89 s/call, concurrency 2) buys 31 reviews
    assert _council_budget(100, 720.0, 22.8922) == 31
    assert _council_budget(5, 720.0, 22.8922) == 5
    assert _council_budget(100, 720.0, None) == 0
    assert _council_budget(100, 720.0, 0.0) == 0


def _answer(token: str) -> dict[str, Any]:
    return {
        "model": "seat",
        "choices": [
            {
                "message": {"content": token},
                "logprobs": {
                    "content": [
                        {
                            "token": token,
                            "top_logprobs": [
                                {"token": "yes", "logprob": -0.1 if token == "yes" else -2.3},
                                {"token": "no", "logprob": -2.3 if token == "yes" else -0.1},
                            ],
                        }
                    ]
                },
            }
        ],
        "usage": {"prompt_tokens": 10},
    }


class _Seat:
    """Yes for case value v1, no for v2, a transport failure for v3."""

    def complete(self, **request: Any) -> dict[str, Any]:
        content = str(request["messages"][0]["content"])
        if "v1" in content:
            return _answer("yes")
        if "v2" in content:
            return _answer("no")
        raise RuntimeError("down")


def _case(case_id: str, event: str, value: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "anchor_entity": value,
        "members": [{"type": "episode", "id": f"ep-{event}", "value": value}],
    }


def test_a_judged_only_view_excludes_unjudged_members() -> None:
    cases = [
        {
            "case_id": "c1",
            "members": [
                {"type": "episode", "value": "a", "unjudged": False},
                {"type": "signal", "value": "b", "unjudged": True},
                {"type": "signal", "value": "c", "unjudged": False},
            ],
            "unjudged": True,
        }
    ]
    view = judged_only_cases(cases)
    assert [member["value"] for member in view[0]["members"]] == ["a", "c"]
    assert all(not member["unjudged"] for member in view[0]["members"])
    assert len(cases[0]["members"]) == 3


def test_no_case_is_dropped_by_a_model_answer(tmp_path: Path) -> None:
    facts = CaseFacts(
        {"e1": ("v1", "ix:st"), "e2": ("v2", "ix:st"), "e3": ("v3", "ix:st")},
        {},
        {"ep-e1": ("e1",), "ep-e2": ("e2",), "ep-e3": ("e3",)},
    )
    cases = [_case("c1", "e1", "v1"), _case("c2", "e2", "v2"), _case("c3", "e3", "v3")]
    judged, receipt = judge_cases(
        cases,
        out=tmp_path,
        client=_Seat(),
        model="seat",
        facts=facts,
        notables={},
        request_budget=3,
    )
    assert sorted(case["case_id"] for case in judged) == ["c1", "c2", "c3"]
    assert receipt["judged"] == 2 and receipt["unjudged"] == 1
    assert judged[0]["p_yes"] > 0.5 and judged[1]["p_yes"] < 0.5
    assert judged[2]["p_yes"] is None and judged[2]["judge"]["reason"] == "request_failed"
    order = case_order(judged)
    assert sorted(order) == [0, 1, 2]
