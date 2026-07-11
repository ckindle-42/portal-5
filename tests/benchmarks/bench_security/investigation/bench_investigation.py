"""SHIM — moved to portal.modules.security.core.investigation.bench_investigation. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.investigation.bench_investigation as _real

sys.modules[__name__] = _real
