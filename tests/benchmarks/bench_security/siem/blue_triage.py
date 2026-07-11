"""SHIM — moved to portal.modules.security.core.siem.blue_triage. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.siem.blue_triage as _real

sys.modules[__name__] = _real
