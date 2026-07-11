"""SHIM — moved to portal.modules.security.core.validate_captures. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.validate_captures as _real

sys.modules[__name__] = _real
