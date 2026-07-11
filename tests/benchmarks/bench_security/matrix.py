"""SHIM — moved to portal.modules.security.core.matrix. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.matrix as _real

sys.modules[__name__] = _real
