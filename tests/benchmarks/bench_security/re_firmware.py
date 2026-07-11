"""SHIM — moved to portal.modules.security.core.re_firmware. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.re_firmware as _real

sys.modules[__name__] = _real
