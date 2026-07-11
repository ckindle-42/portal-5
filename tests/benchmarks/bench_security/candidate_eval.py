"""SHIM — moved to portal.modules.security.core.candidate_eval. Removed in the final cleanup slice."""

import sys

import portal.modules.security.core.candidate_eval as _real

sys.modules[__name__] = _real
