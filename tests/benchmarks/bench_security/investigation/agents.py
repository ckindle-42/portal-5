"""SHIM — moved to portal.modules.security.core.investigation.agents. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.investigation.agents as _real

sys.modules[__name__] = _real
