"""SHIM — moved to portal.modules.security.core.unknown_defense. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.unknown_defense as _real

sys.modules[__name__] = _real
