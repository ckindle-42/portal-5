"""Ollama-direct chat (native /api/chat + options) + one-shot and +1-repair arms.

Eviction mirrors capability_probe.py's model-major pattern (one resident model).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from tests.benchmarks.bench_capability import _emits_reasoning
from tests.benchmarks.bench_repair.config import (
    ARM_ONESHOT,
    ARM_REPAIR,
    OLLAMA_URL,
    ONE_SHOT_TEMPLATE,
    ONESHOT_N,
    REPAIR_N,
    REPAIR_TEMPLATE,
)
from tests.benchmarks.bench_repair.scoring import score_code

_SAMPLING_OPTION_KEYS = (
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "repeat_penalty",
    "presence_penalty",
    "seed",
)


@dataclass
class SampleResult:
    workspace: str
    model_hint: str
    arm: str
    problem_id: str
    sample_idx: int
    passed: bool
    detail: str
    latency_s: float


def _chat_ollama(
    model_hint: str,
    messages: list[dict],
    *,
    token_budget: int,
    sampling: dict | None = None,
    think: bool | None = None,
    timeout: float = 600.0,
) -> tuple[str, float]:
    """Returns (content, elapsed_s). Uses Ollama's native /api/chat + options."""
    options = {"num_predict": token_budget}
    for key in _SAMPLING_OPTION_KEYS:
        val = (sampling or {}).get(key)
        if val is not None:
            options[key] = val
    payload = {
        "model": model_hint,
        "messages": messages,
        "options": options,
        "stream": False,
    }
    if think is not None:
        payload["think"] = think
    t0 = time.monotonic()
    r = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=timeout)
    r.raise_for_status()
    elapsed = time.monotonic() - t0
    content = r.json().get("message", {}).get("content", "")
    return content, elapsed


def evict_all() -> None:
    try:
        ps = httpx.get(f"{OLLAMA_URL}/api/ps", timeout=5).json()
        for m in ps.get("models", []):
            httpx.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": m["name"], "keep_alive": 0},
                timeout=10,
            )
    except Exception:  # noqa: BLE001
        pass  # best-effort; a stale model just slows the next run


def _budget_for(workspace: str) -> int:
    if _emits_reasoning(workspace):
        return 8192
    return 4096


def run_one_shot(
    workspace: str,
    model_hint: str,
    problem: dict,
    *,
    n: int = ONESHOT_N,
    sampling: dict | None = None,
    think: bool | None = None,
) -> list[SampleResult]:
    """n samples of one-shot generation + grading."""
    budget = _budget_for(workspace)
    prompt = ONE_SHOT_TEMPLATE.format(prompt=problem["prompt"])
    out: list[SampleResult] = []
    for i in range(n):
        messages = [{"role": "user", "content": prompt}]
        try:
            resp, elapsed = _chat_ollama(
                model_hint, messages, token_budget=budget, sampling=sampling, think=think
            )
            passed, _pytest_out, _code = score_code(resp, problem["test"])
            detail = "pass" if passed else "fail"
        except Exception as exc:  # noqa: BLE001
            passed = False
            elapsed = 0.0
            detail = f"harness_error: {exc.__class__.__name__}: {exc}"
        out.append(
            SampleResult(
                workspace=workspace,
                model_hint=model_hint,
                arm=ARM_ONESHOT,
                problem_id=problem["id"],
                sample_idx=i,
                passed=passed,
                detail=detail,
                latency_s=elapsed,
            )
        )
    return out


def run_repair(
    workspace: str,
    model_hint: str,
    problem: dict,
    *,
    n: int = REPAIR_N,
    sampling: dict | None = None,
    think: bool | None = None,
) -> list[SampleResult]:
    """n samples of one-shot; on fail, one repair attempt with pytest stderr."""
    budget = _budget_for(workspace)
    first_prompt = ONE_SHOT_TEMPLATE.format(prompt=problem["prompt"])
    out: list[SampleResult] = []
    for i in range(n):
        elapsed_total = 0.0
        try:
            # First attempt
            resp1, e1 = _chat_ollama(
                model_hint,
                [{"role": "user", "content": first_prompt}],
                token_budget=budget,
                sampling=sampling,
                think=think,
            )
            elapsed_total += e1
            passed1, pytest_out, code1 = score_code(resp1, problem["test"])
            if passed1:
                out.append(
                    SampleResult(
                        workspace=workspace,
                        model_hint=model_hint,
                        arm=ARM_REPAIR,
                        problem_id=problem["id"],
                        sample_idx=i,
                        passed=True,
                        detail="pass_first_try",
                        latency_s=elapsed_total,
                    )
                )
                continue
            # Repair attempt — model sees its own code + pytest output
            repair_prompt = REPAIR_TEMPLATE.format(
                prompt=problem["prompt"],
                prev_code=code1 if code1 else "(no code block extracted)",
                pytest_output=pytest_out,
            )
            resp2, e2 = _chat_ollama(
                model_hint,
                [{"role": "user", "content": repair_prompt}],
                token_budget=budget,
                sampling=sampling,
                think=think,
            )
            elapsed_total += e2
            passed2, _pytest_out2, _code2 = score_code(resp2, problem["test"])
            detail = "pass_after_repair" if passed2 else "fail_after_repair"
            out.append(
                SampleResult(
                    workspace=workspace,
                    model_hint=model_hint,
                    arm=ARM_REPAIR,
                    problem_id=problem["id"],
                    sample_idx=i,
                    passed=passed2,
                    detail=detail,
                    latency_s=elapsed_total,
                )
            )
        except Exception as exc:  # noqa: BLE001
            out.append(
                SampleResult(
                    workspace=workspace,
                    model_hint=model_hint,
                    arm=ARM_REPAIR,
                    problem_id=problem["id"],
                    sample_idx=i,
                    passed=False,
                    detail=f"harness_error: {exc.__class__.__name__}: {exc}",
                    latency_s=elapsed_total,
                )
            )
    return out
