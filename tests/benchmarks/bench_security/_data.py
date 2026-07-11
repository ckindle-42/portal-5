"""SHIM — moved to portal.modules.security.core._data. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core._data as _real

sys.modules[__name__] = _real
