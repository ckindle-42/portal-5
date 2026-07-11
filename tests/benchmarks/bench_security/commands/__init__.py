"""SHIM — moved to portal.modules.security.core.commands. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.commands as _real

sys.modules[__name__] = _real
