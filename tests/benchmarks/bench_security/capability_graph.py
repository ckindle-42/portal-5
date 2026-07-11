"""SHIM — moved to portal.modules.security.core.capability_graph. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.capability_graph as _real

sys.modules[__name__] = _real
