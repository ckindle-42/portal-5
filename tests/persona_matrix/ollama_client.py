"""SHIM — moved to portal.modules.eval.persona_matrix.ollama_client. Removed in the final cleanup slice."""

import sys

import portal.modules.eval.persona_matrix.ollama_client as _real

sys.modules[__name__] = _real
