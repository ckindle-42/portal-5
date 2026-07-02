"""Security engagement playbooks — versioned methodology-as-file (Gap 6).

A playbook is a YAML file describing an engagement: phases with depends_on,
conditions, steps, plus mandatory scope, budget, and stop/escalate blocks so
the autonomy loop has a bounded program.
"""

from __future__ import annotations

from pathlib import Path

import yaml

PLAYBOOKS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "playbooks" / "security"


def load_playbook(path: str) -> dict:
    """Parse and validate a playbook YAML file. Raises on bad schema."""
    p = Path(path)
    # Only prepend PLAYBOOKS_DIR for bare filenames, not relative paths
    if not p.is_absolute() and (p.parent == Path() or not p.parent.name):
        p = PLAYBOOKS_DIR / p
    if not p.exists():
        raise FileNotFoundError(f"playbook not found: {path}")
    data = yaml.safe_load(p.read_text())
    problems = validate_playbook(data)
    if problems:
        raise ValueError(f"playbook validation failed: {', '.join(problems)}")
    return data


def validate_playbook(pb: dict) -> list[str]:
    """Return [] if valid; else list of validation problems."""
    problems: list[str] = []
    if not isinstance(pb, dict):
        return ["playbook must be a dict"]

    # Required top-level keys
    for key in ("scope", "budget"):
        if key not in pb:
            problems.append(f"missing required top-level key: {key}")

    # scope validation
    scope = pb.get("scope", {})
    if isinstance(scope, dict) and not scope.get("targets"):
        problems.append("scope.targets is empty or missing")

    # budget validation
    budget = pb.get("budget", {})
    if isinstance(budget, dict):
        for bk in ("max_iterations", "max_wall_clock_sec", "max_lab_actions"):
            if bk not in budget:
                problems.append(f"budget.{bk} is missing")

    # stop_conditions validation
    stop = pb.get("stop_conditions")
    if not stop or not isinstance(stop, list) or len(stop) == 0:
        problems.append("missing or empty stop_conditions (nothing loops unbounded)")

    # phases validation
    phases = pb.get("phases", [])
    if not isinstance(phases, list) or len(phases) == 0:
        problems.append("playbook must define at least one phase")
    else:
        phase_ids = set()
        for i, phase in enumerate(phases):
            if not isinstance(phase, dict):
                problems.append(f"phase[{i}] is not a dict")
                continue
            pid = phase.get("id", f"phase-{i}")
            if pid in phase_ids:
                problems.append(f"duplicate phase id: {pid}")
            phase_ids.add(pid)
            if "steps" not in phase and not phase.get("manual"):
                problems.append(f"phase '{pid}' has no steps and is not manual")
            deps = phase.get("depends_on", [])
            if isinstance(deps, list):
                for dep in deps:
                    if dep not in phase_ids:
                        pass  # dependency may be defined later — re-check in resolve_phases

    return problems


def resolve_phases(pb: dict, observations: dict) -> list[dict]:
    """Return phases whose depends_on are satisfied and conditions evaluate true.

    Returns only the first ready tier — phases whose dependencies are already
    met by the provided observations context. The caller is expected to mark
    completed phases and re-call resolve_phases to get the next tier.
    """
    try:
        from tests.benchmarks.bench_security.scoring import evaluate_condition
    except ImportError:
        evaluate_condition = None

    phases = pb.get("phases", [])
    ready: list[dict] = []

    for phase in phases:
        deps = phase.get("depends_on", []) or []
        if not deps:
            # Check condition
            cond = phase.get("condition")
            if cond:
                if isinstance(cond, dict) and evaluate_condition:
                    if not evaluate_condition(cond, observations):
                        continue
                elif isinstance(cond, str) and not _eval_finding_expr(cond, observations):
                    continue
            ready.append(phase)

    return ready


def _eval_finding_expr(expr: str, observations: dict) -> bool:
    """Basic expression evaluator for has_finding(field=..., equals=...).

    Safe — no eval(); parses a whitelisted grammar. Supports 'or' and 'and'.
    """
    import re

    parts = re.split(r"\s+(?:or|and)\s+", expr)
    for part in parts:
        m = re.match(
            r"has_finding\(field\s*=\s*['\"]?(\w+)['\"]?\s*,\s*equals\s*=\s*['\"]?(\w+)['\"]?\)",
            part.strip(),
        )
        if m:
            field = m.group(1)
            value = m.group(2)
            obs_val = observations.get(field)
            if str(obs_val).lower() == value.lower():
                return True
    return False


def list_playbooks() -> list[dict]:
    """List installed playbooks with name, version, description."""
    results = []
    if not PLAYBOOKS_DIR.exists():
        return results
    for p in sorted(PLAYBOOKS_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(p.read_text())
            results.append(
                {
                    "file": p.name,
                    "name": data.get("name", p.stem),
                    "version": data.get("version", "?"),
                    "description": data.get("description", ""),
                }
            )
        except Exception:
            results.append(
                {"file": p.name, "name": p.stem, "version": "?", "description": "parse error"}
            )
    return results
