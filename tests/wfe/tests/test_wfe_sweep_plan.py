"""P5-A3: the sweep plan is generated from the candidate queue.

Incumbents come from the decision plans. A queued model is a challenger only in
an intended workspace that workspace_routing serves, and only when its ctxNk
window meets that workspace's context_limit.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.wfe import campaign
from tests.wfe import sweep_plan as sp

REPO = Path(__file__).resolve().parents[3]
PLAN = REPO / "tests" / "wfe" / "plans" / "sweep_from_queue_v1.yaml"


def _plan_file(directory: Path, name: str, workloads: dict) -> None:
    (directory / name).write_text(yaml.safe_dump({"workloads": workloads}))


def _seat(incumbent: str, home: str) -> dict:
    return {
        "tool_mode": "production",
        "home": home,
        "discovery": [],
        "arms": {"incumbent": incumbent, "challengers": ["not-from-the-queue"]},
    }


def test_a_candidate_is_placed_only_where_routing_and_window_allow(tmp_path):
    plans = tmp_path / "plans"
    plans.mkdir()
    _plan_file(
        plans, "data_decision_v1.yaml", {"auto-data": _seat("seat:ctx32k", "data_production")}
    )
    _plan_file(
        plans,
        "documents_decision_v1.yaml",
        {"auto-documents": _seat("docs-seat:ctx16k", "documents_production")},
    )
    queue = tmp_path / "queue.yaml"
    queue.write_text(
        yaml.safe_dump(
            {
                "models": {
                    "alias:ctx32k": {"available": True, "intended": ["auto-data"]},
                    "good:ctx32k": {"available": True, "intended": ["auto-data", "auto-documents"]},
                    "small:ctx8k": {"available": True, "intended": ["auto-data"]},
                    "nowindow": {"available": True, "intended": ["auto-data"]},
                    "foreign:ctx64k": {"available": True, "intended": ["auto-data"]},
                    "gone:ctx64k": {"available": False, "intended": ["auto-data"]},
                    "seat:ctx32k": {"available": True, "intended": ["auto-data"]},
                    "unplanned:ctx32k": {"available": True, "intended": ["auto-nowhere"]},
                }
            }
        )
    )
    backends = {
        "workspace_routing": {"auto-data": ["general"], "auto-documents": ["coding"]},
        "backends": [
            {
                "group": "general",
                "models": [
                    {"id": "good:ctx32k"},
                    {"id": "small:ctx8k"},
                    {"id": "nowindow"},
                    {"id": "gone:ctx64k"},
                    {"id": "seat:ctx32k"},
                ],
                "aliases": {"alias:ctx32k": "served-elsewhere"},
            },
            {"group": "coding", "models": [{"id": "other:ctx32k"}]},
        ],
    }
    portal = {
        "auto-data": {"context_limit": 32768},
        "auto-documents": {"context_limit": 16384},
        "auto-nowhere": {"context_limit": 8192},
    }
    plan, notes = sp.generate(queue, plans, backends, portal)
    assert plan["workloads"]["auto-data"]["arms"] == {
        "incumbent": "seat:ctx32k",
        "challengers": ["alias:ctx32k", "good:ctx32k"],
    }
    assert plan["workloads"]["auto-data"]["home"] == "data_production"
    assert "not-from-the-queue" not in str(plan)
    assert plan["workloads"]["auto-documents"]["arms"]["challengers"] == []
    assert "auto-nowhere" not in plan["workloads"]
    text = "\n".join(notes)
    assert "small:ctx8k left out: window 8192 < context_limit 32768" in text
    assert "nowindow left out: tag has no ctxNk window" in text
    assert "foreign:ctx64k left out: not served by auto-data's workspace_routing groups" in text
    assert "gone:ctx64k left out: unavailable" in text
    assert "seat:ctx32k left out: it is the incumbent" in text
    assert "unplanned:ctx32k left out: no decision-plan incumbent" in text
    assert "auto-documents: good:ctx32k left out: not served" in text
    assert any(n.startswith("auto-documents: no eligible queued challenger") for n in notes)
    again, again_notes = sp.generate(queue, plans, backends, portal)
    assert (plan, notes) == (again, again_notes)
    assert sp.render(plan, notes) == sp.render(again, again_notes)


def test_two_decision_plans_for_one_workspace_are_refused(tmp_path):
    plans = tmp_path / "plans"
    plans.mkdir()
    _plan_file(plans, "a_decision_v1.yaml", {"auto-data": _seat("one:ctx32k", "data_production")})
    _plan_file(plans, "b_decision_v1.yaml", {"auto-data": _seat("two:ctx32k", "data_production")})
    queue = tmp_path / "queue.yaml"
    queue.write_text(yaml.safe_dump({"models": {}}))
    with pytest.raises(ValueError, match="auto-data"):
        sp.generate(queue, plans, {"workspace_routing": {}, "backends": []}, {})


def test_the_checked_in_sweep_matches_the_generator_and_expands(monkeypatch):
    """Production allowlists are a pipeline-mode property, so the gap check is too."""
    monkeypatch.setattr(campaign, "ENGINE", "pipeline")
    plan, notes = sp.generate()
    assert PLAN.read_text() == sp.render(plan, notes)
    backends = yaml.safe_load((REPO / "config" / "backends.yaml").read_text())
    portal = yaml.safe_load((REPO / "config" / "portal.yaml").read_text())["workspaces"]
    queue = yaml.safe_load((REPO / "tests" / "wfe" / "candidate_queue.yaml").read_text())["models"]
    seats = sp.incumbents(REPO / "tests" / "wfe" / "plans")
    for ws, wl in plan["workloads"].items():
        assert wl["arms"]["incumbent"] == seats[ws]["incumbent"]
        assert wl["home"] == seats[ws]["home"]
        for model in wl["arms"]["challengers"]:
            assert ws in (queue[model].get("intended") or [])
            assert model in sp.servable(ws, backends)
            assert sp.window_tokens(model) >= portal[ws]["context_limit"]
    rows = campaign.expand_matrix(PLAN, 1, tier="screen")
    assert rows
    assert campaign.tool_gaps(rows) == []
    # Challengers carry card sampling, so the arm id is ``<tag>@card-<digest>``.
    models = {r.get("model") or r["arm"].split("@", 1)[0] for r in rows}
    for wl in plan["workloads"].values():
        assert wl["arms"]["incumbent"] in models
        for model in wl["arms"]["challengers"]:
            assert model in models
