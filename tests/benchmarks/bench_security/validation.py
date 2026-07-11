"""SHIM — moved to portal.modules.security.core.validation. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.validation as _real

sys.modules[__name__] = _real
