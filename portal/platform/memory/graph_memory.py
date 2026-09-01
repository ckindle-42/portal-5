"""Portal 5 — Temporal knowledge-graph memory (replaces the flat vector store).

This module owns ALL memory endpoints. ``remember`` extracts entities/relations
and populates the graph on write; ``recall`` is graph-aware (vector seed +
relation expansion). ``memory_mcp.py`` registers these and no longer holds any
flat-vector recall logic.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid

import httpx
import lancedb
import pyarrow as pa
from starlette.responses import JSONResponse

LANCE_DIR = os.environ.get("PORTAL5_LANCE_DIR", "/Volumes/data01/portal5_lance")
EMBEDDING_URL = os.environ.get("MLX_EMBEDDING_URL", "http://localhost:8917/v1/embeddings")
EMBEDDING_DIM = 1024
DEFAULT_USER = "default"
MEMORY_TABLE = "memory"
ENTITIES_TABLE = "memory_entities"
RELATIONS_TABLE = "memory_relations"
OLLAMA_CHAT = os.environ.get("OLLAMA_CHAT_URL", "http://localhost:11434/api/chat")
# Small, fast, installed — entity/relation extraction runs on every write.
EXTRACT_MODEL = os.environ.get("MEMORY_EXTRACT_MODEL", "gemma4:e4b-it-q4_K_M")
_MAX_NODES = int(os.environ.get("MEMORY_GRAPH_MAX_NODES", "200"))
_NAME_RE = re.compile(r"^[^'\"\\]{1,200}$")

_db = None
_tables: dict = {}


def _conn():
    global _db
    if _db is None:
        os.makedirs(LANCE_DIR, exist_ok=True)
        _db = lancedb.connect(LANCE_DIR)
    return _db


def _memory_table():
    if "mem" not in _tables:
        db = _conn()
        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("user_id", pa.string()),
                pa.field("text", pa.string()),
                pa.field("category", pa.string()),
                pa.field("tags", pa.list_(pa.string())),
                pa.field("vector", pa.list_(pa.float32(), EMBEDDING_DIM)),
                pa.field("created_at", pa.float64()),
                pa.field("last_accessed_at", pa.float64()),
                pa.field("access_count", pa.int64()),
            ]
        )
        _tables["mem"] = (
            db.create_table(MEMORY_TABLE, schema=schema)
            if MEMORY_TABLE not in db.table_names()
            else db.open_table(MEMORY_TABLE)
        )
    return _tables["mem"]


def _entities():
    if "ent" not in _tables:
        db = _conn()
        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("user_id", pa.string()),
                pa.field("name", pa.string()),
                pa.field("etype", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), EMBEDDING_DIM)),
                pa.field("first_seen", pa.float64()),
                pa.field("last_seen", pa.float64()),
                pa.field("mention_count", pa.int64()),
            ]
        )
        _tables["ent"] = (
            db.create_table(ENTITIES_TABLE, schema=schema)
            if ENTITIES_TABLE not in db.table_names()
            else db.open_table(ENTITIES_TABLE)
        )
    return _tables["ent"]


def _relations():
    if "rel" not in _tables:
        db = _conn()
        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("user_id", pa.string()),
                pa.field("src", pa.string()),
                pa.field("dst", pa.string()),
                pa.field("rel_type", pa.string()),
                pa.field("observed_at", pa.float64()),
                pa.field("source_memory_id", pa.string()),
                pa.field("weight", pa.float64()),
            ]
        )
        _tables["rel"] = (
            db.create_table(RELATIONS_TABLE, schema=schema)
            if RELATIONS_TABLE not in db.table_names()
            else db.open_table(RELATIONS_TABLE)
        )
    return _tables["rel"]


def _safe(name: str) -> str:
    if not name or not _NAME_RE.match(str(name)):
        raise ValueError(f"invalid entity name: {name!r}")
    return str(name)


async def _embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(EMBEDDING_URL, json={"input": text})
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]


async def _extract(text: str) -> dict:
    """Extract entities + relations from text via the local model. Returns
    ``{"entities":[[name,type],...], "relations":[[src,rel,dst],...]}``. Failures
    are non-fatal — the memory still stores; extraction quality is worked live."""
    prompt = (
        "Extract entities and relations as strict JSON with keys 'entities' "
        "(list of [name, type]) and 'relations' (list of [src, relation, dst]). "
        "Only output JSON.\n\nTEXT:\n" + text[:2000]
    )
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                OLLAMA_CHAT,
                json={
                    "model": EXTRACT_MODEL,
                    "stream": False,
                    "think": False,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            r.raise_for_status()
            content = r.json()["message"]["content"]
        m = re.search(r"\{.*\}", content, re.S)
        data = json.loads(m.group(0)) if m else {}
        return {
            "entities": [_norm_entity(e) for e in data.get("entities", []) or []],
            "relations": [_norm_relation(r) for r in data.get("relations", []) or []],
        }
    except Exception:  # extraction is best-effort; the write still succeeds
        return {"entities": [], "relations": []}


def _norm_entity(item) -> tuple[str, str]:
    """Normalise one extracted entity to (name, type). Local models emit either
    ``["Foo", "asset"]`` or ``{"name": "Foo", "type": "asset"}`` (key names vary)."""
    if isinstance(item, dict):
        name = (
            item.get("name")
            or item.get("entity")
            or item.get("id")
            or next(iter(item.values()), "")
        )
        etype = item.get("type") or item.get("etype") or item.get("category") or "concept"
        return str(name), str(etype)
    if isinstance(item, (list, tuple)):
        return (str(item[0]) if item else ""), (str(item[1]) if len(item) > 1 else "concept")
    return str(item), "concept"


def _norm_relation(item) -> tuple[str, str, str]:
    """Normalise one extracted relation to (src, rel_type, dst). Models emit
    ``["A", "rel", "B"]`` or ``{"src": "A", "relation": "rel", "dst": "B"}``
    (key names vary: source/subject/from, relation/predicate/type, target/object/to)."""
    if isinstance(item, dict):
        src = item.get("src") or item.get("source") or item.get("subject") or item.get("from") or ""
        rel = (
            item.get("relation")
            or item.get("rel")
            or item.get("predicate")
            or item.get("type")
            or item.get("rel_type")
            or "related_to"
        )
        dst = item.get("dst") or item.get("target") or item.get("object") or item.get("to") or ""
        return str(src), str(rel), str(dst)
    if isinstance(item, (list, tuple)) and len(item) >= 3:
        return str(item[0]), str(item[1]), str(item[2])
    return "", "", ""


async def _upsert_entity(name: str, etype: str = "concept") -> None:
    name = _safe(name)
    tbl = _entities()
    now = time.time()
    existing = (
        tbl.search().where(f"user_id = '{DEFAULT_USER}' AND name = '{name}'").limit(1).to_list()
    )
    if existing:
        e = existing[0]
        tbl.delete(f"id = '{e['id']}'")
        e["last_seen"] = now
        e["mention_count"] = int(e.get("mention_count", 0)) + 1
        e.pop("_distance", None)
        tbl.add([e])
        return
    vec = await _embed(f"{name} ({etype})")
    tbl.add(
        [
            {
                "id": str(uuid.uuid4()),
                "user_id": DEFAULT_USER,
                "name": name,
                "etype": etype,
                "vector": vec,
                "first_seen": now,
                "last_seen": now,
                "mention_count": 1,
            }
        ]
    )


async def _ingest_graph(text: str, source_memory_id: str) -> None:
    ex = await _extract(text)
    for name, etype in ex["entities"]:
        try:
            await _upsert_entity(name, etype)
        except Exception:  # noqa: BLE001 — one bad entity must not abort ingestion
            continue
    now = time.time()
    rows = []
    for src_raw, rel_raw, dst_raw in ex["relations"]:
        try:
            src, rel_type, dst = _safe(src_raw), str(rel_raw), _safe(dst_raw)
        except ValueError:
            continue
        await _upsert_entity(src)
        await _upsert_entity(dst)
        rows.append(
            {
                "id": str(uuid.uuid4()),
                "user_id": DEFAULT_USER,
                "src": src,
                "dst": dst,
                "rel_type": rel_type,
                "observed_at": now,
                "source_memory_id": source_memory_id,
                "weight": 1.0,
            }
        )
    if rows:
        _relations().add(rows)


def _rels_for(names: set[str]) -> list[dict]:
    tbl = _relations()
    out = {}
    for name in names:
        try:
            n = _safe(name)
        except ValueError:
            continue
        for r in (
            tbl.search()
            .where(f"user_id = '{DEFAULT_USER}' AND (src = '{n}' OR dst = '{n}')")
            .limit(100)
            .to_list()
        ):
            out[r["id"]] = r
    return list(out.values())


# ── Endpoint handlers (replace the flat-vector versions) ─────────────────────
async def _remember(request):
    args = (await request.json()).get("arguments", {})
    text = (args.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=400)
    if len(text) > 4000:
        return JSONResponse({"error": "text too long (max 4000 chars)"}, status_code=400)
    try:
        vec = await _embed(text)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"embedding failed: {e}"}, status_code=503)
    now = time.time()
    mid = str(uuid.uuid4())
    category = args.get("category", "fact")
    _memory_table().add(
        [
            {
                "id": mid,
                "user_id": DEFAULT_USER,
                "text": text,
                "category": category,
                "tags": args.get("tags", []),
                "vector": vec,
                "created_at": now,
                "last_accessed_at": now,
                "access_count": 0,
            }
        ]
    )
    await _ingest_graph(text, mid)  # populate the graph on write
    return JSONResponse({"id": mid, "stored": True, "category": category, "graph_updated": True})


async def _recall(request):
    """Graph-aware recall: vector-seed memories + entities, expand relations,
    return memories with connected context. Replaces flat top-K."""
    args = (await request.json()).get("arguments", {})
    query = args.get("query", "")
    if not query:
        return JSONResponse({"error": "query is required"}, status_code=400)
    top_k = min(max(int(args.get("top_k", 5)), 1), 20)
    category = args.get("category")
    tags = args.get("tags", [])
    hops = min(int(args.get("hops", 2)), 3)
    try:
        qvec = await _embed(query)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"embedding failed: {e}"}, status_code=503)
    mtbl = _memory_table()
    where = f"user_id = '{DEFAULT_USER}'" + (f" AND category = '{category}'" if category else "")
    seed_mem = mtbl.search(qvec).where(where).limit(min(top_k * 3, 60)).to_list()
    if tags:
        ts = set(tags)
        seed_mem = [r for r in seed_mem if ts & set(r.get("tags", []))]
    now = time.time()
    for r in seed_mem:
        recency = max(0, 1 - (now - r.get("last_accessed_at", 0)) / (90 * 86400))
        r["_score"] = r.get("_distance", 1.0) - 0.05 * recency
    seed_mem = sorted(seed_mem, key=lambda r: r["_score"])[:top_k]
    memories = [
        {
            "id": r["id"],
            "text": r["text"],
            "category": r["category"],
            "tags": r["tags"],
            "similarity": round(1 - r.get("_distance", 1.0), 3),
            "created_at": r["created_at"],
        }
        for r in seed_mem
    ]
    # graph expansion from entities near the query
    try:
        seed_ent = _entities().search(qvec).where(f"user_id = '{DEFAULT_USER}'").limit(3).to_list()
    except Exception:  # noqa: BLE001
        seed_ent = []
    frontier = {e["name"] for e in seed_ent}
    nodes, edges = set(frontier), []
    for _ in range(hops):
        rels = _rels_for(frontier)
        new = set()
        for r in rels:
            edges.append({"src": r["src"], "dst": r["dst"], "rel_type": r["rel_type"]})
            for side in (r["src"], r["dst"]):
                if side not in nodes and len(nodes) < _MAX_NODES:
                    new.add(side)
                    nodes.add(side)
        if not new:
            break
        frontier = new
    uniq = list({(e["src"], e["dst"], e["rel_type"]): e for e in edges}.values())
    return JSONResponse(
        {
            "query": query,
            "num_results": len(memories),
            "memories": memories,
            "graph_context": {"nodes": sorted(nodes), "edges": uniq},
        }
    )


async def _forget(request):
    args = (await request.json()).get("arguments", {})
    mid = args.get("id", "")
    if not mid:
        return JSONResponse({"error": "id is required"}, status_code=400)
    try:
        _memory_table().delete(f"id = '{mid}'")
        _relations().delete(f"source_memory_id = '{mid}'")
        return JSONResponse({"id": mid, "deleted": True})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)


async def _list_memories(request):
    args = (await request.json()).get("arguments", {})
    category = args.get("category")
    tags = args.get("tags", [])
    limit = min(int(args.get("limit", 50)), 500)
    where = f"user_id = '{DEFAULT_USER}'" + (f" AND category = '{category}'" if category else "")
    rows = _memory_table().search().where(where).limit(limit).to_list()
    if tags:
        ts = set(tags)
        rows = [r for r in rows if ts & set(r.get("tags", []))]
    return JSONResponse(
        {
            "total": len(rows),
            "memories": [
                {
                    "id": r["id"],
                    "text": r["text"][:200],
                    "category": r["category"],
                    "tags": r["tags"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ],
        }
    )


async def _clear_memories(request):
    args = (await request.json()).get("arguments", {})
    if args.get("confirm_token") != "YES_DELETE_ALL":
        return JSONResponse({"error": "confirm_token must be 'YES_DELETE_ALL'"}, status_code=400)
    for t in (_memory_table(), _entities(), _relations()):
        t.delete(f"user_id = '{DEFAULT_USER}'")
    return JSONResponse({"deleted": "all", "user_id": DEFAULT_USER})


# ── New graph tools ──────────────────────────────────────────────────────────
async def _link(request):
    args = (await request.json()).get("arguments", {})
    try:
        src, dst = _safe(args["src"]), _safe(args["dst"])
        await _upsert_entity(src)
        await _upsert_entity(dst)
        rid = str(uuid.uuid4())
        _relations().add(
            [
                {
                    "id": rid,
                    "user_id": DEFAULT_USER,
                    "src": src,
                    "dst": dst,
                    "rel_type": args.get("rel_type", "related_to"),
                    "observed_at": time.time(),
                    "source_memory_id": args.get("source_memory_id", ""),
                    "weight": float(args.get("weight", 1.0)),
                }
            ]
        )
        return JSONResponse({"id": rid, "linked": True})
    except KeyError as e:
        return JSONResponse({"error": f"missing arg: {e}"}, status_code=400)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=400)


async def _neighbors(request):
    args = (await request.json()).get("arguments", {})
    try:
        start = _safe(args["name"])
        hops = min(int(args.get("hops", 1)), 3)
        frontier, nodes, edges = {start}, {start}, []
        for _ in range(hops):
            new = set()
            for r in _rels_for(frontier):
                edges.append({"src": r["src"], "dst": r["dst"], "rel_type": r["rel_type"]})
                for side in (r["src"], r["dst"]):
                    if side not in nodes and len(nodes) < _MAX_NODES:
                        new.add(side)
                        nodes.add(side)
            if not new:
                break
            frontier = new
        uniq = list({(e["src"], e["dst"], e["rel_type"]): e for e in edges}.values())
        return JSONResponse(
            {"start": start, "node_count": len(nodes), "nodes": sorted(nodes), "edges": uniq}
        )
    except KeyError as e:
        return JSONResponse({"error": f"missing arg: {e}"}, status_code=400)


async def _entity_timeline(request):
    args = (await request.json()).get("arguments", {})
    try:
        name = _safe(args["name"])
        rels = (
            _relations()
            .search()
            .where(f"user_id = '{DEFAULT_USER}' AND (src = '{name}' OR dst = '{name}')")
            .limit(500)
            .to_list()
        )
        rels.sort(key=lambda r: r.get("observed_at", 0))
        return JSONResponse(
            {
                "entity": name,
                "event_count": len(rels),
                "timeline": [
                    {
                        "observed_at": r["observed_at"],
                        "src": r["src"],
                        "dst": r["dst"],
                        "rel_type": r["rel_type"],
                        "source_memory_id": r.get("source_memory_id", ""),
                    }
                    for r in rels
                ],
            }
        )
    except KeyError as e:
        return JSONResponse({"error": f"missing arg: {e}"}, status_code=400)


async def migrate_existing() -> dict:
    """One-way, in-task migration: process every existing memory into the graph."""
    rows = _memory_table().search().where(f"user_id = '{DEFAULT_USER}'").limit(100000).to_list()
    done = 0
    for r in rows:
        await _ingest_graph(r["text"], r["id"])
        done += 1
    return {"migrated": done}


def register_memory_routes(mcp) -> None:
    """Register ALL memory endpoints (replacements + graph tools) on the server."""
    mcp.custom_route("/tools/remember", methods=["POST"])(_remember)
    mcp.custom_route("/tools/recall", methods=["POST"])(_recall)
    mcp.custom_route("/tools/forget", methods=["POST"])(_forget)
    mcp.custom_route("/tools/list_memories", methods=["POST"])(_list_memories)
    mcp.custom_route("/tools/clear_memories", methods=["POST"])(_clear_memories)
    mcp.custom_route("/tools/link", methods=["POST"])(_link)
    mcp.custom_route("/tools/neighbors", methods=["POST"])(_neighbors)
    mcp.custom_route("/tools/entity_timeline", methods=["POST"])(_entity_timeline)
    mcp.custom_route("/tools/graph_recall", methods=["POST"])(_recall)  # recall is graph-aware
