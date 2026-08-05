"""Routing policy — workspace catalog, persona map, and tool whitelist resolution.

``WORKSPACES`` is the canonical catalog loaded at import time from
``config/portal.yaml`` via ``get_workspace_dict``; keys must match
``workspace_routing`` in ``config/backends.yaml``. ``bench-*`` workspaces are
user-pickable but excluded from auto-routing. ``_PERSONA_MAP`` maps persona
slugs → PersonaSpec from ``config/personas/``. ``_resolve_persona_tools``
combines persona ``tools_allow``/``tools_deny`` with the workspace default.
The public surface is re-exported from ``router_pipe.py``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from portal.platform.inference.config import (
    PersonaSpec,
    get_workspace_dict,
    load_persona_map,
    load_portal_config,
    resolve_preset_tools,
)

logger = logging.getLogger(__name__)

# ── Persona map (for tool whitelist resolution) ─────────────────────────────
# Loaded at import time; keys are persona slugs, values are PersonaSpec instances.
_PERSONA_MAP: dict[str, PersonaSpec] = {}  # type: ignore[assignment]


def _load_persona_map() -> None:
    """Populate ``_PERSONA_MAP`` from the typed PersonaSpec loader."""
    global _PERSONA_MAP
    _PERSONA_MAP.update(load_persona_map())  # type: ignore[arg-type]


_load_persona_map()

# ─── Canonical workspace catalog ─────────────────────────────────────────────
# Keys here MUST match `workspace_routing` in config/backends.yaml exactly
# (consistency is enforced on startup).
#
# Per-entry fields (all optional except `name` and `description`):
#   name                       Display name shown in Open WebUI.
#   description                Open WebUI tooltip / model description.
#   model_hint                 Preferred Ollama tag in the routed backend group.
#   tools                      Default tool-name whitelist (overridable per-persona).
#   predict_limit              Max output tokens (Ollama: num_predict).
#   context_limit              Max context window for this workspace.
#   max_concurrent             Per-workspace concurrency cap (router_pipe semaphore).
#   system_prompt_append       String appended after the persona system prompt.
#   think                      False → disable Qwen3/thinking-mode extended thinking.
#   emits_reasoning            True → model emits reasoning chains (DeepSeek-R1 family).
#
# Workspace ID prefixes:
#   auto       — auto-routable (the LLM intent classifier may route here).
#   auto-*     — user-selectable AND auto-route targets.
#   bench-*    — user-selectable only; excluded from auto-routing.
# ─────────────────────────────────────────────────────────────────────────────


class _WorkspaceCatalog(dict):
    """dict that hides synthetic ``"<base>::<variant>"`` entries from
    iteration/len/keys/items/values.

    resolve_workspace_variant() lazily caches merged variant configs under a
    synthetic key so ``WORKSPACES.get(id, {})`` picks them up transparently,
    while iteration-shaped views (lifespan hint validation, metrics workspace
    count, keyword-classifier id list) only see the real catalog.
    """

    def __iter__(self):
        return (k for k in super().__iter__() if "::" not in k)

    def keys(self):  # noqa: D102
        return (k for k in super().keys() if "::" not in k)  # noqa: SIM118

    def items(self):  # noqa: D102
        return ((k, v) for k, v in super().items() if "::" not in k)

    def values(self):  # noqa: D102
        return (v for k, v in self.items())

    def __len__(self):
        return sum(1 for _ in self.__iter__())


WORKSPACES: dict[str, dict[str, Any]] = _WorkspaceCatalog(get_workspace_dict(load_portal_config()))

# ── Tool-call helpers ───────────────────────────────────────────────────────

# Max iterations of the streaming tool-call loop before the pipeline gives up.
# Env-overridable. Consumed in router_pipe._stream_with_tool_loop_impl.
MAX_TOOL_HOPS = int(os.environ.get("MAX_TOOL_HOPS", "20"))


def _workspace_tools(workspace_id: str) -> list[str]:
    """Return the default tool whitelist for ``workspace_id``.

    Unknown workspace ids return ``[]`` rather than raising, so a request
    referencing a since-removed workspace still serves without tools.

    Args:
        workspace_id: A ``WORKSPACES`` key. Unknown ids return ``[]``.

    Returns:
        Tool names from the workspace's ``tools`` field, or ``[]``.
    """
    return WORKSPACES.get(workspace_id, {}).get("tools", [])


def _resolve_persona_tools(persona: PersonaSpec | dict, workspace_id: str) -> list[str]:
    """Resolve the effective tool list for one persona × workspace pair.

    Delegates to ``config.resolve_preset_tools``; accepts both ``PersonaSpec``
    and legacy ``dict`` callers. Resolution:
    1. ``tools_allow`` absent (``None``) → use workspace default unchanged.
    2. ``tools_allow`` present (even ``[]``) → replaces workspace default.
    3. ``tools_deny`` removes any matching entries.

    Returns sorted, deduplicated tool names.
    """
    ws_tools = _workspace_tools(workspace_id)
    if isinstance(persona, PersonaSpec):
        return resolve_preset_tools(persona, ws_tools)
    # Legacy dict path (still used by router_pipe direct dict lookups)
    raw_allow = persona.get("tools_allow")
    deny = set(persona.get("tools_deny", []) or [])
    effective = set(ws_tools) if raw_allow is None else set(raw_allow)
    return sorted(effective - deny)


def _resolve_persona_tool_choice(persona: PersonaSpec | dict) -> str | None:
    """Return a persona's ``tool_choice`` override, or ``None`` to inherit the
    request default ("auto"). Accepts both ``PersonaSpec`` and legacy ``dict``.
    """
    if isinstance(persona, PersonaSpec):
        return persona.tool_choice
    return persona.get("tool_choice")
