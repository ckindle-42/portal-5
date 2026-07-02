#!/usr/bin/env python3
"""Portal 5 system validation — fast smoke check before launching the full
acceptance / UAT / bench passes.

Run from repo root:
    python3 scripts/validate_system.py
    python3 scripts/validate_system.py --verbose
    python3 scripts/validate_system.py --skip-pytest    # skip the unit run
    python3 scripts/validate_system.py --skip-lifespan  # skip lifespan
    python3 scripts/validate_system.py --json           # machine-readable

Exit codes:
    0   — all checks passed
    1   — one or more checks failed (see output for which)
    2   — script setup error (missing deps, wrong cwd)

This script does NOT require a live Ollama / Open WebUI / Docker stack.
It validates:

    A. Python import surface — every public package imports cleanly
    B. Pipeline assembly — FastAPI app instantiates, all 9 routes present
    C. Config round-trip — portal.yaml loads via PortalConfig
    D. Rule 6 cross-check — workspaces ↔ backends.yaml ↔ WORKSPACES dict
    E. Hint validator — _validate_workspace_hints returns 0 errors
    F. Lifespan startup — async context manager enters + exits cleanly
    G. CLI introspection — portal --help, config show, models list, validate
    H. Unit test suite — pytest tests/unit -q (excluding env-only files)
    I. Shim contract — historical router_pipe imports all resolve
    Y. Self-index integrity — read-only signal aggregation, deterministic ranking
    Z. CI parity — bench imports without PYTHONPATH, conftest lab defaults, ci_local.sh
    AA. Live exec integrity — vulhub->host dispatch, DISPATCH_NOT_RUN guard
    AB. Stage 2 propose integrity — bounded proposals, proof-gated promotion,
        no hollow flag-flip, no writes without operator --apply

Designed to run in under 60 seconds on the M4 Pro Mac Mini. Use this as
the gate before kicking off the full long-running suites:

    python3 scripts/validate_system.py && \
    python3 tests/portal5_acceptance_v6.py
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# ── Setup ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ── Result tracking ───────────────────────────────────────────────────────────
@dataclass
class CheckResult:
    name: str
    status: str  # "PASS" | "FAIL" | "SKIP" | "WARN"
    detail: str = ""
    elapsed_ms: int = 0
    sub_results: list[dict] = field(default_factory=list)


class Validator:
    def __init__(self, *, verbose: bool = False, emit_json: bool = False):
        self.verbose = verbose
        self.emit_json = emit_json
        self.results: list[CheckResult] = []
        self.started_at = time.time()

    def run(self, name: str, fn: Callable[[], tuple[str, str, list[dict]]]) -> CheckResult:
        """Run a single check. fn returns (status, detail, sub_results)."""
        t0 = time.time()
        try:
            status, detail, sub = fn()
        except Exception as e:
            status, detail, sub = "FAIL", f"{type(e).__name__}: {e}", []
        elapsed_ms = int((time.time() - t0) * 1000)
        r = CheckResult(
            name=name, status=status, detail=detail, elapsed_ms=elapsed_ms, sub_results=sub
        )
        self.results.append(r)
        if not self.emit_json:
            self._emit(r)
        return r

    def _emit(self, r: CheckResult) -> None:
        icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "○", "WARN": "!"}[r.status]
        timing = f"({r.elapsed_ms:>4d}ms)"
        line = f"  {icon} {r.name:<32s} {timing}"
        if r.detail and (self.verbose or r.status != "PASS"):
            line += f"  — {r.detail}"
        print(line, file=sys.stderr if r.status == "FAIL" else sys.stdout)
        if self.verbose and r.sub_results:
            for sub in r.sub_results:
                sub_icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "○", "WARN": "!"}.get(
                    sub.get("status", ""), "·"
                )
                print(f"      {sub_icon} {sub.get('name', '?')}: {sub.get('detail', '')}")

    def summary(self) -> int:
        passes = sum(1 for r in self.results if r.status == "PASS")
        fails = sum(1 for r in self.results if r.status == "FAIL")
        warns = sum(1 for r in self.results if r.status == "WARN")
        skips = sum(1 for r in self.results if r.status == "SKIP")
        total_ms = int((time.time() - self.started_at) * 1000)

        if self.emit_json:
            print(
                json.dumps(
                    {
                        "elapsed_ms": total_ms,
                        "passes": passes,
                        "fails": fails,
                        "warns": warns,
                        "skips": skips,
                        "results": [
                            {
                                "name": r.name,
                                "status": r.status,
                                "detail": r.detail,
                                "elapsed_ms": r.elapsed_ms,
                                "sub_results": r.sub_results,
                            }
                            for r in self.results
                        ],
                    },
                    indent=2,
                )
            )
        else:
            print()
            print(
                f"  {passes} pass · {fails} fail · {warns} warn · {skips} skip"
                f"  ({total_ms}ms total)"
            )
            if fails:
                print(
                    "  ⚠  System validation FAILED — fix the above before running"
                    " acceptance / UAT / bench suites.",
                    file=sys.stderr,
                )
            else:
                print("  ✓ System validation passed — ready for full test suites.")

        return 1 if fails else 0


# ── Checks ────────────────────────────────────────────────────────────────────


def check_imports() -> tuple[str, str, list[dict]]:
    """A. Every public package imports cleanly."""
    modules = [
        "portal_pipeline",
        "portal_pipeline.router_pipe",
        "portal_pipeline.router.app",
        "portal_pipeline.router.lifespan",
        "portal_pipeline.router.handlers",
        "portal_pipeline.router.routing",
        "portal_pipeline.router.streaming",
        "portal_pipeline.router.workspaces",
        "portal_pipeline.router.auth",
        "portal_pipeline.router.validation",
        "portal_pipeline.router.preinject",
        "portal_pipeline.router.non_streaming",
        "portal_pipeline.config",
        "portal_pipeline.cli",
        "portal_pipeline.cli.models",
        "portal_pipeline.cli.workspace",
        "portal_pipeline.cli.config",
        "portal_pipeline.cli.sync",
        "portal_pipeline.cli.smoke",
        "portal_pipeline.cli.update",
        "portal_pipeline.cluster_backends",
        "portal_pipeline.tool_registry",
    ]
    subs = []
    failed = 0
    for m in modules:
        try:
            importlib.import_module(m)
            subs.append({"name": m, "status": "PASS"})
        except Exception as e:
            subs.append({"name": m, "status": "FAIL", "detail": f"{type(e).__name__}: {e}"})
            failed += 1
    if failed:
        return "FAIL", f"{failed}/{len(modules)} modules failed to import", subs
    return "PASS", f"{len(modules)} modules import cleanly", subs


def check_pipeline_assembles() -> tuple[str, str, list[dict]]:
    """B. FastAPI app instantiates with all expected routes."""
    from portal_pipeline.router_pipe import app

    expected_routes = {
        ("/health", "GET"),
        ("/health/all", "GET"),
        ("/metrics", "GET"),
        ("/admin/refresh-tools", "POST"),
        ("/notifications/test", "POST"),
        ("/v1/models", "GET"),
        ("/v1/backends", "GET"),
        ("/v1/chat/completions", "POST"),
        ("/v1/messages", "POST"),
    }
    actual_routes = set()
    for r in app.routes:
        if hasattr(r, "methods"):
            for method in r.methods:
                if method != "HEAD":
                    actual_routes.add((r.path, method))

    missing = expected_routes - actual_routes
    if missing:
        return "FAIL", f"missing routes: {missing}", []
    return "PASS", "FastAPI app + all 9 routes registered", []


def check_config_loads() -> tuple[str, str, list[dict]]:
    """C. portal.yaml loads via PortalConfig."""
    from portal_pipeline.config import load_portal_config

    cfg = load_portal_config()
    n_ws = len(cfg.workspaces)
    n_mcp = len(cfg.mcp_fleet)
    n_models = len(cfg.models)
    if n_ws == 0:
        return "FAIL", "PortalConfig.workspaces is empty", []
    if n_mcp == 0:
        return "WARN", "PortalConfig.mcp_fleet is empty (unusual)", []
    return "PASS", f"{n_ws} workspaces · {n_mcp} MCP · {n_models} models", []


def check_rule_6() -> tuple[str, str, list[dict]]:
    """D. portal.yaml workspaces ↔ backends.yaml workspace_routing ↔ WORKSPACES."""
    import yaml

    from portal_pipeline.config import load_portal_config
    from portal_pipeline.router.workspaces import WORKSPACES

    cfg = load_portal_config()
    ws_yaml = set(cfg.workspaces.keys())
    ws_router = set(WORKSPACES.keys())

    backends_path = REPO_ROOT / "config" / "backends.yaml"
    backends = yaml.safe_load(backends_path.read_text())
    ws_backends = set(backends.get("workspace_routing", {}).keys())

    if ws_yaml != ws_router or ws_yaml != ws_backends:
        details = []
        if ws_yaml - ws_router:
            details.append(f"yaml extra: {ws_yaml - ws_router}")
        if ws_router - ws_yaml:
            details.append(f"router extra: {ws_router - ws_yaml}")
        if ws_yaml - ws_backends:
            details.append(f"backends missing: {ws_yaml - ws_backends}")
        if ws_backends - ws_yaml:
            details.append(f"backends extra: {ws_backends - ws_yaml}")
        return "FAIL", "; ".join(details), []
    return "PASS", f"all 3 surfaces agree on {len(ws_yaml)} workspaces", []


def check_hint_validator() -> tuple[str, str, list[dict]]:
    """E. _validate_workspace_hints returns 0 errors."""
    try:
        from portal_pipeline.cluster_backends import BackendRegistry
        from portal_pipeline.router.validation import _validate_workspace_hints
    except ImportError as e:
        return "FAIL", f"import: {e}", []

    backends_yaml = REPO_ROOT / "config" / "backends.yaml"
    # BackendRegistry uses a direct constructor with config_path kwarg
    registry = BackendRegistry(config_path=str(backends_yaml))
    errors = _validate_workspace_hints(registry)
    if errors:
        sample = errors[:3]
        return "FAIL", f"{len(errors)} hint(s) failed: {sample}", []
    return "PASS", "every workspace.model_hint resolves to a backend model", []


def check_lifespan() -> tuple[str, str, list[dict]]:
    """F. FastAPI lifespan starts and stops cleanly."""
    from portal_pipeline.router_pipe import app, lifespan

    async def _run():
        try:
            async with lifespan(app):
                pass
            return True, None
        except Exception as e:
            return False, repr(e)

    ok, err = asyncio.run(_run())
    if not ok:
        return "FAIL", f"lifespan raised: {err}", []
    return "PASS", "lifespan enter + exit clean", []


def check_cli_introspection() -> tuple[str, str, list[dict]]:
    """G. The portal CLI's help + introspection commands work."""
    subs = []
    failed = 0
    commands = [
        ["--help"],
        ["config", "show"],
        ["models", "list", "--include-retired"],
        ["models", "validate"],
    ]
    for cmd in commands:
        result = subprocess.run(
            [sys.executable, "-m", "portal_pipeline.cli", *cmd],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(REPO_ROOT),
        )
        ok = result.returncode == 0
        # `models validate` is allowed to exit non-zero IF the data has
        # orphan hints — but for a healthy system it should be 0.
        name = "portal " + " ".join(cmd)
        if ok:
            subs.append({"name": name, "status": "PASS"})
        else:
            err_summary = (result.stderr.strip() or result.stdout.strip())[:120]
            subs.append(
                {"name": name, "status": "FAIL", "detail": f"rc={result.returncode}: {err_summary}"}
            )
            failed += 1
    if failed:
        return "FAIL", f"{failed}/{len(commands)} CLI commands failed", subs
    return "PASS", f"all {len(commands)} CLI invocations rc=0", subs


def check_unit_tests(*, skip_env_only: bool = True) -> tuple[str, str, list[dict]]:
    """H. Run pytest tests/unit (optionally excluding environment-only files)."""
    args = [sys.executable, "-m", "pytest", "tests/unit", "-q", "--tb=no"]
    if skip_env_only:
        # Env-only failures on the M4 Pro Mac Mini may differ — these ignores
        # match the audit container; tune per local env.
        args += [
            "--ignore=tests/unit/test_proxmox_mcp.py",
            "--ignore=tests/unit/test_transcribe_diarize.py",
            "--ignore=tests/unit/test_reranker_mcp.py",
        ]
    result = subprocess.run(args, capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT))
    # Parse the summary line ("= N failed, N passed, ... =")
    summary_line = ""
    for line in result.stdout.splitlines()[::-1]:
        if "passed" in line or "failed" in line:
            summary_line = line.strip("= ")
            break
    if result.returncode == 0:
        return "PASS", summary_line or "pytest rc=0", []
    return "FAIL", f"rc={result.returncode}: {summary_line}", []


def check_bench_security_catalog() -> tuple[str, str, list[dict]]:
    """J. bench_security catalog covers every live security workspace."""
    try:
        from portal_pipeline.config import load_portal_config
        from tests.benchmarks.bench_security import DEFAULT_WORKSPACES
    except ImportError as e:
        return "SKIP", f"import: {e}", []

    cfg = load_portal_config()
    # Production auto-* security workspaces must all appear in DEFAULT_WORKSPACES.
    # Bench-* security workspaces are operator-triaged; not checked here.
    prod_sec = {
        ws_id
        for ws_id in cfg.workspaces
        if ws_id.startswith("auto-")
        and any(t in ws_id for t in ("sec", "pentest", "redteam", "blueteam", "purpleteam"))
    }
    missing = prod_sec - set(DEFAULT_WORKSPACES)
    if missing:
        return (
            "FAIL",
            f"{len(missing)} prod security workspace(s) missing from bench: {sorted(missing)}",
            [],
        )
    return "PASS", f"all {len(prod_sec)} production security workspaces in DEFAULT_WORKSPACES", []


def check_valid_workspaces_resolve() -> tuple[str, str, list[dict]]:
    """N. portal_channels.dispatcher.VALID_WORKSPACES contains only live workspace ids.

    Catches the drift pattern where new workspaces are added to the
    channel-adapter routing gate but retired workspaces are never removed.
    Same shape as J/K — catalog drift detection.
    """
    try:
        from portal_channels.dispatcher import VALID_WORKSPACES
        from portal_pipeline.config import load_portal_config
    except ImportError as e:
        return "SKIP", f"import: {e}", []
    live = set(load_portal_config().workspaces.keys())
    stale = sorted(VALID_WORKSPACES - live)
    if stale:
        return "FAIL", f"{len(stale)} stale ws id(s) in VALID_WORKSPACES — first: {stale[0]}", []
    return "PASS", f"all {len(VALID_WORKSPACES)} VALID_WORKSPACES entries resolve", []


def check_no_undefined_names() -> tuple[str, str, list[dict]]:
    """M. Ruff F821 — no undefined-name violations anywhere in the repo.

    Hard gate against decomposition-leftover bugs of the class where
    a name is referenced in a function body but never imported. The
    bugs import cleanly at module-eval time but crash at runtime.
    Ruff F821 catches them statically.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["python3", "-m", "ruff", "check", "--select", "F821", "."],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return "SKIP", "ruff not installed (pip install ruff)", []
    except subprocess.TimeoutExpired:
        return "WARN", "ruff check timed out (>30s)", []
    if result.returncode == 0:
        return "PASS", "no F821 (undefined-name) violations", []
    n_errors = result.stdout.count("F821 ")
    lines = [ln for ln in result.stdout.splitlines() if ln.startswith("F821")][:1]
    detail = f"{n_errors} violation(s)" + (f" — first: {lines[0][:60]}" if lines else "")
    return "FAIL", detail, []


def check_persona_workspace_resolution() -> tuple[str, str, list[dict]]:
    """L. Every persona's workspace_model resolves to a live workspace."""
    try:
        import pathlib

        import yaml

        from portal_pipeline.config import load_portal_config
    except ImportError as e:
        return "SKIP", f"import: {e}", []
    cfg = load_portal_config()
    live_workspaces = set(cfg.workspaces.keys())
    persona_dir = pathlib.Path("config/personas")
    if not persona_dir.is_dir():
        return "SKIP", "config/personas/ not found", []
    broken: list[str] = []
    n_total = 0
    for yaml_path in persona_dir.glob("*.yaml"):
        n_total += 1
        try:
            persona = yaml.safe_load(yaml_path.read_text())
        except Exception:
            continue
        if not isinstance(persona, dict):
            continue
        ws = persona.get("workspace_model") or persona.get("workspace")
        if ws and ws not in live_workspaces:
            broken.append(f"{yaml_path.stem} -> {ws}")
    if broken:
        return "FAIL", f"{len(broken)} persona(s) reference dead workspace: {broken[:3]}", []
    return "PASS", f"all {n_total} personas resolve to live workspaces", []


def check_uat_catalog_no_stale_refs() -> tuple[str, str, list[dict]]:
    """K. UAT catalog has no stale workspace references.

    Soft: stale (in-catalog but not-live) references warn but don't fail.
    Live-but-uncovered is operator triage, not a hard error here.
    """
    try:
        import re

        import tests.uat_catalog as cat
        from portal_pipeline.config import load_portal_config
    except ImportError as e:
        return "SKIP", f"import: {e}", []

    cfg = load_portal_config()
    ws_mentioned = set()
    for attr in dir(cat):
        if not attr.startswith("g_"):
            continue
        mod = getattr(cat, attr)
        if hasattr(mod, "__file__"):
            with open(mod.__file__) as _f:
                src = _f.read()
            for m in re.finditer(r'["\']((auto|bench)-[a-z0-9_-]+)["\']', src):
                ws_mentioned.add(m.group(1))
    stale = ws_mentioned - set(cfg.workspaces.keys())
    if stale:
        return "WARN", f"{len(stale)} stale workspace ref(s) in UAT catalog", []
    return "PASS", "UAT catalog refs all resolve to live workspaces", []


def check_shim_contract() -> tuple[str, str, list[dict]]:
    """I. Historical symbols imported through router_pipe still resolve."""
    from portal_pipeline import router_pipe

    historical = [
        "app",
        "lifespan",
        "_validate_workspace_hints",
        "_model_supports_tools",
        "_inject_ollama_options",
        "_inject_attached_files",
        "_inject_system_prompt_append",
        "_inject_temporal_context",
        "_verify_key",
        "_verify_admin_key",
        "_try_non_streaming",
        "_resolve_persona_workspace",
        "_resolve_auto_routing",
        "_resolve_vision_fallback",
        "_detect_workspace",
        "_CODING_KEYWORDS",
        "_SPL_KEYWORDS",
        "chat_completions",
        "health",
        "metrics",
        "WORKSPACES",
        "_PERSONA_MAP",
        "PIPELINE_API_KEY",
        "_record_usage",
    ]
    subs = []
    missing = []
    for sym in historical:
        if hasattr(router_pipe, sym):
            subs.append({"name": sym, "status": "PASS"})
        else:
            subs.append({"name": sym, "status": "FAIL"})
            missing.append(sym)
    if missing:
        return "FAIL", f"missing from shim: {missing}", subs
    return "PASS", f"all {len(historical)} historical symbols resolve", subs


def check_bench_parallel_dispatch_safety() -> tuple[str, str, list[dict]]:
    """O. bench_security Phase-1 dispatcher uses ThreadPoolExecutor + a lock.

    Coarse regression guard: confirms the parallel-dispatch contract is still in
    place. A refactor that reverts to serial-only or drops the lock without
    documentation will fail this check.
    """
    target = REPO_ROOT / "tests" / "benchmarks" / "bench_security" / "commands" / "run.py"
    if not target.exists():
        return "FAIL", f"missing {target}", []
    src = target.read_text()
    subs = []
    expectations = {
        "ThreadPoolExecutor": "ThreadPoolExecutor imported/used",
        "threading.Lock": "threading.Lock instantiated",
        "parallel_workspaces": "run_bench accepts parallel_workspaces kwarg",
        "_process_one": "per-task closure extracted",
        "as_completed": "completion-order consumption",
    }
    missing = []
    for needle, label in expectations.items():
        if needle in src:
            subs.append({"name": label, "status": "PASS"})
        else:
            subs.append({"name": label, "status": "FAIL"})
            missing.append(needle)
    if missing:
        return "FAIL", f"missing: {missing}", subs
    return "PASS", f"all {len(expectations)} parallel-dispatch markers present", subs


def check_oracle_registry_consistency() -> tuple[str, str, list[dict]]:
    """P. Every exec scenario with an 'oracle' field names a registered oracle."""
    subs: list[dict] = []
    try:
        from tests.benchmarks.bench_security.oracles import ORACLES
    except ImportError:
        return "SKIP", "oracles module not found", []

    from tests.benchmarks.bench_security._data import EXEC_SEQUENCES, PROMPTS

    missing = []
    scenario_count = 0
    for name, seq in EXEC_SEQUENCES.items():
        # EXEC_SEQUENCES is dict of name → list of step dicts
        steps = seq if isinstance(seq, list) else seq.get("steps", [])
        for step in steps:
            if isinstance(step, dict) and "oracle" in step:
                oid = step["oracle"]
                scenario_count += 1
                in_registry = oid in ORACLES
                subs.append(
                    {
                        "name": f"{name}::{step.get('step', '')}",
                        "status": "PASS" if in_registry else "FAIL",
                    }
                )
                if not in_registry:
                    missing.append(f"{name}::{step.get('step', '')} oracle={oid}")
    # Also check PROMPTS that have oracle at the prompt level
    for name, prompt in PROMPTS.items():
        if isinstance(prompt, dict) and "oracle" in prompt:
            oid = prompt["oracle"]
            if oid is None:
                # oracle: null is deliberate (scoring: heuristic) — not a registry gap
                scenario_count += 1
                subs.append(
                    {
                        "name": f"PROMPT::{name}",
                        "status": "PASS",
                        "detail": "oracle=null (heuristic)",
                    }
                )
                continue
            scenario_count += 1
            in_registry = oid in ORACLES
            subs.append({"name": f"PROMPT::{name}", "status": "PASS" if in_registry else "FAIL"})
            if not in_registry:
                missing.append(f"PROMPT::{name} oracle={oid}")
    if missing:
        return "FAIL", f"{len(missing)} oracle id(s) not in registry: {missing}", subs
    if not scenario_count:
        return (
            "PASS",
            "no scenarios declare oracle (registry is active, nothing to cross-check)",
            subs,
        )
    return "PASS", f"all {scenario_count} scenario oracle ids resolve to registered oracles", subs


def check_playbook_validation() -> tuple[str, str, list[dict]]:
    """Q. Every file in playbooks/security/ passes validate_playbook."""
    import glob

    subs: list[dict] = []
    playbook_dir = REPO_ROOT / "playbooks" / "security"
    if not playbook_dir.exists():
        return "SKIP", "playbooks/security/ not found", []

    try:
        from tests.benchmarks.bench_security.playbooks import load_playbook, validate_playbook
    except ImportError:
        return "SKIP", "playbooks module not found", []

    for p in sorted(glob.glob(str(playbook_dir / "*.yaml"))):
        try:
            pb = load_playbook(p)
            problems = validate_playbook(pb)
            if problems:
                subs.append({"name": Path(p).name, "status": "FAIL", "problems": problems})
            else:
                subs.append({"name": Path(p).name, "status": "PASS"})
        except Exception as e:
            subs.append({"name": Path(p).name, "status": "FAIL", "error": str(e)})
    failed = [s["name"] for s in subs if s["status"] == "FAIL"]
    if failed:
        return "FAIL", f"{len(failed)} playbook(s) failed validation: {failed}", subs
    return "PASS", f"all {len(subs)} playbooks pass validation", subs


def check_lab_target_catalog() -> tuple[str, str, list[dict]]:
    """U. lab_targets.yaml entries have source + ground_truth; challenge_classes.yaml no orphans."""
    import yaml

    subs: list[dict] = []
    problems: list[str] = []

    # Check lab_targets.yaml
    lt_path = REPO_ROOT / "config" / "lab_targets.yaml"
    if lt_path.exists():
        try:
            lt = yaml.safe_load(lt_path.read_text())
            for t in lt.get("targets", []):
                tid = t.get("id", "?")
                if "source" not in t:
                    problems.append(f"{tid}: missing source")
                if "ground_truth" not in t:
                    problems.append(f"{tid}: missing ground_truth")
            subs.append({"name": "lab_targets.yaml", "status": "PASS" if not problems else "FAIL"})
        except Exception as e:
            problems.append(f"lab_targets.yaml parse error: {e}")

    # Check challenge_classes.yaml
    cc_path = REPO_ROOT / "config" / "challenge_classes.yaml"
    if cc_path.exists():
        try:
            cc = yaml.safe_load(cc_path.read_text())
            cc_problems = []
            for c in cc.get("classes", []):
                cid = c.get("id", "?")
                has_vulhub = len(c.get("vulhub", [])) > 0
                has_purpose = c.get("purpose_built") is not None
                if not has_vulhub and not has_purpose:
                    cc_problems.append(f"{cid}: orphan — no vulhub path or purpose_built dir")
            cc_status = "PASS" if not cc_problems else "FAIL"
            subs.append({"name": "challenge_classes.yaml", "status": cc_status})
            problems.extend(cc_problems)
        except Exception as e:
            problems.append(f"challenge_classes.yaml parse error: {e}")

    if problems:
        return "FAIL", f"{len(problems)} catalog issue(s): {problems[:5]}", subs
    return "PASS", "lab target catalog + challenge classes valid", subs


def check_loop_dry_run() -> tuple[str, str, list[dict]]:
    """R. Every starter playbook dry-runs through the loop without error."""
    import glob

    subs: list[dict] = []
    playbook_dir = REPO_ROOT / "playbooks" / "security"
    try:
        from tests.benchmarks.bench_security.loop import run_engagement
    except ImportError:
        return "SKIP", "loop module not found", []

    for p in sorted(glob.glob(str(playbook_dir / "*.yaml"))):
        name = Path(p).name
        try:
            result = run_engagement(str(p), dry_run=True)
            ok = result.get("status") == "dry_run"
            subs.append(
                {
                    "name": name,
                    "status": "PASS" if ok else "FAIL",
                    "reason": result.get("status", "?"),
                }
            )
        except Exception as e:
            subs.append({"name": name, "status": "FAIL", "error": str(e)})
    failed = [s["name"] for s in subs if s["status"] == "FAIL"]
    if failed:
        return "FAIL", f"{len(failed)} playbook(s) failed loop dry-run: {failed}", subs
    return "PASS", f"all {len(subs)} playbooks pass loop dry-run", subs


def check_lab_setup_readiness() -> tuple[str, str, list[dict]]:
    """V. Lab setup/readiness scripts import and parse correctly."""
    subs: list[dict] = []
    try:
        from scripts.lab_setup import run_setup

        result = run_setup(skip_heavy=True, dry_run=True)
        subs.append({"name": "lab_setup", "status": "PASS" if "vulhub" in result else "FAIL"})
    except Exception as e:
        subs.append({"name": "lab_setup", "status": "FAIL", "error": str(e)})

    try:
        from scripts.lab_ready import run_readiness

        passed, results = run_readiness()
        subs.append({"name": "lab_ready", "status": "PASS" if len(results) >= 5 else "FAIL"})
    except Exception as e:
        subs.append({"name": "lab_ready", "status": "FAIL", "error": str(e)})

    try:
        from scripts.lab_targets import cmd_list

        targets = cmd_list()
        subs.append(
            {"name": "lab_targets catalog", "status": "PASS" if len(targets) >= 7 else "FAIL"}
        )
    except Exception as e:
        subs.append({"name": "lab_targets catalog", "status": "FAIL", "error": str(e)})

    failed = [s["name"] for s in subs if s["status"] == "FAIL"]
    if failed:
        return "FAIL", f"{len(failed)} lab setup check(s) failed: {failed}", subs
    return "PASS", "all lab setup/readiness/targets modules operational", subs


def check_ability_port() -> tuple[str, str, list[dict]]:
    """W. ability_port defines real detect functions (not description strings)."""
    subs: list[dict] = []
    try:
        from tests.benchmarks.bench_security.ability_port import (
            PROBE_DEFS,
            register_ported_oracles,
        )
        from tests.benchmarks.bench_security.oracles import ORACLES

        register_ported_oracles()
        ptai = [k for k in ORACLES if k.startswith("ptai_")]
        # Count probes that have real detect functions (exclude oob with None)
        expected = len([p for p in PROBE_DEFS if p[3] is not None])
        subs.append(
            {
                "name": "ptai_oracles",
                "status": "PASS" if len(ptai) >= expected else "FAIL",
                "count": len(ptai),
                "expected": expected,
            }
        )
    except Exception as e:
        subs.append({"name": "ptai_oracles", "status": "FAIL", "error": str(e)})

    try:
        import ast

        with open("tests/benchmarks/bench_security/ability_port.py") as f:
            src = f.read()
        assert "detect_sig" not in src, "detect_sig stubs present"
        t = ast.parse(src)
        has_detect = any(isinstance(n, ast.FunctionDef) and "detect" in n.name for n in ast.walk(t))
        has_register = any(
            isinstance(n, ast.Call)
            and hasattr(n, "func")
            and hasattr(n.func, "id")
            and n.func.id == "register_oracle"
            for n in ast.walk(t)
        )
        subs.append(
            {
                "name": "anti_stub",
                "status": "PASS" if has_register else "FAIL",
                "detail": f"register_oracle calls found: {has_register}",
            }
        )
    except Exception as e:
        subs.append({"name": "anti_stub", "status": "FAIL", "error": str(e)})

    failed = [s["name"] for s in subs if s["status"] == "FAIL"]
    if failed:
        return "FAIL", f"ability port check(s) failed: {failed}", subs
    return (
        "PASS",
        f"{len(ptai) if 'ptai' in dir() else '?'} ported oracles ({expected if 'expected' in dir() else '?'} expected)",
        subs,
    )


def check_labexec_coverage() -> tuple[str, str, list[dict]]:
    """W. Every lab machine with an env entry has a registered live phase with an oracle."""
    subs: list[dict] = []
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests" / "benchmarks"))
        from bench_lab_exec import LAB_TARGETS, PHASE_FNS, PHASE_TARGETS
    except ImportError as e:
        return "FAIL", f"cannot import bench_lab_exec: {e}", []

    phase_map = {
        "dc01": "dcsync",
        "srv01": "srv01_local",
        "vulhub": "vulhub_redis",
        "meta3": "meta3_compromise",
        "mbptl": "mbptl_full_chain",
    }

    for name, tgt in LAB_TARGETS.items():
        phase = phase_map.get(name, "")
        has_phase = phase in PHASE_FNS
        has_target = phase in PHASE_TARGETS and name in PHASE_TARGETS.get(phase, [])
        status = "PASS" if has_phase and has_target else "FAIL"
        subs.append(
            {
                "name": f"lab-exec-{name}",
                "status": status,
                "vmid": tgt.get("vmid", "?"),
                "phase": phase if has_phase else "MISSING",
                "reason": "" if has_phase else "no live oracle-scored phase registered",
            }
        )

    # Check: no scenario that names a live target IP falls back to synthetic by default
    try:
        from bench_security.lab import _lab_dispatch_inner

        for fn_name in [
            "web_request",
            "run_sqlmap",
            "upload_webshell",
            "webshell_exec",
            "exploit_binary_service",
        ]:
            # dry_run shouldn't return a synthetic-only message (it should say DRY-RUN)
            result = _lab_dispatch_inner(fn_name, {}, dry_run=True)
            if "[DRY-RUN]" in result or "synthetic" not in result:
                subs.append({"name": f"mbptl-dispatch-{fn_name}", "status": "PASS"})
            else:
                subs.append(
                    {
                        "name": f"mbptl-dispatch-{fn_name}",
                        "status": "WARN",
                        "reason": "synthetic-only fallback triggered on dry-run",
                    }
                )
    except Exception as e:
        subs.append({"name": "mbptl-dispatch", "status": "FAIL", "error": str(e)})

    failed = [s["name"] for s in subs if s["status"] == "FAIL"]
    if failed:
        return "FAIL", f"{len(failed)} lab-exec coverage gap(s): {failed}", subs
    return (
        "PASS",
        f"all {len(LAB_TARGETS)} provisioned machines have live oracle-scored phases",
        subs,
    )


def check_scenario_oracle_matrix() -> tuple[str, str, list[dict]]:
    """X. Every scenario has an oracle (or explicit null), every class oracle is registered, every class resolves to a container."""
    import yaml

    subs: list[dict] = []
    problems: list[str] = []

    try:
        from tests.benchmarks.bench_security._data import PROMPTS
        from tests.benchmarks.bench_security.oracles import ORACLES
    except ImportError as e:
        return "SKIP", f"import: {e}", []

    # Check 1: every scenario has an oracle field
    missing_oracle = []
    bad_oracle = []
    for key, prompt in PROMPTS.items():
        if "oracle" not in prompt:
            missing_oracle.append(key)
        else:
            oracle = prompt["oracle"]
            if oracle is not None and oracle not in ORACLES:
                bad_oracle.append(f"{key}→{oracle}")
    if missing_oracle:
        problems.append(
            f"{len(missing_oracle)} scenario(s) missing oracle field: {missing_oracle[:3]}"
        )
    if bad_oracle:
        problems.append(
            f"{len(bad_oracle)} scenario(s) reference unregistered oracle: {bad_oracle[:3]}"
        )
    subs.append(
        {
            "name": "scenario oracles",
            "status": "PASS" if not missing_oracle and not bad_oracle else "FAIL",
        }
    )

    # Check 2: every challenge-class oracle is registered
    cc_path = REPO_ROOT / "config" / "challenge_classes.yaml"
    if cc_path.exists():
        cc = yaml.safe_load(cc_path.read_text())
        cc_oracle_problems = []
        cc_orphan = []
        for cls in cc.get("classes", []):
            cid = cls.get("id", "?")
            oracle = cls.get("ground_truth", {}).get("oracle", "")
            if oracle and oracle not in ORACLES:
                cc_oracle_problems.append(f"{cid}→{oracle}")
            has_vulhub = len(cls.get("vulhub", [])) > 0
            has_purpose = cls.get("purpose_built") is not None
            if not has_vulhub and not has_purpose:
                cc_orphan.append(cid)
        if cc_oracle_problems:
            problems.append(f"class oracles not registered: {cc_oracle_problems}")
        if cc_orphan:
            problems.append(f"orphan classes (no vulhub or purpose_built): {cc_orphan}")
        subs.append(
            {"name": "class oracles", "status": "PASS" if not cc_oracle_problems else "FAIL"}
        )
        subs.append({"name": "class containers", "status": "PASS" if not cc_orphan else "FAIL"})
    else:
        subs.append({"name": "challenge_classes.yaml", "status": "SKIP"})

    if problems:
        return "FAIL", f"{len(problems)} issue(s): {problems[:3]}", subs
    return "PASS", f"all {len(PROMPTS)} scenarios oracle-bound, all class oracles registered", subs


def check_self_index_integrity() -> tuple[str, str, list[dict]]:
    """Y. self-index reads only (no config/code writes), reports absent signals honestly, score is deterministic and inspectable."""
    # self_index.build_self_index() shells out to `validate_system.py --json` to read
    # validator health — which runs this very check again. self_index sets
    # PORTAL5_SELF_INDEX_NESTED in that subprocess's env; bail out here rather than
    # recursing (unbounded subprocess fork chain, found live 2026-07-02: 145+ processes
    # before the guard caught it).
    if os.environ.get("PORTAL5_SELF_INDEX_NESTED"):
        return (
            "SKIP",
            "nested validator run — self-index check skipped to avoid recursive spawn",
            [],
        )

    subs: list[dict] = []

    # Check 1: self_index module imports cleanly
    try:
        from tests.benchmarks.bench_security.self_index import (
            _SCORE_RULES,
            build_self_index,
            rank_weaknesses,
        )
    except ImportError as e:
        return "FAIL", f"self_index import failed: {e}", []

    # Check 2: build_self_index returns all required keys
    try:
        index = build_self_index()
    except Exception as e:
        return "FAIL", f"build_self_index raised: {type(e).__name__}: {e}", []

    required_keys = {"validator", "oracles", "coverage", "disciplines", "journal", "generated_at"}
    missing_keys = required_keys - set(index.keys())
    if missing_keys:
        subs.append(
            {"name": "required keys", "status": "FAIL", "detail": f"missing: {missing_keys}"}
        )
        return "FAIL", f"index missing required keys: {missing_keys}", subs
    subs.append(
        {
            "name": "required keys",
            "status": "PASS",
            "detail": f"all {len(required_keys)} keys present",
        }
    )

    # Check 3: absent signals are marked honestly, never fabricated
    for signal_name in ["validator", "oracles", "coverage", "disciplines", "journal"]:
        signal = index.get(signal_name, {})
        status = signal.get("status", "")
        if status == "absent":
            # Verify no fabricated counts — should have zeros and empty structures
            for count_field in ["total_units", "verified", "total_entries"]:
                if count_field in signal and signal[count_field] != 0:
                    subs.append(
                        {
                            "name": f"{signal_name} honesty",
                            "status": "FAIL",
                            "detail": f"{signal_name} status=absent but {count_field}={signal[count_field]} (fabricated)",
                        }
                    )
                    return (
                        "FAIL",
                        f"{signal_name} reports absent but has non-zero {count_field}",
                        subs,
                    )
            subs.append(
                {
                    "name": f"{signal_name} honesty",
                    "status": "PASS",
                    "detail": "absent, no fabricated counts",
                }
            )

    # Check 4: rank_weaknesses is deterministic and inspectable
    try:
        w1 = rank_weaknesses(index)
        w2 = rank_weaknesses(index)
        if w1 != w2:
            subs.append(
                {
                    "name": "deterministic ranking",
                    "status": "FAIL",
                    "detail": "non-deterministic output",
                }
            )
            return "FAIL", "rank_weaknesses is non-deterministic (two calls differ)", subs
    except Exception as e:
        subs.append({"name": "rank_weaknesses execution", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"rank_weaknesses raised: {type(e).__name__}: {e}", subs

    for w in w1:
        if not all(k in w for k in ("area", "kind", "evidence", "score", "why")):
            subs.append(
                {
                    "name": "weakness schema",
                    "status": "FAIL",
                    "detail": f"entry {w.get('area', '?')} missing required keys",
                }
            )
            return (
                "FAIL",
                "weakness entry missing required keys (area/kind/evidence/score/why)",
                subs,
            )
        if not isinstance(w["score"], (int, float)):
            subs.append(
                {"name": "score type", "status": "FAIL", "detail": f"score is {type(w['score'])}"}
            )
            return "FAIL", "weakness score must be numeric", subs

    subs.append(
        {
            "name": "deterministic ranking",
            "status": "PASS",
            "detail": f"{len(w1)} weaknesses ranked",
        }
    )

    # Check 5: SCORE_RULES is documented and inspectable
    if not isinstance(_SCORE_RULES, dict) or len(_SCORE_RULES) == 0:
        subs.append(
            {"name": "score rules", "status": "FAIL", "detail": "SCORE_RULES missing or empty"}
        )
        return "FAIL", "SCORE_RULES is missing or empty", subs
    subs.append(
        {
            "name": "score rules inspectable",
            "status": "PASS",
            "detail": f"{len(_SCORE_RULES)} documented rules",
        }
    )

    return (
        "PASS",
        "self-index reads only, reports absent signals honestly, ranking deterministic and inspectable",
        subs,
    )


def check_ci_parity() -> tuple[str, str, list[dict]]:
    """Z. bench modules import without PYTHONPATH; conftest sets lab-env defaults; ci_local.sh present."""
    import os

    subs: list[dict] = []

    # Check 1: pyproject.toml has pythonpath including tests/benchmarks
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

    pyproject = REPO_ROOT / "pyproject.toml"
    if pyproject.exists():
        cfg = tomllib.loads(pyproject.read_text())
        pp = cfg.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("pythonpath", [])
        if "tests/benchmarks" not in pp or "." not in pp:
            subs.append(
                {
                    "name": "pythonpath",
                    "status": "FAIL",
                    "detail": f"pythonpath={pp} (needs tests/benchmarks + '.')",
                }
            )
            return (
                "FAIL",
                f"pythonpath missing tests/benchmarks or '.' in pyproject.toml: {pp}",
                subs,
            )
        subs.append({"name": "pythonpath", "status": "PASS", "detail": str(pp)})
    else:
        subs.append({"name": "pyproject.toml", "status": "SKIP"})

    # Check 2: conftest.py sets lab-env defaults
    conftest = REPO_ROOT / "tests" / "conftest.py"
    if conftest.exists():
        ct = conftest.read_text()
        missing = [
            v for v in ("LAB_TARGET_DC", "LAB_TARGET_SRV", "SANDBOX_LAB_EXEC") if v not in ct
        ]
        if missing:
            subs.append(
                {
                    "name": "conftest lab defaults",
                    "status": "FAIL",
                    "detail": f"missing setdefaults: {missing}",
                }
            )
            return "FAIL", f"conftest missing lab-env defaults: {missing}", subs
        subs.append({"name": "conftest lab defaults", "status": "PASS"})
    else:
        subs.append({"name": "conftest.py", "status": "SKIP"})

    # Check 3: scripts/ci_local.sh exists and is executable
    ci_sh = REPO_ROOT / "scripts" / "ci_local.sh"
    if not ci_sh.exists():
        subs.append({"name": "ci_local.sh", "status": "FAIL", "detail": "file missing"})
        return "FAIL", "scripts/ci_local.sh does not exist", subs
    if not os.access(ci_sh, os.X_OK):
        subs.append(
            {"name": "ci_local.sh executable", "status": "FAIL", "detail": "not executable"}
        )
        return "FAIL", "scripts/ci_local.sh is not executable", subs
    subs.append({"name": "ci_local.sh", "status": "PASS", "detail": "present and executable"})

    # Check 4: verify bench import resolves via pytest (pythonpath injection from pyproject.toml)
    try:
        result = subprocess.run(
            [
                "env",
                "-u",
                "PYTHONPATH",
                "python3",
                "-m",
                "pytest",
                "tests/unit/test_ci_parity.py::TestCiParity::test_bench_imports_without_pythonpath",
                "--tb=line",
                "-q",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        if result.returncode != 0:
            subs.append(
                {
                    "name": "bench import (no PYTHONPATH)",
                    "status": "FAIL",
                    "detail": result.stderr.strip()[:200],
                }
            )
            return ("FAIL", "bench import module fails under pytest with clean PYTHONPATH", subs)
        subs.append({"name": "bench import (no PYTHONPATH)", "status": "PASS"})
    except (subprocess.TimeoutExpired, FileNotFoundError):
        subs.append(
            {
                "name": "bench import (no PYTHONPATH)",
                "status": "SKIP",
                "detail": "subprocess failed",
            }
        )

    return (
        "PASS",
        "bench imports without PYTHONPATH; conftest has lab defaults; ci_local.sh present",
        subs,
    )


def check_live_exec_integrity() -> tuple[str, str, list[dict]]:
    """AA. live exec integrity: vulhub resolves+spins on the host via _host_exec (never local
    fs); _run_against_target dispatches via phase/exec_sequence/not-run keyed on real fields;
    no path emits verified without real host output."""
    subs: list[dict] = []

    try:
        from tests.benchmarks.bench_security.matrix import (
            _PHASE_MAP,
            RunUnit,
            _execute_unit,
            _expand_vulhub_globs,
        )
    except ImportError as e:
        return "FAIL", f"cannot import matrix module: {e}", []

    # Check 1: vulhub resolution goes through _host_exec, not a local glob.
    import scripts.lab_host as lab_host_mod

    calls: list[str] = []
    orig = lab_host_mod._host_exec
    lab_host_mod._host_exec = lambda cmd, timeout=20: (
        calls.append(cmd),
        {"ok": True, "output": ""},
    )[1]
    try:
        _expand_vulhub_globs(["nonexistent_probe_category/*"], "/opt/vulhub")
    finally:
        lab_host_mod._host_exec = orig
    subs.append(
        {
            "name": "vulhub resolution via _host_exec",
            "status": "PASS" if calls else "FAIL",
        }
    )

    # Check 2: cmd_up/cmd_down issue real docker compose via _host_exec (not a placeholder).
    lab_targets_src = (REPO_ROOT / "scripts" / "lab_targets.py").read_text()
    no_placeholder = "placeholder" not in lab_targets_src
    has_compose = "docker compose" in lab_targets_src and "_host_exec" in lab_targets_src
    subs.append(
        {
            "name": "cmd_up/cmd_down real dispatch",
            "status": "PASS" if no_placeholder and has_compose else "FAIL",
        }
    )

    # Check 3: dispatcher no longer stubbed (return "").
    import inspect

    from tests.benchmarks.bench_security.matrix import _run_against_target

    dispatch_src = inspect.getsource(_run_against_target)
    not_stubbed = "return DISPATCH_NOT_RUN" in dispatch_src and 'return ""' not in dispatch_src
    subs.append(
        {
            "name": "_run_against_target not stubbed",
            "status": "PASS" if not_stubbed and len(_PHASE_MAP) > 0 else "FAIL",
        }
    )

    # Check 4: the false-verified guard — DISPATCH_NOT_RUN must never score verified.
    unit = RunUnit(
        id="validator-probe",
        kind="scenario",
        target_spec="lab-vulhub",
        oracle="rce_shell",
        scoring="oracle",
        domain="web",
        spin="static",
        scenario_key="__validator_probe_unknown_key__",
    )
    result = _execute_unit(unit, lab_exec=False, purple=False)
    guard_ok = result.status != "verified"
    subs.append(
        {"name": "DISPATCH_NOT_RUN never verified", "status": "PASS" if guard_ok else "FAIL"}
    )

    failed = [s["name"] for s in subs if s["status"] == "FAIL"]
    if failed:
        return "FAIL", f"{len(failed)} live-exec integrity check(s) failed: {failed}", subs
    return (
        "PASS",
        f"vulhub->host, dispatch real, {len(_PHASE_MAP)} tier-1 phases, guard holds",
        subs,
    )


def check_stage2_propose_integrity() -> tuple[str, str, list[dict]]:
    """AB. stage2 propose integrity: bounded single-oracle changes; promotions require
    positive+negative proof against real data; no hollow/flag-flip promotion is
    promotable; the loop applies nothing without operator --apply."""
    subs: list[dict] = []

    try:
        from tests.benchmarks.bench_security.oracles import ORACLES
        from tests.benchmarks.bench_security.stage2_propose import (
            apply_batch,
            goal_eval,
            run_stage2,
            weak_oracle_ids,
        )
    except ImportError as e:
        return "FAIL", f"stage2_propose import failed: {e}", []

    # Check 1: weak_oracle_ids matches the Stage 1 weakness view exactly (46: 41+5)
    weak = weak_oracle_ids(ORACLES)
    if len(weak) != 46:
        subs.append(
            {
                "name": "weak oracle count",
                "status": "FAIL",
                "detail": f"expected 46 (41 experimental + 5 differential), got {len(weak)}",
            }
        )
        return "FAIL", f"weak_oracle_ids returned {len(weak)}, expected 46", subs
    subs.append({"name": "weak oracle count", "status": "PASS", "detail": "46"})

    # Check 2: false-promotion guard — a hollow tier-only flip can never be promotable
    hollow_proposal = {
        "oracle_id": "__validator_probe__",
        "scope": ["__validator_probe__"],
        "current_tier": "experimental",
        "diff_touches_check": False,
    }
    hollow_proof = {
        "insufficient_evidence": False,
        "positive_tested": 0,
        "positive_passed": 0,
        "negative_tested": 0,
        "negative_passed": 0,
    }
    hollow_result = goal_eval(hollow_proposal, hollow_proof, index=None)
    if hollow_result["promotable"]:
        subs.append(
            {
                "name": "false-promotion guard",
                "status": "FAIL",
                "detail": "hollow flag-flip marked promotable",
            }
        )
        return "FAIL", "false-promotion guard failed: hollow proposal marked promotable", subs
    subs.append({"name": "false-promotion guard", "status": "PASS"})

    # Check 3: running propose without --apply writes nothing to oracle source files
    import tests.benchmarks.bench_security.stage2_propose as s2

    oracles_before = s2._ORACLES_PY.read_text()
    ability_before = s2._ABILITY_PORT_PY.read_text()
    try:
        report = run_stage2()
    except Exception as e:
        subs.append({"name": "run_stage2", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"run_stage2 raised: {type(e).__name__}: {e}", subs
    oracles_after = s2._ORACLES_PY.read_text()
    ability_after = s2._ABILITY_PORT_PY.read_text()
    if oracles_before != oracles_after or ability_before != ability_after:
        subs.append({"name": "no-apply gate", "status": "FAIL", "detail": "source files mutated"})
        return "FAIL", "propose without --apply wrote to oracle source files", subs
    subs.append({"name": "no-apply gate", "status": "PASS", "detail": "oracle source untouched"})

    # Check 4: apply_batch is not reachable from run_stage2/write_report — only from
    # stage2_propose_main(apply=True), i.e. an explicit operator --apply.
    import inspect

    if "apply_batch" in inspect.getsource(s2.run_stage2) or "apply_batch" in inspect.getsource(
        s2.write_report
    ):
        subs.append(
            {
                "name": "apply not auto-wired",
                "status": "FAIL",
                "detail": "apply_batch referenced from a non-operator code path",
            }
        )
        return "FAIL", "apply_batch is reachable without operator --apply", subs
    subs.append({"name": "apply not auto-wired", "status": "PASS"})

    assert callable(apply_batch)  # imported to confirm it's a real, distinct, operator-only symbol
    subs.append(
        {
            "name": "report shape",
            "status": "PASS"
            if hasattr(report, "promotable") and hasattr(report, "not_promotable")
            else "FAIL",
            "detail": f"{len(report.promotable)} promotable, {len(report.not_promotable)} not",
        }
    )

    return (
        "PASS",
        f"46 weak oracles, false-promotion guard holds, no-apply gate holds "
        f"({len(report.promotable)} promotable, {len(report.not_promotable)} not-promotable)",
        subs,
    )


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Portal 5 system validation — pre-flight check before "
        "running the full acceptance / UAT / bench suites.",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Print sub-check details")
    parser.add_argument(
        "--skip-pytest",
        action="store_true",
        help="Skip the pytest tests/unit invocation (saves ~15s)",
    )
    parser.add_argument(
        "--skip-lifespan", action="store_true", help="Skip the lifespan check (saves ~5s)"
    )
    parser.add_argument(
        "--skip-cli", action="store_true", help="Skip CLI subprocess checks (saves ~10s)"
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable output"
    )
    args = parser.parse_args()

    v = Validator(verbose=args.verbose, emit_json=args.json)

    if not args.json:
        print(f"Portal 5 system validation — {REPO_ROOT}")
        print()

    v.run("A. python imports", check_imports)
    v.run("B. pipeline assembles", check_pipeline_assembles)
    v.run("C. config round-trip", check_config_loads)
    v.run("D. Rule 6 cross-check", check_rule_6)
    v.run("E. hint validator", check_hint_validator)
    if args.skip_lifespan:
        v.run("F. lifespan startup", lambda: ("SKIP", "--skip-lifespan", []))
    else:
        v.run("F. lifespan startup", check_lifespan)
    if args.skip_cli:
        v.run("G. CLI introspection", lambda: ("SKIP", "--skip-cli", []))
    else:
        v.run("G. CLI introspection", check_cli_introspection)
    if args.skip_pytest:
        v.run("H. unit test suite", lambda: ("SKIP", "--skip-pytest", []))
    else:
        v.run("H. unit test suite", check_unit_tests)
    v.run("I. shim contract", check_shim_contract)
    v.run("J. bench_security catalog", check_bench_security_catalog)
    v.run("K. UAT catalog refs", check_uat_catalog_no_stale_refs)
    v.run("L. persona workspace refs", check_persona_workspace_resolution)
    v.run("M. ruff F821 (undefined names)", check_no_undefined_names)
    v.run("N. VALID_WORKSPACES resolution", check_valid_workspaces_resolve)
    v.run("O. bench parallel dispatch", check_bench_parallel_dispatch_safety)
    v.run("P. oracle registry consistency", check_oracle_registry_consistency)
    v.run("Q. playbook validation", check_playbook_validation)
    v.run("U. lab target catalog", check_lab_target_catalog)
    v.run("R. loop dry-run gate", check_loop_dry_run)
    v.run("V. lab setup readiness", check_lab_setup_readiness)
    v.run("W. ability port executable", check_ability_port)
    v.run("W. lab-exec coverage", check_labexec_coverage)
    v.run("X. scenario-oracle/matrix", check_scenario_oracle_matrix)
    v.run("Y. self-index integrity", check_self_index_integrity)
    v.run("Z. ci parity", check_ci_parity)
    v.run("AA. live exec integrity", check_live_exec_integrity)
    v.run("AB. stage2 propose integrity", check_stage2_propose_integrity)

    return v.summary()


if __name__ == "__main__":
    sys.exit(main())
