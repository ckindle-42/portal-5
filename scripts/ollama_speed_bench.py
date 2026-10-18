#!/usr/bin/env python3
"""Measure an Ollama model's prefill and decode speed on a given host.

For each requested prompt size, builds a deterministic filler prompt (estimated
at 4 characters per token), sends one non-streaming ``POST /api/chat`` request
with ``options.num_predict: 128``, and reports prompt tokens, prefill tok/s,
decode tok/s and load seconds from the Ollama response (durations are ns).

Standard library only. Exit status is non-zero if any request failed, naming
the failed size(s).

Usage:
    uv run python scripts/ollama_speed_bench.py --model qwen3.8:27b --sizes 2000,8000,32000
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

#: Estimated characters per token, used to size the filler prompt.
CHARS_PER_TOKEN = 4

#: Fixed decode length (tokens) for every benchmark request.
NUM_PREDICT = 128

_NS_PER_S = 1_000_000_000

_COLUMNS = ("size", "prompt", "prefill tok/s", "decode tok/s", "load s")


def build_filler_prompt(n_tokens: int) -> str:
    """Return a deterministic filler prompt of ``n_tokens * CHARS_PER_TOKEN`` chars.

    A fixed repeated word keeps the prompt (and thus the measurement)
    reproducible from run to run.
    """
    if n_tokens < 1:
        raise ValueError("n_tokens must be at least 1")
    base = n_tokens * CHARS_PER_TOKEN
    word = "bench fill "
    return (word * (base // len(word) + 1))[:base]


def speed_metrics(data: dict) -> dict:
    """Compute prefill/decode tok/s and load seconds from an ``/api/chat`` response.

    Durations are nanoseconds; a missing or zero counter/duration yields 0.0
    rather than a division error.
    """

    def per_second(count: object, ns: object) -> float:
        c = int(count or 0)
        d = int(ns or 0)
        return c / (d / _NS_PER_S) if c and d else 0.0

    return {
        "prompt_tokens": int(data.get("prompt_eval_count") or 0),
        "prefill_tps": per_second(data.get("prompt_eval_count"), data.get("prompt_eval_duration")),
        "decode_tps": per_second(data.get("eval_count"), data.get("eval_duration")),
        "load_seconds": int(data.get("load_duration") or 0) / _NS_PER_S,
    }


def request_chat(host: str, model: str, prompt: str, timeout: float = 600.0) -> dict:
    """Send one non-streaming chat completion to ``host`` and return the JSON body."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_predict": NUM_PREDICT},
    }
    req = urllib.request.Request(
        host.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def format_table(rows: list[dict]) -> str:
    """Render one aligned table row per measured size."""
    cells = [
        [
            str(row["size_tokens"]),
            str(row["prompt_tokens"]),
            f"{row['prefill_tps']:.1f}",
            f"{row['decode_tps']:.1f}",
            f"{row['load_seconds']:.3f}",
        ]
        for row in rows
    ]
    widths = [len(header) for header in _COLUMNS]
    for row in cells:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    lines = ["  ".join(h.ljust(w) for h, w in zip(_COLUMNS, widths, strict=True))]
    lines.extend("  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)) for row in cells)
    return "\n".join(lines)


def run_bench(host: str, model: str, sizes: list[int], out: str | None = None) -> int:
    """Benchmark every size; print the table; return 0 on success, 1 on any failure."""
    rows: list[dict] = []
    failures: list[str] = []
    for size in sizes:
        prompt = build_filler_prompt(size)
        try:
            data = request_chat(host, model, prompt)
        except (OSError, ValueError) as exc:
            failures.append(f"FAILED size {size} tokens: {exc}")
            continue
        rows.append({"size_tokens": size, **speed_metrics(data)})

    if rows:
        print(format_table(rows))
    for message in failures:
        print(message, file=sys.stderr)

    if out is not None:
        report = {"host": host, "model": model, "results": rows, "failures": failures}
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
            f.write("\n")
    return 1 if failures else 0


def parse_sizes(spec: str) -> list[int]:
    """Parse a comma-separated list of positive prompt sizes."""
    try:
        sizes = [int(part) for part in spec.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--sizes must be positive integers, got {spec!r}"
        ) from exc
    if not sizes or any(s <= 0 for s in sizes):
        raise argparse.ArgumentTypeError(
            "--sizes must be a comma-separated list of positive integers"
        )
    return sizes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure an Ollama model's prefill and decode tok/s on a given host."
    )
    parser.add_argument(
        "--host",
        default="http://localhost:11434",
        help="Ollama base URL (default: %(default)s)",
    )
    parser.add_argument("--model", required=True, help="Ollama model name/tag")
    parser.add_argument(
        "--sizes",
        type=parse_sizes,
        default=[2000, 8000, 32000],
        help="Comma-separated prompt sizes in tokens (default: 2000,8000,32000)",
    )
    parser.add_argument(
        "--out", default=None, help="Optional path to write the JSON results report"
    )
    args = parser.parse_args(argv)
    return run_bench(args.host, args.model, args.sizes, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
