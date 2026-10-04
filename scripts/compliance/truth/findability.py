"""DATA_TRUTH D1c — key-independent findability.

The gate that cannot be fitted to the answer key (task L5): a unit is
findable when a query built from the unit's OWN text returns the unit.

* ``requirements`` — every in-force requirement Part of the governing
  standards, queried by its own requirement sentence (the normative field of
  its applicability-first table row), must appear in the top 3 of its corpus.
* ``operator`` — every indexed operator section that carries a heading,
  queried by that heading, must appear in the top 5 of the operator corpus.

Queries are embedded in checkpointed batches with a persistent cache (task
L3: the VL embed server wedges under sustained load, so progress survives a
restart and nothing re-embeds a seen text). Never key question text, never
key section ids — the population comes from the store.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
CACHE_PATH = (
    REPO_ROOT
    / "portal"
    / "modules"
    / "compliance"
    / "data"
    / "private"
    / "reading_truth"
    / "dt"
    / "findability_embed_cache.json"
)
EMBED_BATCH = 12
#: the six standards the acceptance set draws from, as in-force in the store.
GOVERNING_STANDARDS = (
    "NERC/CIP-002-5.1a",
    "NERC/CIP-003-9",
    "NERC/CIP-004-7",
    "NERC/CIP-007-6",
    "NERC/CIP-010-4",
    "NERC/CIP-013-2",
)
NERC_KB = "nerc_corpus"
OPERATOR_KB = "operator_corpus"


# ── population ───────────────────────────────────────────────────────────────


PART_TITLE_RE = re.compile(r"^\d+(\.\d+)*\.?$")
PART_TOKEN_RE = re.compile(r"^(R\d+(?:\.\d+)*|\d+(?:\.\d+)*)\.?\s+")


def requirement_parts(repo: Any, standards: tuple[str, ...] | None) -> list[dict[str, Any]]:
    """Indexed requirement Part rows of the given standards, with queries.

    A Part is an R&M section that is titled by its part number (the
    applicability-first table rows: ``"5.3 | <applicability> | <requirement>
    | <measures>"``) or whose text opens with a part token (``R1. …``,
    ``1.2.6. …`` — the list-item Parts). Excluded on purpose: the section
    header rows, whole-Table units, Measures rows (``M1. …``) and applicability
    sub-lists (roman numerals) — none of them is a requirement Part. The
    query is the Part's own normative sentence, so the definition survives the
    D2 re-cut: it reads titles and text, never ids.
    """
    placeholders = ",".join("?" * len(standards or ()))
    clause = f"and r.logical_id in ({placeholders})" if standards else ""  # noqa: S608
    rows = repo._conn.execute(
        f"""select s.section_id, s.revision_id, s.char_start, s.char_end, s.title,
                   s.unit_kind, r.logical_id
            from source_sections s
            join document_revisions r on r.revision_id = s.revision_id
            where s.role = 'B_REQUIREMENTS_AND_MEASURES' {clause}""",  # noqa: S608
        tuple(standards or ()),
    ).fetchall()
    cache: dict[str, str] = {}
    out: list[dict[str, Any]] = []
    for row in rows:
        title = str(row["title"] or "").strip()
        revision_id = str(row["revision_id"])
        if revision_id not in cache:
            cache[revision_id] = repo.get_document_text(revision_id) or ""
        full = cache[revision_id]
        start, end = int(row["char_start"] or 0), int(row["char_end"] or 0)
        text = full[start:end] if full and 0 <= start < end <= len(full) else ""
        query = ""
        if PART_TITLE_RE.match(title):
            fields = [f.strip() for f in text.split(" | ")]
            query = fields[2] if len(fields) >= 3 else ""
            if not query and len(fields) >= 2:
                query = fields[1]
        if not query:
            match = PART_TOKEN_RE.match(text.strip())
            if match and not re.match(r"^M\d", text.strip()):
                query = text.strip()[match.end() :].strip()
        if query:
            out.append(
                {
                    "section_id": str(row["section_id"]),
                    "logical_id": str(row["logical_id"]),
                    "query": query,
                    "text": text,
                }
            )
    return out


def operator_headings(repo: Any, indexed_parents: set[str] | None = None) -> list[dict[str, Any]]:
    """Every indexed operator section with a heading, queried by that heading.

    DATA_TRUTH D3, measured: 85% of the misses under bare-title queries are
    sections whose title is SHARED across documents ("Purpose",
    "Introduction", the approval-matrix names) — no retrieval path can pick
    one of a dozen same-title sections from the title alone, so for those the
    query carries the section's own distinguishing context, the document
    title, exactly what the D3 embed prefix gives the unit. Unique titles are
    queried bare. The query records which shape it used.
    """
    rows = repo._conn.execute(
        """select s.section_id, s.title, s.heading_path, d.title as document_title
           from source_sections s
           join document_revisions r on r.revision_id = s.revision_id
           join source_documents d on d.logical_id = r.logical_id
           where d.jurisdiction = 'internal' and coalesce(s.title, '') <> ''"""
    ).fetchall()
    counts: dict[str, int] = {}
    kept = []
    for row in rows:
        # the section's heading is the line the document shows: the number and
        # the words ("3.1.3 Shared Accounts"), not the bare words — the words
        # alone ("Purpose", "Introduction") name dozens of sections across the
        # corpus and no retrieval path can pick one from them.
        heading = str(row["heading_path"]).strip() or str(row["title"]).strip()
        section_id = str(row["section_id"])
        if heading and (indexed_parents is None or section_id in indexed_parents):
            counts[heading] = counts.get(heading, 0) + 1
            kept.append((section_id, heading, str(row["document_title"] or "").strip()))
    out = []
    for section_id, heading, document_title in kept:
        if counts[heading] > 1 and document_title:
            query = f"{document_title} — {heading}"
            shape = "heading+document"
        else:
            query = heading
            shape = "heading"
        out.append(
            {
                "section_id": section_id,
                "logical_id": "",
                "query": query,
                "query_shape": shape,
                "text": "",
            }
        )
    return out


# ── ranking ──────────────────────────────────────────────────────────────────


def _load_cache() -> dict[str, list[float]]:
    if CACHE_PATH.is_file():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict[str, list[float]]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")


def _embed_queries(queries: list[str]) -> dict[str, list[float]]:
    """Query embeddings with a persistent checkpoint cache (L3)."""
    cache = _load_cache()
    keys = {query: hashlib.sha1(query.encode()).hexdigest() for query in queries}
    vectors: dict[str, list[float]] = {
        query: cache[key] for query, key in keys.items() if key in cache
    }
    pending = [q for q in queries if q not in vectors]
    for start in range(0, len(pending), EMBED_BATCH):
        batch = pending[start : start + EMBED_BATCH]
        for query, raw_vector in zip(batch, _run_embeds(batch), strict=True):
            vector = _normalise(raw_vector)
            vectors[query] = vector
            cache[keys[query]] = vector
        _save_cache(cache)
    return vectors


async def _embed_one(text: str) -> list[float]:
    from portal.platform.retrieval import embedding

    return await embedding.vl_embed(text=text, is_query=True)


def _run_embeds(batch: list[str]) -> list[list[float]]:
    import asyncio

    async def _all() -> list[list[float]]:
        return [await _embed_one(q) for q in batch]

    return asyncio.run(_all())


def _normalise(vector: list[float]) -> list[float]:
    import math

    magnitude = math.sqrt(sum(component * component for component in vector)) or 1.0
    return [component / magnitude for component in vector]


def _corpus_rows(kb_id: str) -> tuple[list[str], Any]:
    """chunk ids and the (unnormalised) vector matrix of one corpus."""
    import lancedb
    import numpy as np

    from portal.platform.retrieval import store as lance_store

    full_name = f"compliance_{kb_id}"
    if not (Path(lance_store.RAG_DIR) / f"{full_name}.lance").exists():
        raise SystemExit(f"unknown kb {kb_id!r}: no lance table {full_name}")
    db = lancedb.connect(str(lance_store.RAG_DIR))
    rows = db.open_table(full_name).to_arrow().select(["chunk_id", "vector"]).to_pylist()
    chunk_ids = [str(row["chunk_id"]) for row in rows]
    matrix = np.array([row["vector"] for row in rows], dtype=np.float32)
    return chunk_ids, matrix


def rank_section(
    chunk_ids: list[str], matrix: Any, parent: str, query_vector: list[float]
) -> int | None:
    """1-based best rank of a section's chunks under cosine similarity."""
    import numpy as np

    query = np.array(query_vector, dtype=np.float32)
    sims = matrix @ query
    order = np.argsort(-sims)
    parents = [chunk_id.split("#")[0] for chunk_id in chunk_ids]
    for position, index in enumerate(order, start=1):
        if parents[index] == parent:
            return position
    return None


def measure(
    population: list[dict[str, Any]],
    kb_id: str,
    *,
    top: int,
    sample: int | None,
    seed: int,
    quiet: bool = False,
) -> dict[str, Any]:
    import random

    population = [item for item in population if item["query"]]
    skipped = len(population)
    if sample and sample < len(population):
        random.Random(seed).shuffle(population)
        population = population[:sample]
    chunk_ids, matrix = _corpus_rows(kb_id)
    matrix = _normalise_rows(matrix)
    vectors = _embed_queries([item["query"] for item in population])
    rows = []
    for item in population:
        rank = rank_section(chunk_ids, matrix, item["section_id"], vectors[item["query"]])
        rows.append(
            {
                "section_id": item["section_id"],
                "logical_id": item["logical_id"],
                "rank": rank,
                "pass": rank is not None and rank <= top,
            }
        )
    passed = sum(1 for row in rows if row["pass"])
    total = len(rows)
    if not quiet:
        for row in rows:
            if not row["pass"]:
                print(f"  MISS {row['logical_id']} {row['section_id'][:30]} rank={row['rank']}")
    return {
        "kb": kb_id,
        "top": top,
        "population": skipped,
        "measured": total,
        "passed": passed,
        "rate": round(passed / total, 4) if total else None,
        "rows": rows,
    }


def _normalise_rows(matrix: Any) -> Any:
    import numpy as np

    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    req = sub.add_parser("requirements", help="Part found by its own requirement sentence (top 3)")
    req.add_argument(
        "--all-standards",
        action="store_true",
        help="every standard revision, not the governing six",
    )
    req.add_argument("--sample", type=int, default=None)
    req.add_argument("--seed", type=int, default=20261004)
    req.add_argument("--out", type=Path, default=None)
    req.add_argument("--quiet", action="store_true")
    op = sub.add_parser("operator", help="operator section found by its heading (top 5)")
    op.add_argument("--sample", type=int, default=None)
    op.add_argument("--seed", type=int, default=20261004)
    op.add_argument("--out", type=Path, default=None)
    op.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    from portal.modules.compliance.core.repository import Repository

    repo = Repository()
    try:
        if args.command == "requirements":
            standards = None if args.all_standards else GOVERNING_STANDARDS
            population = requirement_parts(repo, standards)
            result = measure(
                population, NERC_KB, top=3, sample=args.sample, seed=args.seed, quiet=args.quiet
            )
        else:
            chunk_ids, _matrix = _corpus_rows(OPERATOR_KB)
            parents = {chunk.split("#")[0] for chunk in chunk_ids}
            population = operator_headings(repo, indexed_parents=parents)
            result = measure(
                population, OPERATOR_KB, top=5, sample=args.sample, seed=args.seed, quiet=args.quiet
            )
    finally:
        repo.close()
    summary = {k: v for k, v in result.items() if k != "rows"}
    print(json.dumps(summary, indent=1))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
