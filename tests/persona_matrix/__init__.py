"""SHIM — moved to portal.modules.eval.persona_matrix. Removed in the final cleanup slice."""

import sys

import portal.modules.eval.persona_matrix as _real

sys.modules[__name__] = _real
