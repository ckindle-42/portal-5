"""SHIM — moved to portal.modules.security.core.bench_integration. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.bench_integration as _real

sys.modules[__name__] = _real
