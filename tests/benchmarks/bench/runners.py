"""Bench runners: direct Ollama, pipeline workspaces, persona routing.

Extracted byte-for-byte from tests/benchmarks/bench_tps.py, except two
dead conditionals (identical branches) collapsed to direct assignments —
see A6 in TASK_BENCH_MODULARIZE_V1.
"""

import os
import time

from .config import (
    _MATH_SPECIALIST_PATTERNS,
    MATH_SPECIALIST_WORKSPACES,
    OLLAMA_URL,
    PIPELINE_INACTIVITY_TIMEOUT,
    PIPELINE_URL,
)
from .discovery import (
    _config_ollama_models_by_group,
    _config_ollama_models_unique,
    _config_workspaces,
    _discover_personas,
    _load_backends_config,
    _parse_model_size_gb,
    _runtime_ollama_models,
)
from .lifecycle import (
    _unload_all_running_ollama_models,
    _wait_metal_drain,
    _wait_ollama_idle,
    _warmup_ollama_model,
)
from .measure import _warmup_pipeline_model, bench_tps
from .prompts import (
    PROMPTS,
    WORKSPACE_PROMPT_MAP,
    _get_prompt_for_model,
    _get_prompt_for_persona_category,
    _get_prompt_for_workspace,
    _prompt_category_for_model,
    _prompt_category_for_persona,
)
from .results_io import _append_result, _result_already_done


def bench_direct(
    ollama_available: bool,
    models_filter: str | None,
    runs: int,
    dry_run: bool,
    cooldown: float = 10.0,
    order: str = "size",
    output_path: str = "",
) -> list[dict]:
    results = []

    if ollama_available and not os.environ.get("BENCH_SKIP_OLLAMA"):
        ollama_groups = _config_ollama_models_by_group()
        ollama_unique = _config_ollama_models_unique()
        if models_filter:
            ollama_unique = [m for m in ollama_unique if models_filter in m]
        if order in ("size", "largest"):
            ollama_unique = sorted(
                ollama_unique,
                key=lambda m: _parse_model_size_gb(m),
                reverse=(order == "largest"),
            )
        runtime = _runtime_ollama_models()
        print(
            f"\n  Ollama models configured: {len(ollama_unique)} (across {len(ollama_groups)} groups, order={order})"
        )
        if runtime:
            installed = [m for m in ollama_unique if m in runtime]
            missing = [m for m in ollama_unique if m not in runtime]
            print(f"  Ollama installed: {len(installed)}/{len(ollama_unique)}")
            if missing:
                print(f"  Ollama not installed: {', '.join(missing)}")
        for i, model in enumerate(ollama_unique, 1):
            # Resume: skip already-completed models
            if output_path and _result_already_done(output_path, "model", model):
                print(f"    [{i}/{len(ollama_unique)}] {model} SKIP (already done)")
                continue
            available = model in runtime if runtime else True
            size_gb = _parse_model_size_gb(model)
            marker = "" if available else " [not installed]"
            print(
                f"    [{i}/{len(ollama_unique)}] {model} ({size_gb:.0f}GB){marker} ...",
                end=" ",
                flush=True,
            )
            if dry_run:
                print("(dry run)")
                continue
            if not available:
                print("SKIP")
                r = {
                    "model": model,
                    "label": "ollama-direct",
                    "backend": "ollama",
                    "path": "direct",
                    "available": False,
                    "error": "not installed in Ollama",
                    "est_memory_gb": size_gb,
                    "groups": [g for g, ms in ollama_groups.items() if model in ms],
                    "runs_total": runs,
                    "runs_success": 0,
                    "avg_tps": 0,
                    "min_tps": 0,
                    "max_tps": 0,
                    "stddev_tps": None,
                    "cv": None,
                    "avg_completion_tokens": 0,
                    "avg_elapsed_s": 0,
                    "runs": [],
                }
                results.append(r)
                if output_path:
                    _append_result(output_path, r)
                continue
            model_groups = [g for g, ms in ollama_groups.items() if model in ms]
            group = model_groups[0] if model_groups else ""
            prompt = _get_prompt_for_model(model, group=group)
            # Warm-up: force Ollama to load model before timed runs so run 1
            # doesn't include model-load latency.
            print("(warm-up) ", end="", flush=True)
            _warmup_ollama_model(model)
            prompt_cat = _prompt_category_for_model(model, group=group)
            r = bench_tps(
                OLLAMA_URL,
                model,
                prompt=prompt,
                runs=runs,
                label="ollama-direct",
                prompt_category=prompt_cat,
            )
            r["backend"] = "ollama"
            r["path"] = "direct"
            r["available"] = True
            r["est_memory_gb"] = size_gb
            r["groups"] = model_groups
            r["prompt_category"] = prompt_cat
            results.append(r)
            if output_path:
                _append_result(output_path, r)
            if r["avg_tps"] > 0:
                print(f"{r['avg_tps']} t/s  ({r['runs_success']}/{r['runs_total']} ok)")
            else:
                errors = [run.get("error", "?") for run in r["runs"] if "error" in run]
                print(f"FAIL ({', '.join(set(errors))})")
            if r.get("expected_model_match") is False:
                print(
                    f"  ⚠ ROUTING: got {r['routed_model']}, expected {r['expected_model_detail']}",
                    flush=True,
                )
            cv_val = r.get("cv")
            if cv_val is not None and cv_val > 0.15:
                print(
                    f"  ⚠ HIGH JITTER: cv={cv_val:.2f} "
                    f"(stddev={r.get('stddev_tps')} avg={r.get('avg_tps')})",
                    flush=True,
                )
            # Extra math pass — math-specialist models run the math prompt in addition
            # to their primary category prompt so both QS scores are in the results.
            is_math_specialist = any(p.lower() in model.lower() for p in _MATH_SPECIALIST_PATTERNS)
            if is_math_specialist and r.get("available", True) and not dry_run:
                math_model_label = f"{model}:math"
                if output_path and _result_already_done(output_path, "model", math_model_label):
                    print(f"      {model}:math SKIP (already done)")
                else:
                    print(f"      {model}:math ...", end=" ", flush=True)
                    rm = bench_tps(
                        OLLAMA_URL,
                        model,
                        prompt=PROMPTS["math"],
                        runs=runs,
                        label="ollama-direct",
                        prompt_category="math",
                    )
                    rm["backend"] = "ollama"
                    rm["path"] = "direct"
                    rm["available"] = True
                    rm["est_memory_gb"] = size_gb
                    rm["groups"] = model_groups
                    rm["prompt_category"] = "math"
                    rm["model"] = math_model_label
                    results.append(rm)
                    if output_path:
                        _append_result(output_path, rm)
                    if rm["avg_tps"] > 0:
                        print(
                            f"{rm['avg_tps']} t/s  ({rm['runs_success']}/{rm['runs_total']} ok) [math]"
                        )
                    else:
                        errors = [run.get("error", "?") for run in rm["runs"] if "error" in run]
                        print(f"FAIL [math] ({', '.join(set(errors))})")
            # Force Ollama to release this model from unified memory before next test.
            if i < len(ollama_unique):
                _unload_all_running_ollama_models()
                idle = _wait_ollama_idle(timeout_s=max(cooldown * 10, 60.0))
                if not idle:
                    if cooldown > 0:
                        print(
                            f"    cooldown {cooldown:.0f}s (idle timeout) ...", end=" ", flush=True
                        )
                        time.sleep(cooldown)
                        print("ok")
                else:
                    print("    ollama idle (memory clear)", end="", flush=True)
                    if cooldown > 0:
                        print(f" + {cooldown:.0f}s cooldown ...", end=" ", flush=True)
                        time.sleep(cooldown)
                    print("ok")
                # Poll until Metal GPU buffers drain before loading the next model.
                # Escalates from purge → Ollama restart if polling times out.
                # Returns False if drain fails after all retries — skip next model
                # rather than loading into a known-bad memory state.
                if not _wait_metal_drain(threshold_pct=80.0, timeout_s=30.0, retries=2):
                    print(
                        f"    [{i}/{len(ollama_unique)}] SKIP next — Metal drain failed, "
                        "continuing to avoid OOM cascade",
                        flush=True,
                    )

    return results


# ── Pipeline workspace tests ─────────────────────────────────────────────────


def bench_pipeline(
    pipeline_available: bool,
    workspace_filter: str | None,
    runs: int,
    dry_run: bool,
    output_path: str = "",
) -> list[dict]:
    if not pipeline_available:
        return []

    if workspace_filter:
        # Explicit operator filter overrides pipeline_bench_skip — operator
        # wants to probe this specific workspace intentionally.
        cfg = _load_backends_config()
        routing: dict[str, list[str]] = cfg.get("workspace_routing", {})
        workspaces = [workspace_filter] if workspace_filter in routing else []
    else:
        workspaces = _config_workspaces()

    results = []
    print(f"\n  Pipeline workspaces to test: {len(workspaces)}")
    for i, ws in enumerate(workspaces, 1):
        # Resume: skip already-completed workspaces
        if output_path and _result_already_done(output_path, "workspace", ws):
            print(f"    [{i}/{len(workspaces)}] {ws} SKIP (already done)")
            continue
        print(f"    [{i}/{len(workspaces)}] {ws} ...", end=" ", flush=True)
        if dry_run:
            print("(dry run)")
            continue
        prompt = _get_prompt_for_workspace(ws)
        prompt_cat = WORKSPACE_PROMPT_MAP.get(ws, "general")
        print("(warm-up) ", end="", flush=True)
        _warmup_pipeline_model(ws)
        # Pipeline calls may buffer <think> output before forwarding bytes —
        # use the inactivity timeout for every workspace (reasoning or not).
        _ws_timeout = PIPELINE_INACTIVITY_TIMEOUT
        r = bench_tps(
            PIPELINE_URL,
            ws,
            prompt=prompt,
            runs=runs,
            label="pipeline",
            prompt_category=prompt_cat,
            request_timeout=_ws_timeout,
        )
        r["backend"] = "pipeline"
        r["path"] = "pipeline"
        r["workspace"] = ws
        r["prompt_category"] = prompt_cat
        results.append(r)
        if output_path:
            _append_result(output_path, r)
        if r["avg_tps"] > 0:
            print(f"{r['avg_tps']} t/s  ({r['runs_success']}/{r['runs_total']} ok)")
        else:
            errors = [run.get("error", "?") for run in r["runs"] if "error" in run]
            print(f"FAIL ({', '.join(set(errors))})")
        if r.get("expected_model_match") is False:
            print(
                f"  ⚠ ROUTING: got {r['routed_model']}, expected {r['expected_model_detail']}",
                flush=True,
            )

        # Extra math pass — run math-specialist workspaces with the math prompt
        # in addition to their primary category prompt.
        if ws in MATH_SPECIALIST_WORKSPACES and not dry_run:
            math_label = f"{ws}:math"
            if output_path and _result_already_done(output_path, "workspace", math_label):
                print(f"    [{i}/{len(workspaces)}] {ws}:math SKIP (already done)")
            else:
                print(f"    [{i}/{len(workspaces)}] {ws}:math ...", end=" ", flush=True)
                rm = bench_tps(
                    PIPELINE_URL,
                    ws,
                    prompt=PROMPTS["math"],
                    runs=runs,
                    label="pipeline",
                    prompt_category="math",
                    request_timeout=PIPELINE_INACTIVITY_TIMEOUT,
                )
                rm["backend"] = "pipeline"
                rm["path"] = "pipeline"
                rm["workspace"] = math_label
                rm["prompt_category"] = "math"
                results.append(rm)
                if output_path:
                    _append_result(output_path, rm)
                if rm["avg_tps"] > 0:
                    print(
                        f"{rm['avg_tps']} t/s  ({rm['runs_success']}/{rm['runs_total']} ok) [math]"
                    )
                else:
                    errors = [run.get("error", "?") for run in rm["runs"] if "error" in run]
                    print(f"FAIL [math] ({', '.join(set(errors))})")

    return results


# ── Persona tests ────────────────────────────────────────────────────────────


def bench_personas(
    pipeline_available: bool,
    persona_filter: str | None,
    runs: int,
    dry_run: bool,
    output_path: str = "",
) -> list[dict]:
    """Test TPS for each persona's workspace_model through the pipeline."""
    if not pipeline_available:
        return []

    personas = _discover_personas()
    if persona_filter:
        personas = [
            p
            for p in personas
            if persona_filter in p["slug"] or persona_filter in p["name"].lower()
        ]
    # Sort by workspace_model so personas that share a model run consecutively,
    # minimising Ollama model swaps.
    personas = sorted(personas, key=lambda p: (p["workspace_model"], p["slug"]))

    results = []
    print(f"\n  Personas to test: {len(personas)}")
    for i, p in enumerate(personas, 1):
        slug = p["slug"]
        wm = p["workspace_model"]
        cat = p["category"]
        # Resume: skip already-completed personas
        if output_path and _result_already_done(output_path, "persona_slug", slug):
            print(f"    [{i}/{len(personas)}] {slug} ({cat}) SKIP (already done)")
            continue
        print(f"    [{i}/{len(personas)}] {slug} ({cat}) → {wm} ...", end=" ", flush=True)
        if dry_run:
            print("(dry run)")
            continue
        prompt = _get_prompt_for_persona_category(cat)
        prompt_cat = _prompt_category_for_persona(cat)
        _warmup_pipeline_model(wm)
        # Same rationale as the workspace path: inactivity timeout for all.
        _p_timeout = PIPELINE_INACTIVITY_TIMEOUT
        r = bench_tps(
            PIPELINE_URL,
            wm,
            prompt=prompt,
            runs=runs,
            label="persona",
            prompt_category=prompt_cat,
            request_timeout=_p_timeout,
        )
        r["backend"] = "pipeline"
        r["path"] = "persona"
        r["persona_slug"] = slug
        r["persona_name"] = p["name"]
        r["persona_category"] = cat
        r["workspace_model"] = wm
        r["prompt_category"] = prompt_cat
        results.append(r)
        if output_path:
            _append_result(output_path, r)
        if r["avg_tps"] > 0:
            print(f"{r['avg_tps']} t/s  ({r['runs_success']}/{r['runs_total']} ok)")
        else:
            errors = [run.get("error", "?") for run in r["runs"] if "error" in run]
            print(f"FAIL ({', '.join(set(errors))})")
        if r.get("expected_model_match") is False:
            print(
                f"  ⚠ ROUTING: got {r['routed_model']}, expected {r['expected_model_detail']}",
                flush=True,
            )

    return results
