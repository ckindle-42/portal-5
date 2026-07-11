"""SHIM — moved to portal.modules.security.core.episode. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.episode as _real

sys.modules[__name__] = _real
