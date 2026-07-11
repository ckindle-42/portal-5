"""SHIM — moved to portal.modules.security.core.blue. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.blue as _real

sys.modules[__name__] = _real
