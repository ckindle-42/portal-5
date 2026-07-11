"""SHIM — moved to portal.modules.security.core.commands.run. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.commands.run as _real

sys.modules[__name__] = _real
