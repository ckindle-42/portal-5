"""Function extractor + corpus assembler for positional-recall bench.

Reads real Portal 5 source files, extracts top-level and method definitions
via Python's `ast` module, and assembles corpora of known token depth.
Samples functions stratified by position bucket (front/middle/tail) so the
lost-in-the-middle effect is measurable — the whole point of the bench (A4).
"""

from __future__ import annotations

import ast
import random
from pathlib import Path
from typing import Any


def extract_functions(path: str | Path) -> list[dict[str, Any]]:
    """Extract all function/method defs from a Python file.

    Returns list of dicts with name, start_line, body, char_offset.
    """
    source = Path(path).read_text()
    tree = ast.parse(source)

    funcs: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and hasattr(node.body[0], "lineno"):
                start_lineno = node.lineno
                end_lineno = node.body[-1].end_lineno or node.body[-1].lineno
                body_lines = source.splitlines()[start_lineno - 1 : end_lineno]
                body_text = "\n".join(body_lines)
            else:
                body_text = ast.get_source_segment(source, node) or ""

            funcs.append(
                {
                    "name": node.name,
                    "start_line": node.lineno,
                    "body": body_text,
                    "char_offset": _char_offset(source, node.lineno),
                }
            )

    return sorted(funcs, key=lambda f: f["char_offset"])


def _char_offset(source: str, lineno: int) -> int:
    """Compute the 0-indexed char offset of a given line number."""
    lines = source.splitlines(keepends=True)
    return sum(len(lines[i]) for i in range(min(lineno - 1, len(lines))))


def assemble_corpus(
    paths: list[str | Path],
    pad_ceilings: dict[int, int] | None = None,
    target_ctx: int | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Concatenate source files into a single corpus text.

    Args:
        paths: Source files to include.
        pad_ceilings: Not used in simple mode — pass target_ctx instead.
        target_ctx: If set, pad corpus by repeating with distinct headers to
            reach approximately target_ctx tokens (est ≈ bytes/4).

    Returns:
        (corpus_text, list_of_functions_with_corpus_relative_offsets)
    """
    chunks: list[str] = []
    all_funcs: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    offset = 0

    for path in paths:
        header = f"# === {path} ===\n"
        chunks.append(header)
        offset += len(header)

        text = Path(path).read_text()
        chunks.append(text)

        funcs = extract_functions(path)
        for f in funcs:
            if f["name"] not in seen_names:
                seen_names.add(f["name"])
                all_funcs.append(
                    {**f, "char_offset": f["char_offset"] + offset, "source_file": str(path)}
                )

        offset += len(text)

    corpus = "".join(chunks)

    if target_ctx and len(chunks) > 0:
        target_bytes = target_ctx * 4
        if len(corpus) < target_bytes:
            copies_needed = (target_bytes // max(len(corpus), 1)) + 1
            base_funcs = list(all_funcs)
            base_corpus = corpus
            for copy_idx in range(1, copies_needed):
                header = f"\n# === copy{copy_idx} ===\n"
                corpus += header
                corpus += base_corpus
                copy_offset = len(corpus) - len(base_corpus)
                for f in base_funcs:
                    all_funcs.append(
                        {
                            **f,
                            "char_offset": f["char_offset"] + copy_offset,
                            "source_file": f"copy{copy_idx}/{f['source_file']}",
                        }
                    )
        # Hard-truncate to target — padding can overshoot, and char-count != byte-count
        # for UTF-8 source files with unicode chars (docstrings, comments).
        # Truncate on bytes then re-decode so token estimate stays within target_ctx.
        if len(corpus.encode()) // 4 > target_ctx:
            encoded = corpus.encode()[:target_bytes]
            corpus = encoded.decode("utf-8", errors="ignore")
            all_funcs = [f for f in all_funcs if f["char_offset"] < len(corpus)]

    return corpus, all_funcs


def bucket(offset: int, total: int) -> str:
    """Classify a char offset into front/middle/tail by thirds."""
    third = total / 3
    if offset < third:
        return "front"
    elif offset < 2 * third:
        return "middle"
    return "tail"


def sample(
    functions: list[dict[str, Any]],
    k: int,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Stratified sample — ensure each bucket is represented."""
    rng = random.Random(seed)
    by_bucket: dict[str, list[dict[str, Any]]] = {"front": [], "middle": [], "tail": []}
    for f in functions:
        by_bucket[f.get("bucket", "front")].append(f)

    selected: list[dict[str, Any]] = []
    n_buckets = sum(1 for b in by_bucket.values() if b)
    per_bucket = max(1, k // n_buckets) if n_buckets else 0

    for bucket_name in ("front", "middle", "tail"):
        pool = by_bucket.get(bucket_name, [])
        if pool:
            selected.extend(rng.sample(pool, min(per_bucket, len(pool))))

    # Top up to k with random picks from remaining
    remaining = [f for f in functions if f not in selected and f.get("bucket")]
    while len(selected) < k and remaining:
        selected.append(remaining.pop(rng.randrange(len(remaining))))

    return selected[:k]
