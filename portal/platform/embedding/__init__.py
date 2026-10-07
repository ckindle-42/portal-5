"""Platform embedding service client — one embedder for every consumer.

TASK_EMBEDDINGGEMMA2_PLATFORM_V1. The EmbeddingGemma 2 service (:8946,
``scripts/eg2-embedding-server.py``) is the single embedding backend. This
package is the only way platform code talks to it:

* ``contract``   — task prefixes, Matryoshka dimensions, vector math, identity.
* ``client``     — async HTTP client (httpx only).
* ``classifier`` — anchor-set nearest-neighbour classifier over the service.

Pure stdlib + httpx by construction: ``Dockerfile.pipeline`` copies
``portal/platform/`` into an image that has fastapi/uvicorn/httpx/pyyaml and
nothing numeric, and Rule 8 forbids torch/transformers anywhere under
``portal/platform/inference/``. Nothing here may import numpy.
"""

from __future__ import annotations

from .contract import (
    MRL_DIMS,
    NATIVE_DIM,
    Identity,
    Role,
    Task,
    cosine,
    format_text,
    l2_normalize,
    truncate,
)

__all__ = [
    "MRL_DIMS",
    "NATIVE_DIM",
    "Identity",
    "Role",
    "Task",
    "cosine",
    "format_text",
    "l2_normalize",
    "truncate",
]
