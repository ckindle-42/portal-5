"""SHIM — moved to portal.modules.security.core.rescore_run. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.rescore_run as _real

sys.modules[__name__] = _real
