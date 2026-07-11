"""SHIM — moved to portal.modules.security.core.llm_redteam. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.llm_redteam as _real

sys.modules[__name__] = _real
