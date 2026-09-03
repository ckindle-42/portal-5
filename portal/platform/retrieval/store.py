"""LanceDB store stage — moved verbatim from ``rag_multimodal`` (SEAM V1 P3).

Table open/create, the KB list, and the model + stage-set stamp sidecar
(``meta_path`` / ``read_stamp`` / ``write_stamp`` / ``assert_embedding_space``).
``require_lance_dir`` (``lance_guard``) still runs first on connect. The
compliance composition (P7) points ``RAG_DIR`` at its own directory so its
tables never collide with ``kb_*``.
"""

from __future__ import annotations

import json
import os
import time

import lancedb
import pyarrow as pa

from portal.platform.retrieval import embedding as _embedding
from portal.platform.retrieval.embedding import VLUnavailableError

LANCE_DIR = os.environ.get("PORTAL5_LANCE_DIR", "/Volumes/data01/portal5_lance")
RAG_DIR = os.path.join(LANCE_DIR, "rag")

_db = None


def get_db():
    global _db
    if _db is None:
        from portal.platform.lance_guard import require_lance_dir

        require_lance_dir(LANCE_DIR)
        os.makedirs(RAG_DIR, exist_ok=True)
        _db = lancedb.connect(RAG_DIR)
    return _db


# SEAM V1 P7: a second composition (compliance) reuses this stage with its own
# table prefix, so its tables and stamps never collide with `kb_*`. Everything is
# keyed off `prefix`; the default keeps the general RAG unchanged.
DEFAULT_PREFIX = "kb_"


def meta_path(kb_id: str, prefix: str = DEFAULT_PREFIX) -> str:
    """Sidecar recording which embedding model + stage set produced a KB's index.
    A JSON file next to the LanceDB dir — no vector-table schema change."""
    return os.path.join(RAG_DIR, f"{prefix}{kb_id}.meta.json")


def read_stamp(kb_id: str, prefix: str = DEFAULT_PREFIX) -> dict | None:
    try:
        with open(meta_path(kb_id, prefix)) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def write_stamp(
    kb_id: str,
    embed_model: str,
    dim: int,
    stage_set: dict | None = None,
    prefix: str = DEFAULT_PREFIX,
) -> None:
    """Record which embedding model AND which stage set produced a KB's index.

    SEAM V1 P6: the stage set (chunker, chunk size/overlap, figure-page policy,
    transcription setting, fusion mode) is stamped alongside the embedding model
    so that when a stage changes — a migration, not a flag — a stale index is
    caught by the same machinery, not a new one. A KB with no ``stage_set`` key
    predates the stamp and is not blocked (same grandfathering as ``embed_model``).
    """
    payload: dict = {"embed_model": embed_model, "vl_dim": dim, "stamped_at": time.time()}
    if stage_set is not None:
        payload["stage_set"] = stage_set
    with open(meta_path(kb_id, prefix), "w") as fh:
        json.dump(payload, fh)


def assert_embedding_space(
    kb_id: str,
    live_model: str,
    stage_set: dict | None = None,
    prefix: str = DEFAULT_PREFIX,
) -> None:
    """Raise if the KB was stamped with a different embedding model or, when a
    ``stage_set`` is supplied and the KB carries one, a different stage set."""
    stamp = read_stamp(kb_id, prefix)
    if not stamp:
        return
    if stamp.get("embed_model") not in (None, "?", live_model):
        raise VLUnavailableError(
            f"KB '{kb_id}' was embedded with '{stamp['embed_model']}' but the VL "
            f"server now serves '{live_model}'. Stored vectors and live queries "
            f"are in different spaces — re-run rag_multimodal.reindex_all()."
        )
    stamped = stamp.get("stage_set")
    if stage_set is not None and stamped is not None and stamped != stage_set:
        changed = sorted(
            k for k in set(stamped) | set(stage_set) if stamped.get(k) != stage_set.get(k)
        )
        raise VLUnavailableError(
            f"KB '{kb_id}' was indexed with a different retrieval stage set — "
            f"changed: {', '.join(changed)} "
            f"(stamped {[(k, stamped.get(k)) for k in changed]}, "
            f"running {[(k, stage_set.get(k)) for k in changed]}). "
            f"A stage change is a re-ingest, not a flag — re-ingest this KB."
        )


def tname(kb_id: str, prefix: str = DEFAULT_PREFIX) -> str:
    return f"{prefix}{kb_id}"


def vname(kb_id: str, prefix: str = DEFAULT_PREFIX) -> str:
    return f"{prefix}{kb_id}_visual"


def text_table(kb_id: str, create: bool = False, prefix: str = DEFAULT_PREFIX):
    db = get_db()
    name = tname(kb_id, prefix)
    if name in db.table_names():
        return db.open_table(name)
    if not create:
        return None
    schema = pa.schema(
        [
            pa.field("chunk_id", pa.string()),
            pa.field("kb_id", pa.string()),
            pa.field("source_file", pa.string()),
            pa.field("chunk_index", pa.int64()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), _embedding.VL_DIM)),
            pa.field("char_start", pa.int64()),
            pa.field("char_end", pa.int64()),
            pa.field("ingested_at", pa.float64()),
        ]
    )
    return db.create_table(name, schema=schema)


def visual_table(kb_id: str, create: bool = False, prefix: str = DEFAULT_PREFIX):
    db = get_db()
    name = vname(kb_id, prefix)
    if name in db.table_names():
        return db.open_table(name)
    if not create:
        return None
    schema = pa.schema(
        [
            pa.field("chunk_id", pa.string()),
            pa.field("kb_id", pa.string()),
            pa.field("source_file", pa.string()),
            pa.field("page", pa.int64()),
            pa.field("image_path", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), _embedding.VL_DIM)),
            pa.field("ingested_at", pa.float64()),
        ]
    )
    return db.create_table(name, schema=schema)


def list_kbs(prefix: str = DEFAULT_PREFIX) -> list[str]:
    n = len(prefix)
    return sorted(
        t[n:] for t in get_db().table_names() if t.startswith(prefix) and not t.endswith("_visual")
    )
