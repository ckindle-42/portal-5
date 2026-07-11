"""SHIM — moved to portal.modules.security.core.siem. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.siem as _real

sys.modules[__name__] = _real
