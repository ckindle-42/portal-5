"""SHIM — moved to portal.modules.security.core.loop. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.loop as _real

sys.modules[__name__] = _real
