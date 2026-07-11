"""SHIM — moved to portal.modules.security.core.oracles. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.oracles as _real

sys.modules[__name__] = _real
