"""SHIM — moved to portal.modules.security.core._sweep_driver. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core._sweep_driver as _real

sys.modules[__name__] = _real
