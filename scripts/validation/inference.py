"""Inference-family checks: import surface, pipeline assembly, hint validation,
lifespan, CLI introspection, and the unit-test suite gate."""

from __future__ import annotations

import asyncio
import importlib
import subprocess
import sys

from ._shared import REPO_ROOT
from .registry import register


@register("imports", "A. python imports", order=0)
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


@register("pipeline_assembles", "B. pipeline assembles", order=1)
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


@register("hint_validator", "E. hint validator", order=4)
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


@register("lifespan", "F. lifespan startup", order=5)
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


@register("cli", "G. CLI introspection", order=6)
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


@register("unit_tests", "H. unit test suite", order=7)
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
