"""SHIM — moved to portal.modules.security.core.telemetry. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.telemetry as _real

sys.modules[__name__] = _real
