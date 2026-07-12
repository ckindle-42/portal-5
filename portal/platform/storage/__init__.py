"""Public surface for Portal's config loader (storage/config-loader — M0 of
BUILD_PROGRAM_MODULARIZATION_ALL_V1).

Same facade pattern as portal.modules.security.knowledge: the config loader
lives with the inference pipeline that consumes it most directly
(portal.platform.inference.config) — this is a stable re-export boundary
for other code that needs config access without depending on the whole
inference package.
"""

from portal.platform.inference.config import (
    PortalConfig,
    get_pipeline_mcp_servers,
    get_workspace_dict,
    load_persona_map,
    load_portal_config,
    ollama_url,
)

__all__ = [
    "PortalConfig",
    "get_pipeline_mcp_servers",
    "get_workspace_dict",
    "load_persona_map",
    "load_portal_config",
    "ollama_url",
]
