"""SHIM — moved to portal.modules.security.core.field_journal. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.field_journal as _real

sys.modules[__name__] = _real
