"""bully.config -- hunt.yaml / heart.yaml loading + per-hunt frozen snapshot.

P1.0. No SQL I/O, no network. Pure config loading + a role-alias resolver
that mirrors the `blueteam-council` resolution path (config/portal.yaml) so
that no bully module ever hardcodes a model tag (MASTER SS3, SS11).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# HARV corpus roles whose learned behavior is actually consumed by the
# investigation arm. The deterministic cousin classifier is intentionally
# absent: its weights/thresholds are calibrated, never LoRA-trained (P6.7/A5).
REFINEMENT_ROLE_MAP: dict[str, str] = {
    "hunter": "tool",
    "analyst": "reasoning",
    "disprover": "expert",
}

_REPO_ROOT = Path(__file__).resolve().parents[5]
_HUNT_YAML = _REPO_ROOT / "config" / "security" / "hunt.yaml"
_HEART_YAML = _REPO_ROOT / "config" / "security" / "heart.yaml"


class ConfigError(RuntimeError):
    """Raised when hunt/heart config is missing or malformed."""


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"missing required config file: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ConfigError(f"{path} did not parse to a mapping")
    return data


def load_hunt_config(path: Path | None = None) -> dict[str, Any]:
    """Load ``config/security/hunt.yaml`` (operator dials for LOOP/MUT/TGT/PLT)."""
    return _load_yaml(path or _HUNT_YAML)


def load_heart_config(path: Path | None = None) -> dict[str, Any]:
    """Load ``config/security/heart.yaml`` (council floors + roster + waiver policy)."""
    return _load_yaml(path or _HEART_YAML)


def resolve_role_model(role: str, *, hunt_config: dict[str, Any] | None = None) -> str | list[str]:
    """Resolve a bully model *role* (e.g. ``"tool"``, ``"reasoning"``,
    ``"expert"``) to a concrete Ollama model tag, via the workspace named in
    ``hunt.yaml::models.workspace`` (default ``blueteam-orchestrated``, which
    holds exactly the tool/reasoning/expert trio the investigation arm's
    ``_run_three_section`` expects) — mirroring the precedent resolution
    path documented at ``config/portal.yaml::workspaces.blueteam-council``
    (a sibling confirm-only workspace holding the analogous
    tool_model/council_models/expert_model trio for the council variant).

    Never returns a literal hardcoded model name from this module: the tag
    always comes from config/portal.yaml at call time, so a model-catalog
    change under the operator's feet is picked up automatically (MASTER SS5).
    """
    cfg = hunt_config or load_hunt_config()
    models_cfg = cfg.get("models") or {}
    workspace_id = models_cfg.get("workspace", "blueteam-orchestrated")
    field_map = models_cfg.get("role_fields") or {
        "tool": "tool_model",
        "reasoning": "reasoning_model",
        "expert": "expert_model",
    }
    field = field_map.get(role)
    if field is None:
        raise ConfigError(
            f"unknown bully model role {role!r}; declare it in hunt.yaml::models.role_fields"
        )

    from portal.platform.inference.config import load_portal_config

    portal_cfg = load_portal_config()
    value = _lookup_workspace_field(portal_cfg, workspace_id, field)
    if value is None:
        raise ConfigError(
            f"workspace/variant {workspace_id!r} referenced by hunt.yaml::models not found in "
            f"portal.yaml, or has no {field!r} configured for role {role!r}"
        )
    return value


def _lookup_workspace_field(portal_cfg: Any, workspace_id: str, field: str) -> Any:
    """Resolve `field` off a top-level workspace OR a *variant* nested under
    one (`WorkspaceSpec.variants: dict[str, dict]`).

    Drift finding (re-anchored live, MASTER SS0): `blueteam-council` and
    `blueteam-orchestrated` are not top-level `config/portal.yaml`
    workspace ids -- both are entries under `auto-security`'s `variants`
    dict (confirm-only variants of the auto-security workspace, not
    separately routable workspaces; `expose_to_owui: false`). The task
    file's "mirroring the blueteam-council resolution path" cites the
    field *names* (tool_model/reasoning_model/expert_model) correctly; the
    container is one level deeper than a flat `workspaces[id]` lookup.
    This function tries a direct top-level workspace first (matches the
    precedent's literal shape if it or a future workspace is ever promoted
    to top-level), then searches every top-level workspace's `variants`
    dict for `workspace_id` as a variant key.
    """
    top_level = portal_cfg.workspaces.get(workspace_id)
    if top_level is not None:
        value = getattr(top_level, field, None)
        if value:
            return value
    for workspace in portal_cfg.workspaces.values():
        variant = (getattr(workspace, "variants", None) or {}).get(workspace_id)
        if variant is not None and variant.get(field):
            return variant[field]
    return None


def resolve_investigation_models(*, hunt_config: dict[str, Any] | None = None) -> dict[str, str]:
    """`{"tool": ..., "reasoning": ..., "expert": ...}` -- exactly the shape
    `investigation.run_arm`/`_run_three_section` expect, each tag resolved
    via `resolve_role_model` (no hardcoded model id)."""
    cfg = hunt_config or load_hunt_config()
    return {
        role: resolve_role_model(role, hunt_config=cfg) for role in ("tool", "reasoning", "expert")
    }


def resolve_council_models(*, hunt_config: dict[str, Any] | None = None) -> list[str]:
    """Resolve HEART's council seat roster to a list of concrete Ollama
    model tags via ``hunt.yaml::models.council_workspace``/``council_field``
    (default ``blueteam-council``/``council_models``) -- same
    config-resolved-alias discipline as `resolve_role_model` (MASTER SS3/
    SS11: no hardcoded model id anywhere in the bully package)."""
    cfg = hunt_config or load_hunt_config()
    models_cfg = cfg.get("models") or {}
    workspace_id = models_cfg.get("council_workspace", "blueteam-council")
    field = models_cfg.get("council_field", "council_models")

    from portal.platform.inference.config import load_portal_config

    portal_cfg = load_portal_config()
    value = _lookup_workspace_field(portal_cfg, workspace_id, field)
    if not value:
        raise ConfigError(
            f"workspace/variant {workspace_id!r} referenced by hunt.yaml::models.council_workspace "
            f"not found in portal.yaml, or has no {field!r} configured"
        )
    if not isinstance(value, list):
        raise ConfigError(f"{workspace_id!r}.{field!r} must be a list of model tags")
    return list(value)


def content_hash(*payloads: dict[str, Any]) -> str:
    """Deterministic content hash of one or more JSON-serializable payloads.

    Used as the hunt row's ``config_version`` (DATA_MODEL SS1.1): the frozen
    per-hunt snapshot is identified by its own content, not a mutable path.
    """
    h = hashlib.sha256()
    for payload in payloads:
        h.update(json.dumps(payload, sort_keys=True, default=str).encode("utf-8"))
    return h.hexdigest()


@dataclass(frozen=True)
class HuntConfigSnapshot:
    """A per-hunt frozen copy of hunt.yaml + heart.yaml (I-3 / I-5 `config_version`).

    Immutable: once a hunt is authorized, later edits to the YAML files on
    disk never retroactively change a running/closed hunt's behavior.
    """

    hunt: dict[str, Any]
    heart: dict[str, Any]
    version: str

    @classmethod
    def capture(
        cls,
        *,
        hunt_config: dict[str, Any] | None = None,
        heart_config: dict[str, Any] | None = None,
    ) -> HuntConfigSnapshot:
        hunt = hunt_config if hunt_config is not None else load_hunt_config()
        heart = heart_config if heart_config is not None else load_heart_config()
        return cls(hunt=hunt, heart=heart, version=content_hash(hunt, heart))

    def to_dict(self) -> dict[str, Any]:
        return {"hunt": self.hunt, "heart": self.heart, "version": self.version}


def hunt_dir() -> Path:
    """``PORTAL5_HUNT_DIR`` (optional override; default ``/Volumes/data01/portal5_hunt/``).

    State (``hunt_state.db``, ``corpus/``, ``playbooks/``, ``artifacts/``)
    lives outside the repo (MASTER SS10).
    """
    raw = os.environ.get("PORTAL5_HUNT_DIR", "/Volumes/data01/portal5_hunt/")
    return Path(raw)
