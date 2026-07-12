"""SHIM — moved to portal.modules.media.tools.tts_mcp. Removed in the final cleanup slice."""

import runpy
import sys

import portal.modules.media.tools.tts_mcp as _real

sys.modules[__name__] = _real

if __name__ == "__main__":
    runpy.run_module("portal.modules.media.tools.tts_mcp", run_name="__main__")
