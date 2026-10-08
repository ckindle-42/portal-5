#!/usr/bin/env python3
"""Move Open WebUI's RAG embeddings to EmbeddingGemma 2 and re-embed every stored collection
(TASK_EG2_CUTOVER_V1 C3).

Open WebUI persists its embedding engine/model/URL in webui.db, which overrides the compose env,
so the switch goes through its own admin API (``/api/v1/retrieval/embedding/update``). The
query/content prefixes are env-only in Open WebUI and come from the compose file (pinned to
``portal.platform.embedding.contract.format_text`` by a unit test).

Re-embedding uses only Open WebUI's own endpoints, in this order:

1. knowledge bases: ``/api/v1/knowledge/reindex`` (rebuilds each KB and its files' ``file-*``)
2. KB metadata: ``/api/v1/knowledge/metadata/reindex``
3. Open WebUI memories: ``/api/v1/memories/reindex``
4. every remaining ``file-*`` collection, one file at a time, from the file's stored text via
   ``/api/v1/retrieval/process/file`` with ``content`` (which drops and rebuilds the collection).

Steps 1-3 are idempotent whole-set calls; step 4 checkpoints each finished file id, so a rerun
only does what is left. Collections whose file row no longer exists cannot be queried by Open
WebUI and are reported, not touched.

    python3 scripts/owui_reembed.py record  --out PRE.json   # snapshot collections + dims
    python3 scripts/owui_reembed.py switch                   # point OWUI at :8946
    python3 scripts/owui_reembed.py run     --pre PRE.json   # re-embed (resumable)
    python3 scripts/owui_reembed.py verify                   # every live collection is 768d
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

OWUI = os.environ.get("OPENWEBUI_URL", "http://localhost:8080").rstrip("/")
CONTAINER = os.environ.get("OWUI_CONTAINER", "portal5-open-webui")
EG2_BASE = os.environ.get("OWUI_EG2_BASE_URL", "http://host.docker.internal:8946/v1")
EG2_MODEL = os.environ.get("EG2_MODEL", "google/embeddinggemma-2")
TARGET_DIM = 768
BATCH = 32
DEFAULT_CKPT = Path("/Volumes/data01/portal5_backups/owui_reembed_checkpoint.json")

# Runs inside the Open WebUI container. Reads Chroma's own sqlite catalog (collection name +
# dimension) read-only; a second chromadb client loading every collection does not fit in the
# container's 2 GiB limit (exit 137, and it took Open WebUI down with it).
_INSPECT = r"""
import json, sqlite3
cdb = sqlite3.connect('file:/app/backend/data/vector_db/chroma.sqlite3?mode=ro', uri=True)
db = sqlite3.connect('file:/app/backend/data/webui.db?mode=ro', uri=True)
files = {r[0] for r in db.execute('select id from file')}
kb_files = {r[0] for r in db.execute('select file_id from knowledge_file')}
out = {}
for n, dim in cdb.execute('select name, dimension from collections'):
    fid = n[5:] if n.startswith('file-') else None
    out[n] = {'dim': dim,
              'file_row': (fid in files) if fid else None,
              'in_kb': (fid in kb_files) if fid else None}
print(json.dumps(out))
"""


def _key() -> str:
    key = os.environ.get("OWUI_API_KEY")
    if not key:
        env = Path(__file__).resolve().parents[1] / ".env"
        for line in env.read_text().splitlines() if env.is_file() else []:
            if line.startswith("OWUI_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        sys.exit("OWUI_API_KEY not set (env or .env)")
    return key


def _client(timeout: float = 600) -> httpx.Client:
    return httpx.Client(
        base_url=OWUI, headers={"Authorization": f"Bearer {_key()}"}, timeout=timeout
    )


def inspect() -> dict[str, Any]:
    r = subprocess.run(
        ["docker", "exec", CONTAINER, "python", "-W", "ignore", "-c", _INSPECT],
        capture_output=True,
        text=True,
        check=True,
    )
    return dict(json.loads(r.stdout.strip().splitlines()[-1]))


def record(out: Path) -> None:
    snap = {"taken_at": time.time(), "collections": inspect()}
    out.write_text(json.dumps(snap, indent=1))
    dims: dict[str, int] = {}
    for c in snap["collections"].values():
        dims[str(c["dim"])] = dims.get(str(c["dim"]), 0) + 1
    print(f"{len(snap['collections'])} collections, dims {dims} -> {out}")


def switch() -> None:
    with _client() as c:
        cur = c.get("/api/v1/retrieval/embedding")
        cur.raise_for_status()
        cfg = cur.json()
        body = {
            "RAG_EMBEDDING_ENGINE": "openai",
            "RAG_EMBEDDING_MODEL": EG2_MODEL,
            "RAG_EMBEDDING_BATCH_SIZE": BATCH,
            "ENABLE_ASYNC_EMBEDDING": cfg.get("ENABLE_ASYNC_EMBEDDING", True),
            "RAG_EMBEDDING_CONCURRENT_REQUESTS": cfg.get("RAG_EMBEDDING_CONCURRENT_REQUESTS", 0),
            "openai_config": {"url": EG2_BASE, "key": (cfg.get("openai_config") or {}).get("key")},
        }
        r = c.post("/api/v1/retrieval/embedding/update", json=body)
        r.raise_for_status()
        new = r.json()
    print(
        f"embedding: {cfg.get('RAG_EMBEDDING_MODEL')} @ {(cfg.get('openai_config') or {}).get('url')}"
        f" -> {new['RAG_EMBEDDING_MODEL']} @ {new['openai_config']['url']}"
        f" (batch {new['RAG_EMBEDDING_BATCH_SIZE']})"
    )


def _load(ckpt: Path) -> dict[str, Any]:
    if ckpt.is_file():
        return dict(json.loads(ckpt.read_text()))
    return {"steps": {}, "files_done": [], "files_failed": {}}


def _save(ckpt: Path, state: dict[str, Any]) -> None:
    tmp = ckpt.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    os.replace(tmp, ckpt)


def run(pre: Path, ckpt: Path) -> None:
    before = json.loads(pre.read_text())["collections"]
    state = _load(ckpt)
    with _client() as c:
        for step, path in (
            ("knowledge", "/api/v1/knowledge/reindex"),
            ("knowledge_metadata", "/api/v1/knowledge/metadata/reindex"),
            ("memories", "/api/v1/memories/reindex"),
        ):
            if state["steps"].get(step):
                continue
            t = time.time()
            r = c.post(path)
            r.raise_for_status()
            state["steps"][step] = {"at": time.time(), "seconds": round(time.time() - t, 1)}
            _save(ckpt, state)
            print(f"{step}: done in {state['steps'][step]['seconds']}s", flush=True)

        todo = sorted(
            n[5:]
            for n, m in before.items()
            if n.startswith("file-") and m["file_row"] and not m["in_kb"]
        )
        done = set(state["files_done"])
        left = [f for f in todo if f not in done]
        print(f"files: {len(todo)} standalone, {len(left)} left", flush=True)
        for i, fid in enumerate(left, 1):
            try:
                g = c.get(f"/api/v1/files/{fid}/data/content")
                g.raise_for_status()
                content = (g.json() or {}).get("content") or ""
                if not content.strip():
                    raise ValueError("no stored content")
                p = c.post(
                    "/api/v1/retrieval/process/file", json={"file_id": fid, "content": content}
                )
                p.raise_for_status()
            except (httpx.HTTPError, ValueError) as e:
                state["files_failed"][fid] = str(e)[:300]
            else:
                state["files_done"].append(fid)
                state["files_failed"].pop(fid, None)
            if i % 10 == 0 or i == len(left):
                _save(ckpt, state)
                print(f"files: {len(state['files_done'])}/{len(todo)}", flush=True)
    orphans = [n for n, m in before.items() if n.startswith("file-") and not m["file_row"]]
    print(f"failed {len(state['files_failed'])}; orphan collections left as-is: {orphans}")


def verify() -> int:
    now = inspect()
    bad = {
        n: m["dim"]
        for n, m in now.items()
        if m["dim"] not in (TARGET_DIM, None) and (m["file_row"] is not False)
    }
    dims: dict[str, int] = {}
    for m in now.values():
        dims[str(m["dim"])] = dims.get(str(m["dim"]), 0) + 1
    print(f"{len(now)} collections, dims {dims}; reachable non-{TARGET_DIM}d: {bad}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--out", type=Path, required=True)
    sub.add_parser("switch")
    u = sub.add_parser("run")
    u.add_argument("--pre", type=Path, required=True)
    u.add_argument("--checkpoint", type=Path, default=DEFAULT_CKPT)
    sub.add_parser("verify")
    a = ap.parse_args()
    if a.cmd == "record":
        record(a.out)
    elif a.cmd == "switch":
        switch()
    elif a.cmd == "run":
        run(a.pre, a.checkpoint)
    else:
        return verify()
    return 0


if __name__ == "__main__":
    sys.exit(main())
