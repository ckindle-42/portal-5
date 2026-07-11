"""SHIM — moved to portal.modules.security.core.oast_bench. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.oast_bench as _real

sys.modules[__name__] = _real
