"""SHIM — moved to portal.modules.security.core. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core as _real

sys.modules[__name__] = _real
