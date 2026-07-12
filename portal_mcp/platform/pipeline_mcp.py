"""SHIM — moved to portal.platform.mcp_host.pipeline_mcp. Removed in the final cleanup slice."""

import runpy
import sys

import portal.platform.mcp_host.pipeline_mcp as _real

sys.modules[__name__] = _real

if __name__ == "__main__":
    runpy.run_module("portal.platform.mcp_host.pipeline_mcp", run_name="__main__")
