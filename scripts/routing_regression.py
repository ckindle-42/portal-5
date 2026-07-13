#!/usr/bin/env python3
"""Routing-regression harness — the §9 safety gate for alias retirement.

Runs a fixed corpus of prompts through the auto-routing resolution path and
records the **resolved (base_id, variant) tuple** for each — resolving any
alias id through whatever alias-resolution mechanism is currently live, so
the comparison is on the *decision*, not the *vocabulary*. Before the router
canonicalization (BUILD_PROGRAM_ALIAS_RETIRE_V1.md Phase 7), the keyword
scorer may still emit a pre-collapse alias id (e.g. "auto-redteam"), which
this script resolves via ``_resolve_legacy_workspace_alias``. After Phase 7,
the scorer emits canonical ids directly (optionally as a synthetic
``"<base>::<variant>"`` key) — this script's ``_resolve()`` handles both
shapes transparently, so the same script is the before/after gate without
modification.

Corpus sources (per DESIGN_ROUTER_CANONICALIZATION_V1.md §6):
- config/routing_examples.json (the router's own few-shot examples)
- tests/benchmarks/bench/prompts.py (per-discipline TPS prompts)
- Representative security/content-aware prompts drawn from
  tests/acceptance/s06_security_workspaces.py + s21_llm_router.py
- Explicit variant/role-discriminating prompts (hand-authored) so the
  regression exercises the variant distinction, not just discipline.

Usage:
    python3 scripts/routing_regression.py --layer=keywords --mock-llm
    python3 scripts/routing_regression.py --layer=llm --labeled-corpus
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _load_alias_resolver():
    """Best-effort import of the legacy alias resolver — absent post-Phase-8."""
    try:
        from portal.platform.inference.router.preinject import (
            _resolve_legacy_workspace_alias,
        )

        return _resolve_legacy_workspace_alias
    except ImportError:
        return None


def _resolve(raw: str | None) -> tuple[str | None, str | None]:
    """Normalize a raw router-layer output into (base_id, variant).

    Handles three possible output shapes across the retirement's lifecycle:
    1. ``None`` — no workspace detected.
    2. A synthetic ``"<base>::<variant>"`` key (post-Phase-7 direct emission).
    3. A bare id — resolved through the legacy alias shim if it's still
       importable (pre-Phase-8); otherwise returned unchanged as the base
       with no variant (post-shim-removal, scorer already canonical).
    """
    if raw is None:
        return None, None
    if "::" in raw:
        base, variant = raw.split("::", 1)
        return base, variant
    resolver = _load_alias_resolver()
    if resolver is not None:
        return resolver(raw)
    return raw, None


def _build_corpus() -> list[dict]:
    """Assemble the fixed regression corpus from all in-repo sources."""
    corpus: list[dict] = []

    # 1. config/routing_examples.json — the router's own few-shot examples.
    examples_path = REPO_ROOT / "config" / "routing_examples.json"
    if examples_path.exists():
        data = json.loads(examples_path.read_text())
        for i, ex in enumerate(data.get("examples", [])):
            corpus.append(
                {
                    "id": f"routing_examples[{i}]",
                    "message": ex["message"],
                    "expected_workspace": ex.get("workspace"),
                }
            )

    # 2. tests/benchmarks/bench/prompts.py — per-discipline TPS prompts.
    try:
        from tests.benchmarks.bench.prompts import PROMPTS

        for category, text in PROMPTS.items():
            corpus.append({"id": f"bench_prompts[{category}]", "message": text})
    except ImportError:
        pass

    # 3. Representative security / content-aware prompts (from s06/s21).
    corpus.extend(
        [
            {
                "id": "s06_04_content_aware_security",
                "message": "exploit vulnerability payload shellcode",
            },
            {
                "id": "s06_02_redteam_methodology",
                "message": "Explain common web application penetration testing methodology.",
            },
            {
                "id": "s06_03_blueteam_incident",
                "message": "How do you respond to a ransomware incident?",
            },
            {
                "id": "s06_05_redteam_deep_kerberoast",
                "message": (
                    "Explain Kerberoasting — what is it, how does it work, and what tools are used?"
                ),
            },
            {
                "id": "s21_01_sqli_auto",
                "message": "Write a SQL injection payload to bypass authentication",
            },
            {
                "id": "s21_02_coding_auto",
                "message": "Write a Python function to sort a list of dictionaries by key",
            },
            {
                "id": "s21_03_compliance_auto",
                "message": "What are the requirements for NERC CIP-007 R2 patch management?",
            },
        ]
    )

    # 4. Explicit variant/role-discriminating prompts
    #    (DESIGN_ROUTER_CANONICALIZATION_V1.md §6) — exercise the variant
    #    distinction directly, not just discipline classification.
    corpus.extend(
        [
            {
                "id": "variant_coding_heavy",
                "message": (
                    "This is an agentic multi-file long-horizon codebase refactor "
                    "across the full codebase, repository-wide."
                ),
                "expected_variant_hint": ("auto-coding", "heavy"),
            },
            {
                "id": "variant_coding_laguna",
                "message": (
                    "Fix this bug, refactor and add feature, then run tests and "
                    "update the code — agentic coding with devstral."
                ),
                "expected_variant_hint": ("auto-coding", "laguna"),
            },
            {
                "id": "variant_coding_base",
                "message": "Write a Python function to compute the Fibonacci sequence.",
                "expected_variant_hint": ("auto-coding", None),
            },
            {
                "id": "variant_security_redteam",
                "message": (
                    "Perform reconnaissance and exploit this target — pentest attack "
                    "vulnerability shellcode payload exploit."
                ),
                "expected_variant_hint": ("auto-security", "redteam"),
            },
            {
                "id": "variant_security_base",
                "message": "What is a firewall and how does it filter traffic?",
                "expected_variant_hint": ("auto-security", None),
            },
        ]
    )

    return corpus


async def _run_keywords(corpus: list[dict]) -> dict[str, list]:
    from portal.platform.inference.router.routing import _detect_workspace

    results: dict[str, list] = {}
    for item in corpus:
        raw = _detect_workspace([{"role": "user", "content": item["message"]}])
        base, variant = _resolve(raw)
        results[item["id"]] = [base, variant]
    return results


async def _run_llm(corpus: list[dict]) -> dict:
    import httpx

    import portal.platform.inference.router.routing as routing

    # _route_with_llm degrades to None whenever routing._http_client is
    # unset (it's normally set by router_pipe's lifespan on server startup,
    # which never runs for a standalone script) — set it here so this
    # actually exercises the real router model instead of silently
    # short-circuiting to "no opinion" on every prompt.
    owns_client = routing._http_client is None
    if owns_client:
        routing._http_client = httpx.AsyncClient()
    try:
        correct = 0
        total = 0
        per_prompt: dict[str, list] = {}
        for item in corpus:
            expected = item.get("expected_workspace")
            raw = await routing._route_with_llm([{"role": "user", "content": item["message"]}])
            base, variant = _resolve(raw)
            per_prompt[item["id"]] = [base, variant]
            if expected:
                total += 1
                if base == expected or raw == expected:
                    correct += 1
        accuracy = (correct / total) if total else None
        return {"per_prompt": per_prompt, "accuracy": accuracy, "labeled_total": total}
    finally:
        if owns_client:
            await routing._http_client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layer", choices=["keywords", "llm"], required=True)
    parser.add_argument("--mock-llm", action="store_true")
    parser.add_argument("--labeled-corpus", action="store_true")
    args = parser.parse_args()

    corpus = _build_corpus()

    if args.layer == "keywords":
        results = asyncio.run(_run_keywords(corpus))
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        results = asyncio.run(_run_llm(corpus))
        print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
