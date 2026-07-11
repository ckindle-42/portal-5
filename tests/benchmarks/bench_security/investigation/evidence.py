"""SHIM — moved to portal.modules.security.core.investigation.evidence. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.investigation.evidence as _real

sys.modules[__name__] = _real
