"""SHIM — moved to portal.modules.security.core.siem.capture_enrichment. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.siem.capture_enrichment as _real

sys.modules[__name__] = _real
