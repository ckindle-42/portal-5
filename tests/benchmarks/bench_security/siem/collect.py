"""SHIM — moved to portal.modules.security.core.siem.collect. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.siem.collect as _real

sys.modules[__name__] = _real
