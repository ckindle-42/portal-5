"""SHIM — moved to portal.modules.security.tools. Removed in the final cleanup slice."""

import sys

import portal.modules.security.tools as _real

sys.modules[__name__] = _real
