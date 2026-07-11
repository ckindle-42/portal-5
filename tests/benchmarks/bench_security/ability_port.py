"""SHIM — moved to portal.modules.security.core.ability_port. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.ability_port as _real

sys.modules[__name__] = _real
