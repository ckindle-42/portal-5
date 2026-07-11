"""SHIM — moved to portal.modules.security.core.decision_engine. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.decision_engine as _real

sys.modules[__name__] = _real
