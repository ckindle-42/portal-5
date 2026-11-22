"""QAT configuration and live discovery.

Reads the repo sources of truth — config/portal.yaml, config/personas/*.yaml,
imports/openwebui/workspaces/workspaces_all.json, config/bench_workspaces.yaml
— plus named keys from .env (parsed in-process, never `source .env`). All
counts are derived; nothing about the roster is baked into this package.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PORTAL_YAML = REPO_ROOT / "config" / "portal.yaml"
BENCH_YAML = REPO_ROOT / "config" / "bench_workspaces.yaml"
PRESETS_JSON = REPO_ROOT / "imports" / "openwebui" / "workspaces" / "workspaces_all.json"
PERSONA_DIR = REPO_ROOT / "config" / "personas"
BACKENDS_YAML = REPO_ROOT / "config" / "backends.yaml"

ENV_FILE = REPO_ROOT / ".env"

# Named keys only — QAT never invents or exports ambient env.
_ENV_KEYS: dict[str, str] = {
    "OPENWEBUI_URL": "http://localhost:8080",
    "PIPELINE_URL": "http://localhost:9099",
    "PIPELINE_API_KEY": "portal-pipeline",
    "OPENWEBUI_ADMIN_EMAIL": "admin@portal.local",
    "OPENWEBUI_ADMIN_PASSWORD": "",
    "OWUI_API_KEY": "",
    "OLLAMA_URL": "http://localhost:11434",
    "OMLX_URL": "http://localhost:8085",
    "OMLX_API_KEY": "",
    "AI_OUTPUT_DIR": str(Path.home() / "AI_Output"),
    "PORTAL_ARM_APPROVAL_TTL_SECONDS": "0",
}

DEFAULT_MEM_CAP_PCT = 80.0
DEFAULT_SWEEP_MAX_AGE_DAYS = 7


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    owui_url: str
    pipeline_url: str
    pipeline_api_key: str
    owui_user: str
    owui_pass: str
    owui_api_key: str
    ollama_url: str
    omlx_url: str
    omlx_api_key: str
    workspace_dir: Path
    arm_approval_ttl_s: int
    mem_cap_pct: float = DEFAULT_MEM_CAP_PCT
    sweep_max_age_days: int = DEFAULT_SWEEP_MAX_AGE_DAYS

    @classmethod
    def load(cls, env_file: Path = ENV_FILE, environ: dict[str, str] | None = None) -> Settings:
        env = {k: os.environ.get(k, "") for k in _ENV_KEYS}
        env.update({k: v for k, v in parse_env_file(env_file).items() if v != ""})
        supplied = environ or {}
        merged = {
            k: supplied.get(k) or env.get(k, "") or default for k, default in _ENV_KEYS.items()
        }
        return cls(
            repo_root=REPO_ROOT,
            owui_url=_host_url(merged["OPENWEBUI_URL"]).rstrip("/"),
            pipeline_url=_host_url(merged["PIPELINE_URL"]).rstrip("/"),
            pipeline_api_key=merged["PIPELINE_API_KEY"],
            owui_user=merged["OPENWEBUI_ADMIN_EMAIL"],
            owui_pass=merged["OPENWEBUI_ADMIN_PASSWORD"],
            owui_api_key=merged["OWUI_API_KEY"],
            ollama_url=_host_url(merged["OLLAMA_URL"]).rstrip("/"),
            omlx_url=_host_url(merged["OMLX_URL"]).rstrip("/"),
            omlx_api_key=merged["OMLX_API_KEY"],
            workspace_dir=Path(merged["AI_OUTPUT_DIR"]),
            arm_approval_ttl_s=_to_int(merged["PORTAL_ARM_APPROVAL_TTL_SECONDS"]),
        )

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.pipeline_api_key}"}

    def omlx_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.omlx_api_key}"} if self.omlx_api_key else {}


def _to_int(raw: str) -> int:
    try:
        return int(raw)
    except ValueError:
        return 0


def parse_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE lines; double-quoted values unquoted; comments and blanks skipped."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if not key.isidentifier() and not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        out[key] = value
    return out


@dataclass(frozen=True)
class WorkspaceDef:
    id: str
    name: str
    module: str
    model_hint: str
    tools: tuple[str, ...]
    expose_to_owui: bool
    think: bool
    description: str
    variants: tuple[str, ...]
    exposed_variants: tuple[str, ...] = ()


@dataclass(frozen=True)
class OwuiPreset:
    id: str
    name: str
    tool_ids: tuple[str, ...]
    function_calling: bool
    system: str


@dataclass(frozen=True)
class PersonaDef:
    slug: str
    name: str
    workspace_model: str
    category: str
    model_pin: str


@dataclass(frozen=True)
class McpFleetEntry:
    id: str
    name: str
    port: int
    module: str


@dataclass
class Discovery:
    modules_enabled: frozenset[str]
    workspaces: dict[str, WorkspaceDef]
    presets: dict[str, OwuiPreset]
    personas: tuple[PersonaDef, ...]
    bench_workspaces: dict[str, WorkspaceDef]
    mcp_fleet: tuple[McpFleetEntry, ...]
    gaps: tuple[str, ...] = field(default=())

    def preset_tools(self, preset_id: str) -> tuple[str, ...]:
        preset = self.presets.get(preset_id)
        return preset.tool_ids if preset else ()


def load_modules(portal: dict | None = None) -> frozenset[str]:
    portal = portal if portal is not None else _load_yaml(PORTAL_YAML)
    mods = portal.get("modules") or {}
    return frozenset(m for m, cfg in mods.items() if isinstance(cfg, dict) and cfg.get("enabled"))


def _workspace_def(ws_id: str, cfg: dict) -> WorkspaceDef:
    cfg = cfg or {}
    variants = cfg.get("variants") or {}
    exposed = tuple(
        sorted(v for v, vc in variants.items() if (vc or {}).get("expose_to_owui") is True)
    )
    return WorkspaceDef(
        id=ws_id,
        name=str(cfg.get("name", ws_id)),
        module=str(cfg.get("module", "")),
        model_hint=str(cfg.get("model_hint", "")),
        tools=tuple(str(t) for t in cfg.get("tools") or ()),
        expose_to_owui=cfg.get("expose_to_owui") is True,
        think=bool(cfg.get("think", False)),
        description=str(cfg.get("description", "")),
        variants=tuple(sorted(variants.keys())),
        exposed_variants=exposed,
    )


def load_workspaces(portal: dict | None = None) -> dict[str, WorkspaceDef]:
    portal = portal if portal is not None else _load_yaml(PORTAL_YAML)
    return {wid: _workspace_def(wid, cfg) for wid, cfg in (portal.get("workspaces") or {}).items()}


def primary_model_for(workspace_slug: str, portal_data: dict[str, Any] | None = None) -> str:
    """Return the primary hint for a workspace or inherited variant."""
    if workspace_slug == "auto":
        return ""
    portal = portal_data if portal_data is not None else _load_yaml(PORTAL_YAML)
    workspaces = portal.get("workspaces") or {}
    try:
        from portal.platform.inference.config import effective_workspace

        workspace = effective_workspace(workspaces, workspace_slug)
    except (KeyError, TypeError):
        return ""
    return str(workspace.get("model_hint") or "")


def load_bench_workspaces() -> dict[str, WorkspaceDef]:
    if not BENCH_YAML.is_file():
        return {}
    data = _load_yaml(BENCH_YAML)
    return {wid: _workspace_def(wid, cfg) for wid, cfg in (data.get("workspaces") or {}).items()}


def load_presets(presets: list[dict] | None = None) -> dict[str, OwuiPreset]:
    raw = presets
    if raw is None:
        raw = json.loads(PRESETS_JSON.read_text(encoding="utf-8")) if PRESETS_JSON.is_file() else []
    out: dict[str, OwuiPreset] = {}
    for entry in raw or []:
        pid = str(entry.get("id", ""))
        if not pid:
            continue
        meta = entry.get("meta") or {}
        params = entry.get("params") or {}
        out[pid] = OwuiPreset(
            id=pid,
            name=str(meta.get("name", pid)),
            tool_ids=tuple(str(t) for t in meta.get("toolIds") or ()),
            function_calling=params.get("function_calling") == "native",
            system=str(params.get("system", "")),
        )
    return out


def _host_url(raw: str) -> str:
    """Rewrite Docker-only hostnames so host-side QAT can reach loopback services."""
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    if not (
        host
        in {
            "portal-pipeline",
            "portal_pipeline",
            "host.docker.internal",
            "open-webui",
            "browser-mcp",
        }
        or host.startswith("portal5-")
    ):
        return raw
    userinfo, separator, host_port = parts.netloc.rpartition("@")
    if not separator:
        host_port = parts.netloc
    host_port = f"127.0.0.1{host_port[len(host) :]}"
    netloc = f"{userinfo}@{host_port}" if separator else host_port
    return urlunsplit(parts._replace(netloc=netloc))


def load_personas(persona_dir: Path = PERSONA_DIR) -> tuple[PersonaDef, ...]:
    """Top-level persona YAMLs; bench/ personas are excluded from the roster."""
    out: list[PersonaDef] = []
    if not persona_dir.is_dir():
        return ()
    for path in sorted(persona_dir.glob("*.yaml")):
        data = _load_yaml(path)
        if not isinstance(data, dict):
            continue
        slug = str(data.get("slug", path.stem))
        out.append(
            PersonaDef(
                slug=slug,
                name=str(data.get("name", slug)),
                workspace_model=str(data.get("workspace_model", "")),
                category=str(data.get("category", "")),
                model_pin=str(data.get("model_pin", "")),
            )
        )
    return tuple(out)


def load_mcp_fleet(portal: dict | None = None) -> tuple[McpFleetEntry, ...]:
    portal = portal if portal is not None else _load_yaml(PORTAL_YAML)
    out = []
    for entry in portal.get("mcp_fleet") or []:
        out.append(
            McpFleetEntry(
                id=str(entry.get("id", "")),
                name=str(entry.get("name", "")),
                port=int(entry.get("port", 0) or 0),
                module=str(entry.get("module", "")),
            )
        )
    return tuple(out)


def designed_exposed_ids(workspaces: dict[str, WorkspaceDef], enabled: frozenset[str]) -> set[str]:
    """Workspace + exposed-variant ids the design says OWUI should carry.

    Mirrors sync-config's emission rule: base workspace exposed when
    expose_to_owui, module enabled and not eval; a variant exposed when the
    variant itself sets expose_to_owui (and its module is enabled).
    """
    out: set[str] = set()
    for wid, ws in workspaces.items():
        if ws.module == "eval" or ws.module not in enabled:
            continue
        out.update(f"{wid}::{vid}" for vid in ws.exposed_variants)
        if ws.expose_to_owui:
            out.add(wid)
    return out


def exposure_gaps(discovery: Discovery) -> tuple[str, ...]:
    """Designed-but-missing and preset-without-design, both directions."""
    designed = designed_exposed_ids(discovery.workspaces, discovery.modules_enabled)
    preset_ids = set(discovery.presets)
    missing = sorted(designed - preset_ids)
    extra = sorted(preset_ids - designed)
    return tuple(
        [f"designed-not-seeded: {pid}" for pid in missing]
        + [f"seeded-not-designed: {pid}" for pid in extra]
    )


def discover(portal: dict | None = None, presets: list[dict] | None = None) -> Discovery:
    workspaces = load_workspaces(portal)
    enabled = load_modules(portal)
    preset_map = load_presets(presets)
    d = Discovery(
        modules_enabled=enabled,
        workspaces=workspaces,
        presets=preset_map,
        personas=load_personas(),
        bench_workspaces=load_bench_workspaces(),
        mcp_fleet=load_mcp_fleet(portal),
    )
    d.gaps = exposure_gaps(d)
    return d


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}
