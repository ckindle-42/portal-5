"""SHIM — moved to portal.modules.eval.persona_matrix.loaders. Removed in the final cleanup slice."""

import sys

import portal.modules.eval.persona_matrix.loaders as _real

sys.modules[__name__] = _real
