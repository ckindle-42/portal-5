"""Re-embed the graph-memory store into the EmbeddingGemma 2 space (TASK_EG2_CUTOVER_V1 C2).

The retired :8917 embedder wrote 1024d vectors with no identity stamp; ``graph_memory`` now
embeds 768d EG2 SEARCH vectors and refuses a store in any other dimension. This rewrites the
``memory`` and ``memory_entities`` tables in place. Relations carry no vectors and are untouched.

Resumable: every embedded batch is written to a checkpoint inside the store, so a rerun embeds
only what is missing. Each table is rebuilt through a ``<table>__reembed`` staging copy, and a
run that died between dropping a table and recreating it restores from that copy.

    python -m portal.platform.memory.reembed            # back up, re-embed, swap
    python -m portal.platform.memory.reembed --check    # report state, change nothing
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]  # pyarrow ships no stubs/py.typed

from portal.platform.embedding.contract import Role, Task
from portal.platform.memory import graph_memory as gm

BATCH = 64
CHECKPOINT = "_reembed_checkpoint.json"
BACKUP_DIR = "_backup_pre_eg2"
TABLES: dict[str, Any] = {
    gm.MEMORY_TABLE: lambda r: str(r["text"]),
    gm.ENTITIES_TABLE: lambda r: f"{r['name']} ({r['etype']})",
}


def _store() -> Path:
    return Path(gm.LANCE_DIR)


def _dim(tbl: Any) -> int:
    return int(tbl.schema.field("vector").type.list_size)


def _names(db: Any) -> set[str]:
    return set(db.table_names())


def _load_checkpoint() -> dict[str, dict[str, list[float]]]:
    p = _store() / CHECKPOINT
    return json.loads(p.read_text()) if p.is_file() else {}


def _save_checkpoint(ck: dict[str, dict[str, list[float]]]) -> None:
    p = _store() / CHECKPOINT
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(ck))
    os.replace(tmp, p)


def _backup() -> Path:
    """Copy every table directory once, before anything is rewritten."""
    dest = _store() / BACKUP_DIR
    if dest.exists():
        return dest
    dest.mkdir()
    for d in _store().glob("*.lance"):
        shutil.copytree(d, dest / d.name)
    return dest


def _restore_interrupted_swap(db: Any) -> None:
    for name in TABLES:
        staged = f"{name}__reembed"
        if staged in _names(db) and name not in _names(db):
            db.create_table(name, data=db.open_table(staged).to_arrow())
            db.drop_table(staged)


def state() -> dict[str, Any]:
    db = gm._conn()
    out: dict[str, Any] = {"store": str(_store()), "target_dim": gm.EMBEDDING_DIM}
    for name in TABLES:
        if name in _names(db):
            t = db.open_table(name)
            out[name] = {"rows": t.count_rows(), "dim": _dim(t)}
    out["checkpoint_rows"] = {k: len(v) for k, v in _load_checkpoint().items()}
    return out


async def _reembed_table(db: Any, name: str, ck: dict[str, dict[str, list[float]]]) -> int:
    if name not in _names(db):
        return 0
    tbl = db.open_table(name)
    if _dim(tbl) == gm.EMBEDDING_DIM:
        return 0
    rows = tbl.to_arrow().to_pylist()
    done = ck.setdefault(name, {})
    todo = [r for r in rows if r["id"] not in done]
    text_of = TABLES[name]
    for s in range(0, len(todo), BATCH):
        batch = todo[s : s + BATCH]
        vecs = await gm._client.embed_texts(
            [text_of(r) for r in batch], task=Task.SEARCH, role=Role.DOCUMENT, dim=gm.EMBEDDING_DIM
        )
        done.update({r["id"]: v for r, v in zip(batch, vecs, strict=True)})
        _save_checkpoint(ck)
        print(f"{name}: {len(done)}/{len(rows)} embedded", flush=True)

    version = await gm._version()
    old = tbl.schema
    fields = [
        pa.field("vector", pa.list_(pa.float32(), gm.EMBEDDING_DIM)) if f.name == "vector" else f
        for f in old
        if f.name != "embedding_version"
    ]
    at = [i for i, f in enumerate(fields) if f.name == "vector"][0] + 1
    fields.insert(at, pa.field("embedding_version", pa.string()))
    schema = pa.schema(fields)
    new_rows = [{**r, "vector": done[r["id"]], "embedding_version": version} for r in rows]
    staged = f"{name}__reembed"
    if staged in _names(db):
        db.drop_table(staged)
    st = db.create_table(staged, data=pa.Table.from_pylist(new_rows, schema=schema))
    if st.count_rows() != len(rows):
        raise RuntimeError(f"{staged}: {st.count_rows()} rows staged, expected {len(rows)}")
    db.drop_table(name)
    db.create_table(name, data=st.to_arrow())
    db.drop_table(staged)
    return len(rows)


async def run() -> dict[str, Any]:
    db = gm._conn()
    _restore_interrupted_swap(db)
    backup = _backup()
    ck = _load_checkpoint()
    out: dict[str, Any] = {"backup": str(backup)}
    for name in TABLES:
        out[name] = await _reembed_table(db, name, ck)
    p = _store() / CHECKPOINT
    if p.is_file():  # keep the finished checkpoint as a record, never delete it
        os.replace(p, p.with_name(f"{CHECKPOINT}.done-{int(time.time())}"))
    gm._tables.clear()
    out["after"] = state()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="report store state only")
    a = ap.parse_args()
    print(json.dumps(state() if a.check else asyncio.run(run()), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
