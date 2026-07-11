"""SHIM — moved to portal.modules.security.core.continuous_eval. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.continuous_eval as _real

sys.modules[__name__] = _real
