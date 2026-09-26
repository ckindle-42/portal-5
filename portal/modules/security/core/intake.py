"""Candidate intake pipeline — intake.py.

Split from chain.py (M6-B1).  Public surface unchanged; chain.py re-exports
everything from this module.
"""

from __future__ import annotations

from typing import Any

import httpx

from .exec_chain import OLLAMA_URL, OMLX_URL
from .refusal import _audit_tools_probe

# ── Candidate intake constants ────────────────────────────────────────────────

TPS_FLOOR = 20.0  # minimum t/s for chain participation
PULL_TIMEOUT_S = 900.0  # large models on slow connections need headroom


# ── Pull helper ───────────────────────────────────────────────────────────────


def _pull_model(model: str, ollama_url: str = OLLAMA_URL) -> dict[str, Any]:
    """Pull a model via Ollama /api/pull with streaming progress."""
    import json as _j

    print(f"  pulling  {model} ...", end="", flush=True)
    try:
        with (
            httpx.Client(timeout=httpx.Timeout(PULL_TIMEOUT_S, connect=10.0)) as _c,
            _c.stream(
                "POST",
                f"{ollama_url}/api/pull",
                json={"name": model, "stream": True},
            ) as _r,
        ):
            _r.raise_for_status()
            _status = ""
            for _line in _r.iter_lines():
                if not _line:
                    continue
                try:
                    _obj = _j.loads(_line)
                    _status = _obj.get("status", _status)
                except _j.JSONDecodeError:
                    pass
        print(f" done ({_status})")
        return {"model": model, "pulled": True, "error": None}
    except Exception as _exc:
        print(f" ERROR: {_exc}")
        return {"model": model, "pulled": False, "error": str(_exc)}


# ── TPS warmup probe ──────────────────────────────────────────────────────────


def _tps_warmup(
    model: str,
    ollama_url: str = OLLAMA_URL,
    tokens: int = 200,
    tps_floor: float = TPS_FLOOR,
    engine: str = "ollama",
) -> dict[str, Any]:
    """Single-run TPS probe with a security-relevant prompt.

    ``engine="omlx"`` probes oMLX's OpenAI-compatible /v1/chat/completions
    instead of Ollama's native /api/generate — oMLX never reports an
    eval_count field, so token count there is the number of non-empty
    streamed content deltas (one per token on both engines' streaming
    servers), not an Ollama-specific accounting trick.
    """
    import json as _j2
    import time as _t

    print(f"  tps-probe {model[:45]} ...", end="", flush=True)
    try:
        _t0 = _t.perf_counter()
        _n = 0
        _probe_prompt = (
            "List 10 common network penetration testing tools and briefly state what each one does."
        )
        if engine == "omlx":
            with (
                httpx.Client(timeout=httpx.Timeout(120.0, connect=5.0)) as _c2,
                _c2.stream(
                    "POST",
                    f"{OMLX_URL}/v1/chat/completions",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": _probe_prompt}],
                        "max_tokens": tokens,
                        "stream": True,
                    },
                ) as _r2,
            ):
                _r2.raise_for_status()
                for _line2 in _r2.iter_lines():
                    if not _line2.startswith("data: ") or _line2 == "data: [DONE]":
                        continue
                    try:
                        _chunk = _j2.loads(_line2[len("data: ") :])
                        if (_chunk.get("choices") or [{}])[0].get("delta", {}).get("content"):
                            _n += 1
                    except Exception:
                        pass
        else:
            with (
                httpx.Client(timeout=httpx.Timeout(120.0, connect=5.0)) as _c2,
                _c2.stream(
                    "POST",
                    f"{ollama_url}/api/generate",
                    json={
                        "model": model,
                        "prompt": _probe_prompt,
                        "options": {"num_predict": tokens},
                        "stream": True,
                    },
                ) as _r2,
            ):
                _r2.raise_for_status()
                for _line2 in _r2.iter_lines():
                    if not _line2:
                        continue
                    try:
                        _obj2 = _j2.loads(_line2)
                        if _obj2.get("eval_count"):
                            _n = _obj2["eval_count"]
                            break
                        if not _obj2.get("done", False):
                            _n += 1
                    except Exception:
                        pass
        _elapsed = _t.perf_counter() - _t0
        _tps = round(_n / _elapsed, 1) if _elapsed > 0 and _n > 0 else 0.0
        _below = bool(_tps < tps_floor and _tps > 0)
        _flag = f"  ⚠  BELOW {tps_floor} t/s FLOOR — will skip" if _below else ""
        print(f" {_tps} t/s{_flag}")
        return {
            "model": model,
            "tps": _tps,
            "below_floor": _below,
            "elapsed_s": round(_elapsed, 1),
            "tokens": _n,
            "error": None,
        }
    except Exception as _exc2:
        print(f" ERROR: {_exc2}")
        return {
            "model": model,
            "tps": 0.0,
            "below_floor": True,
            "elapsed_s": 0.0,
            "tokens": 0,
            "error": str(_exc2),
        }


# ── Candidate intake pipeline ─────────────────────────────────────────────────


def run_candidate_intake(
    models: list[str],
    dry_run: bool = False,
    skip_pull: bool = False,
    tps_floor: float = TPS_FLOOR,
    engine: str = "ollama",
) -> list[dict[str, Any]]:
    """Full intake pipeline: pull → TPS probe → audit-tools → queue verdict.

    Gate order:
      1. Pull  — model must exist in Ollama after pull (skip with skip_pull=True).
                 No-op for engine="omlx": an oMLX candidate is already resident
                 weights on disk (oMLX's model_dir), not something to pull —
                 always treated as skip_pull regardless of the flag.
      2. TPS   — must sustain >= tps_floor t/s; below-floor models are skipped
      3. Tools — the engine must emit a tool_call for get_current_time

    Returns one result dict per model:
      model, pulled, tps, below_floor, tool_outcome, queued, skip_reason
    """
    print("\n── Candidate Intake Pipeline ──\n")
    results: list[dict[str, Any]] = []

    for model in models:
        rec: dict[str, Any] = {
            "model": model,
            "pulled": False,
            "tps": 0.0,
            "below_floor": False,
            "tool_outcome": "skipped",
            "queued": False,
            "skip_reason": None,
        }

        if dry_run:
            print(f"  [dry-run] {model}")
            rec["queued"] = True
            results.append(rec)
            continue

        # Gate 1: pull (oMLX candidates are already-resident local weights)
        if not skip_pull and engine != "omlx":
            _pull_r = _pull_model(model)
            rec["pulled"] = _pull_r["pulled"]
            if not rec["pulled"]:
                rec["skip_reason"] = f"pull failed: {_pull_r['error']}"
                results.append(rec)
                continue
        else:
            rec["pulled"] = True

        # Gate 2: TPS floor
        _tps_r = _tps_warmup(model, tps_floor=tps_floor, engine=engine)
        rec["tps"] = _tps_r["tps"]
        rec["below_floor"] = _tps_r["below_floor"]
        if _tps_r["below_floor"] and _tps_r["tps"] > 0:
            rec["skip_reason"] = (
                f"tps {_tps_r['tps']} t/s below floor {tps_floor} t/s — "
                "chain turns would stall before meaningful output"
            )
            results.append(rec)
            continue

        # Gate 3: audit-tools
        _audit_r = _audit_tools_probe(model, engine=engine)
        rec["tool_outcome"] = _audit_r["outcome"]
        if _audit_r["outcome"] != "tool_call":
            rec["skip_reason"] = (
                f"tool probe returned '{_audit_r['outcome']}' "
                f"— needs chat-template fix before chain bench"
            )
            results.append(rec)
            continue

        rec["queued"] = True
        results.append(rec)

    return results
