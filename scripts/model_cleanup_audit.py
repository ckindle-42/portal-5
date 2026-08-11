#!/usr/bin/env python3
"""Dry-run disk-reclaim audit for the Ollama model store.

Errs heavily toward KEEP. A model is a candidate only if its base tag
(``-ctxNk`` suffix stripped, case-folded) appears nowhere in: workspace
``model_hint``/``variants[*].model_hint`` in config/portal.yaml, a broad
grep of config/portal/tests source, or a documented exclusion in either
prior config/UNUSED_MODELS_*.md audit. Candidates are further split by
whether their bench workspace (if any) has real eval evidence — checked
by BOTH the raw model tag and the workspace slug, since result files are
often keyed by workspace name, not model tag.

    python3 scripts/model_cleanup_audit.py

Never calls `ollama rm`. Report-only; a human decides what to delete.
"""

from __future__ import annotations

import glob
import json
import re
import urllib.request
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
OLLAMA_URL = "http://localhost:11434"

CODE_SEARCH_GLOBS = ["config/*.yaml", "config/personas/*.yaml", "portal/**/*.py", "tests/**/*.py"]
RESULT_SEARCH_GLOBS = [
    "tests/benchmarks/results/**/*",
    "results/**/*",
    "tests/results/**/*",
    "portal/modules/security/core/results/candidates/**/*",
    "portal/modules/security/core/results/checkpoints/**/*",
    "portal/modules/security/core/results/antares_probe/**/*",
    "reports/**/*",
]
PRIOR_AUDIT_DOCS = ["config/UNUSED_MODELS_20260721.md", "config/UNUSED_MODELS_20260810.md"]


def base(tag: str) -> str:
    return re.sub(r"-ctx\d+k$", "", tag, flags=re.I).lower()


def fetch_on_disk() -> list[dict]:
    with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=10) as r:
        return json.load(r).get("models", [])


def read_globs(patterns: list[str]) -> str:
    corpus = []
    for pattern in patterns:
        for path in glob.glob(str(REPO_ROOT / pattern), recursive=True):
            if Path(path).is_file():
                try:
                    corpus.append(Path(path).read_text(encoding="utf-8", errors="ignore"))
                except OSError:
                    continue
    return "\n".join(corpus).lower()


def production_bases() -> set[str]:
    """Every model a live production workspace can route to: top-level model_hint
    plus every variant's model_hint. The Layer-1 router model is production infra
    too but isn't a workspace, so it's added explicitly."""
    d = yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text())
    bases = set()
    for k, v in d.get("workspaces", {}).items():
        if k.startswith("bench-"):
            continue
        if v.get("model_hint"):
            bases.add(base(v["model_hint"]))
        for variant in (v.get("variants") or {}).values():
            if isinstance(variant, dict) and variant.get("model_hint"):
                bases.add(base(variant["model_hint"]))
    bases.add(base("hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M"))
    return bases


def bench_workspaces_by_base() -> dict[str, list[str]]:
    d = yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text())
    out: dict[str, list[str]] = {}
    for k, v in d.get("workspaces", {}).items():
        if k.startswith("bench-") and v.get("model_hint"):
            out.setdefault(base(v["model_hint"]), []).append(k)
    return out


def documented_keep_tags() -> set[str]:
    """Tags mentioned anywhere in either prior UNUSED_MODELS audit doc — a tag that
    appears there has already been individually adjudicated, one way or another."""
    tags = set()
    for doc in PRIOR_AUDIT_DOCS:
        p = REPO_ROOT / doc
        if p.exists():
            tags.add(p.read_text(encoding="utf-8", errors="ignore").lower())
    return tags


def catalog_verdict(tag: str) -> str | None:
    """DROPPED or PROMOTED if the model's OWN catalog unit title says so (matching
    by title, not body, avoids false hits from another unit's cross-reference)."""
    for path in glob.glob(str(REPO_ROOT / "portal_wiki/canonical/unit-model-catalog-*.md")):
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'title: "(.*?)"', text, re.S)
        title = (m.group(1) if m else "").replace("\\u2014", "—").replace("\\", "")
        if tag not in title:
            continue
        if re.search(r"dropped|not.?adopted", title, re.I):
            return "DROPPED"
        if re.search(r"promoted", title, re.I):
            return "PROMOTED"
    return None


def classify(
    m: dict,
    *,
    prod_bases: set,
    bench_by_base: dict,
    code_corpus: str,
    result_corpus: str,
    prior_docs: set,
) -> str:
    tag = m["name"]
    b = base(tag)

    if b in prod_bases:
        return "PRODUCTION"
    if any(tag.lower() in doc for doc in prior_docs):
        return "DOCUMENTED_KEEP"

    tag_l = tag.lower()
    code_referenced = tag_l in code_corpus or (
        tag_l.endswith(":latest") and tag_l.rsplit(":", 1)[0] in code_corpus
    )

    verdict = catalog_verdict(tag)
    if verdict == "DROPPED":
        return "DROPPED_VERDICT"
    if verdict == "PROMOTED":
        return "PROMOTED_NOT_WIRED"

    bench_ws = bench_by_base.get(b, [])
    has_evidence = tag_l in result_corpus or any(ws.lower() in result_corpus for ws in bench_ws)

    if not bench_ws and not code_referenced:
        return "NO_WORKSPACE_ORPHAN"
    if has_evidence:
        return "EVALUATED_PENDING"
    return "NEVER_EVALUATED"


def gb(nbytes: int) -> float:
    return nbytes / (1024**3)


def render_report(categorized: dict[str, list[dict]]) -> str:
    lines = ["# Model cleanup audit (dry-run — nothing deleted)", ""]
    order = [
        "PRODUCTION",
        "DOCUMENTED_KEEP",
        "PROMOTED_NOT_WIRED",
        "DROPPED_VERDICT",
        "NO_WORKSPACE_ORPHAN",
        "NEVER_EVALUATED",
        "EVALUATED_PENDING",
    ]
    for cat in order:
        items = categorized.get(cat, [])
        total = sum(gb(m["size"]) for m in items)
        lines.append(f"## {cat}: {len(items)} models, {total:.1f} GB")
        lines.append("")
        for m in sorted(items, key=lambda x: -x["size"]):
            lines.append(f"- {gb(m['size']):.1f} GB  `{m['name']}`")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    print("Fetching on-disk Ollama models...")
    on_disk = fetch_on_disk()
    print(f"  {len(on_disk)} models on disk")

    prod_bases = production_bases()
    bench_by_base = bench_workspaces_by_base()
    code_corpus = read_globs(CODE_SEARCH_GLOBS)
    result_corpus = read_globs(RESULT_SEARCH_GLOBS)
    prior_docs = documented_keep_tags()

    categorized: dict[str, list[dict]] = {}
    for m in on_disk:
        cat = classify(
            m,
            prod_bases=prod_bases,
            bench_by_base=bench_by_base,
            code_corpus=code_corpus,
            result_corpus=result_corpus,
            prior_docs=prior_docs,
        )
        categorized.setdefault(cat, []).append(m)

    for cat, items in categorized.items():
        print(f"  {cat}: {len(items)} models, {sum(gb(m['size']) for m in items):.1f} GB")

    out_path = REPO_ROOT / "reports" / "model_cleanup_audit.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_report(categorized))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
