#!/usr/bin/env python3
"""Block WFE seat screens when repository setup can invalidate the result."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from portal.platform.inference.cluster_backends import BackendRegistry  # noqa: E402
from portal.platform.inference.config import (  # noqa: E402
    effective_workspace,
    load_bench_workspaces_raw,
)
from scripts import host_quiet  # noqa: E402
from tests.wfe import settings_audit  # noqa: E402

CONTAINER_PIPELINE_HOSTS = {"pipeline", "portal-pipeline", "portal5-pipeline"}
CONTAINER_METRICS_DIRS = {"/dev/shm/portal_metrics", "/tmp/portal_metrics"}


def _strip_jsonc_comments(source: str) -> str:
    output: list[str] = []
    index = 0
    quoted = False
    escaped = False
    while index < len(source):
        char = source[index]
        if quoted:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            index += 1
        elif char == '"':
            quoted = True
            output.append(char)
            index += 1
        elif source.startswith("//", index):
            while index < len(source) and source[index] not in "\r\n":
                output.append(" ")
                index += 1
        elif source.startswith("/*", index):
            output.extend("  ")
            index += 2
            while index < len(source) and not source.startswith("*/", index):
                output.append("\n" if source[index] == "\n" else " ")
                index += 1
            if index < len(source):
                output.extend("  ")
                index += 2
        else:
            output.append(char)
            index += 1
    return "".join(output)


def _parse_jsonc(source: str) -> dict:
    uncommented = _strip_jsonc_comments(source)
    clean = re.sub(r",(\s*[}\]])", r"\1", uncommented)
    value = json.loads(clean)
    if not isinstance(value, dict):
        raise ValueError("opencode.jsonc root must be an object")
    return value


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )


def _committed_opencode_model(repo: Path, model: str) -> list[str]:
    reasons: list[str] = []
    path = repo / "opencode.jsonc"
    if _run_git(repo, "ls-files", "--error-unmatch", "opencode.jsonc").returncode != 0:
        reasons.append("opencode.jsonc is not tracked by this worktree")
    if _run_git(repo, "cat-file", "-e", "HEAD:opencode.jsonc").returncode != 0:
        reasons.append("HEAD does not contain opencode.jsonc")
    if _run_git(repo, "diff", "--quiet", "HEAD", "--", "opencode.jsonc").returncode != 0:
        reasons.append("opencode.jsonc has staged or unstaged edits not committed at HEAD")
    if reasons:
        return reasons
    try:
        config = _parse_jsonc(path.read_text())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"opencode.jsonc cannot be parsed: {exc}"]
    match = re.fullmatch(r"opencode:portal/([^/]+)", model)
    if not match:
        return [f"screen model {model!r} must use opencode:portal/<model-id>"]
    model_id = match.group(1)
    provider = (config.get("providers") or {}).get("portal") or {}
    models = provider.get("models") or {}
    if model_id not in models:
        reasons.append(f"committed opencode.jsonc has no providers.portal.models[{model_id!r}]")
    if not isinstance(provider.get("settings"), dict) or not provider["settings"].get("baseURL"):
        reasons.append("committed opencode.jsonc has no Portal provider baseURL")
    return reasons


def _load_seat(repo: Path, workspace_id: str) -> tuple[dict, dict, dict]:
    portal = yaml.safe_load((repo / "config/portal.yaml").read_text()) or {}
    workspaces = dict(portal.get("workspaces") or {})
    bench_path = repo / "config/bench_workspaces.yaml"
    if bench_path.exists():
        workspaces.update(load_bench_workspaces_raw(repo))
    return effective_workspace(workspaces, workspace_id), workspaces, portal


def _resolve_workspace_id(repo: Path, selection: str) -> str:
    portal = yaml.safe_load((repo / "config/portal.yaml").read_text()) or {}
    workspaces = dict(portal.get("workspaces") or {})
    if (repo / "config/bench_workspaces.yaml").exists():
        workspaces.update(load_bench_workspaces_raw(repo))
    base_id = selection.partition("::")[0]
    if base_id in workspaces:
        return selection
    personas = []
    for path in (repo / "config/personas").rglob("*.yaml"):
        entry = yaml.safe_load(path.read_text()) or {}
        if entry.get("slug") == selection:
            workspace = str(entry.get("workspace_model") or "")
            variant = str(entry.get("variant") or "")
            if workspace:
                personas.append(f"{workspace}::{variant}" if variant else workspace)
    if len(set(personas)) == 1:
        return personas[0]
    if personas:
        raise ValueError(f"persona slug {selection!r} maps to multiple workspace seats: {personas}")
    return selection


def _infer_expected_engine(workspace_id: str, hint: str, repo: Path) -> str | None:
    backends = yaml.safe_load((repo / "config/backends.yaml").read_text()) or {}
    registry = BackendRegistry(str(repo / "config/backends.yaml"))
    matches: list[tuple[str, bool, int]] = []
    for backend in registry.get_backend_candidates(workspace_id):
        raw = next((row for row in backends.get("backends", []) if row.get("id") == backend.id), {})
        engine = "omlx" if backend.type == "omlx" else "ollama"
        aliases = raw.get("aliases") or {}
        model_ids = {
            item.get("id") if isinstance(item, dict) else item for item in raw.get("models") or []
        }
        if hint in aliases:
            matches.append((engine, True, int(raw.get("priority") or 0)))
        elif hint in model_ids:
            matches.append((engine, False, int(raw.get("priority") or 0)))
    preferred_aliases = [row for row in matches if row[1] and row[0] == "omlx" and row[2] == 10]
    if preferred_aliases:
        return "omlx"
    engines = {row[0] for row in matches}
    if len(engines) == 1:
        return next(iter(engines))
    normalized = hint.lower()
    if "mlx" in normalized and "gguf" not in normalized:
        return "omlx"
    if "gguf" in normalized or ".gguf" in normalized:
        return "ollama"
    return None


def _served_engine(repo: Path, workspace_id: str, ws: dict, expected: str | None) -> list[str]:
    hint = str(ws.get("model_hint") or "")
    if not hint:
        return [f"{workspace_id} has no model_hint"]
    backends = yaml.safe_load((repo / "config/backends.yaml").read_text()) or {}
    registry = BackendRegistry(str(repo / "config/backends.yaml"))
    resolved = settings_audit._served_path(workspace_id, hint, registry)
    if resolved is None:
        return [f"{workspace_id} model_hint {hint} resolves to no backend"]
    engine, backend_id, served_id = resolved
    actual = next((row for row in backends.get("backends", []) if row.get("id") == backend_id), {})
    group = actual.get("group", "unknown")
    wanted = expected or _infer_expected_engine(workspace_id, hint, repo)
    if wanted is None:
        return [
            f"{workspace_id} model_hint {hint} resolves via {backend_id}/{group} to {served_id}, "
            "but its intended engine is ambiguous; pass --expected-engine ollama|omlx"
        ]
    reasons = []
    if engine != wanted:
        reasons.append(
            f"{workspace_id} model_hint {hint} should use {wanted}, but resolves via "
            f"{backend_id}/{group} to {engine}:{served_id}"
        )
    identity = served_id.lower()
    identity_engine = (
        "ollama"
        if "gguf" in identity or ".gguf" in identity
        else ("omlx" if "mlx" in identity else None)
    )
    if identity_engine and engine != identity_engine:
        reasons.append(
            f"{backend_id} resolves {hint} to {served_id}, whose model id indicates "
            f"{identity_engine} while the backend type is {engine}"
        )
    return reasons


def _container_environment_issues(environment: dict[str, str]) -> list[str]:
    issues: list[str] = []
    pipeline_url = environment.get("PIPELINE_URL", "")
    if pipeline_url:
        host = (urlsplit(pipeline_url).hostname or "").lower()
        if host in CONTAINER_PIPELINE_HOSTS:
            issues.append(f"PIPELINE_URL={pipeline_url} is a container service address")
    metrics_dir = environment.get("PROMETHEUS_MULTIPROC_DIR", "")
    if metrics_dir and os.path.normpath(metrics_dir) in CONTAINER_METRICS_DIRS:
        issues.append(f"PROMETHEUS_MULTIPROC_DIR={metrics_dir} is a container metrics path")
    return issues


def _duration_seconds(value: str) -> float | None:
    text = value.strip().lower()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return float(text)
    parts = re.findall(r"(-?\d+(?:\.\d+)?)(ns|us|µs|ms|s|m|h)", text)
    if not parts or "".join(number + unit for number, unit in parts) != text:
        return None
    scales = {"ns": 1e-9, "us": 1e-6, "µs": 1e-6, "ms": 1e-3, "s": 1, "m": 60, "h": 3600}
    return sum(float(number) * scales[unit] for number, unit in parts)


def _sidecar_issues(url: str | None, keep_alive: str | None) -> list[str]:
    if not url:
        return []
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return [f"Ollama sidecar URL {url!r} is not an http(s) URL"]
    if keep_alive is None:
        return ["Ollama sidecar URL was supplied without its configured keep_alive value"]
    seconds = _duration_seconds(keep_alive)
    if seconds is None:
        return [f"Ollama keep_alive value {keep_alive!r} is not a valid duration"]
    if seconds == 0:
        return ["Ollama sidecar keep_alive is 0; the model is unloaded after every request"]
    return []


def _default_screen_model(workspace: str) -> str:
    """Variant seats register under their flat variant slug in opencode.jsonc,
    not the namespaced ``base::variant`` id."""
    _base, _, variant = workspace.partition("::")
    return f"opencode:portal/{variant or _base}"


def preflight(args: argparse.Namespace, environment: dict[str, str] | None = None) -> list[str]:
    repo = Path(args.repo).resolve()
    environment = os.environ if environment is None else environment
    model = args.model or _default_screen_model(args.workspace)
    issues = _committed_opencode_model(repo, model)
    issues.extend(_container_environment_issues(environment))
    keep_alive = args.ollama_keep_alive or environment.get("OLLAMA_KEEP_ALIVE")
    issues.extend(_sidecar_issues(args.ollama_sidecar_url, keep_alive))
    try:
        workspace_id = _resolve_workspace_id(repo, args.workspace)
        ws, _workspaces, _portal = _load_seat(repo, workspace_id)
        issues.extend(_served_engine(repo, workspace_id, ws, args.expected_engine))
        report = settings_audit.audit_config_seats(
            repo=repo, workspace_ids=[workspace_id], include_bench=True
        )
        issues.extend(
            f"settings_audit {row['severity']} {row['kind']}: {row['detail']}"
            for row in report["violations"]
            if row["severity"] in {"WARN", "FAIL"}
        )
    except (OSError, KeyError, ValueError) as exc:
        issues.append(f"seat configuration could not be checked: {exc}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument(
        "--workspace", required=True, help="configured Portal workspace or variant id"
    )
    parser.add_argument(
        "--model",
        help="OpenCode model reference; defaults to opencode:portal/<variant-or-workspace>",
    )
    parser.add_argument("--expected-engine", choices=("ollama", "omlx"))
    parser.add_argument("--ollama-sidecar-url")
    parser.add_argument("--ollama-keep-alive")
    parser.add_argument("--force", action="store_true", help="override host-quiet blockers")
    args = parser.parse_args()
    pipeline_url = os.environ.get("PIPELINE_URL", "http://localhost:9099").rstrip("/")
    api_key = os.environ.get("PIPELINE_API_KEY", "portal-pipeline")
    host_context = host_quiet.begin_run(pipeline_url, api_key, force=args.force)
    if not host_context["allowed"]:
        host_quiet.finish_run(host_context, pipeline_url, api_key)
        print(f"host-quiet receipt: {json.dumps(host_context, sort_keys=True)}")
        print(f"BLOCK: {host_quiet.refusal(host_context)}")
        return 1
    if host_context["override_reason"]:
        print(f"HOST-QUIET OVERRIDE: {host_context['override_reason']}")
    issues = preflight(args)
    host_quiet.finish_run(host_context, pipeline_url, api_key)
    print(f"host-quiet receipt: {json.dumps(host_context, sort_keys=True)}")
    if issues:
        for issue in issues:
            print(f"BLOCK: {issue}")
        print(f"seat preflight BLOCKED ({len(issues)} reason(s))")
        return 1
    print(f"seat preflight PASS: {args.workspace} is committed and config-conformant")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
