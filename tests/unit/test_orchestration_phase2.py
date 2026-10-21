"""Offline tests for planner, reviewer, Telegram and calibration contracts."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from portal.modules.orchestration.calibration import calibration_status, project_remaining
from portal.modules.orchestration.contracts import parse_plan
from portal.modules.orchestration.planner import PLANNER_RULES, validate_planned_plan
from portal.modules.orchestration.service import _require_calibration
from portal.modules.orchestration.worker import check_output
from portal_channels.telegram.arm_bridge import ArmTelegramStore, send_outbox_once
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.runner import load_suite
from tests.wfe.schema import Outcome


def test_planner_prompt_includes_required_decomposition_rules() -> None:
    assert "deterministic acceptance check" in PLANNER_RULES
    assert "Split reading from acting" in PLANNER_RULES
    assert "stage='assembly' followed by stage='final_review'" in PLANNER_RULES


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_check", "deterministic check or review"),
        ("context_overflow", "exceeds Fast context budget"),
        ("mixed_access", "reading and acting"),
        ("missing_closure", "assembly and final_review"),
    ],
)
def test_planned_plan_rejects_phase2_contract_violations(mutation: str, message: str) -> None:
    plan = _valid_plan()
    if mutation == "missing_check":
        plan["bites"][0]["accept"] = []
    elif mutation == "context_overflow":
        plan["bites"][0]["budget"]["context_tokens"] = 16385
    elif mutation == "mixed_access":
        plan["bites"][0]["tools"] = ["file_read", "file_write"]
    else:
        plan["bites"][-1]["stage"] = "work"
    with pytest.raises(ValueError, match=message):
        validate_planned_plan(plan, _arm_config(), "test_fixing")


def test_planned_plan_accepts_review_only_bite_with_reason() -> None:
    plan = _valid_plan()
    work = plan["bites"][0]
    work["accept"] = []
    work["review"] = "deep"
    work["review_reason"] = "The output has no deterministic equivalence oracle."
    validated = validate_planned_plan(plan, _arm_config(), "test_fixing")
    assert validated.bites[0].review == "deep"


def test_wfe_planner_suite_is_backed_by_the_validator() -> None:
    root = Path(__file__).resolve().parents[2]
    suite = yaml.safe_load((root / "tests/wfe/orchestration/planner_suite.yaml").read_text())
    mutations = {
        "check-or-deep-review-reason": lambda plan: plan["bites"][0].update(accept=[]),
        "comfortable-fast-context": lambda plan: plan["bites"][0]["budget"].update(
            context_tokens=16385
        ),
        "separated-tool-purposes": lambda plan: plan["bites"][0].update(
            tools=["file_read", "file_write"]
        ),
        "assembly-then-final-review": lambda plan: plan["bites"][-1].update(stage="work"),
    }
    for case in suite["cases"]:
        raw = _valid_plan()
        mutation = mutations.get(case["rule"])
        if mutation:
            mutation(raw)
        if case["expected"] == "pass":
            validate_planned_plan(raw, _arm_config(), "test_fixing")
        else:
            with pytest.raises(ValueError):
                validate_planned_plan(raw, _arm_config(), "test_fixing")


def test_calibration_projects_remaining_probability_cost_and_pause() -> None:
    plan = parse_plan(
        {
            "task_id": "calibration",
            "goal": "check calibration",
            "bites": [_raw_bite("first", "fast"), _raw_bite("second", "deep")],
        }
    )
    rates = {
        "test_fixing": {
            "fast": {"pass_probability": 0.8, "mean_seconds": 4},
            "deep": {"pass_probability": 0.9, "mean_seconds": 5},
        }
    }
    projection = project_remaining(plan.bites, {"first"}, rates)
    assert projection.pass_probability == pytest.approx(0.9)
    assert projection.expected_seconds == pytest.approx(5)
    policy = {"minimum_pass_probability": 0.95, "rates_by_discipline": rates}
    projected, pause = calibration_status(policy, plan, {"first"})
    assert projected == projection and pause


def test_unattended_run_refuses_null_gate_c_threshold() -> None:
    with pytest.raises(ValueError, match="unattended runs are disabled"):
        _require_calibration({"calibration": {"minimum_pass_probability": None}}, True)
    _require_calibration({"calibration": {"minimum_pass_probability": None}}, False)


def test_wfe_checker_suite_rejects_plausible_wrong_outputs(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    suite = yaml.safe_load((root / "tests/wfe/orchestration/checker_suite.yaml").read_text())
    for case in suite["cases"]:
        raw = _raw_bite(case["id"], "fast")
        raw["accept"] = case.get("checks") or [
            {"type": "equals", "path": "$.answer", "value": "fixed"}
        ]
        raw["output"] = {
            "path": f"bites/{case['id']}.json",
            "schema": case.get("schema", {"type": "object"}),
        }
        bite = parse_plan(
            {"task_id": f"checker-{case['id']}", "goal": "Check output", "bites": [raw]}
        ).bites[0]
        result = check_output(bite, case["output"], tmp_path)
        schema_passed = not case.get("schema") or Draft202012Validator(case["schema"]).is_valid(
            case["output"]
        )
        assert (result.passed and schema_passed) is (case["expected"] == "pass")


def test_test_fixing_wfe_suite_uses_hidden_pytest(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    suite = load_suite(root / "tests/wfe/suites/orchestration_test_fixing.jsonl")
    solutions = {
        "arm-testfix-clamp": "def clamp(value, low, high):\n    return min(max(value, low), high)\n",
        "arm-testfix-percent": (
            "def percent(part, whole):\n"
            "    if whole == 0:\n        raise ValueError('whole must not be zero')\n"
            "    return part / whole * 100\n"
        ),
    }
    for task in suite:
        source = next(
            name for name in task["seed"] if name.endswith(".py") and not name.startswith("test_")
        )
        for label, text in (("reference", solutions[task["id"]]), ("seed", task["seed"][source])):
            sandbox = tmp_path / task["id"] / label
            sandbox.mkdir(parents=True)
            (sandbox / source).write_text(text, encoding="utf-8")
            result = apply_checkers(
                task,
                CheckContext(task=task, final_text="", tool_calls=[], sandbox_root=sandbox),
            )
            assert (result.outcome == Outcome.PASS) is (label == "reference")


@pytest.mark.parametrize(("decision", "expected"), [("approve", True), ("deny", False)])
def test_fake_telegram_bot_decision_round_trip(
    tmp_path: Path, decision: str, expected: bool
) -> None:
    store = ArmTelegramStore(tmp_path / "telegram.sqlite3")
    bot = _FakeBot()
    assert store.request_approval("task-a", "bite-a", "high-risk write") is None
    notice = store.outbox()[0]
    sent = asyncio.run(
        send_outbox_once(
            store,
            bot,
            {73},
            lambda request_id: {"callback_data": f"arm:{request_id}:{decision}"},
        )
    )
    assert sent == 1
    assert bot.messages[0]["chat_id"] == 73
    assert store.decide(notice.request_id, "approve", 99, {73}) is False
    assert store.decide(notice.request_id, decision, 73, {73}) is True
    assert store.request_approval("task-a", "bite-a", "high-risk write") is expected


class _FakeBot:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_message(self, **kwargs: Any) -> None:
        self.messages.append(kwargs)


def _valid_plan() -> dict[str, Any]:
    final = _raw_bite("final", "deep", stage="final_review", depends_on=["assembly"])
    final["accept"] = []
    final["review"] = "deep"
    final["review_reason"] = "Verify the final repair is complete."
    return {
        "task_id": "valid-plan",
        "goal": "Fix an incorrect function.",
        "bites": [
            _raw_bite("inspect", "fast", tools=["file_read"]),
            _raw_bite(
                "assembly", "fast", stage="assembly", tools=["file_write"], depends_on=["inspect"]
            ),
            final,
        ],
    }


def _raw_bite(
    bite_id: str,
    model: str,
    *,
    stage: str = "work",
    tools: list[str] | None = None,
    depends_on: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "bite_id": bite_id,
        "goal": f"Complete {bite_id}.",
        "discipline": "test_fixing",
        "inputs": [],
        "depends_on": depends_on or [],
        "tools": tools or [],
        "output": {"path": f"bites/{bite_id}.txt", "file_type": "text"},
        "accept": [{"type": "contains", "value": "done"}],
        "risk": "low",
        "stage": stage,
        "budget": {"turns": 2, "minutes": 2, "output_tokens": 128, "context_tokens": 512},
        "model": model,
        "procedure": "Use only the selected tool group.",
    }


def _arm_config() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    raw = yaml.safe_load((root / "config" / "orchestration_arm.yaml").read_text())
    return raw
