"""Per-(persona, model) cell execution and full-sweep orchestration.

run_cell runs every applicable scenario from a workspace fixture
against one (persona, model) pair, aggregating assertion outcomes.
run_sweep iterates the cell-grid for a workspace, loading and
evicting models one at a time per the memory-discipline contract.
"""
from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from ._common import (
    EVICT_BACKOFF_S,
    OLLAMA_URL,
    WORKSPACE_REGISTRY,
    _load_workspace_modules,
    cf,
)
from .loaders import (
    _ollama_size_estimate,
    chain_models_for_workspace,
    load_backends_yaml,
    load_personas_by_slugs,
    load_personas_for_workspace,
)
from .ollama_client import (
    _chat_direct,
    _ollama_unload,
)


async def run_cell(
    client: httpx.AsyncClient,
    persona: dict[str, Any],
    model: dict[str, Any],
    scenarios: list,
) -> dict[str, Any]:
    persona_slug = persona["slug"]
    system = persona.get("system_prompt", "")
    cell: dict[str, Any] = {
        "persona": persona_slug,
        "model": model["id"],
        "backend": model["backend_type"],
        "group": model["group"],
        "scenarios": [],
        "summary": {"PASS": 0, "WARN": 0, "FAIL": 0, "ERROR": 0},
    }

    applicable = [s for s in scenarios if s.persona_slug == persona_slug]
    if not applicable:
        return cell

    for scenario in applicable:
        t0 = time.time()
        code, response = await _chat_direct(
            client,
            backend_type=model["backend_type"],
            model_id=model["id"],
            system=system,
            user_prompt=scenario.prompt,
        )
        elapsed = time.time() - t0

        if code != 200:
            cell["scenarios"].append(
                {
                    "id": scenario.scenario_id,
                    "framework": scenario.framework_id,
                    "status": "ERROR",
                    "http_status": code,
                    "detail": f"HTTP {code}: {response[:120]}",
                    "response_preview": response[:800],
                    "elapsed_s": round(elapsed, 2),
                }
            )
            cell["summary"]["ERROR"] += 1
            continue

        outcome = cf.run_assertions(scenario, response)
        results_payload = [
            {
                "name": r.name,
                "passed": r.passed,
                "severity": r.severity,
                "detail": r.detail[:200],
            }
            for r in outcome.results
        ]
        cell["scenarios"].append(
            {
                "id": scenario.scenario_id,
                "framework": scenario.framework_id,
                "status": outcome.status,
                "http_status": 200,
                "results": results_payload,
                "response_chars": len(response),
                "response_preview": response[:800],
                "elapsed_s": round(elapsed, 2),
                "tps": round(len(response) / elapsed, 1) if elapsed > 0 else 0.0,
            }
        )
        cell["summary"][outcome.status] += 1
        await asyncio.sleep(0.2)

    return cell


# ── Sweep orchestrator ────────────────────────────────────────────────────


async def run_sweep(args) -> dict[str, Any]:
    cfg = load_backends_yaml()

    workspace_id = args.workspace
    ca_module, cf_module, persona_categories = _load_workspace_modules(workspace_id)

    # Driver-wide aliases so the rest of run_sweep doesn't change.
    global ca, cf
    ca = ca_module
    cf = cf_module

    # If the registry entry pins specific persona slugs (V2 capability survey),
    # bypass the category-based loader and load exactly those slugs in order.
    # Otherwise fall through to the production category-filtered loader.
    # See TASK_CODING_SHOOTOUT_V2.md §A2 / §A7.
    _ws_cfg = WORKSPACE_REGISTRY.get(workspace_id, {})
    _persona_slugs_explicit = _ws_cfg.get("persona_slugs_explicit")
    if _persona_slugs_explicit:
        personas = load_personas_by_slugs(_persona_slugs_explicit)
    else:
        personas = load_personas_for_workspace(workspace_id, persona_categories)

    if args.persona:
        personas = [p for p in personas if args.persona in p["slug"]]
        if not personas:
            print(f"no persona matched filter '{args.persona}'", file=sys.stderr)
            sys.exit(2)

    # If the registry entry pins specific models, use them (shootout harness).
    # Otherwise fall through to the production workspace_routing chain.
    # See TASK_CODING_SHOOTOUT_V1.md §T3.
    _ws_cfg = WORKSPACE_REGISTRY.get(workspace_id, {})
    _models_explicit = _ws_cfg.get("models_explicit")
    if _models_explicit:
        # Build the chain by looking up each named model in backends.yaml.
        # An explicit model that is not registered is a hard error — fail
        # fast rather than silently producing partial results.
        all_models: dict[str, dict[str, Any]] = {}
        for be in cfg.get("backends", []):
            if True:
                for mid in be.get("models", []):
                    model_id = mid["id"] if isinstance(mid, dict) else mid
                    all_models[model_id] = {
                        "id": model_id,
                        "backend_type": "ollama",
                        "big_model": False,
                        "is_vlm": False,
                        "memory_gb": _ollama_size_estimate(model_id),
                        "group": be.get("group", "general"),
                    }
        chain = []
        missing = []
        for mid in _models_explicit:
            if mid in all_models:
                chain.append(all_models[mid])
            else:
                missing.append(mid)
        if missing:
            print(
                f"workspace '{workspace_id}' models_explicit references unregistered "
                f"models (not found in backends.yaml): {missing}",
                file=sys.stderr,
            )
            sys.exit(4)
    else:
        chain = chain_models_for_workspace(cfg, workspace_id)

    if args.backend:
        chain = [m for m in chain if m["backend_type"] == args.backend]
    if args.model:
        chain = [m for m in chain if args.model in m["id"]]
    if not args.include_big_models:
        chain = [m for m in chain if not m["big_model"]]

    chain.sort(key=lambda m: m["memory_gb"])

    if args.require:
        required = [r.strip() for r in args.require.split(",") if r.strip()]
        chain_ids = [m["id"] for m in chain]
        missing = [r for r in required if not any(r in cid for cid in chain_ids)]
        if missing:
            print(
                f"REQUIRED models missing from resolved chain: {missing}\n"
                f"Available models in chain: {chain_ids}",
                file=sys.stderr,
            )
            sys.exit(3)

    # Thread the workspace's persona_categories down into the fixtures loader so
    # auto-coding (production) and auto-coding-bench (shootout) load different
    # persona sets from the same coding_scenarios.yaml. See
    # TASK_CODING_SHOOTOUT_V1.md §T1.5 for rationale.
    _ws_cfg = WORKSPACE_REGISTRY.get(args.workspace, {})
    _persona_categories = tuple(_ws_cfg.get("persona_categories", ()))
    # Only the coding fixtures module accepts a categories kwarg; the
    # compliance fixtures select personas from the fixture YAML itself.
    # Guard on the signature so workspaces with persona_categories but a
    # non-parameterised fixtures module (auto-compliance) don't TypeError.
    import inspect as _inspect

    _accepts_categories = "categories" in _inspect.signature(cf.expand_scenarios).parameters
    if _persona_categories and _accepts_categories:
        scenarios = list(cf.expand_scenarios(categories=_persona_categories))
    else:
        scenarios = list(cf.expand_scenarios())
    if args.max_scenarios:
        kept: dict[str, int] = {}
        scenarios = [
            s
            for s in scenarios
            if (
                kept.setdefault(s.persona_slug, 0) < args.max_scenarios
                and not kept.update({s.persona_slug: kept[s.persona_slug] + 1})
            )
        ]

    plan = {
        "workspace": workspace_id,
        "personas": [p["slug"] for p in personas],
        "models": [
            {
                "id": m["id"],
                "backend": m["backend_type"],
                "group": m["group"],
                "big_model": m["big_model"],
                "memory_gb": m["memory_gb"],
            }
            for m in chain
        ],
        "scenarios_total": len(scenarios),
        "cells_total": len(personas) * len(chain),
    }

    print(f"\n=== PERSONA MATRIX SWEEP — workspace={workspace_id} ===")
    print(f"  personas:  {len(personas)}  ({', '.join(plan['personas'])})")
    print(f"  models:    {len(chain)}  (smallest-first)")
    print(f"  scenarios: {len(scenarios)}")
    print(f"  cells:     {plan['cells_total']}")
    if args.dry_run:
        print("\nDRY RUN — exiting without execution.")
        for m in chain:
            print(
                f"    {m['backend_type']:6}  {m['id']:60}  {m['memory_gb']:5.1f}GB  group={m['group']}"
            )
        return {"plan": plan, "cells": []}

    results: list[dict[str, Any]] = []
    started = time.time()

    async with httpx.AsyncClient() as client:
        for mi, model in enumerate(chain, start=1):
            print(
                f"\n  [{mi}/{len(chain)}] model: {model['backend_type']}/{model['id']}  ({model['memory_gb']:.1f}GB)"
            )
            # Pre-model cleanup: evict ALL Ollama models to ensure only one
            # model is resident at a time. Without this, Ollama accumulates
            # models and exhausts 64GB unified memory mid-sweep.
            if model["backend_type"] == "ollama" and mi > 1:
                try:
                    r = await client.get(f"{OLLAMA_URL}/api/ps", timeout=5.0)
                    for m in r.json().get("models", []):
                        await _ollama_unload(client, m["name"])
                except Exception:
                    pass
            for pi, persona in enumerate(personas, start=1):
                pre = time.time()
                cell = await run_cell(client, persona, model, scenarios)
                summary = cell["summary"]
                el = time.time() - pre
                print(
                    f"    [{pi}/{len(personas)}] {persona['slug']:35}"
                    f"  PASS={summary['PASS']:3} WARN={summary['WARN']:2}"
                    f" FAIL={summary['FAIL']:2} ERR={summary['ERROR']:2}"
                    f"  ({el:.1f}s)"
                )
                results.append(cell)

            if model["backend_type"] == "ollama":
                await _ollama_unload(client, model["id"])
            await asyncio.sleep(EVICT_BACKOFF_S)

    elapsed = time.time() - started
    print(f"\n=== SWEEP COMPLETE — {elapsed:.0f}s ===")

    return {
        "schema": "portal5.persona_matrix.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(elapsed, 1),
        "plan": plan,
        "cells": results,
    }


# ── Console summary table ─────────────────────────────────────────────────

