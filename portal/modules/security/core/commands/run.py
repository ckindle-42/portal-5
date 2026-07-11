"""Main bench runner and summary printers — commands/run.py.

Extracted from cli.py (M6-B2).  cli.py now imports from here and keeps
only the argparse ``main()`` dispatcher.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .._config import BenchConfig
from .._data import (
    EXECUTION_WORKSPACES,
    PER_WORKSPACE_TIMEOUT,
    PIPELINE_API_KEY,
    PIPELINE_URL,
    PROMPT_MAX_TOKENS,
    PROMPTS,
    REQUEST_TIMEOUT,
)
from ..chain import (
    _run_exec_chain,
)
from ..scoring import (
    score_execution,
    score_response,
    scoring_criteria_met,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _workspace_category(workspace: str) -> str:
    if "redteam" in workspace or "pentest" in workspace:
        return "redteam"
    if "blueteam" in workspace:
        return "blueteam"
    if "purpleteam" in workspace:
        return "purpleteam"
    return "general"


# ── Main runner ───────────────────────────────────────────────────────────────


def _emit_parallel_preflight(parallel_workspaces: int) -> None:
    """Emit a startup banner + Ollama MAX_LOADED warning when running parallel."""
    import contextlib
    import os

    _env_path = Path(__file__).resolve().parents[5] / ".env"
    _max_loaded: int | None = None
    if _env_path.exists():
        for _line in _env_path.read_text().splitlines():
            _line = _line.strip()
            if _line.startswith("OLLAMA_MAX_LOADED_MODELS"):
                _, _, _v = _line.partition("=")
                _v = _v.split("#")[0].strip()
                with contextlib.suppress(ValueError):
                    _max_loaded = int(_v)
                break

    # Process env override wins over the .env file when both are set
    _env_override = os.environ.get("OLLAMA_MAX_LOADED_MODELS", "").strip()
    if _env_override:
        with contextlib.suppress(ValueError):
            _max_loaded = int(_env_override)

    print(f"  [parallel] workspaces={parallel_workspaces}")
    if _max_loaded is not None:
        if _max_loaded < 4 and parallel_workspaces >= 2:
            print(
                f"  [parallel] WARNING: OLLAMA_MAX_LOADED_MODELS={_max_loaded} "
                f"is below the recommended 4 for chained workspaces under "
                f"parallel dispatch. auto-purpleteam-deep loads 4 chain "
                f"models — at <4 slots Ollama will evict/reload between hops. "
                f"Recommended: 5 (router + 4 chain models)."
            )
        else:
            print(f"  [parallel] OLLAMA_MAX_LOADED_MODELS={_max_loaded} (OK)")
    else:
        print(
            "  [parallel] note: could not read OLLAMA_MAX_LOADED_MODELS "
            "from .env — verify the running Ollama process has it set to "
            ">=4 for purpleteam-deep parallel runs."
        )


def run_bench(
    workspaces: list[str],
    prompt_keys: list[str],
    cfg: BenchConfig,
    dry_run: bool = False,
    exec_eval: bool = False,
    exec_chain_models: list[str] | None = None,
    blue_defender_model: str | None = None,
    chain_rounds: int = 1,
    lab_exec: bool = False,
    direct_theory_model: str | None = None,
    strip_think: bool = False,
    checkpoint_path: Path | None = None,
    parallel_workspaces: int = 1,
) -> list[dict[str, Any]]:
    """Run the dual-pass security bench.

    Theory pass (all workspaces):
      portal_no_tools=true → model has no tools visible → full prose rubric scoring
    Execution pass (EXECUTION_WORKSPACES only, when exec_eval=True):
      tools enabled → tool call sequence scoring against exec_sequence
    Execution chain (when exec_chain_models provided):
      multi-model handoff chain per prompt → chain_exec_composite score

    Phase 1 (theory + exec passes) supports concurrent dispatch via
    ``parallel_workspaces``. Each (workspace, prompt) tuple is an independent
    task; results are sorted deterministically before being returned. Phase 2
    (chain batch) remains serial because the warm-up logic needs surgical
    control over Ollama's MAX_LOADED slots.
    """
    # Deferred import to avoid circular dependency with __init__.py facade.
    # These functions are only needed for workspace scoring (Phase 1); in
    # chain-only mode they are never called, so tolerate absence.
    try:
        from .. import call_pipeline, call_pipeline_exec, call_theory_direct
    except ImportError:
        call_pipeline = call_pipeline_exec = call_theory_direct = None  # type: ignore[assignment]

    results: list[dict[str, Any]] = []
    # Collect (row_index, prompt_key) pairs that need chain runs — executed as a
    # separate phase AFTER all theory/exec pipeline passes complete. This prevents
    # pipeline workspace models (loaded by theory/exec) from evicting chain models
    # mid-run, which caused regression between runs.
    chain_pending: list[tuple[int, str]] = []

    # ── Chain-only shortcut (--skip-workspace-bench + chain models) ──────────
    # When skipping theory/exec passes entirely, directly queue all exec-sequence
    # prompts for the chain. A sentinel row is inserted per prompt so callers
    # have a result row to attach chain data to.
    if not workspaces and exec_chain_models:
        for key in prompt_keys:
            meta = PROMPTS.get(key, {})
            if not meta.get("exec_sequence"):
                continue
            sentinel: dict[str, Any] = {
                "workspace": "(chain-only)",
                "prompt_key": key,
                "prompt_category": meta.get("category", "redteam"),
                "workspace_category": "redteam",
                "status": "ok",
                "elapsed_s": 0.0,
                "scores": {},
                "error": None,
            }
            results.append(sentinel)
            chain_pending.append((len(results) - 1, key))
        print(f"Chain-only mode: {len(chain_pending)} prompt(s) queued")

    # ── Phase 1: Theory + Exec pipeline passes (parallel-capable) ────────────
    # Build the (workspace, prompt, ws_cat, is_exec_ws) task list, then dispatch
    # via ThreadPoolExecutor sized by parallel_workspaces. N=1 → effectively
    # serial. The pipeline's per-workspace semaphore (default 5) and Ollama's
    # OLLAMA_NUM_PARALLEL (default 4) bound backend-side concurrency.
    tasks: list[tuple[str, str, str, bool]] = []
    for workspace in workspaces:
        ws_cat = _workspace_category(workspace)
        is_exec_ws = workspace in EXECUTION_WORKSPACES
        for key in prompt_keys:
            tasks.append((workspace, key, ws_cat, is_exec_ws))

    total = len(tasks)

    def _process_one(
        workspace: str, key: str, ws_cat: str, is_exec_ws: bool
    ) -> tuple[dict[str, Any] | None, list[str]]:
        """Run theory + (optional) exec pass for one (workspace, prompt).

        Returns ``(row, log_lines)``. ``row`` is ``None`` for skips. The
        caller is responsible for emitting ``log_lines`` and appending
        ``row`` to ``results`` under a lock.
        """
        log: list[str] = []
        meta = PROMPTS[key]

        if ws_cat == "blueteam" and meta["category"] == "redteam":
            log.append(f"{workspace} × {key}: SKIP (blue-team workspace, red-team prompt)")
            return None, log
        if ws_cat == "redteam" and meta["category"] == "blueteam":
            log.append(f"{workspace} × {key}: SKIP (red-team workspace, blue-team prompt)")
            return None, log

        if dry_run:
            log.append(f"{workspace} × {key} ... DRY-RUN")
            return None, log

        # ── Theory pass (forced prose for execution workspaces) ───────────
        theory_content, theory_elapsed, status, error = "", 0.0, "ok", None
        theory_scores: dict = {}
        try:
            request_overrides: dict = {}
            if is_exec_ws:
                # portal_no_tools strips tools from the request entirely before
                # it reaches Ollama — tool_choice=none alone leaves tool definitions
                # in the body and causes models to emit skeletal header-only responses.
                request_overrides["portal_no_tools"] = True
                # Cap tokens for exec-workspace theory pass. Exec models have
                # exec-mode system prompts (mandatory tool calls) that conflict
                # with portal_no_tools, causing degenerate loops up to 6000 tokens
                # (~750s on SuperGemma4 at ~8 TPS). 2000 tokens is sufficient for
                # full header coverage and caps worst-case at ~250s.
                request_overrides["max_tokens"] = 2000

            if request_overrides:
                import json as _json_tmp

                import httpx as _httpx_tmp

                _parts: list[str] = []
                _t0 = time.monotonic()
                _hdrs = {"Authorization": f"Bearer {PIPELINE_API_KEY}"}
                _timeout = PER_WORKSPACE_TIMEOUT.get(workspace, REQUEST_TIMEOUT)
                with (
                    _httpx_tmp.Client(timeout=_httpx_tmp.Timeout(_timeout, connect=5.0)) as _cl,
                    _cl.stream(
                        "POST",
                        f"{PIPELINE_URL}/v1/chat/completions",
                        json={
                            "model": workspace,
                            "messages": [{"role": "user", "content": meta["text"]}],
                            "stream": True,
                            "max_tokens": PROMPT_MAX_TOKENS,
                            **request_overrides,
                        },
                        headers=_hdrs,
                    ) as _resp,
                ):
                    _resp.raise_for_status()
                    for _line in _resp.iter_lines():
                        if _line == "data: [DONE]":
                            break
                        if _line.startswith("data: "):
                            try:
                                _d = _json_tmp.loads(_line[6:])
                                _c = _d["choices"][0]["delta"].get("content") or ""
                                if _c:
                                    _parts.append(_c)
                            except Exception:
                                pass
                        # Safe to early-exit here: this path runs only for
                        # EXECUTION_WORKSPACES with portal_no_tools=true, which
                        # causes the pipeline to skip the chain (handlers.py:828).
                        if meta and _parts and scoring_criteria_met("".join(_parts), meta):
                            break
                theory_content = "".join(_parts)
                theory_elapsed = time.monotonic() - _t0
            elif direct_theory_model:
                theory_content, theory_elapsed = call_theory_direct(
                    direct_theory_model,
                    meta["text"],
                    workspace=workspace,
                    prompt_meta=meta,
                )
            else:
                theory_content, theory_elapsed = call_pipeline(
                    workspace, meta["text"], prompt_meta=meta
                )

            if strip_think:
                from portal.platform.inference.router.thinking import strip_think as _strip_think

                theory_content = _strip_think(theory_content)
            theory_scores = score_response(theory_content, meta, ws_cat)
        except Exception as exc:
            theory_scores = {"composite": 0.0, "disclaimers": 0, "mitre_count": 0, "words": 0}
            status = "error"
            error = str(exc)

        # ── Execution pass (execution workspaces only) ────────────────────
        exec_scores: dict = {}
        exec_elapsed = 0.0
        if exec_eval and is_exec_ws and meta.get("exec_sequence") and status == "ok":
            try:
                _, tool_calls, exec_elapsed = call_pipeline_exec(
                    workspace, meta["text"], prompt_meta=meta
                )
                exec_scores = score_execution(tool_calls, meta)
            except Exception as exc_e:
                exec_scores = {"exec_composite": 0.0, "error": str(exc_e)}

        row: dict[str, Any] = {
            "workspace": workspace,
            "prompt_key": key,
            "prompt_category": meta["category"],
            "workspace_category": ws_cat,
            "status": status,
            "elapsed_s": round(theory_elapsed, 2),
            "scores": theory_scores,
            "error": error,
            "_calls": {
                "theory": 1 if theory_content else 0,
                "exec": 1 if exec_scores else 0,
                "chain": 0,
            },
        }
        if exec_scores:
            row["exec_scores"] = exec_scores
            row["exec_elapsed_s"] = round(exec_elapsed, 2)

        # Mark chain-eligible rows — resolved to chain_pending after Phase 1 sorts
        if exec_eval and exec_chain_models and meta.get("exec_sequence") and status == "ok":
            row["_chain_eligible"] = True

        # ── Build per-task log lines ───────────────────────────────────────
        c = theory_scores.get("composite", 0.0)
        d = theory_scores.get("disclaimers", 0)
        m = theory_scores.get("mitre_count", 0)
        h = f"{len(theory_scores.get('headers_present', []))}/{len(theory_scores.get('headers_required', []))}"
        flag = " ⚠️  disclaimers" if d > 0 and ws_cat in ("redteam", "purpleteam") else ""
        exec_tag = (
            (
                f"  exec={exec_scores.get('exec_composite', 0):.2f}"
                f"  steps={len(exec_scores.get('steps_hit', []))}/{len(meta.get('exec_sequence', []))}"
            )
            if exec_scores
            else ""
        )
        log.append(
            f"{workspace} × {key}: {theory_elapsed:.0f}s  theory={c:.2f}  "
            f"headers={h}  mitre={m}{exec_tag}{flag}"
        )
        drivers = theory_scores.get("score_drivers", [])
        if drivers:
            log.append(f"    why: {' | '.join(drivers)}")
        snip = theory_scores.get("snippet", "")
        if snip:
            log.append(f'    snip: "{snip[:200]}"')
        if exec_scores and exec_scores.get("tool_calls_made", 0) > 0:
            for call in exec_scores.get("calls_made", []):
                log.append(f"    tool: {call['tool']}({call['args_snip']})")
        if exec_scores and exec_scores.get("steps_missed"):
            for md in exec_scores.get("miss_detail", []):
                args_seen = md["args_seen"]
                seen_str = (
                    " / ".join(f'"{a}"' for a in args_seen[:2]) if args_seen else "(no calls)"
                )
                log.append(
                    f"    miss [{md['step']}] needed={md['needed_keywords'][:3]}  saw={seen_str}"
                )

        return row, log

    if tasks:
        print(f"\n── Phase 1: {total} task(s), parallel={parallel_workspaces} ──")
        if parallel_workspaces >= 2:
            _emit_parallel_preflight(parallel_workspaces)

        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        _lock = threading.Lock()
        _done = [0]
        _raw_results: list[dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=max(1, parallel_workspaces)) as ex:
            _futures = {ex.submit(_process_one, *t): t for t in tasks}
            for _fut in as_completed(_futures):
                try:
                    _row, _log_lines = _fut.result()
                except Exception as _exc:
                    _row, _log_lines = None, [f"ERROR: {_exc}"]
                with _lock:
                    _done[0] += 1
                    _prefix = f"  [{_done[0]}/{total}] "
                    if _log_lines:
                        print(_prefix + _log_lines[0])
                        for _extra in _log_lines[1:]:
                            print(_extra)
                    if _row is not None:
                        _raw_results.append(_row)
                    if checkpoint_path and not dry_run:
                        try:  # noqa: SIM105
                            checkpoint_path.write_text(json.dumps(_raw_results, indent=2))
                        except Exception:
                            pass

        # Deterministic ordering: workspace-major (input order), prompt-secondary
        _ws_idx = {w: i for i, w in enumerate(workspaces)}
        _pk_idx = {k: i for i, k in enumerate(prompt_keys)}
        _raw_results.sort(
            key=lambda r: (
                _ws_idx.get(r["workspace"], 9999),
                _pk_idx.get(r["prompt_key"], 9999),
            )
        )

        # Promote raw rows to results, building chain_pending from sorted indexes
        for _r in _raw_results:
            results.append(_r)
            if _r.pop("_chain_eligible", False):
                chain_pending.append((len(results) - 1, _r["prompt_key"]))
    # ── Phase 2: Chain batch — all chain runs after theory/exec complete ─────
    # Running chains as a batch prevents pipeline models (loaded above) from
    # evicting chain models. MAX_LOADED=3 means we must be surgical: unload
    # non-chain models first, then warm chain models one by one so all 3 slots
    # are occupied by chain models before any chain prompt runs.
    if chain_pending and exec_chain_models and not dry_run:
        import httpx as _hw

        _ollama_url = PIPELINE_URL.replace(":9099", ":11434")

        # Step 1: inventory what's currently loaded
        _loaded_ids: set[str] = set()
        try:
            with _hw.Client(timeout=_hw.Timeout(10, connect=3.0)) as _pc:
                _ps = _pc.get(f"{_ollama_url}/api/ps")
                _ps.raise_for_status()
                for _m in _ps.json().get("models", []):
                    _loaded_ids.add(_m["name"])
        except Exception:
            pass

        # Step 2: unload non-chain models so we don't hit MAX_LOADED during pre-warm
        _chain_set = set(exec_chain_models)
        if blue_defender_model:
            _chain_set.add(blue_defender_model)
        _to_evict = [_lid for _lid in _loaded_ids if _lid not in _chain_set]
        if _to_evict:
            print(f"\n── Chain phase: evicting {len(_to_evict)} non-chain model(s) ──")
            for _ev in _to_evict:
                print(f"  unload {_ev.split('/')[-1][:35]} ...", end="", flush=True)
                try:
                    with _hw.Client(timeout=_hw.Timeout(30, connect=3.0)) as _ec:
                        _ec.post(
                            f"{_ollama_url}/api/generate",
                            json={"model": _ev, "prompt": "", "keep_alive": 0},
                        )
                    print(" done")
                except Exception as _ee:
                    print(f" skip({type(_ee).__name__})")

        # Step 3: pre-warm chain models that aren't already loaded
        _already_warm = _loaded_ids & _chain_set
        _need_warm = [_cm for _cm in exec_chain_models if _cm not in _already_warm]
        if blue_defender_model and blue_defender_model not in _already_warm:
            _need_warm.append(blue_defender_model)

        print(
            f"\n── Chain phase: pre-warming {len(_need_warm)} model(s) "
            f"({len(_already_warm)} already loaded) ──"
        )
        for _cm in _need_warm:
            print(f"  warming {_cm.split('/')[-1][:35]} ...", end="", flush=True)
            # Workspace slugs (no "/" or ":") route through the pipeline, not Ollama.
            _is_slug = "/" not in _cm and ":" not in _cm
            _warm_url = (
                f"{PIPELINE_URL}/v1/chat/completions"
                if _is_slug
                else f"{_ollama_url}/v1/chat/completions"
            )
            _warm_headers: dict = {}
            if _is_slug and PIPELINE_API_KEY:
                _warm_headers["Authorization"] = f"Bearer {PIPELINE_API_KEY}"
            try:
                with _hw.Client(timeout=_hw.Timeout(300, connect=5.0)) as _wc:
                    _wr = _wc.post(
                        _warm_url,
                        headers=_warm_headers,
                        json={
                            "model": _cm,
                            "messages": [{"role": "user", "content": "hi"}],
                            "max_tokens": 5,
                            "stream": False,
                        },
                    )
                    _wr.raise_for_status()
                print(" warm")
            except Exception as _we:
                print(f" WARN({_we})")

        print(f"\n── Chain phase: {len(chain_pending)} prompt(s) × 1 workspace ──")
        for _ridx, _pkey in chain_pending:
            _meta = PROMPTS[_pkey]
            print(f"  chain {_pkey} ...", end="", flush=True)
            _chain_results: list[dict] = []
            try:
                _chain_results = _run_exec_chain(
                    _pkey,
                    exec_chain_models,
                    cfg,
                    dry_run=False,
                    blue_defender_model=blue_defender_model,
                    chain_rounds=chain_rounds,
                    lab_exec=lab_exec,
                )
            except Exception as _ce:
                _chain_results = [{"error": str(_ce)}]

            results[_ridx]["exec_chain"] = _chain_results

            # Print chain summary
            _ar2 = [_r for _r in _chain_results if not _r.get("_blue_defender")]
            _be2 = next((_r for _r in _chain_results if _r.get("_blue_defender")), None)
            if _ar2:
                _cc = _ar2[0].get("chain_exec_composite", 0)
                _cn = _ar2[0].get("chain_models_with_calls", 0)
                _ct = _ar2[0].get("chain_total_models", len(_ar2))
                _ch = _ar2[0].get("chain_handoff_quality", "?")
                _bdr = _ar2[0].get("blue_detection_rate", 0.0)
                _ber = _ar2[0].get("blue_evasion_rate", 0.0)
                _speed = _ar2[0].get("chain_speed_score", "?")
                _bd_str = f"  blue_det={_bdr:.0%}  evaded={_ber:.0%}" if _be2 else ""
                _spd_str = f"  speed={_speed}" if isinstance(_speed, (int, float)) else ""
                _final_det = f"  final_det={_be2.get('detection_score', 0):.2f}" if _be2 else ""
                print(
                    f"\n  chain({_ct}m)  exec={_cc:.2f}  tools={_cn}/{_ct}  handoff={_ch}{_bd_str}{_spd_str}{_final_det}"
                )

                # Build a lookup of blue turns keyed by round+model so we can
                # interleave blue responses with red tool calls in the display
                _blue_turns_data = _be2.get("blue_turns", []) if _be2 else []
                _bt_lookup: dict[str, dict] = {}
                for _bt in _blue_turns_data:
                    _key = f"{_bt.get('round', 1)}:{_bt.get('after_model', '')}"
                    _bt_lookup[_key] = _bt

                # Per-model tool call detail — interleaved with blue detection responses
                for _rm in _ar2:
                    _mname = _rm.get("model", "?").split("/")[-1][:20]
                    _mround = _rm.get("round", 1)
                    _mtcs = _rm.get("tool_calls", [])
                    _msteps = _rm.get("steps_hit", [])
                    _mmissed = _rm.get("steps_missed", [])
                    _retried = _rm.get("retried", False)
                    _rtag = " [retried]" if _retried else ""
                    _mlab = _rm.get("lab_outputs", [])
                    if _mtcs:
                        for _tc in _mtcs:
                            _asnip = str(_tc.get("arguments", ""))[:100]
                            print(
                                f"    [RED R{_mround} {_mname}{_rtag}] {_tc.get('tool', '?')}({_asnip})"
                            )
                        # Show real execution output (truncated) when lab_exec mode active
                        for _lo in _mlab:
                            _lok = "OK" if _lo.get("ok") else "ERR"
                            _lout = _lo.get("output", "")[:200].replace("\n", " ↵ ")
                            print(f"    [EXEC {_lok}] {_lout}")
                        _mresult = _rm.get("result_hits", [])
                        if _msteps:
                            _method_only = [s for s in _msteps if s not in _mresult]
                            _hit_line = f"    [RED] steps_hit={_method_only}"
                            if _mresult:
                                _hit_line += f"  result_match={_mresult}"
                            print(_hit_line)
                        if _mmissed:
                            print(f"    [RED] steps_missed={_mmissed}")
                        # Show blue inline response for this turn
                        _bt_entry = _bt_lookup.get(f"{_mround}:{_rm.get('model', '')}")
                        if _bt_entry:
                            _det_tag = (
                                "DETECTED"
                                if _bt_entry.get("detected")
                                else ("MISSED" if _bt_entry.get("explicitly_missed") else "LOW")
                            )
                            _mitre_tag = (
                                f" [{', '.join(_bt_entry['mitre_ids'][:2])}]"
                                if _bt_entry.get("mitre_ids")
                                else ""
                            )
                            _bsnip = _bt_entry.get("response", "")[:180].replace("\n", " ")
                            print(f"    [BLUE{_mitre_tag}] {_det_tag}: {_bsnip}")
                            # Show blue active response actions
                            _bar = _bt_entry.get("blue_active_results", [])
                            for _ba in _bar:
                                _bok = "OK" if _ba.get("ok") else "ERR"
                                print(
                                    f"    [BLUE-ACTIVE {_bok}] {_ba['tool']}({_ba.get('arguments', {})}) → {_ba.get('output', '')[:120]}"
                                )
                    else:
                        print(
                            f"    [RED R{_mround} {_mname}{_rtag}] FAIL — no tool calls after retry (steps_missed={_mmissed})"
                        )

                # Final blue summary (post-chain full analysis)
                if _be2 and _be2.get("content_len", 0) > 0:
                    _bsteps_det = _be2.get("steps_detected", [])
                    _bsteps_miss = _be2.get("steps_missed", [])
                    print(
                        f"  [BLUE FINAL] steps_detected={_bsteps_det}  steps_missed_detection={_bsteps_miss}"
                    )
            else:
                print(" (no results)")

    return results


# ── Summary printers ──────────────────────────────────────────────────────────


def _print_summary(results: list[dict[str, Any]]) -> None:
    if not results:
        return
    print("\n" + "═" * 72)
    print("SECURITY BENCH SUMMARY")
    print("═" * 72)

    by_ws: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        if r["status"] == "ok":
            by_ws.setdefault(r["workspace"], []).append(r)

    rows = []
    for ws, rs in by_ws.items():
        # Skip sentinel rows (chain-only mode) that have no theory scores
        rs = [r for r in rs if r.get("scores", {}).get("composite") is not None]
        if not rs:
            continue
        avg_comp = sum(r["scores"]["composite"] for r in rs) / len(rs)
        avg_disc = sum(r["scores"].get("disclaimers", 0) for r in rs) / len(rs)
        avg_mitre = sum(r["scores"].get("mitre_count", 0) for r in rs) / len(rs)
        rows.append((avg_comp, ws, avg_disc, avg_mitre, len(rs)))

    rows.sort(reverse=True)
    print(
        f"{'Workspace':<30} {'Avg Score':>10} {'Disclaimers':>12} {'ATT&CK IDs':>11} {'Prompts':>8}"
    )
    print("-" * 72)
    for comp, ws, disc, mitre, n in rows:
        disc_flag = " ⚠️" if disc > 0.3 else ""
        print(f"{ws:<30} {comp:>10.3f} {disc:>12.1f}{disc_flag:3} {mitre:>11.1f} {n:>8}")
    print("═" * 72)


def _print_intake_summary(results: list) -> None:
    """Print intake results and emit a ready-to-run bench command for queued models."""
    queued = [r for r in results if r.get("queued")]
    skipped = [r for r in results if not r.get("queued")]
    print(f"\n── Intake summary: {len(queued)} queued, {len(skipped)} skipped ──")
    if queued:
        print("\nQueued for chain bench:")
        for r in queued:
            tps_str = f"{r['tps']} t/s" if r["tps"] > 0 else "dry-run"
            print(f"  OK  {r['model'][:65]}  {tps_str}")
    if skipped:
        print("\nSkipped:")
        for r in skipped:
            print(f"  SKIP {r['model'][:65]}")
            print(f"       reason: {r['skip_reason']}")
    if queued and not all(r.get("tps", 0) == 0 for r in queued):
        models_arg = " ".join(r["model"] for r in queued)
        print("\nReady to bench (copy-paste):")
        print(
            f"  python3 tests/benchmarks/bench_security.py "
            f"--skip-workspace-bench "
            f"--exec-chain-models {models_arg}"
        )
        print(
            "\nTo keep current 3-slot chain structure (RECON/EXPLOIT/POST-EXPLOIT), "
            "add existing slots:\n"
            "  --exec-chain-models "
            "hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M "
            "huihui_ai/gemma-4-abliterated:E2b-qat "
            "huihui_ai/baronllm-abliterated"
        )
