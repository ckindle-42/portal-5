"""Next WFE screens use current seats, existing suites, routed tags, and adequate windows."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from portal.platform.inference.model_cards import card_entry

REPO = Path(__file__).resolve().parents[3]
PLANS = {
    "auto-coding": REPO / "tests/wfe/plans/auto_coding_next_screen_20261019.yaml",
    "general-fast": REPO / "tests/wfe/plans/general_fast_k2_screen_20261019.yaml",
    "auto-daily": REPO / "tests/wfe/plans/auto_daily_quant_screen_20261019.yaml",
}


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _registered_in_routed_group(workspace: str, tag: str, backends: dict) -> bool:
    groups = set(backends["workspace_routing"][workspace])
    for backend in backends["backends"]:
        if backend.get("group") not in groups:
            continue
        models = backend.get("models") or []
        model_ids = {m.get("id") if isinstance(m, dict) else m for m in models}
        if tag in model_ids or tag in (backend.get("aliases") or {}):
            return True
    return False


def _window(tag: str) -> int:
    match = re.search(r"-ctx(\d+)k$", tag)
    if match:
        return int(match.group(1)) * 1024
    entry = card_entry(tag)
    return int(entry[1].get("max_context", 0)) if entry else 0


def test_each_next_screen_uses_the_current_seat_and_expected_suite():
    portal = _yaml(REPO / "config/portal.yaml")["workspaces"]
    expected = {
        "auto-coding": ("sandbox", "coding_production", 2),
        "general-fast": ("production", "general_production", 1),
        "auto-daily": ("production", "general_production", 1),
    }

    for workspace, path in PLANS.items():
        plan = _yaml(path)["workloads"][workspace]
        tool_mode, home, challengers = expected[workspace]
        assert plan["tool_mode"] == tool_mode
        assert plan["home"] == home
        assert portal[workspace]["model_hint"] in [
            plan["arms"]["incumbent"],
            *plan["arms"]["challengers"],
        ]
        assert len(plan["arms"]["challengers"]) == challengers
        assert (REPO / "tests/wfe/suites" / f"{home}.jsonl").is_file()


def test_every_next_screen_arm_is_registered_for_the_route_and_fits_context():
    portal = _yaml(REPO / "config/portal.yaml")["workspaces"]
    backends = _yaml(REPO / "config/backends.yaml")

    for workspace, path in PLANS.items():
        plan = _yaml(path)["workloads"][workspace]
        arms = [plan["arms"]["incumbent"], *plan["arms"]["challengers"]]
        for tag in arms:
            assert _registered_in_routed_group(workspace, tag, backends), (workspace, tag)
            assert _window(tag) >= portal[workspace]["context_limit"], (workspace, tag)


def test_production_suites_only_use_tools_authorized_by_the_workspace():
    modes = _yaml(REPO / "tests/wfe/tool_modes.yaml")["workspaces"]

    for workspace, path in PLANS.items():
        plan = _yaml(path)["workloads"][workspace]
        if plan["tool_mode"] != "production":
            continue
        suite_path = REPO / "tests/wfe/suites" / f"{plan['home']}.jsonl"
        tasks = [json.loads(line) for line in suite_path.read_text().splitlines()]
        required = {tool for task in tasks for tool in task.get("requires_tools", [])}
        assert required <= set(modes[workspace]["allow"]), (workspace, sorted(required))
