"""SHIM — moved to portal.modules.media.tools.utils. Removed in the final cleanup slice."""

import sys

import portal.modules.media.tools.utils as _real

sys.modules[__name__] = _real
