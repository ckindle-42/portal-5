"""Section 4 — backend pins and alias targets are really served by their engine."""

from __future__ import annotations

import ast
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .context import TraceContext, expand_env
from .engines import EngineModels, fetch_engine_models
from .model import Hop, Status, short

PIN_NAME = re.compile(r"(BACKEND|SEAT|PIN|JUDGE)")
#: A pin's value is an id or tag, never a prompt body.
IDENTIFIER = re.compile(r"^[\w./:@%+\-]{1,120}$")
BACKENDS_YAML = Path("config") / "backends.yaml"
TASK_MODEL_ID = "task-router"


@dataclass(frozen=True)
class Pin:
    """A module-level constant whose name says it names a backend or a seat."""

    name: str
    value: str
    file: str
    line: int


@dataclass(frozen=True)
class Backend:
    """One backends.yaml entry as the trace needs it."""

    backend_id: str
    kind: str
    url: str
    aliases: dict[str, str]


def discover_pins(root: Path) -> list[Pin]:
    """Module-level ``*BACKEND*`` / ``*SEAT*`` / ``*PIN*`` / ``*JUDGE*`` string constants."""
    pins: list[Pin] = []
    for path in sorted((root / "portal").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in tree.body:
            pin = _pin_of(node)
            if pin is not None:
                pins.append(Pin(pin[0], pin[1], str(path.relative_to(root)), node.lineno))
    return pins


def _pin_of(node: ast.stmt) -> tuple[str, str] | None:
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target, value = node.targets[0], node.value
    elif isinstance(node, ast.AnnAssign) and node.value is not None:
        target, value = node.target, node.value
    else:
        return None
    if not isinstance(target, ast.Name) or not PIN_NAME.search(target.id.upper()):
        return None
    if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
        return None
    return (target.id, value.value) if IDENTIFIER.match(value.value) else None


def load_backends(path: Path) -> list[Backend]:
    """Backends with their URLs resolved and alias maps intact."""
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: list[Backend] = []
    for entry in data.get("backends") or []:
        if not isinstance(entry, dict):
            continue
        aliases = entry.get("aliases")
        out.append(
            Backend(
                backend_id=str(entry.get("id") or ""),
                kind=str(entry.get("type") or ""),
                url=expand_env(entry.get("url")).rstrip("/"),
                aliases={
                    str(key): str(value)
                    for key, value in (aliases if isinstance(aliases, dict) else {}).items()
                },
            )
        )
    return out


def engine_ids(backend: Backend, models: EngineModels) -> set[str]:
    return models.omlx if backend.kind == "omlx" else models.ollama


def classify(value: str, backends: list[Backend], seats: set[str]) -> str:
    """What kind of name a pin holds: a backend id, a seat/workspace, or a model id."""
    if value in {backend.backend_id for backend in backends}:
        return "backend"
    return "seat" if value in seats else "model"


def pin_hop(pin: Pin, backends: list[Backend], models: EngineModels, seats: set[str]) -> Hop:
    """A backend pin must be declared and answered; a seat pin must be addressable."""
    where = f"{pin.file}:{pin.line}"
    kind = classify(pin.value, backends, seats)
    if kind == "backend":
        backend = next(entry for entry in backends if entry.backend_id == pin.value)
        ids = engine_ids(backend, models)
        return Hop(
            pin.name,
            Status.PASS if ids else Status.FAIL,
            pin.value,
            "declared backend answering",
            f"{where} engine_models={len(ids)}",
        )
    from portal.platform.inference.model_addressing import is_addressable

    addressable = is_addressable(pin.value)
    return Hop(
        pin.name,
        Status.PASS if addressable else Status.FAIL,
        pin.value,
        "addressable model",
        f"{where} kind={kind}",
    )


def alias_hop(backend: Backend, hint: str, target: str, models: EngineModels) -> Hop:
    available = engine_ids(backend, models)
    present = target in available
    return Hop(
        f"alias {backend.backend_id} {hint}",
        Status.PASS if present else Status.FAIL,
        f"→{target}",
        "served by engine",
        "" if present else f"engine lists {len(available)} model(s)",
    )


def backend_hops(backend: Backend, models: EngineModels) -> list[Hop]:
    """One row per alias when the engine answers; one honest FAIL when it does not."""
    available = engine_ids(backend, models)
    if not available and backend.aliases:
        return [
            Hop(
                f"alias {backend.backend_id}",
                Status.FAIL,
                f"{backend.backend_id} did not answer",
                "engine model list",
                f"{len(backend.aliases)} alias(es) unverified",
            )
        ]
    return [
        alias_hop(backend, hint, target, models) for hint, target in sorted(backend.aliases.items())
    ]


def expected_catalog(portal: dict[str, Any]) -> dict[str, str]:
    """id -> declared name for configured seats, OWUI variants, and the task model."""
    from portal.platform.wiki.adapters.modules import is_workspace_disabled

    out: dict[str, str] = {}
    for ws_id, cfg in (portal.get("workspaces") or {}).items():
        out[str(ws_id)] = str(cfg.get("name") or "")
        out |= {
            f"{ws_id}::{vid}": str((vcfg or {}).get("name") or out[str(ws_id)])
            for vid, vcfg in (cfg.get("variants") or {}).items()
            if (vcfg or {}).get("expose_to_owui") is True
        }
    disabled = is_workspace_disabled
    return {
        k: v
        for k, v in out.items()
        if not k.startswith("bench") and (not disabled(k) or k == TASK_MODEL_ID)
    }


def catalog_hop(ctx: TraceContext, portal: dict[str, Any]) -> Hop:
    """The running catalogue is this config's: every enabled seat under its declared name."""
    expected = expected_catalog(portal)
    if not ctx.api_key:
        return Hop(
            "served catalog",
            Status.WARN,
            "not run: no PIPELINE_API_KEY",
            "an advertised model list",
        )
    headers = {"Authorization": f"Bearer {ctx.api_key}"}
    try:
        response = httpx.get(f"{ctx.pipeline_url}/v1/models", timeout=15.0, headers=headers)
        response.raise_for_status()
        served = {
            str(e["id"]): str(e.get("name") or "")
            for e in response.json()["data"]
            if not e.get("is_persona") and not str(e["id"]).startswith("bench")
        }
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        error = short(f"{type(exc).__name__}: {exc}", 70)
        return Hop("served catalog", Status.FAIL, error, "GET /v1/models")
    missing, extra = set(expected) - set(served), set(served) - set(expected)
    renamed = {s for s, n in expected.items() if n and n != served.get(s)}
    gaps = [
        f"{label}={','.join(sorted(ids))}"
        for label, ids in (("missing", missing), ("undeclared", extra), ("renamed", renamed))
        if ids
    ]
    status = Status.FAIL if gaps else Status.PASS
    return Hop("served catalog", status, f"served={len(served)}", "config ids", "; ".join(gaps))


def alias_hops(ctx: TraceContext, portal: dict[str, Any]) -> list[Hop]:
    """Each deprecated alias is still accepted by the Pipeline and routes to its table target."""
    from portal.platform.wiki.adapters.modules import is_workspace_disabled

    from .workspaces import stream_turn

    if not ctx.api_key:
        return [Hop("aliases", Status.WARN, "not run: no PIPELINE_API_KEY", "one turn per alias")]
    deadline = time.monotonic() + ctx.budget_s
    hops: list[Hop] = []
    for alias, spec in sorted((portal.get("aliases") or {}).items()):
        target, left = str((spec or {}).get("to") or ""), deadline - time.monotonic()
        if not target:
            hops.append(Hop(str(alias), Status.WARN, "not run", "a declared target", "no `to:`"))
        elif is_workspace_disabled(target):
            hops.append(Hop(str(alias), Status.WARN, "not run: module disabled", f"→{target}"))
        elif left <= 1:
            hops.append(Hop(str(alias), Status.WARN, "not run (budget)", f"→{target}"))
        else:
            turn = stream_turn(ctx.pipeline_url, ctx.api_key, str(alias), min(left, ctx.timeout_s))
            resolved = turn.route[0] if turn.route else ""
            status = Status.PASS if resolved == target else Status.FAIL
            detail = "" if resolved == target else short(turn.error or turn.body, 70)
            hops.append(Hop(str(alias), status, f"→{resolved or '<no route>'}", target, detail))
    return hops or [Hop("aliases", Status.WARN, "none declared", "config/portal.yaml aliases")]


def run(ctx: TraceContext, portal: dict[str, Any]) -> list[Hop]:
    """Every code pin resolves, every alias target exists, and the catalogue is the config's."""
    backends = load_backends(ctx.repo_root / BACKENDS_YAML)
    if not backends:
        return [Hop("backends.yaml", Status.FAIL, "no backends", "config/backends.yaml")]
    models = fetch_engine_models(ctx)
    seats = set((portal.get("workspaces") or {}).keys())
    discovered = discover_pins(ctx.repo_root)
    hops = [
        Hop(
            "code pins",
            Status.PASS,
            f"found={len(discovered)}",
            "module-level *_BACKEND/_SEAT/_PIN/_JUDGE literals",
        ),
        *(pin_hop(pin, backends, models, seats) for pin in discovered),
        catalog_hop(ctx, portal),
    ]
    for backend in backends:
        hops.extend(backend_hops(backend, models))
    return hops
