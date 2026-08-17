"""bully.embedding_bench -- SA3.1 backend-agnostic embedding throughput harness.

Measures items/sec and p50/p95 latency for a fixed sample of real corpus texts
at batch {8, 32, 64, 128}, plus cold-start and resident memory, against whatever
OpenAI-compatible ``/v1/embeddings`` service is listening on the given URL.

Backend-agnostic by construction: the harness only speaks HTTP to
``/v1/embeddings`` (POST ``{"input": [texts]}`` -> ``data[i].embedding``). The
same harness drives the CPU sentence-transformers server (the SA2 incumbent),
Arm A (MLX Qwen3-Embedding), and Arm B (llama.cpp EmbeddingGemma) so the arms
are judged identically (TASK_BULLY_SA3_EMBEDDING_BAKEOFF_V1 SA3.1). It never
imports any embed runtime -- that is the point of the harness.

The embed text used is ``organ``'s canonical record text for the real
``attack_data`` parents of ``SPECIMEN_CORPUS_V2``, so the measured workload is
the same structured security-behavior tokens ``organ._embed`` sends in the real
index/knn path (signatures.semantic_query caps at 64 tokens/section).
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import organ
from .cousin_calibration_bench import corpus_parent_reference_record, load_specimen_corpus

log = logging.getLogger(__name__)

DEFAULT_BATCH_SIZES = (8, 32, 64, 128)
DEFAULT_SAMPLE_SIZE = 128
DEFAULT_REPEATS = 3


def real_corpus_embed_texts(corpus_path: Path) -> list[str]:
    """Canonical embed texts for the real ``attack_data`` parents only.

    Uses ``organ._canonical_record_text`` -- the exact string ``organ.upsert``
    embeds for a record -- so the harness measures the real workload, not a
    synthetic proxy. Never includes forge ``replay_mutation`` children or the
    ``live_lab`` row (A2).
    """
    corpus = load_specimen_corpus(corpus_path)
    texts: list[str] = []
    for specimen in corpus["specimens"]:
        if specimen["source_lane"] != "attack_data":
            continue
        record = corpus_parent_reference_record(specimen)
        text = organ._canonical_record_text(record)  # noqa: SLF001 -- same-package harness
        texts.append(text)
    return sorted(dict.fromkeys(texts), key=len)


def fixed_sample(texts: list[str], *, limit: int = DEFAULT_SAMPLE_SIZE) -> list[str]:
    """Deterministic fixed sample: the ``limit`` shortest unique texts.

    Shortest-first mirrors ``organ``'s batching (``_embedding_batches`` sorts by
    length) and is reproducible without a random seed, so every arm is measured
    on the identical payload.
    """
    return sorted(dict.fromkeys(texts), key=len)[:limit]


@dataclass(frozen=True)
class BatchMeasurement:
    batch_size: int
    batches: int
    items: int
    total_s: float
    items_per_sec: float | None
    p50_ms: float | None
    p95_ms: float | None
    min_ms: float | None
    max_ms: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BackendReport:
    embed_url: str
    model_label: str
    items_sampled: int
    batch_sizes: tuple[int, ...]
    cold_start_s: float | None
    resident_memory_mb: float | None
    batches: tuple[BatchMeasurement, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    k = (len(ordered) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1 if f + 1 < len(ordered) else f
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


def embed_latencies(
    client: Any,
    url: str,
    texts: list[str],
    *,
    batch_size: int,
    repeats: int = DEFAULT_REPEATS,
) -> tuple[float, float, float, float, float]:
    """POST the fixed sample in batches; return (total_s, p50, p95, min, max).

    ``client`` is any object with ``post(url, json=...) -> resp`` (httpx.Client
    in production; a test double in unit tests).
    """
    batched: list[list[str]] = [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]
    per_batch: list[float] = []
    total = 0.0
    for _ in range(repeats):
        for batch in batched:
            t0 = time.perf_counter()
            resp = client.post(url, json={"input": batch})
            resp.raise_for_status()
            elapsed = time.perf_counter() - t0
            per_batch.append(elapsed)
            total += elapsed
    p50 = _percentile(per_batch, 50)
    p95 = _percentile(per_batch, 95)
    return total, p50, p95, min(per_batch), max(per_batch)


def measure_backend(
    client: Any,
    *,
    embed_url: str,
    texts: list[str],
    batch_sizes: tuple[int, ...] = DEFAULT_BATCH_SIZES,
    repeats: int = DEFAULT_REPEATS,
    model_label: str = "unknown",
    cold_start_s: float | None = None,
    resident_memory_mb: float | None = None,
) -> BackendReport:
    measurements = []
    for batch_size in batch_sizes:
        total, p50, p95, lo, hi = embed_latencies(
            client, embed_url, texts, batch_size=batch_size, repeats=repeats
        )
        n_batches = (len(texts) + batch_size - 1) // batch_size * repeats
        items = len(texts) * repeats
        measurements.append(
            BatchMeasurement(
                batch_size=batch_size,
                batches=n_batches,
                items=items,
                total_s=round(total, 4),
                items_per_sec=round(items / total, 4) if total else None,
                p50_ms=round(p50 * 1000.0, 2),
                p95_ms=round(p95 * 1000.0, 2),
                min_ms=round(lo * 1000.0, 2),
                max_ms=round(hi * 1000.0, 2),
            )
        )
    return BackendReport(
        embed_url=embed_url,
        model_label=model_label,
        items_sampled=len(texts),
        batch_sizes=tuple(batch_sizes),
        cold_start_s=cold_start_s,
        resident_memory_mb=resident_memory_mb,
        batches=tuple(measurements),
    )


# ── process observability (host-native servers) ─────────────────────────────


def pid_for_port(port: int) -> int | None:
    """PID of the process listening on ``port`` (via ``lsof``), or None."""
    try:
        out = subprocess.run(
            ["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    lines = [line for line in out.splitlines() if line.strip()]
    return int(lines[0]) if lines else None


def resident_memory_mb(pid: int) -> float | None:
    """RSS of ``pid`` in MiB (macOS/Linux ``ps -o rss`` is KiB)."""
    try:
        out = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        return round(int(out.split()[0]) / 1024.0, 2)
    except (ValueError, IndexError):
        return None


def measure_cold_start(client: Any, *, health_url: str, embed_url: str) -> float:
    """Seconds from first contact until the first successful embed response.

    Includes the server's lazy model-load: the harness calls /health until it
    answers, then times the first real embed POST. Backend-agnostic; the arm
    servers load their model lazily on first request, so this captures the true
    cold-start the operator would feel.
    """
    t0 = time.perf_counter()
    for _ in range(120):
        try:
            health = client.get(health_url)
            if health.status_code == 200:
                break
        except Exception:  # noqa: BLE001 -- any transport error = not up yet
            pass
        time.sleep(0.25)
    else:
        return time.perf_counter() - t0
    resp = client.post(embed_url, json={"input": ["cold-start probe"]})
    resp.raise_for_status()
    return round(time.perf_counter() - t0, 4)


def write_report(report: BackendReport, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_json(report.to_dict()) + "\n", encoding="utf-8")
    return output_path


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=str)


# ── CLI driver ───────────────────────────────────────────────────────────────


def run_cli(argv: list[str] | None = None) -> int:
    """Backend-agnostic embedding throughput benchmark (SA3.1).

    Usage:
        uv run python -m portal.modules.security.core.bully.embedding_bench \
            --embed-url http://localhost:8917/v1/embeddings \
            --corpus /Volumes/data01/portal5_hunt/artifacts/specimen_corpus_v2/specimen_corpus_v2.json \
            --out /tmp/embed_bench_cpu.json
    """
    import argparse
    import json

    import httpx

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embed-url", default="http://localhost:8917/v1/embeddings")
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(
            "/Volumes/data01/portal5_hunt/artifacts/specimen_corpus_v2/specimen_corpus_v2.json"
        ),
    )
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--model-label", default="cpu-sentence-transformers")
    parser.add_argument("--batch-sizes", type=int, nargs="+", default=list(DEFAULT_BATCH_SIZES))
    parser.add_argument("--port", type=int, default=8917, help="port to read RSS from")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    texts = real_corpus_embed_texts(args.corpus)
    sample = fixed_sample(texts, limit=args.sample_size)
    log.info("sampled %d real-parent embed texts", len(sample))

    with httpx.Client(timeout=600.0) as client:
        cold_start = measure_cold_start(
            client,
            health_url=args.embed_url.replace("/v1/embeddings", "/health"),
            embed_url=args.embed_url,
        )
        pid = pid_for_port(args.port)
        rss = resident_memory_mb(pid) if pid is not None else None
        report = measure_backend(
            client,
            embed_url=args.embed_url,
            texts=sample,
            batch_sizes=tuple(args.batch_sizes),
            repeats=args.repeats,
            model_label=args.model_label,
            cold_start_s=cold_start,
            resident_memory_mb=rss,
        )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True, default=str))
    if args.out:
        write_report(report, args.out)
        print(f"report written: {args.out}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(run_cli())
