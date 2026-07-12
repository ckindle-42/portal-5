"""SHIM — moved to portal.modules.security.tools.proxmox_mcp. Removed in the final cleanup slice."""

import runpy
import sys

import portal.modules.security.tools.proxmox_mcp as _real

sys.modules[__name__] = _real

if __name__ == "__main__":
    runpy.run_module("portal.modules.security.tools.proxmox_mcp", run_name="__main__")
