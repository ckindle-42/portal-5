"""SHIM — moved to portal.modules.security.core.refusal. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.refusal as _real

sys.modules[__name__] = _real
