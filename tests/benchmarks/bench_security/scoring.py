"""SHIM — moved to portal.modules.security.core.scoring. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.scoring as _real

sys.modules[__name__] = _real
