"""The window a workspace's seat SERVES, resolved from the backend config.

TASK_COMPLIANCE_DATA_TRUTH_V1 D1b/D7 (F8). A workspace declares
``context_limit``; the seat it routes to serves whatever its engine loaded.
Those two disagree silently whenever ``model_hint`` resolves through a
``backends.yaml`` alias — ``gemma4:26b-a4b-it-q4_K_M-ctx32k`` aliases to an
oMLX MLX conversion serving 262,144 — and the pricing side of the reading
guard under-reserves or refuses material that fits. The tag's ``-ctxNk``
suffix is the seat's *baked* window only on the backend that baked it; through
an alias it describes a model the target engine never loaded.

Resolution is data-driven: the same ``config/backends.yaml`` the router reads,
then a short probe of the backend's own model endpoint for the resolved
model's window. Probes are best-effort and never raise — an unreachable
engine yields ``applied_window=None`` with the reason recorded, because a
validator must run on a host with the stack down and a guard must fail closed
on the static facts it can still compare.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

DEFAULT_CONFIG_RELPATH = ("config", "backends.yaml")


@dataclass
class ServedWindow:
    """What a workspace's ``model_hint`` actually serves, and how it was known."""

    hint: str
    backend_id: str = ""
    backend_type: str = ""
    resolved_model: str = ""
    #: the window the engine applies to this model right now (``max_model_len``
    #: on oMLX, the loaded ``num_ctx`` from ``/api/ps`` on Ollama). ``None``
    #: when the backend is unreachable or reports nothing — unknown, not zero.
    applied_window: int | None = None
    #: the model's trained/context ceiling (``context_length``), known even
    #: when the model is not loaded; never confused with the applied window.
    ceiling_window: int | None = None
    source: str = ""
    #: static alias observation: the hint routes to a model whose id is not the
    #: hint, so any window baked into the hint's tag describes another model.
    aliased: bool = False
    #: every in-group route that answered, as (backend_id, applied_window) in
    #: config order — the primary fields carry only the first.
    route_windows: list[tuple[str, int]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"hint={self.hint!r}"]
        if self.backend_id:
            parts.append(f"backend={self.backend_id}({self.backend_type})")
        if self.resolved_model and self.resolved_model != self.hint:
            parts.append(f"resolved={self.resolved_model!r}")
        parts.append(
            f"applied={self.applied_window if self.applied_window is not None else 'unknown'}"
        )
        if self.ceiling_window is not None:
            parts.append(f"ceiling={self.ceiling_window}")
        if self.source:
            parts.append(f"source={self.source}")
        return " ".join(parts)


def backends_config_path(explicit: str | Any = None) -> Any:
    """The backends.yaml path, following the router's own search order."""
    from pathlib import Path

    if explicit is not None:
        return Path(explicit)
    env = None
    try:
        import os

        env = os.environ.get("BACKEND_CONFIG_PATH")
    except Exception:  # pragma: no cover - os is always importable
        env = None
    if env:
        return Path(env)
    docker = Path("/app/config/backends.yaml")
    if docker.is_file():
        return docker
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / DEFAULT_CONFIG_RELPATH[0] / DEFAULT_CONFIG_RELPATH[1]
        if candidate.is_file():
            return candidate
    return docker


def load_backend_entries(config_path: str | Any = None) -> list[dict[str, Any]]:
    """The ``backends:`` list from backends.yaml, as plain dicts.

    Read directly rather than through ``BackendRegistry`` so the resolver works
    without starting health-check machinery; the keys consumed here (``id``,
    ``type``, ``url``, ``models``, ``aliases``) are the registry's own.
    """
    import yaml

    path = backends_config_path(config_path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("backends") or []
    return [e for e in entries if isinstance(e, dict)]


_CTX_TAG_RE = re.compile(r"-ctx(\d+)k$")

_ENV_TEMPLATE_RE = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?::-(?P<default>[^}]*))?\}")


def expand_env(value: str) -> str:
    """Expand ``${VAR}`` / ``${VAR:-default}`` in a config string.

    ``backends.yaml`` writes URLs as env templates (``${OMLX_URL:-…}``) and the
    router expands them at load; a resolver reading the yaml directly must do
    the same or its probes target a literal ``${…}`` "URL".
    """
    import os

    def _sub(match: re.Match[str]) -> str:
        name, default = match.group("name"), match.group("default") or ""
        return os.environ.get(name) or default

    return _ENV_TEMPLATE_RE.sub(_sub, value)


def tag_window(hint: str) -> int | None:
    """The window a seat tag's ``-ctxNk`` suffix declares, or ``None``."""
    match = _CTX_TAG_RE.search(hint or "")
    return int(match.group(1)) * 1024 if match else None


def _resolve(entries: list[dict[str, Any]], hint: str) -> list[tuple[dict[str, Any], str, bool]]:
    """Every backend that can serve the hint, with its native model id."""
    out: list[tuple[dict[str, Any], str, bool]] = []
    for entry in entries:
        model_ids = _model_ids(entry)
        aliases = {str(k): str(v) for k, v in (entry.get("aliases") or {}).items()}
        if hint in model_ids:
            out.append((entry, hint, False))
        elif hint in aliases:
            out.append((entry, aliases[hint], True))
    return out


def _model_ids(entry: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for model in entry.get("models") or []:
        if isinstance(model, str):
            ids.add(model)
        elif isinstance(model, dict) and model.get("id"):
            ids.add(str(model["id"]))
    return ids


def _route_window(
    entry: dict[str, Any],
    model_id: str,
    aliased: bool,
    *,
    hint: str,
    probe: bool,
    probe_timeout: float,
) -> ServedWindow:
    """Probe one candidate backend for one model id. Never raises."""
    route = ServedWindow(hint=hint)
    route.backend_id = str(entry.get("id", ""))
    route.backend_type = str(entry.get("type", ""))
    route.resolved_model = model_id
    route.aliased = aliased
    if aliased:
        route.notes.append(
            "hint resolves through an alias — the hint tag's -ctxNk window "
            "describes a model this backend does not serve"
        )
    if not probe:
        return route
    if route.backend_type == "omlx":
        _probe_omlx(route, entry, model_id, probe_timeout)
    elif route.backend_type == "ollama":
        _probe_ollama(route, entry, model_id, probe_timeout)
    else:
        route.notes.append(f"no window probe for backend type {route.backend_type!r}")
    return route


def served_window_for_hint(
    hint: str,
    config_path: str | Any = None,
    *,
    groups: list[str] | None = None,
    probe_timeout: float = 3.0,
    probe: bool = True,
) -> ServedWindow:
    """Resolve one workspace ``model_hint`` to the window its engine serves.

    A hint can be servable by MORE than one backend (listed on one, aliased on
    another), and the routes need not agree on a window — the reading seat's
    ctx32k tag is listed on the Ollama backend and aliased to a 262,144-token
    MLX conversion on oMLX. ``groups`` scopes to the routes the workspace
    actually draws candidates from (its ``workspace_routing`` groups, the
    router's tier 1); out-of-group servability is recorded as a note because
    the degrade tiers can reach them but pricing gates the normal route. The
    primary fields carry the FIRST in-group route that answered, and
    ``notes`` names disagreement and silence. Never raises: every network
    failure becomes a note and an unknown window.
    """
    result = ServedWindow(hint=hint)
    try:
        entries = load_backend_entries(config_path)
    except Exception as exc:  # noqa: BLE001 - config absence is a finding, not a crash
        result.notes.append(f"backends config unreadable: {exc}")
        return result
    candidates = _resolve(entries, hint)
    if not candidates:
        result.notes.append("no backend lists or aliases this hint")
        return result
    answered = 0
    for entry, model_id, aliased in candidates:
        if groups is not None and str(entry.get("group", "")) not in groups:
            if aliased:
                result.notes.append(
                    f"out-of-group route exists: {entry.get('id', '')} aliases this hint to "
                    f"{model_id!r} (group {entry.get('group', '')!r})"
                )
            continue
        route = _route_window(
            entry, model_id, aliased, hint=hint, probe=probe, probe_timeout=probe_timeout
        )
        if not result.backend_id:
            result.backend_id, result.backend_type = route.backend_id, route.backend_type
            result.resolved_model, result.aliased = route.resolved_model, route.aliased
        if route.applied_window is None and route.ceiling_window is None:
            result.notes.append(
                f"{route.backend_id}: unreachable or silent ({'; '.join(route.notes) or 'no data'})"
            )
            continue
        answered += 1
        if route.applied_window is not None:
            result.route_windows.append((route.backend_id, route.applied_window))
        if result.applied_window is None:
            result.applied_window = route.applied_window
            result.ceiling_window = route.ceiling_window
            result.source = route.source
        elif route.applied_window is not None and route.applied_window != result.applied_window:
            result.notes.append(
                f"routes disagree: {route.backend_id} serves {route.applied_window}, "
                f"first answer ({result.backend_id}) was {result.applied_window}"
            )
    if answered == 0:
        result.notes.append("no in-group candidate backend answered a probe")
    return result


def _http_json(
    result: ServedWindow, method: str, url: str, *, payload: Any = None, timeout: float = 3.0
) -> Any:
    """One probe request, folded into notes on any failure.

    ``backends.yaml`` addresses engines as ``host.docker.internal`` — the name
    resolves inside the pipeline container but not on the host itself, where a
    host-side validator must reach the same engine on loopback. A connect/DNS
    failure therefore retries once with the loopback form; both shapes are
    recorded so the note never hides which one answered.
    """
    import json as _json

    candidates = [url]
    if "host.docker.internal" in url:
        candidates.append(url.replace("host.docker.internal", "127.0.0.1"))
    try:
        from portal.platform.inference.omlx_auth import omlx_api_key

        headers = {}
        key = ""
        try:
            key = omlx_api_key()
        except Exception:  # noqa: BLE001 - key lookup is best-effort
            key = ""
        if key:
            headers["Authorization"] = f"Bearer {key}"
        import httpx

        last_error: Exception | None = None
        for candidate in candidates:
            try:
                if method == "GET":
                    response = httpx.get(candidate, headers=headers, timeout=timeout)
                else:
                    headers["Content-Type"] = "application/json"
                    response = httpx.post(
                        candidate,
                        headers=headers,
                        content=_json.dumps(payload or {}),
                        timeout=timeout,
                    )
                response.raise_for_status()
                return response.json()
            except Exception as exc:  # noqa: BLE001 - probe failure is a finding
                last_error = exc
        if last_error is not None:
            result.notes.append(f"probe {url} failed: {last_error}")
        return None
    except Exception as exc:  # noqa: BLE001 - probe failure is a finding
        result.notes.append(f"probe {url} failed: {exc}")
        return None


def _probe_omlx(result: ServedWindow, entry: dict[str, Any], model_id: str, timeout: float) -> None:
    url = expand_env(str(entry.get("url", ""))).rstrip("/")
    body = _http_json(result, "GET", f"{url}/v1/models", timeout=timeout)
    if not body:
        return
    for model in body.get("data") or []:
        if str(model.get("id")) == model_id:
            window = model.get("max_model_len")
            if isinstance(window, int):
                result.applied_window = window
                result.ceiling_window = window
                result.source = "omlx /v1/models max_model_len"
            return


def _probe_ollama(
    result: ServedWindow, entry: dict[str, Any], model_id: str, timeout: float
) -> None:
    base = expand_env(str(entry.get("url", ""))).rstrip("/")
    show = _http_json(
        result, "POST", f"{base}/api/show", payload={"model": model_id}, timeout=timeout
    )
    if show:
        info = show.get("model_info") or {}
        ceiling = info.get(f"{model_id}.context_length")
        if isinstance(ceiling, int):
            result.ceiling_window = ceiling
    ps = _http_json(result, "GET", f"{base}/api/ps", timeout=timeout)
    for loaded in (ps or {}).get("models") or []:
        if str(loaded.get("name")) == model_id:
            window = loaded.get("context_length")
            if isinstance(window, int):
                result.applied_window = window
                result.source = "ollama /api/ps context_length"
            return
    if result.ceiling_window is not None:
        result.notes.append("model not loaded — /api/ps carries no applied window")
