"""SHIM — moved to portal.modules.security.core.stage2_propose. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.stage2_propose as _real

sys.modules[__name__] = _real
