"""SHIM — moved to portal.modules.security.core.model_survey. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.model_survey as _real

sys.modules[__name__] = _real
