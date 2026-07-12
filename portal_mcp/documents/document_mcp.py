"""SHIM — moved to portal.modules.documents.tools.document_mcp. Removed in the final cleanup slice."""

import runpy
import sys

import portal.modules.documents.tools.document_mcp as _real

sys.modules[__name__] = _real

if __name__ == "__main__":
    runpy.run_module("portal.modules.documents.tools.document_mcp", run_name="__main__")
