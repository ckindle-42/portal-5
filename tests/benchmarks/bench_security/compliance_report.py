"""SHIM — moved to portal.modules.security.core.compliance_report. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.compliance_report as _real

sys.modules[__name__] = _real
