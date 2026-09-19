"""Prefix-sharing fan-out harness (splash / oMLX / Ollama).

PRIMARY QUESTION. `portal/modules/compliance/core/sweep.py` maps a standard's
requirements sequentially, and its docstring gives a reason that MEASUREMENT
HAS SINCE CONTRADICTED: "the prompt cache holds one slot: call N reuses the
fixed body call N-1 prefilled". PROVE_THEN_SCALE_V1 P4.1 ran exactly that
shape - twenty sequential map readings, shared body first - and measured
collapse x1.0: first call prefilled 48.7s, the remaining nineteen averaged
48.8s. The mechanism was then isolated: Ollama 0.34.2 reuses a prefix WITHIN
an append-only conversation and NOT across independent requests that merely
share one.

So the sequential loop is not buying what its docstring claims. It is neither
faster nor slower than a concurrent one would be on prefix grounds, because
there is no prefix reuse to protect - and Ollama does no continuous batching
either, so fanning out on that runner gains nothing. The loop is correct by
accident.

One slot is an Ollama property, not a law. oMLX does block-based paged KV with
prefix sharing and copy-on-write; splash ships a shared cache with a memory
plan that sizes KV capacity and batch limits for concurrent requests. The
sweep's traffic is the textbook case for both: ONE fixed standard body, then N
varying requirement tails hung off it. The question this harness answers is
therefore not "which engine is faster at n=4" but:

    Does concurrent-with-prefix-sharing beat the sequential loop on wall
    clock, WITHOUT losing a prefill collapse - on an engine that HAS one?

Both halves matter. An engine that fans out 4-wide while re-prefilling the
13.9k-token body four times has not won anything.

MEASUREMENT NOTE. `prompt_eval_count` reads the FULL prompt length on a cache
hit and cannot answer this - the last campaign established that the hard way.
`cached_tokens` is captured when an engine reports it, but it is corroboration,
not evidence: engines differ in whether and how they populate it over the
OpenAI surface. The ground truth here is TIME. On a long shared prefix, TTFT is
dominated by prefill, so warm-TTFT / cold-TTFT is the honest cache signal, and
its behaviour as concurrency rises is the whole finding.

SECONDARY. The same harness runs chat shapes (`short`, `multiturn`) so the
chat-lane question is answered alongside at near-zero extra cost. For chat,
per-stream TTFT and inter-token latency are the metrics; aggregate throughput
is the agent/sweep metric and is never the chat headline.

THIRD. Concurrency capacity on Apple silicon is a memory question. Splash
computes context, KV capacity and batch limits ONCE at startup from what Metal
recommends less the weights. Every run records its memory state; `--state`
labels it and the summarizer refuses to compare across labels.

Usage:
  # PRIMARY: sequential baseline, then the same work fanned out
  python3 tests/benchmarks/bench_engine_concurrency.py run \
      --engine ollama --model <tag> --shape fanout --mode sequential \
      --concurrency 4 --state B
  python3 tests/benchmarks/bench_engine_concurrency.py run \
      --engine splash --model incoai/Qwen3.8-27B-Splash \
      --shape fanout --mode concurrent --concurrency 1,2,4,8 --state B

  # CONTROL: the append shape Ollama DOES cache, to prove the instrument
  python3 tests/benchmarks/bench_engine_concurrency.py run \
      --engine ollama --model <tag> --shape append --mode sequential \
      --concurrency 4 --state B

  python3 tests/benchmarks/bench_engine_concurrency.py summarize \
      --results tests/benchmarks/results --state B --shape fanout
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

RESULTS_DIR = Path(__file__).parent / "results"

# All three speak OpenAI /v1/chat/completions, which is what makes one protocol
# possible. splash is reached through the host forwarder, never 127.0.0.1:8000
# directly, so the number measured is the number the pipeline would get.
ENGINES = {
    "ollama": os.environ.get("BENCH_OLLAMA_URL", "http://localhost:11434"),
    "omlx": os.environ.get("BENCH_OMLX_URL", "http://localhost:8085"),
    "splash": os.environ.get("BENCH_SPLASH_URL", "http://localhost:8086"),
}
PIPELINE_URL = os.environ.get("BENCH_PIPELINE_URL", "http://localhost:9099")

# Stand-in for a standard's fixed body. Roughly 30 tokens per repetition; the
# default body target matches the ~13.9k tokens reading_material.py assembles
# per requirement Part. Substitute the real fixed body with --body-file when
# running against the live corpus - the synthetic text is for engine mechanics,
# and a real-corpus run is the one that goes in the decision record.
_BODY_UNIT = (
    "The Responsible Entity shall implement one or more documented processes "
    "that collectively include each of the applicable requirement parts, and "
    "shall retain evidence of implementation for the full audit period. "
)

# Varying tails. Each request in a wave gets a different one, so the wave is a
# genuine fan-out over a shared prefix rather than N copies of one request,
# which any cache would trivially collapse and which would prove nothing.
_TAILS = [
    "Question: identify the obligation governing electronic access authorization, and cite the part.",
    "Question: identify the obligation governing evidence retention, and cite the part.",
    "Question: identify the obligation governing periodic review, and cite the part.",
    "Question: identify the obligation governing documented process ownership, and cite the part.",
    "Question: identify the obligation governing applicability determination, and cite the part.",
    "Question: identify the obligation governing implementation timing, and cite the part.",
    "Question: identify the obligation governing exception handling, and cite the part.",
    "Question: identify the obligation governing the audit period itself, and cite the part.",
    "Question: contrast the access and retention obligations above.",
    "Question: contrast the review and timing obligations above.",
    "Question: which obligation above is the most prescriptive, and why.",
    "Question: which obligation above admits the widest range of compliant implementations.",
    "Question: list every obligation above that names a time interval.",
    "Question: list every obligation above that names a document.",
    "Question: state which single control would satisfy the most obligations above.",
    "Question: state which obligation above would be hardest to evidence at audit.",
]

FILLER = (
    "The transmission operator shall maintain a documented process for "
    "authorizing electronic access to BES Cyber Systems, including the "
    "identification of individuals with authorized access and the periodic "
    "review of that authorization. "
)


def build_body(body_tokens: int, body_file: str | None) -> str:
    """The shared prefix. Real corpus text if given, else synthetic filler."""
    if body_file:
        return Path(body_file).read_text()
    reps = max(1, body_tokens // 30)
    return _BODY_UNIT * reps


def build_messages(shape: str, index: int, body: str) -> list[dict]:
    """`index` varies the tail so a fan-out wave is N different requests over
    one shared prefix - the sweep's actual shape."""
    if shape == "fanout":
        # Body FIRST, tail last. Prefix reuse depends entirely on the shared
        # text being a literal prefix; putting the varying part first destroys
        # it. Same reason the sweep leads with the standard body.
        return [
            {"role": "system", "content": body},
            {"role": "user", "content": _TAILS[index % len(_TAILS)]},
        ]
    if shape == "append":
        # CONTROL. The append-only conversation shape PROVE_THEN_SCALE_V1 P4.1
        # measured Ollama DOES cache (26,005 tokens prefilled in 19.5s against
        # 38.2s for 19,743). Every prior tail stays in the thread, so request N
        # is a strict extension of request N-1 rather than a sibling of it.
        # This is the instrument's positive control: an engine that reports
        # PREFIX_LOST here is not forming a prefix at all.
        msgs: list[dict] = [{"role": "system", "content": body}]
        for i in range(index):
            msgs.append({"role": "user", "content": _TAILS[i % len(_TAILS)]})
            msgs.append(
                {"role": "assistant", "content": f"Answer {i}: the governing part is cited above."}
            )
        msgs.append({"role": "user", "content": _TAILS[index % len(_TAILS)]})
        return msgs
    if shape == "short":
        return [
            {
                "role": "user",
                "content": (
                    "Explain in about 300 words how TCP congestion control "
                    "reacts differently to loss-based and delay-based signals, "
                    "and why that matters on a lossy wireless link."
                ),
            }
        ]
    if shape == "multiturn":
        msgs = []
        for i in range(6):
            msgs.append(
                {
                    "role": "user",
                    "content": f"Turn {i}: {FILLER * 12}Summarize the constraint above.",
                }
            )
            msgs.append(
                {
                    "role": "assistant",
                    "content": f"Summary {i}: access authorization must be documented and reviewed.",
                }
            )
        msgs.append(
            {
                "role": "user",
                "content": f"Now contrast turns {index % 5} and 5 and say which is stricter.",
            }
        )
        return msgs
    if shape == "long32k":
        return [{"role": "user", "content": FILLER * 1400 + "\n\n" + _TAILS[index % len(_TAILS)]}]
    raise SystemExit(f"unknown shape: {shape}")


def reasoning_payload(engine: str, reasoning: str) -> dict:
    """Same intent, three dialects. Never assume one engine's key works on another.

    splash: reasoning is on by default, disabled with "reasoning_effort": "none"
      (the 27B also takes low/medium/xhigh). portal.yaml records that Qwen3.8's
      chat template opens <think> by default and degenerates on hard compliance
      questions without this, so a splash reading run that forgets it is not
      measuring the production shape.
    ollama / omlx over /v1: chat_template_kwargs.enable_thinking is the lever.
      Ollama's /v1 surface silently drops an `options` sub-dict and a bare
      `think` field (P5-OLLAMA-OPTIONS-001), so neither is sent here.
    """
    if reasoning == "on":
        return (
            {"reasoning_effort": "medium"}
            if engine == "splash"
            else {"chat_template_kwargs": {"enable_thinking": True}}
        )
    if engine == "splash":
        return {"reasoning_effort": "none"}
    return {"chat_template_kwargs": {"enable_thinking": False}}


def memory_snapshot() -> dict:
    """A concurrency number without this is not comparable to any other."""
    out: dict = {"captured_at": datetime.now(UTC).isoformat()}
    try:
        vm = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=10).stdout
        pages: dict[str, int] = {}
        page_size = 16384
        for line in vm.splitlines():
            if "page size of" in line:
                page_size = int(line.split("page size of")[1].split("bytes")[0].strip())
            if ":" in line and "Pages" in line:
                k, _, v = line.partition(":")
                with contextlib.suppress(ValueError):
                    pages[k.strip()] = int(v.strip().rstrip("."))
        out["page_size"] = page_size
        out["pages"] = pages
        free = pages.get("Pages free", 0) + pages.get("Pages inactive", 0)
        out["approx_free_gb"] = round(free * page_size / 1024**3, 2)
    except Exception as exc:  # pragma: no cover - host probe
        out["vm_stat_error"] = str(exc)
    try:
        mp = subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=10).stdout
        for line in mp.splitlines():
            if "percentage" in line.lower():
                out["memory_pressure"] = line.strip()
    except Exception as exc:  # pragma: no cover - host probe
        out["memory_pressure_error"] = str(exc)
    resident = {}
    for name, url in ENGINES.items():
        try:
            resident[name] = httpx.get(f"{url}/v1/models", timeout=4.0).status_code == 200
        except Exception:
            resident[name] = False
    out["engines_reachable"] = resident
    return out


def one_request(
    url: str, model: str, messages: list[dict], extra: dict, max_tokens: int, timeout: float
) -> dict:
    """Stream one completion and time every token boundary."""
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "stream": True,
        "stream_options": {"include_usage": True},
        **extra,
    }
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("SPLASH_API_KEY")
    if key and ":8086" in url:
        headers["Authorization"] = f"Bearer {key}"

    stamps: list[float] = []
    text_len = 0
    usage: dict = {}
    started = time.perf_counter()
    ttft = None
    try:
        with (
            httpx.Client(timeout=timeout) as client,
            client.stream("POST", f"{url}/v1/chat/completions", json=body, headers=headers) as resp,
        ):
            if resp.status_code != 200:
                resp.read()
                return {
                    "ok": False,
                    "status": resp.status_code,
                    "error": resp.text[:400],
                    "started": started,
                    "ended": time.perf_counter(),
                }
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if chunk.get("usage"):
                    usage = chunk["usage"]
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta") or {}
                    piece = delta.get("content") or delta.get("reasoning_content") or ""
                    if piece:
                        now = time.perf_counter()
                        if ttft is None:
                            ttft = now - started
                        stamps.append(now)
                        text_len += len(piece)
    except Exception as exc:
        return {
            "ok": False,
            "status": None,
            "error": f"{type(exc).__name__}: {exc}"[:400],
            "started": started,
            "ended": time.perf_counter(),
        }

    ended = time.perf_counter()
    gaps = [b - a for a, b in zip(stamps, stamps[1:], strict=False)] if len(stamps) > 1 else []
    completion = usage.get("completion_tokens") or len(stamps)
    decode_window = (ended - started - (ttft or 0)) or 1e-9
    return {
        "ok": True,
        "started": started,
        "ended": ended,
        # TTFT on a long shared prefix is prefill-dominated. This is the cache signal.
        "ttft_s": ttft,
        "wall_s": ended - started,
        "completion_tokens": completion,
        "prompt_tokens": usage.get("prompt_tokens"),
        # Corroboration only. Engines differ in whether they populate this, and
        # prompt_eval_count-style counters read full prompt length on a hit.
        "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
        "decode_tps": completion / decode_window,
        "itl_p50_ms": round(statistics.median(gaps) * 1000, 2) if gaps else None,
        "itl_p95_ms": round(sorted(gaps)[int(len(gaps) * 0.95)] * 1000, 2)
        if len(gaps) >= 20
        else None,
        "chars": text_len,
    }


def run_wave(
    url: str,
    model: str,
    shape: str,
    body: str,
    extra: dict,
    n: int,
    mode: str,
    max_tokens: int,
    timeout: float,
) -> dict:
    """One wave of n requests over a shared prefix, either all at once or one
    after another. `sequential` reproduces the sweep's current production loop;
    `concurrent` is the proposal. Same prompts, same n - so the wall clocks are
    directly comparable, and that comparison IS the decision."""
    if mode == "sequential":
        results = [
            one_request(url, model, build_messages(shape, i, body), extra, max_tokens, timeout)
            for i in range(n)
        ]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
            futures = [
                pool.submit(
                    one_request,
                    url,
                    model,
                    build_messages(shape, i, body),
                    extra,
                    max_tokens,
                    timeout,
                )
                for i in range(n)
            ]
            results = [f.result() for f in futures]

    ok = [r for r in results if r.get("ok")]
    failed = [r for r in results if not r.get("ok")]
    wall = max(r["ended"] for r in results) - min(r["started"] for r in results)
    if not ok:
        return {
            "concurrency": n,
            "mode": mode,
            "accepted": 0,
            "failed": len(failed),
            "wall_s": round(wall, 2),
            "errors": [r.get("error") for r in failed][:4],
        }

    ttfts = [r["ttft_s"] for r in ok if r["ttft_s"] is not None]
    per_stream = [r["decode_tps"] for r in ok]
    return {
        "concurrency": n,
        "mode": mode,
        "accepted": len(ok),
        "failed": len(failed),
        "errors": [r.get("error") for r in failed][:4],
        # prefill / cache axis (the primary question on shape=fanout)
        "ttft_p50_s": round(statistics.median(ttfts), 3) if ttfts else None,
        "ttft_max_s": round(max(ttfts), 3) if ttfts else None,
        "cached_tokens_seen": [r.get("cached_tokens") for r in ok],
        "prompt_tokens_seen": [r.get("prompt_tokens") for r in ok][:4],
        # chat axis
        "per_stream_decode_tps_p50": round(statistics.median(per_stream), 2),
        "per_stream_decode_tps_min": round(min(per_stream), 2),
        "itl_p95_ms_max": max([r["itl_p95_ms"] for r in ok if r["itl_p95_ms"]], default=None),
        # throughput axis - wall_s is the one that decides the sweep
        "aggregate_tps": round(sum(r["completion_tokens"] for r in ok) / wall, 2),
        "wall_s": round(wall, 2),
        "requests": ok,
    }


def cmd_run(args: argparse.Namespace) -> int:
    url = PIPELINE_URL if args.via == "pipeline" else ENGINES[args.engine]
    extra = reasoning_payload(args.engine, args.reasoning)
    body = (
        build_body(args.body_tokens, args.body_file) if args.shape in ("fanout", "append") else ""
    )
    ladder = [int(x) for x in args.concurrency.split(",")]

    record = {
        "schema": "engine_concurrency_v2",
        "engine": args.engine,
        "via": args.via,
        "url": url,
        "model": args.model,
        "shape": args.shape,
        "mode": args.mode,
        "reasoning": args.reasoning,
        "state": args.state,
        "body_tokens_target": args.body_tokens if args.shape in ("fanout", "append") else None,
        "body_file": args.body_file,
        "body_chars": len(body),
        "max_tokens": args.max_tokens,
        "rounds": args.rounds,
        "started_at": datetime.now(UTC).isoformat(),
        "memory_before": memory_snapshot(),
        "waves": [],
    }

    print(f"[warm] {args.engine} via {args.via} -> {url}", flush=True)
    warm = one_request(url, args.model, build_messages("short", 0, ""), extra, 32, args.timeout)
    record["warmup_ok"] = warm.get("ok")
    if not warm.get("ok"):
        record["warmup_error"] = warm.get("error")
        print(f"[warm] FAILED: {warm.get('error')}", flush=True)

    # Cold prefill reference. One request carrying the full shared body against
    # a cache that has not seen it. Every later TTFT is read against this, and
    # the ratio is the prefix-reuse evidence.
    if args.shape in ("fanout", "append"):
        print("[cold] single request establishing the shared prefix", flush=True)
        cold = one_request(
            url,
            args.model,
            build_messages(args.shape, 0, body),
            extra,
            args.max_tokens,
            args.timeout,
        )
        record["cold_prefill"] = {
            "ok": cold.get("ok"),
            "ttft_s": round(cold["ttft_s"], 3) if cold.get("ok") and cold.get("ttft_s") else None,
            "prompt_tokens": cold.get("prompt_tokens"),
            "cached_tokens": cold.get("cached_tokens"),
            "error": cold.get("error"),
        }
        print(
            f"[cold] ttft={record['cold_prefill']['ttft_s']}s prompt_tokens={cold.get('prompt_tokens')}",
            flush=True,
        )

    for n in ladder:
        for r in range(args.rounds):
            print(
                f"[run] shape={args.shape} mode={args.mode} n={n} round={r + 1}/{args.rounds}",
                flush=True,
            )
            wave = run_wave(
                url,
                args.model,
                args.shape,
                body,
                extra,
                n,
                args.mode,
                args.max_tokens,
                args.timeout,
            )
            wave["round"] = r
            for req in wave.get("requests", []):
                req.pop("started", None)
                req.pop("ended", None)
            record["waves"].append(wave)
            time.sleep(args.settle)

    record["memory_after"] = memory_snapshot()
    record["finished_at"] = datetime.now(UTC).isoformat()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = (
        RESULTS_DIR
        / f"engconc_{args.engine}_{args.via}_{args.shape}_{args.mode}_{args.reasoning}_state{args.state}_{stamp}.json"
    )
    out.write_text(json.dumps(record, indent=2))
    print(f"[done] {out}")
    return 0


def _load(results: str, state: str, shape: str) -> list[dict]:
    runs = []
    for f in sorted(Path(results).glob("engconc_*.json")):
        try:
            rec = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        if rec.get("schema") != "engine_concurrency_v2":
            continue
        if rec.get("state") == state and rec.get("shape") == shape:
            runs.append(rec)
    return runs


def _collect(runs: list[dict]) -> tuple[dict[str, dict[str, dict[int, dict]]], dict[str, float]]:
    """Fold runs into arm -> mode -> concurrency -> metric lists, plus the
    best cold-prefill TTFT per arm."""
    table: dict[str, dict[str, dict[int, dict]]] = {}
    cold: dict[str, float] = {}
    for rec in runs:
        arm = f"{rec['engine']}/{rec['via']}/{rec['reasoning']}"
        cp = (rec.get("cold_prefill") or {}).get("ttft_s")
        if cp:
            cold[arm] = min(cold.get(arm, cp), cp)
        for wave in rec["waves"]:
            if not wave.get("accepted"):
                continue
            slot = (
                table.setdefault(arm, {})
                .setdefault(wave.get("mode", rec["mode"]), {})
                .setdefault(
                    wave["concurrency"],
                    {"ttft": [], "per": [], "agg": [], "wall": [], "acc": [], "cached": []},
                )
            )
            if wave.get("ttft_p50_s") is not None:
                slot["ttft"].append(wave["ttft_p50_s"])
            slot["per"].append(wave["per_stream_decode_tps_p50"])
            slot["agg"].append(wave["aggregate_tps"])
            slot["wall"].append(wave["wall_s"])
            slot["acc"].append(wave["accepted"] / wave["concurrency"])
            slot["cached"].extend([c for c in (wave.get("cached_tokens_seen") or []) if c])
    return table, cold


def _print_table(state: str, shape: str, table: dict[str, dict[str, dict[int, dict]]]) -> None:
    print(f"\nstate={state} shape={shape}")
    print(
        f"{'arm':30s} {'mode':11s} {'n':>3s} {'wall_s':>8s} {'ttft_p50':>9s} {'per_tps':>8s} {'agg_tps':>8s} {'accept':>7s}"
    )
    for arm in sorted(table):
        for mode in sorted(table[arm]):
            for n in sorted(table[arm][mode]):
                s = table[arm][mode][n]
                t = statistics.median(s["ttft"]) if s["ttft"] else float("nan")
                print(
                    f"{arm:30s} {mode:11s} {n:3d} {statistics.median(s['wall']):8.1f} {t:9.3f} "
                    f"{statistics.median(s['per']):8.2f} {statistics.median(s['agg']):8.2f} {statistics.median(s['acc']):7.2f}"
                )


def _gate_prefix(table: dict[str, dict[str, dict[int, dict]]], cold: dict[str, float]) -> None:
    # GATE 1 - does a prefill collapse exist, and does it survive
    # concurrency? Read warm TTFT under load against the cold
    # single-request prefill. A hit collapses TTFT; re-prefills do not.
    print("\n-- prefix reuse under load (warm TTFT / cold prefill TTFT) --")
    for arm in sorted(table):
        base = cold.get(arm)
        if not base:
            print(f"  {arm}: NO_COLD_REFERENCE")
            continue
        for mode in sorted(table[arm]):
            for n in sorted(table[arm][mode]):
                s = table[arm][mode][n]
                if not s["ttft"]:
                    continue
                ratio = statistics.median(s["ttft"]) / base
                verdict = (
                    "PREFIX_REUSED"
                    if ratio <= 0.35
                    else ("PARTIAL" if ratio <= 0.70 else "PREFIX_LOST")
                )
                seen = f" cached_tokens_reported={len(s['cached'])}" if s["cached"] else ""
                print(f"  {arm} {mode} n={n}: x{ratio:.2f} {verdict}{seen}")


def _gate_fanout(table: dict[str, dict[str, dict[int, dict]]]) -> None:
    # GATE 2 - does fanning out actually finish the work sooner? Same arm,
    # same n, concurrent wall vs sequential wall. This is the number that
    # decides whether sweep.py's loop should change.
    print("\n-- fan-out vs sequential (same arm, same n, wall clock) --")
    for arm in sorted(table):
        modes = table[arm]
        if "sequential" not in modes or "concurrent" not in modes:
            print(f"  {arm}: NEEDS_BOTH_MODES")
            continue
        for n in sorted(set(modes["sequential"]) & set(modes["concurrent"])):
            if n < 2:
                continue
            seq = statistics.median(modes["sequential"][n]["wall"])
            con = statistics.median(modes["concurrent"][n]["wall"])
            speedup = seq / con if con else float("nan")
            flag = (
                "FANOUT_WINS"
                if speedup >= 1.50
                else ("MARGINAL" if speedup >= 1.15 else "FANOUT_NO_WIN")
            )
            print(
                f"  {arm} n={n}: sequential {seq:.1f}s vs concurrent {con:.1f}s = x{speedup:.2f} {flag}"
            )


def _gate_margin(table: dict[str, dict[str, dict[int, dict]]]) -> None:
    print("\n-- engine margin, concurrent wall clock at n=4 --")
    for arm in sorted(table):
        if (
            not arm.startswith("splash/")
            or "concurrent" not in table[arm]
            or 4 not in table[arm]["concurrent"]
        ):
            continue
        tail = arm.split("/", 1)[1]
        mine = statistics.median(table[arm]["concurrent"][4]["wall"])
        for rival in ("omlx", "ollama"):
            other = f"{rival}/{tail}"
            if other in table and "concurrent" in table[other] and 4 in table[other]["concurrent"]:
                theirs = statistics.median(table[other]["concurrent"][4]["wall"])
                ratio = theirs / mine if mine else float("nan")
                flag = "WIN" if ratio >= 1.50 else ("MARGINAL" if ratio >= 1.15 else "NO_WIN")
                print(f"  splash vs {rival} [{tail}]: x{ratio:.2f} {flag}")


def _gate_chat(table: dict[str, dict[str, dict[int, dict]]]) -> None:
    # Chat gate - per-stream responsiveness at n=4 against the same arm alone.
    print("\n-- chat gate (n=4 vs n=1, same arm, concurrent) --")
    for arm in sorted(table):
        con = table[arm].get("concurrent", {})
        if 1 not in con or 4 not in con or not con[1]["ttft"] or not con[4]["ttft"]:
            continue
        ttft_infl = statistics.median(con[4]["ttft"]) / statistics.median(con[1]["ttft"])
        decode_hold = statistics.median(con[4]["per"]) / statistics.median(con[1]["per"])
        verdict = (
            "CHAT_CONCURRENCY_HOLDS"
            if (ttft_infl <= 1.25 and decode_hold >= 0.70)
            else "CHAT_CONCURRENCY_DEGRADES"
        )
        print(f"  {arm}: {verdict} (ttft x{ttft_infl:.2f}, per-stream decode x{decode_hold:.2f})")


def cmd_summarize(args: argparse.Namespace) -> int:
    """Apply the stated thresholds. Refuses to mix memory states."""
    runs = _load(args.results, args.state, args.shape)
    if not runs:
        print(f"NO_DATA state={args.state} shape={args.shape}")
        return 1

    table, cold = _collect(runs)
    _print_table(args.state, args.shape, table)
    if args.shape in ("fanout", "append"):
        _gate_prefix(table, cold)
        _gate_fanout(table)
        _gate_margin(table)
    else:
        _gate_chat(table)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("--engine", choices=sorted(ENGINES), required=True)
    r.add_argument("--via", choices=["direct", "pipeline"], default="direct")
    r.add_argument(
        "--model", required=True, help="engine-native model id, or workspace id when --via pipeline"
    )
    r.add_argument(
        "--shape", choices=["fanout", "append", "short", "multiturn", "long32k"], default="fanout"
    )
    r.add_argument("--mode", choices=["concurrent", "sequential"], default="concurrent")
    r.add_argument("--reasoning", choices=["on", "off"], default="off")
    r.add_argument("--concurrency", default="1,2,4,8")
    r.add_argument("--rounds", type=int, default=3)
    r.add_argument(
        "--body-tokens",
        dest="body_tokens",
        type=int,
        default=13900,
        help="shared-prefix size for shape=fanout|append",
    )
    r.add_argument(
        "--body-file",
        dest="body_file",
        default=None,
        help="real fixed-body text file (preferred for the record)",
    )
    r.add_argument("--max-tokens", dest="max_tokens", type=int, default=400)
    r.add_argument("--timeout", type=float, default=900.0)
    r.add_argument(
        "--settle", type=float, default=10.0, help="seconds between waves, for Metal reclaim"
    )
    r.add_argument(
        "--state",
        required=True,
        help="memory-state label, e.g. A (dedicated) or B (production steady-state)",
    )
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("summarize")
    s.add_argument("--results", default=str(RESULTS_DIR))
    s.add_argument("--state", required=True)
    s.add_argument("--shape", default="fanout")
    s.set_defaults(func=cmd_summarize)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
