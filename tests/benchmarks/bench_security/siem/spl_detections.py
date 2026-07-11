"""SHIM — moved to portal.modules.security.core.siem.spl_detections. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.siem.spl_detections as _real

sys.modules[__name__] = _real
