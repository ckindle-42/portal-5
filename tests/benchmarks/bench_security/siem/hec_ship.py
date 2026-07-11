"""SHIM — moved to portal.modules.security.core.siem.hec_ship. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.siem.hec_ship as _real

sys.modules[__name__] = _real
