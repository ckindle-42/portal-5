"""SHIM — moved to portal.modules.security.core.__main__. Removed in the final cleanup slice."""

import runpy

if __name__ == "__main__":
    runpy.run_module("portal.modules.security.core", run_name="__main__")
