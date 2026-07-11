"""SHIM — moved to portal.modules.security.core.self_index. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.self_index as _real

sys.modules[__name__] = _real
