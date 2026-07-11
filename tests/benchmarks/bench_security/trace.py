"""SHIM — moved to portal.modules.security.core.trace. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.trace as _real

sys.modules[__name__] = _real
