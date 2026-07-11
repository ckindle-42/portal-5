"""SHIM — moved to portal.modules.security.core.exec_chain. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.exec_chain as _real

sys.modules[__name__] = _real
