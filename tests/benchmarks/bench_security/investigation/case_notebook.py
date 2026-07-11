"""SHIM — moved to portal.modules.security.core.investigation.case_notebook. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.investigation.case_notebook as _real

sys.modules[__name__] = _real
