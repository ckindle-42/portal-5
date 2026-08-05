"""Platform-family checks: the platform agent-core inversion gate."""

from __future__ import annotations

from ._shared import REPO_ROOT
from .registry import register


@register("agent_core", "AO. agent core", order=39)
def check_agent_core() -> tuple[str, str, list[dict]]:
    """AO. Platform agent loop is core + inverted.

    (1) portal.platform.agent imports cleanly.
    (2) INVARIANT: no file under portal/platform/agent/ imports portal.modules.*
        (platform must not depend on any module).
    (3) Security's re-homed shim symbols still resolve at their historical paths.
    """
    import ast
    import importlib

    subs: list[dict] = []

    try:
        importlib.import_module("portal.platform.agent")
        subs.append({"name": "import portal.platform.agent", "status": "PASS", "detail": "ok"})
    except Exception as e:  # noqa: BLE001
        return ("FAIL", f"portal.platform.agent import failed: {e}", subs)

    root = REPO_ROOT / "portal" / "platform" / "agent"
    offenders: list[str] = []
    for f in root.rglob("*.py"):
        tree = ast.parse(f.read_text(), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                alias.name == "portal.modules" or alias.name.startswith("portal.modules.")
                for alias in node.names
            ):
                offenders.append(str(f.relative_to(root.parents[2])))
                break
            if (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and (node.module == "portal.modules" or node.module.startswith("portal.modules."))
            ):
                offenders.append(str(f.relative_to(root.parents[2])))
                break
    if offenders:
        subs.append(
            {"name": "inversion", "status": "FAIL", "detail": f"module imports: {offenders}"}
        )
        return ("FAIL", f"platform/agent must not import modules: {offenders}", subs)
    subs.append(
        {"name": "inversion (no portal.modules imports)", "status": "PASS", "detail": "clean"}
    )

    try:
        from portal.modules.security.core.decision_engine import select_tools  # noqa: F401
        from portal.modules.security.core.goal import EngagementGoal, validate_goal  # noqa: F401
        from portal.modules.security.core.goal_decide import decide_next_action  # noqa: F401

        subs.append({"name": "security shim symbols resolve", "status": "PASS", "detail": "ok"})
    except Exception as e:  # noqa: BLE001
        return ("FAIL", f"security shim symbols broken: {e}", subs)

    return ("PASS", "agent core inverted; security consumes it", subs)
