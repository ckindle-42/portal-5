#!/usr/bin/env python3
"""Measure the keyword-layer (deterministic) router against the corpus.

Run once against a checkout of 45edb25 (pre-collapse) and once against the
current tree, from their respective repo roots, each writing its own JSON
output. See BUILD_PROGRAM_ROUTING_INTEGRITY_V1.md Phases R0/R1.

Usage (run from repo root of the checkout being measured):
    python3 tests/routing/measure.py --out /tmp/routing-precollapse-baseline.json
    python3 tests/routing/measure.py --out /tmp/routing-current.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _load_corpus() -> list[dict]:
    # Always read the corpus from the CURRENT tree's copy (it's a shared,
    # versioned artifact — see tests/routing/build_corpus.py) even when this
    # script itself is executed from a pre-collapse worktree checkout.
    corpus_path = Path("tests/routing/corpus.json")
    if not corpus_path.exists():
        raise FileNotFoundError(
            "tests/routing/corpus.json not found — pass --corpus explicitly "
            "when measuring from a worktree that predates this file."
        )
    return json.loads(corpus_path.read_text())


def _resolve_model(workspace_id: str, variant: str | None) -> str | None:
    """Resolve served model_hint for (base, variant) from config/portal.yaml."""
    import yaml

    portal_yaml = Path("config/portal.yaml")
    d = yaml.safe_load(portal_yaml.read_text())
    ws = d.get("workspaces", {})
    entry = ws.get(workspace_id)
    if entry is None:
        return None
    if variant:
        return entry.get("variants", {}).get(variant, {}).get("model_hint")
    return entry.get("model_hint")


def _resolve_alias(raw: str) -> tuple[str, str | None]:
    """Resolve a raw keyword-scorer/LLM output into (base, variant).

    Handles the canonical "<base>::<variant>" synthetic form. When run
    against a pre-collapse worktree (no ``_unpack_synthetic_workspace`` /
    legacy alias shim import target exists there at all) or post-alias-
    closeout current tree, falls back to returning the id unchanged as a
    bare base.
    """
    if "::" in raw:
        base, variant = raw.split("::", 1)
        return base, variant
    try:
        from portal.platform.inference.router.preinject import (
            _unpack_synthetic_workspace,
        )

        return _unpack_synthetic_workspace(raw)
    except ImportError:
        return raw, None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--corpus", default=None)
    args = parser.parse_args()

    corpus = json.loads(Path(args.corpus).read_text()) if args.corpus else _load_corpus()

    from portal.platform.inference.router.routing import _detect_workspace

    results = {}
    for item in corpus:
        raw = _detect_workspace([{"role": "user", "content": item["message"]}])
        if raw is None:
            results[item["id"]] = {
                "raw": None,
                "base": None,
                "variant": None,
                "served_model": None,
            }
            continue
        base, variant = _resolve_alias(raw)
        served = _resolve_model(base, variant)
        results[item["id"]] = {
            "raw": raw,
            "base": base,
            "variant": variant,
            "served_model": served,
        }

    Path(args.out).write_text(json.dumps(results, indent=2, sort_keys=True))
    print(f"Wrote {len(results)} results to {args.out}")


if __name__ == "__main__":
    main()
