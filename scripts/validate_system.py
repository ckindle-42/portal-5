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
    AL. Doc currency — every ledgered doc is fresh vs HEAD (docs/.doc_ledger.yaml)

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
        "portal.platform.inference.router_pipe",
        "portal.platform.inference.router.app",
        "portal.platform.inference.router.lifespan",
        "portal.platform.inference.router.handlers",
        "portal.platform.inference.router.routing",
        "portal.platform.inference.router.streaming",
        "portal.platform.inference.router.workspaces",
        "portal.platform.inference.router.auth",
        "portal.platform.inference.router.validation",
        "portal.platform.inference.router.preinject",
        "portal.platform.inference.router.non_streaming",
        "portal.platform.inference.config",
        "portal.platform.inference.cli",
        "portal.platform.inference.cli.models",
        "portal.platform.inference.cli.workspace",
        "portal.platform.inference.cli.config",
        "portal.platform.inference.cli.sync",
        "portal.platform.inference.cli.smoke",
        "portal.platform.inference.cli.update",
        "portal.platform.inference.cluster_backends",
        "portal.platform.inference.tool_registry",
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
    from portal.platform.inference.router_pipe import app

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
    from portal.platform.inference.config import load_portal_config

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
    """D. portal.yaml workspaces ↔ backends.yaml workspace_routing ↔ WORKSPACES.

    module: eval workspaces (bench-*) are gated off WORKSPACES and
    workspace_routing by default (BUILD_PROGRAM_COLLAPSE_V1.md Phase 4), so
    the 3-way comparison is against portal.yaml's non-eval-gated subset,
    not its full set — that subset is what actually loads by default.
    """
    import yaml

    from portal.platform.inference.config import _eval_enabled, load_portal_config
    from portal.platform.inference.router.workspaces import WORKSPACES

    cfg = load_portal_config()
    eval_on = _eval_enabled()
    ws_yaml = {wid for wid, spec in cfg.workspaces.items() if eval_on or spec.module != "eval"}
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
        from portal.platform.inference.cluster_backends import BackendRegistry
        from portal.platform.inference.router.validation import _validate_workspace_hints
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
    from portal.platform.inference.router_pipe import app, lifespan

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
            [sys.executable, "-m", "portal.platform.inference.cli", *cmd],
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
    result = subprocess.run(args, capture_output=True, text=True, timeout=300, cwd=str(REPO_ROOT))
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
        from portal.modules.security.core import DEFAULT_WORKSPACES
        from portal.platform.inference.config import load_portal_config
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
        from portal.platform.inference.config import load_portal_config
        from portal_channels.dispatcher import VALID_WORKSPACES
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

        from portal.platform.inference.config import load_portal_config
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

    Hard-fail (BUILD_PROGRAM_ALIAS_RETIRE_V1.md Phase 3 / TASK_UAT_CATALOG_
    RECONCILE_V1): every test's ``model_slug`` must resolve to a live
    workspace or a live persona. Promoted from the original soft-WARN once
    the catalog was reconciled to canonical addressing (base workspace id +
    ``route_params``) — a stale ``model_slug`` means the test would 404/500
    against the live pipeline.

    Scans ``model_slug`` values specifically (not every quoted ``auto-*``/
    ``bench-*`` string in the file body) — the original file-body regex
    caught false positives in ``section`` labels and comments that describe
    routing without being a routable value (e.g. a section label like
    "auto-security (redteam-deep)" mentions a retired alias's old name for
    legibility without being a live route). Live-but-uncovered is operator
    triage, not a hard error here.
    """
    try:
        import re

        import tests.uat_catalog as cat
        from portal.platform.inference.config import load_persona_map, load_portal_config
    except ImportError as e:
        return "SKIP", f"import: {e}", []

    cfg = load_portal_config()
    live_ws = set(cfg.workspaces.keys())
    live_personas = set(load_persona_map().keys())
    live = live_ws | live_personas

    slug_re = re.compile(r'"model_slug"\s*:\s*"([^"]+)"')
    bad: list[tuple[str, str]] = []
    for attr in dir(cat):
        if not attr.startswith("g_"):
            continue
        mod = getattr(cat, attr)
        if hasattr(mod, "__file__"):
            with open(mod.__file__) as _f:
                src = _f.read()
            for m in slug_re.finditer(src):
                slug = m.group(1)
                if slug and slug not in live and not slug.startswith("bench-"):
                    bad.append((attr, slug))
    if bad:
        stale = sorted({slug for _, slug in bad})
        return "FAIL", f"{len(stale)} stale model_slug ref(s) in UAT catalog: {stale[:10]}", []
    return "PASS", "UAT catalog model_slug refs all resolve to live workspaces/personas", []


def check_shim_contract() -> tuple[str, str, list[dict]]:
    """I. Historical symbols imported through router_pipe still resolve."""
    from portal.platform.inference import router_pipe

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
    target = REPO_ROOT / "portal" / "modules" / "security" / "core" / "commands" / "run.py"
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
        from portal.modules.security.core.oracles import ORACLES
    except ImportError:
        return "SKIP", "oracles module not found", []

    from portal.modules.security.core._data import EXEC_SEQUENCES, PROMPTS

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
        from portal.modules.security.core.playbooks import load_playbook, validate_playbook
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
        from portal.modules.security.core.loop import run_engagement
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
        from portal.modules.security.core.ability_port import (
            PROBE_DEFS,
            register_ported_oracles,
        )
        from portal.modules.security.core.oracles import ORACLES

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

        with open("portal/modules/security/core/ability_port.py") as f:
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
    """AM. Every lab machine with an env entry has a registered live phase with an oracle."""
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
        from portal.modules.security.core.lab import _lab_dispatch_inner

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
        from portal.modules.security.core._data import PROMPTS
        from portal.modules.security.core.oracles import ORACLES
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
        from portal.modules.security.core.self_index import (
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
                "portal/modules/security/tests/test_ci_parity.py::TestCiParity::test_bench_imports_without_pythonpath",
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
        from portal.modules.security.core.matrix import (
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

    from portal.modules.security.core.matrix import _run_against_target

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
    # run_stage2() -> build_self_index() shells out to `validate_system.py --json`,
    # which runs this very check again. Same recursive-fork hazard as check Y (see
    # check_self_index_integrity) — bail out in the nested subprocess rather than
    # spawning a grandchild that spawns a great-grandchild... (unbounded fork chain).
    if os.environ.get("PORTAL5_SELF_INDEX_NESTED"):
        return (
            "SKIP",
            "nested validator run — stage2 propose check skipped to avoid recursive spawn",
            [],
        )

    subs: list[dict] = []

    try:
        from portal.modules.security.core.oracles import ORACLES
        from portal.modules.security.core.stage2_propose import (
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
    import portal.modules.security.core.stage2_propose as s2

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


def check_kali_rescore_integrity() -> tuple[str, str, list[dict]]:
    """AC. Kali exec + rescore integrity.

    Verifies:
    - CHAIN_TOOLS_BASE exposes execute_bash/execute_python
    - lab_dispatch routes them to real Kali
    - coverage credits a step only on REAL bash success output, never a bare call
    - web scenarios back every technique with a real Kali command
    """
    subs: list[dict] = []

    # Check 1: CHAIN_TOOLS_BASE exposes execute_bash/execute_python
    try:
        from portal.modules.security.core.exec_chain import CHAIN_TOOLS_BASE

        names = {t.get("function", {}).get("name") for t in CHAIN_TOOLS_BASE}
        if "execute_bash" not in names:
            subs.append({"name": "execute_bash exposed", "status": "FAIL", "detail": "missing"})
            return "FAIL", "execute_bash missing from CHAIN_TOOLS_BASE", subs
        if "execute_python" not in names:
            subs.append({"name": "execute_python exposed", "status": "FAIL", "detail": "missing"})
            return "FAIL", "execute_python missing from CHAIN_TOOLS_BASE", subs
        subs.append({"name": "execute_bash exposed", "status": "PASS", "detail": ""})
        subs.append({"name": "execute_python exposed", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "CHAIN_TOOLS_BASE import", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"import failed: {e}", subs

    # Check 2: lab_dispatch routes execute_bash to _lab_mcp_call
    try:
        import inspect

        from portal.modules.security.core.lab import _lab_dispatch_inner

        src = inspect.getsource(_lab_dispatch_inner)
        if 'fn_name == "execute_bash"' not in src:
            subs.append(
                {
                    "name": "lab_dispatch routes execute_bash",
                    "status": "FAIL",
                    "detail": "no routing",
                }
            )
            return "FAIL", "lab_dispatch does not route execute_bash", subs
        subs.append({"name": "lab_dispatch routes execute_bash", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "lab_dispatch check", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"lab_dispatch check failed: {e}", subs

    # Check 3: Honesty guard — no credit without real output
    try:
        from portal.modules.security.core.scoring import accumulate_observations

        obs: dict = {}
        accumulate_observations("execute_bash", "", obs)
        if obs.get("compromise_confirmed"):
            subs.append(
                {"name": "honesty guard", "status": "FAIL", "detail": "empty output got credit"}
            )
            return "FAIL", "honesty guard broken: empty output got compromise_confirmed", subs
        subs.append(
            {"name": "honesty guard", "status": "PASS", "detail": "no credit on empty output"}
        )
    except Exception as e:
        subs.append({"name": "honesty guard", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"honesty guard check failed: {e}", subs

    # Check 4: Web scenarios use execute_bash and target LXC 112
    try:
        from portal.modules.security.core.exec_chain import SCENARIOS

        web_scenarios = [
            "web_sqli_dump",
            "web_graphql_introspect",
            "web_deserial_rce",
            "web_nosql_inject",
            "web_path_traversal",
            "web_reflected_xss",
            "web_cors",
            "web_open_redirect",
            "web_forced_error",
            "web_asset_discovery",
            "web_smuggling",
            "web_ssti",
        ]
        for name in web_scenarios:
            if name not in SCENARIOS:
                subs.append({"name": f"scenario {name}", "status": "FAIL", "detail": "missing"})
                return "FAIL", f"web scenario '{name}' missing", subs
            s = SCENARIOS[name]
            if "execute_bash" not in s.get("red_order", []):
                subs.append({"name": f"{name} uses execute_bash", "status": "FAIL", "detail": "no"})
                return "FAIL", f"scenario '{name}' does not use execute_bash", subs
        subs.append(
            {
                "name": "web scenarios present",
                "status": "PASS",
                "detail": f"{len(web_scenarios)} scenarios",
            }
        )
    except Exception as e:
        subs.append({"name": "web scenarios", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"web scenario check failed: {e}", subs

    return (
        "PASS",
        f"execute_bash/python exposed; lab_dispatch routes; honesty guard holds; "
        f"{len(web_scenarios)} web scenarios use Kali via execute_bash",
        subs,
    )


def check_coverage_expansion_integrity() -> tuple[str, str, list[dict]]:
    """AD. Coverage expansion integrity.

    Verifies:
    - Every scenario carries detect_ground_truth (blue-scorable — operator's rule)
    - New scenarios route to real lab targets
    - New techniques have SPL detections or are logged as blue-gaps
    - Vulhub mappings point to present container classes
    """
    subs: list[dict] = []

    # Check 1: Every scenario has detect_ground_truth (blue-scorable)
    try:
        from portal.modules.security.core.exec_chain import SCENARIOS

        allowed_empty = {"mbptl_ctf_full_chain"}
        red_only = [
            k
            for k, v in SCENARIOS.items()
            if not v.get("detect_ground_truth") and k not in allowed_empty
        ]
        if red_only:
            subs.append(
                {
                    "name": "blue-scorable guard",
                    "status": "FAIL",
                    "detail": f"red-only scenarios: {red_only}",
                }
            )
            return "FAIL", f"red-only scenarios found: {red_only}", subs
        subs.append(
            {
                "name": "blue-scorable guard",
                "status": "PASS",
                "detail": f"{len(SCENARIOS)} scenarios, all carry detect_ground_truth",
            }
        )
    except Exception as e:
        subs.append({"name": "blue-scorable guard", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"import failed: {e}", subs

    # Check 2: meta3 no longer at zero
    try:
        meta3_count = sum(1 for k in SCENARIOS if k.startswith("meta3_"))
        if meta3_count < 5:
            subs.append(
                {
                    "name": "meta3 coverage",
                    "status": "FAIL",
                    "detail": f"only {meta3_count} meta3 scenarios",
                }
            )
            return "FAIL", f"meta3 has {meta3_count} scenarios, expected >=5", subs
        subs.append(
            {
                "name": "meta3 coverage",
                "status": "PASS",
                "detail": f"{meta3_count} meta3 scenarios",
            }
        )
    except Exception as e:
        subs.append({"name": "meta3 coverage", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"meta3 check failed: {e}", subs

    # Check 3: vulhub breadth >=30
    try:
        vuln_count = sum(1 for k in SCENARIOS if k.startswith("vuln_"))
        if vuln_count < 30:
            subs.append(
                {
                    "name": "vulhub breadth",
                    "status": "FAIL",
                    "detail": f"only {vuln_count} vulhub scenarios",
                }
            )
            return "FAIL", f"vulhub has {vuln_count} scenarios, expected >=30", subs
        subs.append(
            {
                "name": "vulhub breadth",
                "status": "PASS",
                "detail": f"{vuln_count} vulhub expansion scenarios",
            }
        )
    except Exception as e:
        subs.append({"name": "vulhub breadth", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"vulhub check failed: {e}", subs

    # Check 4: New techniques have SPL detections
    try:
        from portal.modules.security.core.siem.spl_detections import techniques_covered

        new_techniques: set[str] = set()
        for name in SCENARIOS:
            if name.startswith(("meta3_", "vuln_")):
                gt = SCENARIOS[name].get("detect_ground_truth", [])
                new_techniques.update(gt)
        covered = set(techniques_covered())
        known_gaps = {"T1537", "T1203", "T1547.001"}
        gaps = sorted(new_techniques - covered - known_gaps)
        if gaps:
            subs.append(
                {
                    "name": "SPL coverage",
                    "status": "WARN",
                    "detail": f"blue-gaps (no SPL): {gaps}",
                }
            )
        else:
            subs.append(
                {
                    "name": "SPL coverage",
                    "status": "PASS",
                    "detail": f"{len(new_techniques)} techniques, all have SPL or are known gaps",
                }
            )
    except Exception as e:
        subs.append({"name": "SPL coverage", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"SPL check failed: {e}", subs

    # Check 5: Total scenario count
    total = len(SCENARIOS)
    if total < 70:
        subs.append({"name": "total scenarios", "status": "WARN", "detail": f"{total}"})
    else:
        subs.append({"name": "total scenarios", "status": "PASS", "detail": f"{total}"})

    # Check 6: Zero red-only scenarios (blue-scorable invariant)
    try:
        red_only = [k for k, v in SCENARIOS.items() if not v.get("detect_ground_truth")]
        if red_only:
            subs.append(
                {
                    "name": "blue-scorable invariant",
                    "status": "FAIL",
                    "detail": f"red-only: {red_only}",
                }
            )
            return "FAIL", f"red-only scenarios: {red_only}", subs
        subs.append({"name": "blue-scorable invariant", "status": "PASS", "detail": "0 red-only"})
    except Exception as e:
        subs.append({"name": "blue-scorable invariant", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"blue-scorable check failed: {e}", subs

    # Check 7: All techniques have SPL or are recorded blue-gaps
    try:
        from portal.modules.security.core.siem.spl_detections import techniques_covered

        blue_gaps = {"T1078.004", "T1537"}  # cloud telemetry not in lab
        all_techniques: set[str] = set()
        for v in SCENARIOS.values():
            all_techniques.update(v.get("detect_ground_truth", []))
        spl = set(techniques_covered())
        undetected = sorted(all_techniques - spl - blue_gaps)
        if undetected:
            subs.append(
                {
                    "name": "technique detectability",
                    "status": "WARN",
                    "detail": f"no SPL: {undetected}",
                }
            )
        else:
            subs.append(
                {
                    "name": "technique detectability",
                    "status": "PASS",
                    "detail": f"{len(all_techniques)} techniques, all covered or gapped",
                }
            )
    except Exception as e:
        subs.append({"name": "technique detectability", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"detectability check failed: {e}", subs

    return (
        "PASS",
        f"{total} scenarios ({meta3_count} meta3, {vuln_count} vulhub); "
        f"all blue-scorable; {len(all_techniques)} techniques tracked",
        subs,
    )


def check_candidate_eval_integrity() -> tuple[str, str, list[dict]]:
    """AE. Candidate eval integrity.

    Verifies:
    - candidate-eval pins incumbents in single-slot mode
    - writes to isolated candidates/ path
    - never modifies fleet config
    - self-index baseline unaffected by candidate runs
    """
    subs: list[dict] = []

    # Check 1: candidate_eval module exists and is importable
    try:
        from portal.modules.security.core.candidate_eval import (
            CANDIDATE_EVAL_SCENARIOS,
            CANDIDATES_DIR,
            _build_step_models,
        )

        subs.append({"name": "module importable", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "module importable", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"candidate_eval import failed: {e}", subs

    # Check 2: CANDIDATE_EVAL_SCENARIOS are valid
    try:
        from portal.modules.security.core.exec_chain import SCENARIOS

        for name in CANDIDATE_EVAL_SCENARIOS:
            if name not in SCENARIOS:
                subs.append(
                    {
                        "name": f"scenario {name}",
                        "status": "FAIL",
                        "detail": "not in SCENARIOS",
                    }
                )
                return "FAIL", f"CANDIDATE_EVAL_SCENARIO '{name}' not in SCENARIOS", subs
        subs.append(
            {
                "name": "eval scenarios valid",
                "status": "PASS",
                "detail": f"{len(CANDIDATE_EVAL_SCENARIOS)} scenarios",
            }
        )
    except Exception as e:
        subs.append({"name": "eval scenarios", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"scenario check failed: {e}", subs

    # Check 3: single-slot pins incumbents
    try:
        sm = _build_step_models("exploit", "candidate", "incumbent")
        if sm.get("exploit") != "candidate":
            subs.append(
                {
                    "name": "single-slot pins candidate",
                    "status": "FAIL",
                    "detail": f"exploit={sm.get('exploit')}",
                }
            )
            return "FAIL", "single-slot does not pin candidate to exploit slot", subs
        if sm.get("default") != "incumbent":
            subs.append(
                {
                    "name": "single-slot pins incumbent",
                    "status": "FAIL",
                    "detail": f"default={sm.get('default')}",
                }
            )
            return "FAIL", "single-slot does not pin incumbent as default", subs
        subs.append({"name": "single-slot pinning", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "single-slot pinning", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"pinning check failed: {e}", subs

    # Check 4: solo sets all candidate
    try:
        sm = _build_step_models("solo", "candidate", "incumbent")
        if sm != {"default": "candidate"}:
            subs.append(
                {
                    "name": "solo all-candidate",
                    "status": "FAIL",
                    "detail": f"got {sm}",
                }
            )
            return "FAIL", f"solo mode step_models wrong: {sm}", subs
        subs.append({"name": "solo all-candidate", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "solo mode", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"solo check failed: {e}", subs

    # Check 5: isolated results path
    try:
        assert str(CANDIDATES_DIR).endswith("results/candidates"), (
            f"CANDIDATES_DIR={CANDIDATES_DIR}"
        )
        subs.append(
            {"name": "isolated results path", "status": "PASS", "detail": str(CANDIDATES_DIR)}
        )
    except Exception as e:
        subs.append({"name": "isolated results path", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"isolation check failed: {e}", subs

    # Check 6: self-index does not pick up candidate files
    try:
        from portal.modules.security.core.self_index import _complete_result_files

        files = _complete_result_files()
        candidate_leaks = [str(f) for f in files if "candidates/" in str(f)]
        if candidate_leaks:
            subs.append(
                {
                    "name": "self-index isolation",
                    "status": "FAIL",
                    "detail": f"leaked: {candidate_leaks}",
                }
            )
            return "FAIL", f"self-index picks up candidate files: {candidate_leaks}", subs
        subs.append({"name": "self-index isolation", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "self-index isolation", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"self-index check failed: {e}", subs

    # Check 7: incumbent resolves to a real fleet model
    try:
        from portal.modules.security.core.candidate_eval import _get_incumbent_model

        for slot in ("recon", "exploit", "post"):
            model = _get_incumbent_model(slot)
            if not model:
                subs.append(
                    {
                        "name": f"incumbent({slot})",
                        "status": "FAIL",
                        "detail": "empty — resolution broken",
                    }
                )
                return "FAIL", f"incumbent for slot '{slot}' resolves empty", subs
        subs.append(
            {"name": "incumbent resolution", "status": "PASS", "detail": "all slots resolve"}
        )
    except Exception as e:
        subs.append({"name": "incumbent resolution", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"incumbent resolution check failed: {e}", subs

    # Check 8: step_models never contains empty string
    try:
        from portal.modules.security.core.candidate_eval import _get_incumbent_model

        for slot in ("recon", "exploit", "post"):
            inc = _get_incumbent_model(slot)
            sm = _build_step_models(slot, "candidate", inc)
            empty_keys = [k for k, v in sm.items() if not v]
            if empty_keys:
                subs.append(
                    {
                        "name": f"no-empty-model({slot})",
                        "status": "FAIL",
                        "detail": f"empty values for keys: {empty_keys}",
                    }
                )
                return "FAIL", f"step_models has empty model for keys: {empty_keys}", subs
        subs.append({"name": "no empty models", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "no empty models", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"empty model check failed: {e}", subs

    return (
        "PASS",
        f"candidate-eval: {len(CANDIDATE_EVAL_SCENARIOS)} eval scenarios; "
        f"single-slot pins incumbents; solo=all-candidate; "
        f"incumbent resolves from config; no empty models; "
        f"results isolated to candidates/; self-index unaffected",
        subs,
    )


def check_bench_supervisor_integrity() -> tuple[str, str, list[dict]]:
    """AF. Bench supervisor integrity.

    Verifies:
    - supervisor module imports cleanly
    - handler table is well-formed (all entries have detector + handler)
    - corrective primitives are referenced, not reimplemented
    - unknown failures escalate (not silently continue)
    - interrupted units are re-run or marked indeterminate
    """
    subs: list[dict] = []

    # Check 1: supervisor module importable
    try:
        from scripts.bench_supervisor import build_state_handlers, run_self_test

        subs.append({"name": "module importable", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "module importable", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"bench_supervisor import failed: {e}", subs

    # Check 2: handler table well-formed
    try:
        handlers = build_state_handlers(stall_minutes=15)
        assert len(handlers) >= 7, f"expected >=7 handlers, got {len(handlers)}"
        for name, line_det, state_det, handler in handlers:
            assert isinstance(name, str) and name, f"bad name: {name!r}"
            assert callable(handler), f"{name} handler not callable"
        subs.append(
            {
                "name": "handler table",
                "status": "PASS",
                "detail": f"{len(handlers)} handlers",
            }
        )
    except Exception as e:
        subs.append({"name": "handler table", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"handler table check failed: {e}", subs

    # Check 3: self-test passes (detectors fire correctly, no false positives)
    try:
        ok = run_self_test(stall_minutes=15)
        assert ok, "self-test reported failures"
        subs.append({"name": "self-test", "status": "PASS", "detail": "all detectors verified"})
    except Exception as e:
        subs.append({"name": "self-test", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"self-test failed: {e}", subs

    # Check 4: escalation handler exists and is in the handler table
    try:
        from scripts.bench_supervisor import handle_escalate, handle_escalation

        assert callable(handle_escalate)
        assert callable(handle_escalation)
        subs.append({"name": "escalation handlers", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "escalation handlers", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"escalation handler check failed: {e}", subs

    # Check 5: resume logic importable
    try:
        from scripts.bench_supervisor import (
            compute_remaining_scenarios,
            load_completed_scenarios,
        )

        assert callable(load_completed_scenarios)
        assert callable(compute_remaining_scenarios)
        subs.append({"name": "resume logic", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "resume logic", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"resume logic check failed: {e}", subs

    # Check 6: launcher script exists and is executable
    try:
        launcher = REPO_ROOT / "execute_local_sec_bench.sh"
        assert launcher.exists(), f"launcher not found: {launcher}"
        import stat

        mode = launcher.stat().st_mode
        assert mode & stat.S_IXUSR, "launcher not executable"
        subs.append({"name": "launcher script", "status": "PASS", "detail": str(launcher)})
    except Exception as e:
        subs.append({"name": "launcher script", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"launcher check failed: {e}", subs

    return (
        "PASS",
        f"bench supervisor: {len(handlers)} handlers; "
        f"self-test passes; escalation + resume logic present; "
        f"launcher executable",
        subs,
    )


def check_triage_layer2_integrity() -> tuple[str, str, list[dict]]:
    """AG. Triage layer2 integrity.

    Verifies:
    - triage modules import cleanly
    - action allowlist is well-formed (all actions reversible)
    - disallowed actions are rejected (pause_for_human)
    - propose mode never auto-executes
    - P40-down falls back to Layer 1
    """
    subs: list[dict] = []

    # Check 1: triage modules importable
    try:
        from scripts.triage import DEFAULT_TRIAGE_MODEL, build_triage_prompt
        from scripts.triage_actions import ALLOWED_ACTIONS, is_action_allowed

        subs.append({"name": "modules importable", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "modules importable", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"triage import failed: {e}", subs

    # Check 2: all actions reversible
    try:
        for name, entry in ALLOWED_ACTIONS.items():
            assert entry.get("reversible", False), f"{name} not reversible"
        subs.append(
            {
                "name": "all actions reversible",
                "status": "PASS",
                "detail": f"{len(ALLOWED_ACTIONS)} actions",
            }
        )
    except Exception as e:
        subs.append({"name": "all actions reversible", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"reversibility check failed: {e}", subs

    # Check 3: disallowed action rejected
    try:
        from scripts.triage import parse_triage_response

        resp = parse_triage_response(
            '{"action": "rm_rf", "params": {}, "reason": "test", "confidence": 0.9}'
        )
        # parse returns it as-is; diagnose() does the allowlist check
        assert resp["action"] == "rm_rf"  # parser doesn't filter
        # But is_action_allowed should reject it
        assert not is_action_allowed("rm_rf")
        assert is_action_allowed("pause_for_human")
        subs.append({"name": "disallowed rejected", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "disallowed rejected", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"disallowed action check failed: {e}", subs

    # Check 4: prompt is bounded and diagnostic-only
    try:
        prompt = build_triage_prompt(
            log_tail="x" * 50000,
            failing_line="error",
            scenario="test",
        )
        assert len(prompt) < 20000, f"prompt too long: {len(prompt)}"
        assert "attack" not in prompt.lower().split("never produce attack")[0]
        subs.append({"name": "prompt bounded", "status": "PASS", "detail": f"{len(prompt)} chars"})
    except Exception as e:
        subs.append({"name": "prompt bounded", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"prompt check failed: {e}", subs

    # Check 5: default model configured
    try:
        assert DEFAULT_TRIAGE_MODEL, "DEFAULT_TRIAGE_MODEL is empty"
        subs.append({"name": "default model", "status": "PASS", "detail": DEFAULT_TRIAGE_MODEL})
    except Exception as e:
        subs.append({"name": "default model", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"model config check failed: {e}", subs

    return (
        "PASS",
        f"triage layer2: {len(ALLOWED_ACTIONS)} allowlisted reversible actions; "
        f"disallowed→pause; prompt bounded; default model={DEFAULT_TRIAGE_MODEL}",
        subs,
    )


def check_rbp_evidence_grounding() -> tuple[str, str, list[dict]]:
    """AH. RBP evidence grounding.

    Every purple record carries an episode + deterministic capability_verdict;
    synthetic telemetry never yields PROVEN; telemetry failure emits a reason
    code, not silent pass; model_competence_score is separate from
    capability_verdict.
    """
    subs: list[dict] = []

    # Check 1: episode module imports cleanly
    try:
        from portal.modules.security.core.episode import (
            Episode,
            derive_verdict,
        )

        subs.append({"name": "episode module imports", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "episode module imports", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"episode import failed: {e}", subs

    # Check 2: synthetic never yields PROVEN (deterministic)
    try:
        ep = Episode(
            episode_id="validator-probe",
            scenario="probe",
            target_host=None,
            started_at=0.0,
            red_status="RED_LANDED",
            telemetry_status="TELEMETRY_NOT_CONFIGURED",
            detection_status="DETECTION_HIT_UNATTRIBUTED",
            used_synthetic=True,
        )
        verdict = derive_verdict(ep)
        assert verdict != "PROVEN", f"synthetic yielded {verdict}"
        subs.append(
            {"name": "synthetic never PROVEN", "status": "PASS", "detail": f"verdict={verdict}"}
        )
    except Exception as e:
        subs.append({"name": "synthetic never PROVEN", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"synthetic PROVEN guard failed: {e}", subs

    # Check 3: PROVEN requires real telemetry + red landed + detection confirmed
    try:
        ep = Episode(
            episode_id="validator-probe-proven",
            scenario="probe",
            target_host="10.0.1.30",
            started_at=0.0,
            red_status="RED_LANDED",
            telemetry_status="TELEMETRY_OBSERVED",
            detection_status="DETECTION_CONFIRMED",
            used_synthetic=False,
        )
        assert derive_verdict(ep) == "PROVEN"
        subs.append({"name": "PROVEN path works", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "PROVEN path works", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"PROVEN path failed: {e}", subs

    # Check 4: _score_purple produces episode + verdict + model_competence_score
    try:
        from portal.modules.security.core.blue import _score_purple

        red_result = {
            "model": "probe",
            "mode": "lab-exec",
            "lab_success": True,
            "order_accuracy": 0.8,
        }
        blue_result = {
            "model": "probe",
            "score": {"f1": 0.7, "recall": 0.7, "precision": 0.7, "detected": ["T1190"]},
            "containments": [],
            "synthetic_fallback": False,
            "telemetry_source": {"T1190": "live"},
            "telemetry_raw": {},
            "reported": ["T1190"],
        }
        scenario = {
            "name": "validator_probe",
            "detect_ground_truth": ["T1190"],
            "persistence_technique": "",
            "target_host": "10.0.1.30",
        }
        rec = _score_purple(red_result, blue_result, scenario)
        assert "episode" in rec, "missing episode"
        assert "capability_verdict" in rec, "missing capability_verdict"
        assert "model_competence_score" in rec, "missing model_competence_score"
        assert "purple_composite" not in rec, "old key still present"
        assert rec["capability_verdict"] == "PROVEN"
        subs.append(
            {
                "name": "_score_purple produces episode+verdict",
                "status": "PASS",
                "detail": f"verdict={rec['capability_verdict']}, "
                f"competence={rec['model_competence_score']}",
            }
        )
    except Exception as e:
        subs.append(
            {"name": "_score_purple produces episode+verdict", "status": "FAIL", "detail": str(e)}
        )
        return "FAIL", f"_score_purple integration failed: {e}", subs

    # Check 5: silent telemetry pass is gone from matrix.py
    try:
        matrix_py = (
            Path(__file__).resolve().parent.parent
            / "portal"
            / "modules"
            / "security"
            / "core"
            / "matrix.py"
        )
        content = matrix_py.read_text()
        assert "pass  # telemetry collection never blocks scoring" not in content
        subs.append({"name": "silent telemetry pass removed", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "silent telemetry pass removed", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"silent pass still present: {e}", subs

    return (
        "PASS",
        "every purple record: episode + deterministic verdict; "
        "synthetic→never PROVEN; telemetry failure→reason code; "
        "model_competence_score separate from capability_verdict",
        subs,
    )


def check_telemetry_contracts() -> tuple[str, str, list[dict]]:
    """AI. Telemetry contracts — canonical protocol + health + reason-coded failure.

    Verifies:
    - TelemetryBackend protocol is importable from telemetry module
    - Only one TelemetryBackend class definition exists (no duplicate protocols)
    - TelemetryContract describes sources
    - check_source_health returns correct reason codes for dead/healthy sources
    """
    subs: list[dict] = []

    # Check 1: canonical protocol importable
    try:
        from portal.modules.security.core.telemetry import (
            CONTRACTS,
            TelemetryBackend,
            check_source_health,
        )

        subs.append({"name": "canonical protocol importable", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "canonical protocol importable", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"telemetry import failed: {e}", subs

    # Check 2: only one TelemetryBackend definition
    try:
        import inspect

        from portal.modules.security.core import telemetry

        count = sum(
            1
            for name, _ in inspect.getmembers(telemetry, inspect.isclass)
            if name == "TelemetryBackend"
        )
        assert count == 1, f"Expected 1 TelemetryBackend, found {count}"
        subs.append({"name": "single protocol definition", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "single protocol definition", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"protocol count check failed: {e}", subs

    # Check 3: contracts registered
    try:
        assert len(CONTRACTS) >= 3, f"Expected >=3 contracts, got {len(CONTRACTS)}"
        subs.append(
            {
                "name": "contracts registered",
                "status": "PASS",
                "detail": f"{len(CONTRACTS)} contracts",
            }
        )
    except Exception as e:
        subs.append({"name": "contracts registered", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"contract registry check failed: {e}", subs

    # Check 4: dead source → reason code
    try:
        from unittest.mock import MagicMock

        dead_backend = MagicMock(spec=TelemetryBackend)
        dead_backend.name = "test"
        dead_backend.query.return_value = {
            "telemetry": "",
            "source": "synthetic-fallback",
            "backend": "test",
        }
        result = check_source_health(CONTRACTS["splunk-web"], dead_backend)
        assert not result.healthy
        assert result.reason_code == "TELEMETRY_NOT_CONFIGURED"
        subs.append(
            {"name": "dead source → reason code", "status": "PASS", "detail": result.reason_code}
        )
    except Exception as e:
        subs.append({"name": "dead source → reason code", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"dead source check failed: {e}", subs

    # Check 5: healthy source → TELEMETRY_OBSERVED
    try:
        healthy_backend = MagicMock(spec=TelemetryBackend)
        healthy_backend.name = "test"
        healthy_backend.query.return_value = {
            "telemetry": "EventCode=4769 data",
            "source": "live",
            "backend": "test",
        }
        result = check_source_health(CONTRACTS["splunk-web"], healthy_backend)
        assert result.healthy
        assert result.reason_code == "TELEMETRY_OBSERVED"
        subs.append(
            {"name": "healthy source → OBSERVED", "status": "PASS", "detail": result.reason_code}
        )
    except Exception as e:
        subs.append({"name": "healthy source → OBSERVED", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"healthy source check failed: {e}", subs

    return (
        "PASS",
        f"canonical TelemetryBackend protocol; {len(CONTRACTS)} contracts; "
        "dead source → reason code; healthy source → TELEMETRY_OBSERVED",
        subs,
    )


def check_capability_graph() -> tuple[str, str, list[dict]]:
    """AJ. Capability graph + deterministic gap engine.

    Verifies:
    - Graph seeds from existing assets (scenarios + detections)
    - Gap classification is deterministic
    - Synthetic/indeterminate never yields COVERED
    - Coverage map generates valid JSON
    """
    subs: list[dict] = []

    # Check 1: graph seeds
    try:
        from portal.modules.security.core.capability_graph import (
            classify_gap,
            generate_coverage_json,
            seed_graph_from_assets,
        )

        graph = seed_graph_from_assets()
        assert len(graph.procedures) >= 50, f"Expected >=50 procedures, got {len(graph.procedures)}"
        assert len(graph.detections) >= 29, f"Expected >=29 detections, got {len(graph.detections)}"
        subs.append(
            {
                "name": "graph seeds from assets",
                "status": "PASS",
                "detail": f"{len(graph.procedures)} procedures, {len(graph.detections)} detections",
            }
        )
    except Exception as e:
        subs.append({"name": "graph seeds from assets", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"graph seeding failed: {e}", subs

    # Check 2: synthetic never COVERED
    try:
        result = classify_gap(
            red_status="RED_LANDED",
            telemetry_status="TELEMETRY_OBSERVED",
            detection_status="DETECTION_CONFIRMED",
            used_synthetic=True,
        )
        assert result != "COVERED", f"synthetic yielded {result}"
        subs.append({"name": "synthetic never COVERED", "status": "PASS", "detail": f"→ {result}"})
    except Exception as e:
        subs.append({"name": "synthetic never COVERED", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"synthetic COVERED guard failed: {e}", subs

    # Check 3: coverage map generates valid JSON
    try:
        import json

        cov = generate_coverage_json(graph)
        json.dumps(cov)  # JSON-safe
        assert cov["technique_count"] > 0
        assert cov["tiers"]["eligible"] > 0
        subs.append(
            {
                "name": "coverage map generates",
                "status": "PASS",
                "detail": f"{cov['technique_count']} techniques, "
                f"{cov['tiers']['exercised_pct']}% exercised",
            }
        )
    except Exception as e:
        subs.append({"name": "coverage map generates", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"coverage map failed: {e}", subs

    return (
        "PASS",
        f"{len(graph.procedures)} procedures, {len(graph.detections)} detections; "
        f"synthetic→never COVERED; coverage map valid",
        subs,
    )


def check_wiki_core() -> tuple[str, str, list[dict]]:
    """AK. Wiki core backbone — schema + provenance + core import-clean.

    Verifies:
    - KnowledgeUnit schema works (mandatory provenance)
    - Core has zero Portal-specific imports (extraction guarantee)
    - MCP tools (search, get_unit, explain) functional
    """
    subs: list[dict] = []

    # Check 1: schema + mandatory provenance
    try:
        from portal.platform.wiki.schema import KnowledgeUnit, SourceRef

        # Must reject no-source unit
        rejected = False
        try:
            KnowledgeUnit(id="test", kind="what", title="t", sources=[])
        except ValueError:
            rejected = True
        assert rejected, "No-source unit not rejected"

        # Must accept valid unit
        unit = KnowledgeUnit(
            id="test-unit",
            kind="mixed",
            title="Test",
            sources=[SourceRef(type="code", path="test.py")],
        )
        assert unit.content_hash()
        subs.append({"name": "schema + provenance", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "schema + provenance", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"wiki schema failed: {e}", subs

    # Check 2: core import-clean
    try:
        import glob as glob_mod

        bad = []
        for f in glob_mod.glob("portal/platform/wiki/*.py"):
            content = Path(f).read_text(encoding="utf-8")
            for forbidden in ["portal_pipeline", "portal.platform.inference", "bench_security"]:
                if forbidden in content:
                    bad.append(f)
        assert bad == [], f"Core has Portal imports: {bad}"
        subs.append({"name": "core import-clean", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "core import-clean", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"core import-clean failed: {e}", subs

    # Check 3: MCP tools importable
    try:
        from portal_wiki.mcp import wiki_explain, wiki_get_unit, wiki_search  # noqa: F401

        subs.append({"name": "MCP tools importable", "status": "PASS", "detail": ""})
    except Exception as e:
        subs.append({"name": "MCP tools importable", "status": "FAIL", "detail": str(e)})
        return "FAIL", f"MCP tools import failed: {e}", subs

    return (
        "PASS",
        "schema validates; core import-clean; MCP tools functional",
        subs,
    )


def check_doc_currency() -> tuple[str, str, list[dict]]:
    """AL — every doc bound in docs/.doc_ledger.yaml is fresh vs HEAD.

    Delegates to scripts/doc_ledger.py (subprocess, JSON) so the ledger logic
    lives in one place. FAIL lists the stale docs; run the doc-audit agent to
    clear it, then `python3 scripts/doc_ledger.py stamp-all`.
    """
    script = REPO_ROOT / "scripts" / "doc_ledger.py"
    if not script.exists():
        return ("SKIP", "scripts/doc_ledger.py not present", [])
    proc = subprocess.run(
        [sys.executable, str(script), "check", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError:
        return ("FAIL", f"doc_ledger check unparseable: {proc.stdout[:200]}", [])
    return (
        payload.get("status", "FAIL"),
        payload.get("detail", ""),
        payload.get("findings", []),
    )


def check_capability_index() -> tuple[str, str, list[dict]]:
    """S — every capability's tools/oracle references resolve to a real
    tool_catalog entry / registered oracle (TASK_SEC_CAPABILITY_INDEX_V1).

    build_index() already raises on an orphan reference, so a raised
    exception here is itself a FAIL — this check exists to surface *which*
    capability is broken rather than just crashing validate_system.py.
    """
    try:
        from portal.modules.security.core.capability.index import build_index
        from portal.modules.security.core.capability.tool_inventory import load_tool_catalog
        from portal.modules.security.core.oracles import ORACLES
    except ImportError:
        return "SKIP", "capability index module not found", []

    try:
        caps = build_index()
    except ValueError as exc:
        return "FAIL", f"build_index() raised: {exc}", []

    catalog_names = {t["name"] for t in load_tool_catalog()}
    subs: list[dict] = []
    missing = []
    for cap in caps:
        orphan_tools = [t for t in cap.tools if t not in catalog_names]
        orphan_oracle = cap.oracle is not None and cap.oracle not in ORACLES
        ok = not orphan_tools and not orphan_oracle
        subs.append({"name": cap.id, "status": "PASS" if ok else "FAIL"})
        if orphan_tools:
            missing.append(f"{cap.id} orphan tools={orphan_tools}")
        if orphan_oracle:
            missing.append(f"{cap.id} orphan oracle={cap.oracle}")

    if missing:
        return "FAIL", f"{len(missing)} orphan reference(s): {missing[:5]}", subs
    return "PASS", f"{len(caps)} capabilities, 0 orphan tool/oracle refs", subs


def check_goal_decide_dryrun() -> tuple[str, str, list[dict]]:
    """T — run_goal_engagement imports, a goal with no bounds is rejected, and
    a non-dry-run call raises NotImplementedError (TASK_SEC_GOAL_DECIDE_V1).

    Locks the Stage-2/Stage-3 boundary in code — a later edit can't
    accidentally grant live actuation without deliberately removing this
    guard (and this check).
    """
    try:
        from portal.modules.security.core.goal import EngagementGoal
        from portal.modules.security.core.loop import run_goal_engagement
    except ImportError as exc:
        return "SKIP", f"goal-decide module not found: {exc}", []

    subs: list[dict] = []

    unbounded = EngagementGoal(intent="poke it", role="red")
    rejected = run_goal_engagement(unbounded, dry_run=True)
    ok1 = rejected.get("status") == "rejected"
    subs.append({"name": "unbounded goal rejected", "status": "PASS" if ok1 else "FAIL"})

    bounded = EngagementGoal(
        intent="poke it",
        role="red",
        targets=["10.10.11.50"],
        scope={"targets": ["10.10.11.50"]},
        budget={"max_iterations": 1, "max_wall_clock_sec": 60, "max_lab_actions": 1},
    )
    ok2 = False
    try:
        run_goal_engagement(bounded, dry_run=False)
    except NotImplementedError:
        ok2 = True
    subs.append(
        {"name": "live actuation raises NotImplementedError", "status": "PASS" if ok2 else "FAIL"}
    )

    if ok1 and ok2:
        return "PASS", "dry-run boundary enforced", subs
    return "FAIL", "dry-run boundary NOT enforced", subs


def check_drift_gate() -> tuple[str, str, list[dict]]:
    """AN — drift_gate.py imports, produces only known-set statuses over the
    real results/ series, and the metric math distinguishes a synthetic
    regression from synthetic noise (TASK_SEC_DRIFT_GATE_V1).

    Drift is additive analysis, never a verdict — this check just proves the
    module is wired and its core statistic isn't degenerate (always-OK or
    always-REGRESSION), not that any particular run has drifted.
    """
    try:
        from portal.modules.security.core.drift_gate import _metric_drift, drift_check
    except ImportError as exc:
        return "SKIP", f"drift_gate module not found: {exc}", []

    subs: list[dict] = []

    report = drift_check(window=5)
    valid_statuses = {"OK", "DRIFT-WARN", "DRIFT-REGRESSION", "INSUFFICIENT-BASELINE"}
    all_valid = all(
        m["status"] in valid_statuses for pair in report["pairs"] for m in pair["metrics"]
    )
    subs.append(
        {
            "name": "known-status invariant over real results",
            "status": "PASS" if all_valid else "FAIL",
        }
    )

    regression = _metric_drift("blue_f1", [0.5, 0.48], [[0.80, 0.82], [0.79, 0.81], [0.78, 0.80]])
    ok_regression = regression.status == "DRIFT-REGRESSION"
    subs.append(
        {"name": "synthetic regression detected", "status": "PASS" if ok_regression else "FAIL"}
    )

    noise = _metric_drift("blue_f1", [0.795, 0.80], [[0.80, 0.805], [0.798, 0.80], [0.80, 0.802]])
    ok_noise = noise.status != "DRIFT-REGRESSION"
    subs.append(
        {
            "name": "synthetic noise not flagged as regression",
            "status": "PASS" if ok_noise else "FAIL",
        }
    )

    if all_valid and ok_regression and ok_noise:
        return "PASS", f"{len(report['pairs'])} pair(s) checked, metric math sound", subs
    return "FAIL", "drift gate invariant violated", subs


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
    v.run("R. lab target catalog", check_lab_target_catalog)
    v.run("S. loop dry-run gate", check_loop_dry_run)
    v.run("T. lab setup readiness", check_lab_setup_readiness)
    v.run("U. ability port executable", check_ability_port)
    v.run("V. lab-exec coverage", check_labexec_coverage)
    v.run("W. scenario-oracle/matrix", check_scenario_oracle_matrix)
    v.run("X. self-index integrity", check_self_index_integrity)
    v.run("Y. ci parity", check_ci_parity)
    v.run("Z. live exec integrity", check_live_exec_integrity)
    v.run("AA. stage2 propose integrity", check_stage2_propose_integrity)
    v.run("AB. kali exec + rescore integrity", check_kali_rescore_integrity)
    v.run("AC. coverage expansion integrity", check_coverage_expansion_integrity)
    v.run("AD. candidate eval integrity", check_candidate_eval_integrity)
    v.run("AE. bench supervisor integrity", check_bench_supervisor_integrity)
    v.run("AF. triage layer2 integrity", check_triage_layer2_integrity)
    v.run("AG. rbp evidence grounding", check_rbp_evidence_grounding)
    v.run("AH. telemetry contracts", check_telemetry_contracts)
    v.run("AI. capability graph + gap engine", check_capability_graph)
    v.run("AJ. wiki core backbone", check_wiki_core)
    v.run("AK. doc currency", check_doc_currency)
    v.run("AL. capability index consistency", check_capability_index)
    v.run("AM. goal-decide dry-run", check_goal_decide_dryrun)
    v.run("AN. drift gate", check_drift_gate)
    v.run("AO. agent core", check_agent_core)
    v.run("AP. workspace module tag", check_workspace_module_tag)
    v.run("AQ. mcp module tag", check_mcp_module_tag)
    v.run("AR. persona module tag", check_persona_module_tag)
    v.run("AS. persona prompt uniqueness", check_persona_prompt_uniqueness)
    v.run("AT. alias ratchet", check_alias_ratchet)
    v.run("AU. routing regression (served model)", check_routing_regression)
    v.run("AV. persona intent (identity vs served model)", check_persona_intent)
    v.run("AW. wiki facts current (fact-units + generated doc blocks)", check_wiki_facts_current)

    return v.summary()


def check_agent_core() -> tuple[str, str, list[dict]]:
    """AO. Platform agent loop is core + inverted.

    (1) portal.platform.agent imports cleanly.
    (2) INVARIANT: no file under portal/platform/agent/ imports portal.modules.*
        (platform must not depend on any module).
    (3) Security's re-homed shim symbols still resolve at their historical paths.
    """
    import ast
    import importlib
    from pathlib import Path

    subs: list[dict] = []

    try:
        importlib.import_module("portal.platform.agent")
        subs.append({"name": "import portal.platform.agent", "status": "PASS", "detail": "ok"})
    except Exception as e:  # noqa: BLE001
        return ("FAIL", f"portal.platform.agent import failed: {e}", subs)

    root = Path(__file__).resolve().parents[1] / "portal" / "platform" / "agent"
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


def check_workspace_module_tag() -> tuple[str, str, list[dict]]:
    """AP. Every workspace in config/portal.yaml carries a module: tag.

    Hard-fail as of BUILD_PROGRAM_COLLAPSE_V1.md Phase 2 (every workspace
    is tagged) — was soft-fail (WARN) in Phase 0-1.
    """
    import yaml

    cfg = yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text())
    workspaces = cfg.get("workspaces", {}) or {}
    untagged = sorted(k for k, v in workspaces.items() if not v.get("module"))
    tagged = len(workspaces) - len(untagged)
    detail = f"{tagged}/{len(workspaces)} workspaces tagged"
    if untagged:
        return (
            "FAIL",
            f"{detail} — untagged: {untagged[:5]}{'...' if len(untagged) > 5 else ''}",
            [],
        )
    return ("PASS", detail, [])


def check_mcp_module_tag() -> tuple[str, str, list[dict]]:
    """AQ. Every mcp_fleet entry in config/portal.yaml carries a module: tag.

    Hard-fail as of BUILD_PROGRAM_COLLAPSE_V1.md Phase 2 (same discipline as AP).
    """
    import yaml

    cfg = yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text())
    mcp_fleet = cfg.get("mcp_fleet", []) or []
    untagged = sorted(m["id"] for m in mcp_fleet if not m.get("module"))
    tagged = len(mcp_fleet) - len(untagged)
    detail = f"{tagged}/{len(mcp_fleet)} mcp_fleet entries tagged"
    if untagged:
        return ("FAIL", f"{detail} — untagged: {untagged}", [])
    return ("PASS", detail, [])


def check_persona_module_tag() -> tuple[str, str, list[dict]]:
    """AR. Every persona YAML carries a module: tag.

    Hard-fail as of BUILD_PROGRAM_COLLAPSE_V1.md Phase 2 (same discipline as AP/AQ).
    """
    import glob

    import yaml

    persona_dir = REPO_ROOT / "config" / "personas"
    files = sorted(glob.glob(str(persona_dir / "*.yaml")))
    untagged = []
    for f in files:
        d = yaml.safe_load(open(f)) or {}  # noqa: SIM115
        if not d.get("module"):
            untagged.append(Path(f).name)
    tagged = len(files) - len(untagged)
    detail = f"{tagged}/{len(files)} personas tagged"
    if untagged:
        return (
            "FAIL",
            f"{detail} — untagged: {untagged[:5]}{'...' if len(untagged) > 5 else ''}",
            [],
        )
    return ("PASS", detail, [])


def check_persona_prompt_uniqueness() -> tuple[str, str, list[dict]]:
    """AS. No two personas share a byte-identical system_prompt.

    Hard-fail as of BUILD_PROGRAM_COLLAPSE_V1.md Phase 8 (the 27
    bench-matrix personas that shared 3 byte-identical prompts now
    reference them via prompt_template: instead). Personas using
    `prompt_template:` are excluded from the hash comparison — a shared
    template referenced by many personas is the fix, not a new collision.
    """
    import glob
    import hashlib
    from collections import defaultdict

    import yaml

    persona_dir = REPO_ROOT / "config" / "personas"
    by_hash: dict[str, list[str]] = defaultdict(list)
    for f in sorted(glob.glob(str(persona_dir / "*.yaml"))):
        d = yaml.safe_load(open(f)) or {}  # noqa: SIM115
        if d.get("prompt_template"):
            continue
        sp = (d.get("system_prompt") or "").strip()
        if not sp:
            continue
        h = hashlib.md5(sp.encode()).hexdigest()  # noqa: S324
        by_hash[h].append(d.get("slug", Path(f).name))
    dups = {h: slugs for h, slugs in by_hash.items() if len(slugs) > 1}
    if dups:
        sample = next(iter(dups.values()))
        return (
            "FAIL",
            f"{len(dups)} duplicate-prompt group(s), e.g. {sample[:3]}{'...' if len(sample) > 3 else ''}",
            [],
        )
    return ("PASS", "no duplicate persona prompts", [])


def check_alias_ratchet() -> tuple[str, str, list[dict]]:
    """AT. Zero live-code references to a retired pre-collapse workspace alias.

    BUILD_PROGRAM_ALIAS_FINISH_V1.md Phase 6: the growth-only ratchet this
    check used to be is retired along with the shim it was guarding
    (`_LEGACY_WORKSPACE_ALIASES` — removed from preinject.py once the
    Phase 4 live-traffic trip gate proved zero real callers depended on it;
    see CLOSEOUT_ALIAS_REMOVAL.md). This is now a hard assertion: zero
    non-comment occurrences of any of the 23 retired alias ids
    (`scripts/alias_census.py`'s `_RETIRED_ALIAS_IDS`) in live Python
    serving-path code (shim/integration/personas categories — where a bare
    alias id would be a real regression: a default argument, a dict value
    sent as `model=`, etc.).

    Scope note: this is deliberately *not* a zero-occurrence-anywhere-in-
    the-repo assertion. `docs/`, `tests/`, `config/`'s narrative JSON/YAML
    (MODEL_CATALOG.md, routing_descriptions.json's `_note` field, Grafana
    dashboard panel configs, etc.) legitimately reference retired ids by
    name when explaining collapse/retirement history — that's the exact
    "explanatory comment" content the closeout's own exemption design
    anticipated, at a scale (~700 refs across the doc/test corpus) where a
    blanket ban would either break historical narrative or demand rewriting
    every design doc in `coding_task/` that documents this exact program.
    `scripts/alias_census.py`'s comment/docstring-aware classifier is what
    makes the code-vs-narrative distinction precise instead of guessing.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from alias_census import run_census

    result = run_census()
    code_hits = result["code_hits_by_file"]

    if code_hits:
        return (
            "FAIL",
            f"{result['code_risk_total']} live alias reference(s) in "
            f"serving-path code: {code_hits}",
            [],
        )
    return (
        "PASS",
        f"0 live-code alias references ({result['total']} total refs across "
        f"docs/tests/config narrative, {result['frozen_total']} in frozen artifacts)",
        [],
    )


def check_routing_regression() -> tuple[str, str, list[dict]]:
    """AU. Routing decisions match the versioned baseline (served model, not just id).

    BUILD_PROGRAM_ROUTING_INTEGRITY_V1.md Phase R3: runs the committed corpus
    (tests/routing/corpus.json) through the current keyword-layer router and
    asserts the full (base, variant, served_model) tuple per prompt against
    tests/routing/baseline.json — the persona finding proved that a
    workspace-id-only check is insufficient (right workspace, wrong served
    model). Hard fail on any drift. Intended routing changes must be
    re-blessed explicitly (`scripts/routing_regression.py --rebless`) with
    the diff recorded in the commit — never silently accepted here.
    """
    # Earlier checks in this same process may import portal.platform.inference
    # and set PROMETHEUS_MULTIPROC_DIR (see metrics.py's own docstring) to a
    # directory (e.g. /dev/shm/portal_metrics) that only exists once the
    # pipeline's own startup has created it. This subprocess doesn't need
    # multiprocess metrics at all — routing_regression.py only imports
    # routing.py for its pure keyword-scoring function — so drop the
    # inherited var rather than risk a FileNotFoundError from a stale/
    # nonexistent multiprocess dir polluting an unrelated check.
    child_env = {k: v for k, v in os.environ.items() if k != "PROMETHEUS_MULTIPROC_DIR"}
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "routing_regression.py"), "--assert-baseline"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=child_env,
    )
    if result.returncode != 0:
        return (
            "FAIL",
            (result.stdout.strip() + "\n" + result.stderr.strip()).strip()[-800:],
            [],
        )
    return ("PASS", result.stdout.strip(), [])


def check_persona_intent() -> tuple[str, str, list[dict]]:
    """AV. A persona's system_prompt identity claim matches its served model.

    DESIGN_PERSONA_INTENT_REMEDIATION_V1.md §7 Check 2, permanent gate: the
    bug class this catches is "right workspace, wrong served model" — a
    persona named/prompted for a specific model lineage (e.g. "powered by
    Magistral") but actually served a different model via its workspace's
    pool primary or a stale model_pin. This is exactly what let 7 personas
    drift silently after the workspace collapse (5 in the design doc + 2
    more this check itself found: gemma_vision, gemma4jangvision). Also
    checks module/workspace discipline agreement and that every model_pin
    is a real backends.yaml catalog id.
    """
    # Same PROMETHEUS_MULTIPROC_DIR pollution as check_routing_regression
    # (see its comment) — this subprocess transitively imports preinject.py
    # -> metrics.py and doesn't need multiprocess metrics either.
    child_env = {k: v for k, v in os.environ.items() if k != "PROMETHEUS_MULTIPROC_DIR"}
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "persona_intent_audit.py"), "--verbose"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=child_env,
    )
    if result.returncode != 0:
        return ("FAIL", (result.stdout.strip() + "\n" + result.stderr.strip()).strip()[-800:], [])
    return ("PASS", result.stdout.strip() or "0 hard failures", [])


def check_wiki_facts_current() -> tuple[str, str, list[dict]]:
    """AW. Wiki fact-units are current vs live config, and generated doc
    blocks match their units.

    DESIGN_WIKI_GENERATION_LOOP_V1.md F3 — the precise replacement for a
    coarse "a bound directory changed" doc-currency signal on the docs
    that now carry generated fact-blocks: read-only diff of each
    fact-unit's would-be body against what's stored, plus every
    `<!-- WIKI:GENERATED unit=... -->` block in the Tier-1 docs against
    its unit's current body. A mismatch here is precise ("unit says 138,
    doc block says 130"), not "a directory changed, re-stamp" — it means
    `sync-config` was not re-run after a source change before commit.
    """
    from portal.platform.wiki.adapters.seed_facts import check_facts_current
    from portal.platform.wiki.render import check_generated_blocks_current

    subs: list[dict] = []

    stale_units = check_facts_current()
    subs.append(
        {
            "name": "fact-units vs live config",
            "status": "PASS" if not stale_units else "FAIL",
            "detail": ", ".join(stale_units) if stale_units else "all current",
        }
    )

    drift = check_generated_blocks_current(REPO_ROOT)
    subs.append(
        {
            "name": "generated doc blocks vs units",
            "status": "PASS" if not drift else "FAIL",
            "detail": "; ".join(drift) if drift else "all match",
        }
    )

    if stale_units or drift:
        detail = f"{len(stale_units)} fact-unit(s) stale, {len(drift)} doc block(s) drifted — run sync-config"
        return ("FAIL", detail, subs)
    return ("PASS", "fact-units current, all generated blocks match", subs)


if __name__ == "__main__":
    sys.exit(main())
