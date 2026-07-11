"""SHIM — moved to portal.modules.security.core.capsules. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.capsules as _real

sys.modules[__name__] = _real
