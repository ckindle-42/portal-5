"""SHIM — moved to portal.modules.security.core.siem.spl_backend. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.siem.spl_backend as _real

sys.modules[__name__] = _real
