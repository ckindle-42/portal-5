"""SHIM — moved to portal.modules.security.core.response_loop. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.response_loop as _real

sys.modules[__name__] = _real
