# MCP services package - local portal MCP services
# This also re-exports the MCP SDK to avoid namespace conflicts

import sys
import importlib.util

# Load the MCP SDK from site-packages
# This ensures mcp.server is available even when local mcp shadows the SDK
try:
    # Find the mcp package in site-packages
    for path in sys.path:
        if 'site-packages' in path:
            sdk_path = f"{path}/mcp"
            try:
                spec = importlib.util.spec_from_file_location("mcp_server_sdk", f"{sdk_path}/server/__init__.py")
                if spec and spec.loader:
                    mcp_server_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mcp_server_module)
                    # Make it available as mcp.server
                    sys.modules['mcp.server'] = mcp_server_module
                    break
            except (FileNotFoundError, AttributeError):
                continue
except Exception:
    pass