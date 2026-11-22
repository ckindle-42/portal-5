"""Stage 0 preflight: ground-truth checks before any scenario runs.

Invokes the repo's own preflight CLIs (execute_preflight, routing_regression,
`portal trace`, lab_ready) and audits exposure gaps plus security-sweep report
freshness. Everything here is read-only against the repo; the subprocesses are
the only side-effect-free probes.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .config import Discovery, Settings, discover
from .models import QATResult, Status

PREFLIGHT_SCRIPT = "scripts/execute_preflight.py"
ROUTING_SCRIPT = "scripts/routing_regression.py"
LAB_SCRIPT = "scripts/lab_ready.py"
TRACE_SECTIONS = ("host", "containers", "pins", "engines", "platform")
SUBPROCESS_TIMEOUT_S = 900


def run_cmd(cmd: list[str], cwd: Path, timeout_s: int = SUBPROCESS_TIMEOUT_S) -> tuple[int, str]:
    """Run a repo CLI, returning its complete combined output."""
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout_s)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 124, f"subprocess failed: {exc}"
    return proc.returncode, proc.stdout + proc.stderr


def retired_aliases(repo_root: Path) -> list[str]:
    """The retired-alias vocabulary owned by scripts/execute_preflight.py,
    extracted from its AST so this package never hardcodes a second copy."""
    source = (repo_root / PREFLIGHT_SCRIPT).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", "") == "RETIRED_ALIASES" for t in node.targets
        ):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                return []
            return [str(a) for a in value] if isinstance(value, list) else []
    return []


def retired_alias_guard(repo_root: Path, discovery: Discovery) -> QATResult:
    """No retired alias may appear in any live roster QAT addresses."""
    retired = set(retired_aliases(repo_root))
    if not retired:
        return QATResult("p0-retired-aliases", Status.SKIP, "RETIRED_ALIASES not extractable")
    rosters: dict[str, tuple[str, ...]] = {
        "workspaces": tuple(discovery.workspaces),
        "presets": tuple(discovery.presets),
        "personas": tuple(p.slug for p in discovery.personas),
    }
    hits = [f"{roster}:{rid}" for roster, ids in rosters.items() for rid in ids if rid in retired]
    if hits:
        return QATResult(
            "p0-retired-aliases",
            Status.FAIL,
            f"retired aliases in live roster: {', '.join(hits[:8])}",
        )
    return QATResult(
        "p0-retired-aliases", Status.PASS, f"{len(retired)} retired aliases, none in live rosters"
    )


def run_preflight_script(settings: Settings) -> QATResult:
    rc, out = run_cmd([sys.executable, PREFLIGHT_SCRIPT, "--json"], settings.repo_root)
    if rc != 0:
        return QATResult("p0-execute-preflight", Status.FAIL, f"exit {rc}: {out[-300:]}")
    try:
        counts = json.loads(out[out.index("{") : out.rindex("}") + 1])
    except (ValueError, SyntaxError):
        return QATResult("p0-execute-preflight", Status.WARN, "non-JSON output")
    prod = counts.get("production_workspaces", [])
    personas = counts.get("personas", [])
    return QATResult(
        "p0-execute-preflight",
        Status.PASS,
        f"workspaces={len(prod)} personas={len(personas)}",
        evidence={"counts": {k: len(v) if isinstance(v, list) else v for k, v in counts.items()}},
    )


def run_routing_regression(settings: Settings) -> QATResult:
    rc, out = run_cmd([sys.executable, ROUTING_SCRIPT, "--assert-baseline"], settings.repo_root)
    status = Status.PASS if rc == 0 else Status.FAIL
    detail = out.strip().splitlines()[-1] if out.strip() else f"exit {rc}"
    return QATResult("p0-routing-baseline", status, detail[:300])


def run_trace_sections(settings: Settings) -> QATResult:
    cmd = [sys.executable, "-m", "portal.platform.inference.cli", "trace", "--json"]
    for section in TRACE_SECTIONS:
        cmd.extend(["--section", section])
    rc, out = run_cmd(cmd, settings.repo_root)
    try:
        payload = json.loads(out[out.index("{") : out.rindex("}") + 1])
        sections = payload.get("sections", [])
    except (ValueError, TypeError):
        return QATResult("p0-portal-trace", Status.FAIL, "portal trace returned invalid JSON")
    present = {str(section.get("key", "")) for section in sections if isinstance(section, dict)}
    failed, warned = [], []
    for section in sections:
        if not isinstance(section, dict):
            continue
        key = str(section.get("key", "unknown"))
        for hop in section.get("hops", []):
            if not isinstance(hop, dict):
                continue
            label = f"{key}/{hop.get('name', 'unknown')}"
            if str(hop.get("status", "")).upper() == "FAIL":
                failed.append(label)
            elif str(hop.get("status", "")).upper() == "WARN":
                warned.append(label)
    missing = sorted(set(TRACE_SECTIONS) - present)
    status = Status.FAIL if rc != 0 or failed else Status.WARN if warned or missing else Status.PASS
    problems = [f"failed: {', '.join(failed)}"] if failed else []
    problems.extend([f"warned: {', '.join(warned)}"] if warned else [])
    problems.extend([f"missing sections: {', '.join(missing)}"] if missing else [])
    detail = "; ".join(problems) or f"{len(present)} trace sections clean"
    return QATResult(
        "p0-portal-trace",
        status,
        f"{detail}; exit={rc}",
        evidence={
            "requested_sections": list(TRACE_SECTIONS),
            "present_sections": sorted(present),
            "missing_sections": missing,
            "failed_hops": failed,
            "warned_hops": warned,
            "exit_code": rc,
        },
    )


def run_lab_ready(settings: Settings) -> QATResult:
    rc, out = run_cmd([sys.executable, LAB_SCRIPT], settings.repo_root)
    status = Status.PASS if rc == 0 else Status.WARN
    detail = "lab ready" if rc == 0 else f"lab not ready (exit {rc}) — lab-exec scenarios SKIP"
    return QATResult("p0-lab-ready", status, detail, evidence={"tail": out[-300:]})


def exposure_audit(settings: Settings, discovery: Discovery | None = None) -> QATResult:
    """Designed spaces (portal.yaml) vs OWUI presets (workspaces_all.json)."""
    d = discovery or discover()
    if d.gaps:
        return QATResult(
            "p0-exposure-gap", Status.WARN, f"{len(d.gaps)} gap(s)", evidence={"gaps": list(d.gaps)}
        )
    return QATResult(
        "p0-exposure-gap",
        Status.PASS,
        f"designed == seeded ({len(d.presets)} presets)",
        evidence={"presets": sorted(d.presets)},
    )


def sweep_freshness(settings: Settings) -> QATResult:
    """Newest security_sweep_*.md under ~/.portal5/security within max age."""
    sweep_dir = Path.home() / ".portal5" / "security"
    reports = sorted(sweep_dir.glob("security_sweep_*.md")) if sweep_dir.is_dir() else []
    if not reports:
        return QATResult(
            "p0-sweep-freshness",
            Status.WARN,
            f"no sweep report under {sweep_dir} — run scripts/security_sweep.py",
        )
    newest = reports[-1]
    try:
        stamp = newest.stem.removeprefix("security_sweep_")
        report_date = datetime.strptime(stamp, "%Y%m%d").date()
    except ValueError:
        return QATResult("p0-sweep-freshness", Status.WARN, f"unreadable stamp: {newest.name}")
    age_days = (datetime.now().date() - report_date).days
    if age_days > settings.sweep_max_age_days:
        return QATResult(
            "p0-sweep-freshness",
            Status.WARN,
            f"{newest.name} is {age_days}d old (max {settings.sweep_max_age_days}d)",
        )
    return QATResult("p0-sweep-freshness", Status.PASS, f"{newest.name} ({age_days}d old)")


def run_stage0(settings: Settings) -> list[QATResult]:
    """Order matters: repo-truth first, then CLIs, then freshness."""
    discovery = discover()
    results = [
        run_preflight_script(settings),
        retired_alias_guard(settings.repo_root, discovery),
        run_routing_regression(settings),
        run_trace_sections(settings),
        exposure_audit(settings, discovery),
        run_lab_ready(settings),
        sweep_freshness(settings),
    ]
    return results
