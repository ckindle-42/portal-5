"""Portal Wiki core — stack-agnostic knowledge layer.

ZERO Portal-specific imports.  This is the extraction boundary.
"""

from .interfaces import InferenceBackend, SourceConnector
from .schema import KnowledgeUnit, SourceRef

__all__ = [
    "InferenceBackend",
    "KnowledgeUnit",
    "SourceConnector",
    "SourceRef",
]
