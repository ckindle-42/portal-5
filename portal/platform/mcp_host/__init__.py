"""Portal 5 MCP shared core utilities.

Provides cross-MCP helpers like workspace path resolution. New MCPs should
prefer these helpers over re-implementing path logic. See workspace.py.
"""

from portal.platform.mcp_host.workspace import (
    get_generated_dir,
    get_uploads_dir,
    get_workspace_root,
    resolve_upload_path,
)

__all__ = [
    "get_generated_dir",
    "get_uploads_dir",
    "get_workspace_root",
    "resolve_upload_path",
]
