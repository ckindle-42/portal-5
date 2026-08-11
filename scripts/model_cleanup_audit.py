#!/usr/bin/env python3
"""Dry-run disk-reclaim audit for the Ollama model store.

Errs heavily toward KEEP: a model is DELETE only if its exact tag string
appears nowhere in config/, config/personas/, portal/, or tests/. This
single broad-grep approach catches every known reference mechanism
(workspace model_hint, backends.yaml group membership, persona
preferred_models, router rosters, hardcoded test/bench literals) without
having to hand-enumerate each one — and never mutates or deletes anything.
For each DELETE candidate, pulls its portal_wiki/canonical model-catalog
unit (if any) so the report shows *why* the model is on disk, not just
that it's unreferenced.

    python3 scripts/model_cleanup_audit.py

Never calls `ollama rm`. This is report-only; a human decides what to do
with the DELETE list.
"""

from __future__ import annotations

import glob
import json
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OLLAMA_URL = "http://localhost:11434"

SEARCH_GLOBS = [
    "config/*.yaml",
    "config/personas/*.yaml",
    "portal/**/*.py",
    "tests/**/*.py",
]


def fetch_on_disk() -> list[dict]:
    with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=10) as r:
        data = json.load(r)
    return data.get("models", [])


def build_search_corpus() -> str:
    chunks = []
    for pattern in SEARCH_GLOBS:
        for path in glob.glob(str(REPO_ROOT / pattern), recursive=True):
            try:
                chunks.append(Path(path).read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
    return "\n".join(chunks).lower()


def referenced(tag: str, corpus_lower: str) -> bool:
    """Case-insensitive; also matches the bare repo id (Ollama defaults a tagless
    pull to :latest, so config referencing the bare id must still count as KEEP)."""
    tag_l = tag.lower()
    if tag_l in corpus_lower:
        return True
    base = tag_l.rsplit(":", 1)[0]
    return tag_l.endswith(":latest") and base in corpus_lower


def find_catalog_unit(tag: str) -> str | None:
    """Return the first non-frontmatter paragraph of the model's catalog unit, if any."""
    for path in glob.glob(str(REPO_ROOT / "portal_wiki/canonical/unit-model-catalog-*.md")):
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        if tag in text:
            body = text.split("---", 2)[-1].strip()
            para = body.split("\n\n")[0].replace("\n", " ")
            return para[:500]
    return None


def gb(nbytes: int) -> float:
    return nbytes / (1024**3)


def main() -> int:
    print("Fetching on-disk Ollama models...")
    on_disk = fetch_on_disk()
    print(f"  {len(on_disk)} models on disk")

    print("Building search corpus (config/, portal/, tests/)...")
    corpus = build_search_corpus()

    delete_candidates = []
    keep_count = 0
    for m in on_disk:
        if referenced(m["name"], corpus):
            keep_count += 1
            continue
        delete_candidates.append(m)

    delete_candidates.sort(key=lambda m: m.get("size", 0), reverse=True)
    total_delete_bytes = sum(m.get("size", 0) for m in delete_candidates)

    print(f"\nKEEP (referenced somewhere in config/portal/tests): {keep_count}")
    print(f"DELETE candidates (referenced nowhere found): {len(delete_candidates)}")
    print(f"Total disk if all DELETE candidates removed: {gb(total_delete_bytes):.1f} GB\n")

    lines = [
        "# Model cleanup audit (dry-run — nothing deleted)",
        "",
        f"On-disk: {len(on_disk)}  KEEP: {keep_count}  DELETE candidates: {len(delete_candidates)}"
        f"  Reclaimable: {gb(total_delete_bytes):.1f} GB",
        "",
        "Method: exact-substring match of each on-disk model tag against the full",
        "contents of config/*.yaml, config/personas/*.yaml, portal/**/*.py, and",
        "tests/**/*.py. A tag matched anywhere is KEEP. This is deliberately broad",
        "(errs toward KEEP) and catches workspace model_hint, backends.yaml group",
        "membership, persona preferred_models, router/council rosters, and",
        "hardcoded test literals in one pass.",
        "",
        "| Model | Size (GB) | Catalog history |",
        "|---|---:|---|",
    ]
    for m in delete_candidates:
        tag = m["name"]
        history = find_catalog_unit(tag) or "*(no model-catalog wiki unit found)*"
        lines.append(f"| `{tag}` | {gb(m.get('size', 0)):.1f} | {history} |")

    out_path = REPO_ROOT / "reports" / "model_cleanup_audit.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
