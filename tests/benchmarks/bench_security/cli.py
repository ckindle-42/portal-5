"""SHIM — moved to portal.modules.security.core.cli. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.cli as _real

sys.modules[__name__] = _real
