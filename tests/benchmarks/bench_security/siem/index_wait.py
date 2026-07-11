"""SHIM — moved to portal.modules.security.core.siem.index_wait. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.siem.index_wait as _real

sys.modules[__name__] = _real
