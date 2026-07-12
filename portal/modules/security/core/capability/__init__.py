"""Capability index + retrieval — makes the security library legible to
the decide step (TASK_SEC_CAPABILITY_INDEX_V1, Stage 1).

Read-only: indexes what already exists (tool arsenal, service probes,
challenge classes, lab targets, oracles, field-journal priors) into one
queryable index. Changes nothing about how engagements execute.

Public surface:
    tool_inventory.load_tool_catalog() / tools_for_service() / tools_for_phase()
    index.build_index() / index.query()
    render.render_capabilities() / render.render_tool_arsenal()
"""

from __future__ import annotations

from portal.modules.security.core.capability.index import Capability, build_index, query
from portal.modules.security.core.capability.render import (
    render_capabilities,
    render_tool_arsenal,
)
from portal.modules.security.core.capability.tool_inventory import (
    load_tool_catalog,
    tools_for_phase,
    tools_for_service,
    verify_tools_present,
)

__all__ = [
    "Capability",
    "build_index",
    "query",
    "render_capabilities",
    "render_tool_arsenal",
    "load_tool_catalog",
    "tools_for_phase",
    "tools_for_service",
    "verify_tools_present",
]
