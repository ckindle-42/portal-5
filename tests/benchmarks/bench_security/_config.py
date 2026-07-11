"""SHIM — moved to portal.modules.security.core._config. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core._config as _real

sys.modules[__name__] = _real
