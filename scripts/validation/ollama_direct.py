"""Mechanical inventory of runtime POSTs to Ollama inference endpoints."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import yaml

from ._shared import REPO_ROOT
from .registry import register

_ROUTE = re.compile(r"(?<!/ollama)/api/(?:chat|generate|embed)(?:\b|/)")
_HTTP_METHODS = {"post", "request", "stream", "Request"}
_POST_HELPERS = {"_stream_chain_turn", "omlx_post"}


def _strings(node: ast.AST) -> list[str]:
    values: list[str] = []
    for item in ast.walk(node):
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            values.append(item.value)
    return values


def _assigned_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, ast.Attribute):
        return {target.attr}
    if isinstance(target, (ast.Tuple, ast.List)):
        return set().union(*(_assigned_names(item) for item in target.elts))
    return set()


def _passthrough_names(tree: ast.AST) -> set[str]:
    """Find endpoint/base variables whose defaults explicitly use /ollama."""
    bindings: list[tuple[set[str], ast.AST]] = []
    for item in ast.walk(tree):
        if isinstance(item, (ast.Assign, ast.AnnAssign)):
            value = item.value
            if value is None:
                continue
            targets = item.targets if isinstance(item, ast.Assign) else [item.target]
            names = set().union(*(_assigned_names(target) for target in targets))
            bindings.append((names, value))

    passthrough: set[str] = set()
    changed = True
    while changed:
        changed = False
        for names, value in bindings:
            direct_base = any("/ollama" in val for val in _strings(value)) or any(
                isinstance(node, ast.Call)
                and getattr(node.func, "id", "") in {"native_ollama_base", "_native_ollama_base"}
                for node in ast.walk(value)
            )
            refs = {
                node.id if isinstance(node, ast.Name) else node.attr
                for node in ast.walk(value)
                if isinstance(node, (ast.Name, ast.Attribute))
            }
            if (direct_base or refs & passthrough) and not names <= passthrough:
                passthrough.update(names)
                changed = True
    return passthrough


def _endpoint_names(tree: ast.AST) -> set[str]:
    """Find variables assigned a native inference endpoint or URL."""
    names: set[str] = set()
    for item in ast.walk(tree):
        if not isinstance(item, (ast.Assign, ast.AnnAssign)):
            continue
        value = item.value
        if value is None or not any(_ROUTE.search(val) for val in _strings(value)):
            continue
        targets = item.targets if isinstance(item, ast.Assign) else [item.target]
        names.update(set().union(*(_assigned_names(target) for target in targets)))
    return names


def _is_post(call: ast.Call) -> bool:
    name = (
        call.func.attr
        if isinstance(call.func, ast.Attribute)
        else (call.func.id if isinstance(call.func, ast.Name) else "")
    )
    if name.lower() == "post" or name in _POST_HELPERS:
        return True
    if name not in _HTTP_METHODS - {"post"}:
        return False
    if name == "Request":
        return len(call.args) > 1 or any(keyword.arg == "data" for keyword in call.keywords)
    method_args = [*call.args[:1], *(kw.value for kw in call.keywords if kw.arg in {"method"})]
    return any("POST" in _strings(arg) for arg in method_args)


def direct_ollama_posts(root: Path) -> list[dict[str, Any]]:
    """Return non-passthrough POST callsites under ``portal/``."""
    portal = root / "portal"
    if not portal.is_dir():
        return []
    found: list[dict[str, Any]] = []
    for path in sorted(portal.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if "tests" in path.parts or path.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (OSError, SyntaxError) as exc:
            found.append({"file": rel, "line": 1, "error": f"parse failed: {exc}"})
            continue
        passthrough = _passthrough_names(tree)
        endpoints = _endpoint_names(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_post(node):
                continue
            refs = {
                item.id if isinstance(item, ast.Name) else item.attr
                for item in ast.walk(node)
                if isinstance(item, (ast.Name, ast.Attribute))
            }
            has_route = any(_ROUTE.search(value) for value in _strings(node))
            if not has_route and not refs & endpoints:
                continue
            if refs & passthrough:
                continue
            found.append({"file": rel, "line": node.lineno})
    return found


def check_allowlist(root: Path) -> tuple[str, str, list[dict[str, Any]]]:
    config_path = root / "config" / "ollama_direct_allowlist.yaml"
    try:
        document = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return "FAIL", f"cannot read {config_path.relative_to(root)}: {exc}", []
    raw_allowlist = document.get("allowlist")
    if not isinstance(raw_allowlist, dict):
        return "FAIL", "allowlist must be a path-to-reason mapping", []
    allowlist = {
        str(path): str(reason).strip()
        for path, reason in raw_allowlist.items()
        if str(reason).strip()
    }
    missing_reasons = sorted(set(raw_allowlist) - set(allowlist))
    findings = direct_ollama_posts(root)
    used: set[str] = set()
    failures: list[dict[str, Any]] = []
    for finding in findings:
        path = finding["file"]
        if finding.get("error") or path not in allowlist:
            failures.append(finding)
        else:
            used.add(path)
            finding["reason"] = allowlist[path]
    for path in missing_reasons:
        failures.append({"file": path, "error": "allowlist reason is empty"})
    for path in sorted(set(allowlist) - used):
        failures.append({"file": path, "error": "allowlist entry has no matching direct POST"})
    if failures:
        return "FAIL", f"{len(failures)} direct Ollama POST issue(s)", failures
    return (
        "PASS",
        f"{len(findings)} direct POST callsite(s) are guarded or reason-allowlisted",
        findings,
    )


@register("ollama_direct_allowlist", "HM. Ollama direct-call guard allowlist", order=203)
def check_ollama_direct_allowlist() -> tuple[str, str, list[dict[str, Any]]]:
    """W. Runtime Ollama inference POSTs are guarded or explicitly allowlisted."""
    return check_allowlist(REPO_ROOT)
