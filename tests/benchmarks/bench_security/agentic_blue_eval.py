"""SHIM — moved to portal.modules.security.core.agentic_blue_eval. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.agentic_blue_eval as _real

sys.modules[__name__] = _real
