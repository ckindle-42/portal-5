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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

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
        r = CheckResult(name=name, status=status, detail=detail,
                        elapsed_ms=elapsed_ms, sub_results=sub)
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
                sub_icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "○", "WARN": "!"}.get(sub.get("status", ""), "·")
                print(f"      {sub_icon} {sub.get('name', '?')}: {sub.get('detail', '')}")

    def summary(self) -> int:
        passes = sum(1 for r in self.results if r.status == "PASS")
        fails = sum(1 for r in self.results if r.status == "FAIL")
        warns = sum(1 for r in self.results if r.status == "WARN")
        skips = sum(1 for r in self.results if r.status == "SKIP")
        total_ms = int((time.time() - self.started_at) * 1000)

        if self.emit_json:
            print(json.dumps({
                "elapsed_ms": total_ms,
                "passes": passes,
                "fails": fails,
                "warns": warns,
                "skips": skips,
                "results": [
                    {"name": r.name, "status": r.status, "detail": r.detail,
                     "elapsed_ms": r.elapsed_ms, "sub_results": r.sub_results}
                    for r in self.results
                ],
            }, indent=2))
        else:
            print()
            print(f"  {passes} pass · {fails} fail · {warns} warn · {skips} skip"
                  f"  ({total_ms}ms total)")
            if fails:
                print(f"  ⚠  System validation FAILED — fix the above before running"
                      f" acceptance / UAT / bench suites.", file=sys.stderr)
            else:
                print(f"  ✓ System validation passed — ready for full test suites.")

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
            subs.append({"name": m, "status": "FAIL",
                         "detail": f"{type(e).__name__}: {e}"})
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
    return "PASS", f"FastAPI app + all 9 routes registered", []


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
            capture_output=True, text=True, timeout=15,
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
            subs.append({"name": name, "status": "FAIL",
                         "detail": f"rc={result.returncode}: {err_summary}"})
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
    result = subprocess.run(args, capture_output=True, text=True,
                            timeout=120, cwd=str(REPO_ROOT))
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
        from tests.benchmarks.bench_security import (
            DEFAULT_WORKSPACES, EXECUTION_WORKSPACES,
        )
    except ImportError as e:
        return "SKIP", f"import: {e}", []

    cfg = load_portal_config()
    # Production auto-* security workspaces must all appear in DEFAULT_WORKSPACES.
    # Bench-* security workspaces are operator-triaged; not checked here.
    prod_sec = {
        ws_id for ws_id in cfg.workspaces
        if ws_id.startswith("auto-") and any(t in ws_id for t in ("sec", "pentest", "redteam", "blueteam", "purpleteam"))
    }
    missing = prod_sec - set(DEFAULT_WORKSPACES)
    if missing:
        return "FAIL", f"{len(missing)} prod security workspace(s) missing from bench: {sorted(missing)}", []
    return "PASS", f"all {len(prod_sec)} production security workspaces in DEFAULT_WORKSPACES", []


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
        from portal_pipeline.config import load_portal_config
        import tests.uat_catalog as cat
    except ImportError as e:
        return "SKIP", f"import: {e}", []

    cfg = load_portal_config()
    ws_mentioned = set()
    for attr in dir(cat):
        if not attr.startswith("g_"):
            continue
        mod = getattr(cat, attr)
        if hasattr(mod, "__file__"):
            src = open(mod.__file__).read()
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
        "app", "lifespan",
        "_validate_workspace_hints", "_model_supports_tools",
        "_inject_ollama_options", "_inject_attached_files",
        "_inject_system_prompt_append", "_inject_temporal_context",
        "_verify_key", "_verify_admin_key",
        "_try_non_streaming",
        "_resolve_persona_workspace", "_resolve_auto_routing",
        "_resolve_vision_fallback",
        "_detect_workspace", "_CODING_KEYWORDS", "_SPL_KEYWORDS",
        "chat_completions", "health", "metrics",
        "WORKSPACES", "_PERSONA_MAP",
        "PIPELINE_API_KEY", "_record_usage",
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


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Portal 5 system validation — pre-flight check before "
                    "running the full acceptance / UAT / bench suites.",
    )
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print sub-check details")
    parser.add_argument("--skip-pytest", action="store_true",
                        help="Skip the pytest tests/unit invocation (saves ~15s)")
    parser.add_argument("--skip-lifespan", action="store_true",
                        help="Skip the lifespan check (saves ~5s)")
    parser.add_argument("--skip-cli", action="store_true",
                        help="Skip CLI subprocess checks (saves ~10s)")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON instead of human-readable output")
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

    return v.summary()


if __name__ == "__main__":
    sys.exit(main())
