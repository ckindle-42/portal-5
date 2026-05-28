# TASK: OMLX v0.3.10 Re-Evaluation — Full Bake-off + MTP Side-Car Probe

**Task ID:** TASK_OMLX_REEVAL_V2
**Version target:** v7.0.x patch (probe-only; promotion or further investigation are separate tasks)
**Priority:** Normal — unblocks investigation of P5-FUT-013 (RETIRED 2026-04-25), P5-FUT-SPEC (BLOCKED), P5-MTP-001 (LOW)
**Category:** Research probe — full re-evaluation against new release
**Protected files touched:** None (`scripts/`, `tests/benchmarks/`, `OMLX_DECISION.md`, `KNOWN_LIMITATIONS.md`, `P5_ROADMAP.md`)
**Repo HEAD at audit time:** `d579f88` (2026-05-27)
**Estimated risk:** Low — probe-only. mlx-proxy retains production inference role throughout. Installation is isolated to a separate Homebrew tap; full uninstall is one command.

---

## Why this task exists

`OMLX_DECISION.md` (dated 2026-04-25) recorded **RETIRE** based on a
bake-off against oMLX **v0.3.8.dev2**. Four findings drove the decision:

1. KV cache not working (warm TTFT 31% slower than cold)
2. Cannot load 22 GB Qwen3-Coder-30B with 36 GB free (memory accounting bug)
3. Marginal concurrency benefit (1.9× on 3B only)
4. TPS ~equivalent (mlx-proxy 4-5% faster on small models)

In the four weeks since, oMLX shipped **v0.3.8, v0.3.9, and v0.3.10**.
Release notes explicitly address three of the four findings:

| 2026-04-25 finding | v0.3.10 release-notes evidence |
|---|---|
| KV cache not working | v0.3.8: *"Fix attention dilution on RotatingKVCache SSD restore for sliding-window models. Old restore zero-padded the buffer to max_size, leaking zero positions into attention via softmax. New PrefillReadyRotatingKVCache subclass clamps size() by actual buffer length, and SSD cache format bumped to v2."* — this is exactly the bug class that would produce warm-slower-than-cold behavior. |
| Cannot load 22 GB model on 36 GB free | v0.3.10: *"OOM under sustained load: OMLX_MAX_PROCESS_MEMORY wasn't actually being enforced on batched / VLM engines, and finished requests piled up KV caches in an unbounded SSD-write queue. The two together could push memory past the cap and get the server killed. Both are fixed, and inflight load now scales with memory pressure."* |
| Marginal concurrency | v0.3.8: mlx-vlm bumped to e41cd25 picking up native continuous batching. v0.3.9: PoolingCache / BatchPoolingCache ported. |
| TPS equivalent | Explicitly unchanged. Maintainer states: *"oMLX is tuned for agent workloads with shared context, not single-shot benchmark wins. Cache snapshotting and BatchGenerator add a few percent overhead, and the slightly higher latency vs other engines is expected."* This is acknowledged design tradeoff. |

**Net-new in v0.3.9 beyond bug fixes:**

- **Native MTP support** via `ml-explore/mlx-lm#990` (the same AirRunner
  PR Portal 5's `P5_ROADMAP.md` identifies as the unblock path for
  `P5-FUT-SPEC`).
- Pre-converted MTP variants published by the maintainer at
  `huggingface.co/Jundot` (`Qwen3.6-27B-oQ8-mtp` 30 GB and the 35B-A3B
  MoE variant).

**This task is a full re-evaluation, not narrow probe.** The
2026-04-25 decision measured the right three dimensions (TPS, KV-cache
TTFT, concurrent throughput) against the wrong version. Re-running all
three against v0.3.10 plus adding the new MTP dimension gives a complete
picture in one pass. Narrowing to MTP-only would leave Portal 5 in the
same epistemic position as the canceled bake-off if MTP fails — the
other v0.3.10 fixes might still warrant a different kind of integration
(KV-cache side-car for tools-specialist, for example) that a one-dimensional
probe cannot detect.

---

## What this task is NOT

To prevent scope creep:

- ❌ **Replace mlx-proxy.** mlx-proxy retains the production inference
  role for every Portal 5 workspace throughout this task.
- ❌ **Add oMLX to `launch.sh` as a default-started service.** The probe
  starts oMLX manually for the measurement run and tears it down (or
  leaves it idle) after.
- ❌ **Migrate any existing workspace to dispatch through oMLX.** The
  probe measures TPS / TTFT / concurrent throughput on models loaded
  directly in oMLX; zero `portal_pipeline` or `workspace_routing` changes.
- ❌ **Two-server single-model coexistence (P5-MLX-010).** Probe phases
  run sequentially, not concurrently. mlx-proxy and oMLX both hold
  models only when explicitly tested; otherwise one is idle.
- ❌ **Multi-output-size MTP scan beyond 3 sizes.** Three sizes
  (short / medium / long) are sufficient to characterize the MTP overhead
  curve. More sizes is a follow-up probe, not this one.

---

## Architecture decisions enumerated

| ID | Decision |
|----|----------|
| O1 | **Side-car, not primary.** oMLX runs on port 8085 (matches prior bake-off). mlx-proxy stays on 8081. No portal_pipeline routing change. |
| O2 | **Four test dimensions, one probe run.** TPS (single-shot), KV-cache TTFT (5-turn warm/cold), concurrent throughput (4 workers), MTP speedup (3 output sizes × MTP-on/off). Dimensions 1–3 reuse the existing `bench_omlx.py` bake-off scaffold; dimension 4 is new. |
| O3 | **MTP target: `Jundot/Qwen3.6-27B-oQ8-mtp` (~30 GB).** 8-bit dense, MTP-capable, pre-converted by the oMLX maintainer. The 4-bit Jundot variant (`oQ4`, ~16.7 GB) does NOT have MTP weights — only the `-mtp`-suffixed variants do — so 4-bit MTP is not an option on this maintainer's HF org. 35B-A3B MoE MTP variant is a stretch target if dense probe succeeds with margin. |
| O4 | **MTP comparison baseline: `mlx-community/Qwen3.6-27B-4bit` on mlx-proxy.** This is the production-fleet bench-qwen36-27b entry. NOT apples-to-apples on quantization (4-bit vs 8-bit), but IS what production would actually run. The probe captures the *practical* speedup, not the isolated MTP speedup. The Observations section below interprets the 4-vs-8-bit confound. |
| O5 | **Temperature 0, deterministic prompts** for MTP cells. Spec-dec speedup is highest at temp=0 because draft tokens accept more often. Matches the P5-FUT-SPEC gate threshold (≥1.5× at temp=0). |
| O6 | **Three output sizes for MTP characterization:** 128 (short), 512 (medium), 2048 (long) tokens. MTP overhead is fixed per request; benefit grows with output length. A single size measurement would obscure the relationship. |
| O7 | **Re-use the existing `tests/benchmarks/bench_omlx.py` scaffold.** It has working httpx clients, isolation logic (METAL_RECLAIM_WAIT, `_evict_mlx`, `_wait_mlx_memory`), JSON output format, KV cache 5-turn test, TPS test, concurrent test. Add an `--mode` flag where `bakeoff` (existing) and `mtp` (new) are the two choices. Default to running both. |
| O8 | **Hardware floor: macOS 15.0+ (Sequoia).** Confirmed required by oMLX v0.3.10 README. Verify in pre-flight. |
| O9 | **Decision is multi-dimensional, not binary.** Outcome is mapped via the decision matrix in O-8 below. A single yes/no on MTP would lose information about the other three dimensions. |
| O10 | **All outputs persist to `tests/benchmarks/results/`** with the timestamp pattern matching `bench_omlx.py` and `bench_tps.py`. |
| O11 | **No `portal_pipeline` or `portal_mcp` imports.** The probe script remains standalone (httpx + stdlib + yaml only). |
| O12 | **Existing 4-week-old results files preserved.** Don't delete the 2026-04-25 result JSONs. They are evidence of the original decision and remain referenced from `OMLX_DECISION.md`. |
| O13 | **Conditional cleanup.** Gate failure → uninstall oMLX, delete MTP model. Gate ambiguous → keep oMLX installed for follow-on probes; document explicitly. Gate success → keep installed; write promotion-task skeleton. |

---

## Task index

| # | Task | Files | Risk | Verify |
|---|------|-------|------|--------|
| O-1 | Verify host requirements (macOS 15+, free RAM, free disk, mlx-proxy idle). | (verify only) | None | Outputs of `sw_vers`, `vm_stat`, `df`, `curl /health` recorded in run log. |
| O-2 | Install oMLX v0.3.10+ via Homebrew. | (system install — not committed) | Low | `omlx --version` reports ≥ 0.3.10. |
| O-3 | Configure model discovery (symlink HF cache). Pull MTP target model. | `~/.omlx/settings.json` (system, not repo) | Low | `curl :8085/v1/models` lists `Qwen3.6-27B-oQ8-mtp` AND `Qwen3.6-27B-4bit` AND smaller models that were available at original bake-off. |
| O-4 | Smoke-test both endpoints with the test models. Verify MTP enable knob actually works. | (verify only) | Low | Control and treatment calls both return HTTP 200; treatment shows reduced tokens-per-step in oMLX log. |
| O-5 | Extend `tests/benchmarks/bench_omlx.py` with `--mode mtp` and `--mode all` (bake-off + MTP). | `tests/benchmarks/bench_omlx.py` | Low | Existing modes still work; new mode passes `--dry-run` plan check. |
| O-6 | Run the full re-evaluation. Capture results JSON. | (run only — outputs to `tests/benchmarks/results/`) | Low | Result JSON has ≥4 sections (kv_cache, tps, concurrent, mtp); ~25-40 measurements depending on flags. |
| O-7 | Parse results, write a structured analysis Markdown with the four mandatory judgment questions answered. | `tests/benchmarks/results/omlx_reeval_<ts>.md` (new) | None | All four observation questions answered explicitly; decision matrix cell selected. |
| O-8 | Apply the decision matrix. Pick exactly one cell. Document. | `OMLX_DECISION.md` (append section) | None | New "Re-evaluation 2026-05-XX" section appended; old section preserved. |
| O-9 | Update `P5_ROADMAP.md` for affected items (P5-FUT-013, P5-FUT-SPEC, P5-MTP-001, possibly new follow-on items). | `P5_ROADMAP.md` (edit) | None | All three items have dated update notes. |
| O-10 | Conditional cleanup per the matrix outcome. | (system + optional new task skeleton file) | None | Either oMLX uninstalled cleanly OR follow-on task skeleton committed. |
| O-11 | Commit script change, results, analysis, doc updates. | git | None | `git tag v7.0.x-omlx-reeval` exists; commit shows the expected file set. |

Files actually committed: 5-7 (`tests/benchmarks/bench_omlx.py`,
`tests/benchmarks/results/omlx_reeval_*.json`,
`tests/benchmarks/results/omlx_reeval_*.md`, `OMLX_DECISION.md`,
`P5_ROADMAP.md`, optionally `KNOWN_LIMITATIONS.md`, optionally a
follow-on task skeleton).

---

## Pre-flight checklist (O-1)

Run BEFORE installing anything. If any check fails, stop and report — do
not proceed past O-2.

```bash
# 1. macOS version (oMLX requires 15.0+)
sw_vers
# Expected: ProductVersion: 15.x.y or higher
# If on macOS 14 or earlier: STOP. File a prerequisite task to upgrade
# macOS, or downgrade this task's priority. oMLX v0.3.10 will not run.

# 2. Apple Silicon confirmation
uname -m
# Expected: arm64

# 3. Free RAM check (need ~35 GB free for oMLX to load 30 GB model + headroom)
sysctl hw.memsize  # 64 GB on M4 Pro
vm_stat | head -5
# Free + inactive + speculative pages × pagesize gives effective free.
# Need ≥35 GB. If <35 GB free, restart Mac before bake-off begins.

# 4. Free disk on models volume
df -h /Volumes/data01
# Expected: ≥60 GB free
# Breakdown: 30 GB MTP model + ~20 GB SSD KV cache budget + 10 GB headroom.

# 5. mlx-proxy running and idle
curl -sf http://localhost:8081/health | python3 -m json.tool
# Expected: state = "none" or "ready". loaded_model should be null or
# a small model. If a 30-46 GB model is loaded, evict it first:
#   curl -X POST http://localhost:8081/evict

# 6. Confirm baseline model already pulled
ls -la /Volumes/data01/models/mlx-community/Qwen3.6-27B-4bit/ 2>/dev/null \
  || ls -la ~/.cache/huggingface/hub/models--mlx-community--Qwen3.6-27B-4bit/ 2>/dev/null
# If not present, the V7 model refresh task either hasn't landed or
# the pull was skipped. Run:
#   ./launch.sh pull-mlx-models
# (Qwen3.6-27B-4bit is already in MLX_MODELS array.)

# 7. Confirm the smaller bakeoff models from the prior run are still on disk
for m in mlx-community/Llama-3.2-3B-Instruct-8bit \
         mlx-community/phi-4-8bit \
         mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit; do
    echo -n "$m: "
    if ls -d ~/.cache/huggingface/hub/models--${m//\//--} 2>/dev/null > /dev/null; then
        echo "present"
    else
        echo "MISSING — bakeoff dimension on this model will be skipped"
    fi
done

# 8. Stack idle check
curl -s http://localhost:8081/health | python3 -c "import json,sys; d=json.load(sys.stdin); print('Loaded model:', d.get('loaded_model'))"
# If a model is loaded and other work is in flight, defer this task.
# The bake-off needs exclusive use of MLX memory for ~60-90 min.

# 9. Git state clean
git status
# Should be on a known branch. Untracked OMLX/bench result files are fine.
```

**Pre-flight pass criterion:** Items 1, 2, 5, 6, 8 must pass. Item 7
informs the matrix-of-models in O-6 (any missing model gets `available:
false` in the result). Item 9 is enforced for commit hygiene at O-11.

---

## Safety gate

```bash
git tag pre-omlx-reeval-v2
```

---

## Per-task detail

### O-2 — Install oMLX v0.3.10+ via Homebrew

Portal 5's convention for host-native services is **Homebrew + manual
service control** (mirroring ollama, ComfyUI, embedding service).
Match it.

```bash
# Tap the maintainer's repo (separate tap, isolated from any other taps)
brew tap jundot/omlx https://github.com/jundot/omlx
brew install omlx

# Verify version — must be ≥ 0.3.10 to have the OOM + memory-accounting fixes
omlx --version
# Expected: omlx 0.3.10 or later
# If lower: brew update && brew upgrade omlx
```

**If `brew install` fails:**

- Python version error → confirm `python3 --version` ≥ 3.10. If on 3.9
  or older, this task is blocked on Python upgrade. File a prerequisite
  task and stop.
- Network error during tap → check `git ls-remote https://github.com/jundot/omlx`.
  If GitHub unreachable, retry later.
- Conflicting Python deps via Homebrew → use the source-install fallback:
  ```bash
  python3 -m venv /Volumes/data01/omlx-venv
  source /Volumes/data01/omlx-venv/bin/activate
  pip install --upgrade pip
  pip install "git+https://github.com/jundot/omlx.git@v0.3.10"
  ```
  Note: source install means no `brew services` integration; manual
  start only. Document this in the results notes.

**Do NOT run `brew services start omlx`.** The probe starts oMLX
manually in O-3 to capture clean startup logs. Service-managed startup
makes log collection harder.

### O-3 — Configure oMLX and pull the MTP target

oMLX discovers models from `~/.omlx/models/` by default. Portal 5 stores
models at `~/.cache/huggingface/hub/` (HF cache) and selectively at
`/Volumes/data01/models/`. Rather than duplicate ~50 GB of weights,
symlink the HF cache.

```bash
# Create oMLX model dir, symlink HF cache
mkdir -p "${HOME}/.omlx/models"
ln -sf "${HOME}/.cache/huggingface/hub" "${HOME}/.omlx/models/hf-cache"

# Pull the MTP target (~30 GB, 10-30 min depending on bandwidth)
huggingface-cli download Jundot/Qwen3.6-27B-oQ8-mtp \
    --local-dir "${HOME}/.omlx/models/Qwen3.6-27B-oQ8-mtp"

# Verify the model has its MTP weights (-mtp suffix == MTP-capable)
ls "${HOME}/.omlx/models/Qwen3.6-27B-oQ8-mtp/" | grep -iE "mtp|spec"
# If no MTP-related files visible, the maintainer's packaging may have
# inlined them — confirm by checking config.json for a "multi_token_predict"
# or "mtp_heads" or similar key. If absent, file an issue and stop.
python3 -c "
import json
cfg = json.load(open('${HOME}/.omlx/models/Qwen3.6-27B-oQ8-mtp/config.json'))
print('Model type:', cfg.get('model_type'))
print('MTP-related keys:', [k for k in cfg.keys() if 'mtp' in k.lower() or 'spec' in k.lower() or 'pred' in k.lower()])
"

# Start oMLX manually with verbose output
omlx serve \
    --model-dir "${HOME}/.omlx/models" \
    --port 8085 \
    2>&1 | tee "/tmp/omlx-reeval-$(date -u +%Y%m%dT%H%M%SZ).log" &
OMLX_PID=$!
echo "oMLX PID: $OMLX_PID (to stop: kill $OMLX_PID)"

# Wait for startup (oMLX needs ~30s to scan models + warm up)
sleep 30
curl -s http://localhost:8085/v1/models | python3 -m json.tool | head -40
# Expected: data array contains entries for Qwen3.6-27B-oQ8-mtp,
# Qwen3.6-27B-4bit, and any other models in HF cache.
```

If model discovery fails — most likely cause is symlink not followed by
oMLX's scanner. Workaround: copy model dirs directly into
`~/.omlx/models/` instead of symlinking the parent cache. Or set
`OMLX_MODEL_DIR` env var to the actual HF cache path.

### O-4 — Smoke test both endpoints

Before the timed run, prove both servers respond correctly under the
exact request shapes the bake-off will use.

```bash
# Smoke 1: oMLX serves the MTP model with MTP DISABLED (control)
# The exact MTP-disable knob in oMLX v0.3.10 needs verification — see
# Open Questions section below. Most likely:
#   extra_body.speculative_decoding = "off"  OR  "none"
# OR oMLX requires the non-MTP variant for control: Jundot/Qwen3.6-27B-oQ8
# (no -mtp suffix). Confirm at task execution time.
curl -s -X POST http://localhost:8085/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "Qwen3.6-27B-oQ8-mtp",
        "messages": [{"role": "user", "content": "Write a haiku about an ocean."}],
        "max_tokens": 64,
        "temperature": 0,
        "extra_body": {"speculative_decoding": "off"}
    }' | python3 -m json.tool

# Smoke 2: oMLX serves the MTP model with MTP ENABLED (treatment)
curl -s -X POST http://localhost:8085/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "Qwen3.6-27B-oQ8-mtp",
        "messages": [{"role": "user", "content": "Write a haiku about an ocean."}],
        "max_tokens": 64,
        "temperature": 0,
        "extra_body": {"speculative_decoding": "mtp"}
    }' | python3 -m json.tool

# Smoke 3: mlx-proxy serves the production 4-bit baseline
curl -s -X POST http://localhost:8081/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "mlx-community/Qwen3.6-27B-4bit",
        "messages": [{"role": "user", "content": "Write a haiku about an ocean."}],
        "max_tokens": 64,
        "temperature": 0
    }' | python3 -m json.tool

# Verify MTP actually engaged — look in the oMLX log tail for keywords
tail -50 /tmp/omlx-reeval-*.log | grep -iE "mtp|spec|draft|accept"
# Expected output mentioning "MTP", "speculative", "draft tokens", or
# "acceptance rate". If none appear when MTP was enabled, MTP did NOT
# engage — verify the API surface before proceeding.
```

**Pass criterion:** All three smoke calls return HTTP 200 with non-empty
content. The MTP-on call shows MTP engagement in the oMLX log. If
control and treatment produce identical output at temp=0 (lossless
speculative decoding), that is the expected behavior and confirms MTP
correctness.

**If MTP cannot be enabled** because the API surface differs from this
task's assumption: STOP. Update this task file with the verified API
surface, get re-approval, then resume. Do NOT improvise undocumented
parameters.

### O-5 — Extend `tests/benchmarks/bench_omlx.py`

Add an MTP probe alongside the existing bake-off. The existing scaffold
already covers TPS, KV-cache TTFT, and concurrent throughput.

**Insertion 1**: New constants at the top of the file, after the existing
`SINGLE_PROMPTS` block:

```python
# ── MTP Probe constants (added by TASK_OMLX_REEVAL_V2) ────────────────────────

MTP_MODEL = "Qwen3.6-27B-oQ8-mtp"
MTP_BASELINE_4BIT = "mlx-community/Qwen3.6-27B-4bit"

# MTP probe output-size cells. MTP overhead is per-request fixed; benefit
# grows with output length. Three sizes characterize the curve.
MTP_SIZES = [
    {"label": "short",  "max_tokens": 128},
    {"label": "medium", "max_tokens": 512},
    {"label": "long",   "max_tokens": 2048},
]

# Deterministic prompt that produces predictable output length and avoids
# early-stop. Avoid creative prompts (variable length defeats fixed-budget
# comparison).
MTP_PROMPT = (
    "Write a Python function that computes the Fibonacci sequence up to N=100 "
    "using both recursion and memoization. Then explain each line of both "
    "implementations in detail. Cover every variable, every operation, time "
    "complexity, and space complexity. Do not abbreviate the explanation; "
    "fill the response budget."
)

# Promotion gate (per P5_ROADMAP P5-FUT-SPEC)
MTP_GATE_SPEEDUP = 1.5
```

**Insertion 2**: New function `bench_mtp(args)` after the existing
`run_endpoint` function. Skeleton:

```python
def bench_mtp(args) -> list[dict]:
    """MTP speculative-decoding probe.

    For each output size, runs three conditions:
      - omlx_control:   oMLX, MTP-model, MTP disabled
      - omlx_mtp:       oMLX, MTP-model, MTP enabled
      - mlx_proxy_4bit: mlx-proxy, 4-bit base (production baseline)

    Returns one result dict per (size, condition) cell with TPS, elapsed,
    TTFT, output token count, output prefix (200 chars) for quality contamination
    check, and full request/response context for auditing.
    """
    results: list[dict] = []
    if args.dry_run:
        print("\n  MTP probe plan:")
        for size in MTP_SIZES:
            print(f"    size={size['label']} max_tokens={size['max_tokens']}")
            print(f"      - oMLX control (no MTP) on {MTP_MODEL}")
            print(f"      - oMLX treatment (MTP on) on {MTP_MODEL}")
            print(f"      - mlx-proxy baseline 4bit on {MTP_BASELINE_4BIT}")
        return results

    for size in MTP_SIZES:
        print(f"\n  MTP cell — size={size['label']} max_tokens={size['max_tokens']}")

        # Condition 1: oMLX, MTP DISABLED
        print("    [1/3] oMLX control (MTP off) ...", end=" ", flush=True)
        r = _timed_mtp_call(OMLX_URL, MTP_MODEL, size["max_tokens"],
                            mtp_mode="off")
        r.update({"size": size["label"], "condition": "omlx_control",
                  "model": MTP_MODEL, "endpoint": "omlx"})
        results.append(r)
        _short_cooldown(10)

        # Condition 2: oMLX, MTP ENABLED
        print("    [2/3] oMLX treatment (MTP on)  ...", end=" ", flush=True)
        r = _timed_mtp_call(OMLX_URL, MTP_MODEL, size["max_tokens"],
                            mtp_mode="mtp")
        r.update({"size": size["label"], "condition": "omlx_mtp",
                  "model": MTP_MODEL, "endpoint": "omlx"})
        results.append(r)
        _short_cooldown(10)

        # Condition 3: mlx-proxy, 4-bit baseline
        print("    [3/3] mlx-proxy 4-bit baseline ...", end=" ", flush=True)
        r = _timed_mtp_call(MLX_PROXY_URL, MTP_BASELINE_4BIT,
                            size["max_tokens"], mtp_mode=None)
        r.update({"size": size["label"], "condition": "mlx_proxy_4bit",
                  "model": MTP_BASELINE_4BIT, "endpoint": "mlx-proxy"})
        results.append(r)
        # Larger cooldown before next size — model switch coming
        _short_cooldown(30)

    return results


def _timed_mtp_call(url: str, model: str, max_tokens: int,
                    mtp_mode: str | None) -> dict:
    """Single timed chat completion. Returns TPS, elapsed, TTFT proxy, output meta.

    mtp_mode:
      None  — no extra_body (mlx-proxy)
      "off" — extra_body={"speculative_decoding": "off"} (oMLX control)
      "mtp" — extra_body={"speculative_decoding": "mtp"} (oMLX treatment)
    """
    payload: dict = {
        "model": model,
        "messages": [{"role": "user", "content": MTP_PROMPT}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": False,
    }
    if mtp_mode is not None:
        payload["extra_body"] = {"speculative_decoding": mtp_mode}

    t0 = time.time()
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as c:
            resp = c.post(f"{url}/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
        t1 = time.time()
    except Exception as e:
        print(f"FAIL: {e}")
        return {"available": False, "error": str(e), "tps": 0.0,
                "elapsed_s": round(time.time() - t0, 2)}

    elapsed = t1 - t0
    out_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = data.get("usage", {}) or {}
    out_tokens = usage.get("completion_tokens") or max(1, len(out_text) // 4)
    tps = out_tokens / elapsed if elapsed > 0 else 0.0
    print(f"{tps:.1f} t/s ({out_tokens} tok, {elapsed:.1f}s)")

    return {
        "available": True,
        "tps": round(tps, 2),
        "elapsed_s": round(elapsed, 2),
        "output_tokens": out_tokens,
        "output_chars": len(out_text),
        # First 200 chars captured for quality-contamination cross-check:
        # if condition outputs differ meaningfully at temp=0, the speedup
        # measurement is contaminated by quality drift, not pure speedup.
        "output_prefix": out_text[:200],
        "completion_tokens_reported": "completion_tokens" in usage,
    }


def _short_cooldown(seconds: int) -> None:
    print(f"    (cooldown {seconds}s)")
    time.sleep(seconds)
```

**Insertion 3**: Update the argparse block to accept `--mode`:

```python
    parser.add_argument(
        "--mode",
        choices=["bakeoff", "mtp", "all"],
        default="all",
        help="bakeoff: original P5-FUT-013 dimensions (TPS+KV+concurrent). "
             "mtp: new MTP speculative-decoding probe only. "
             "all: bakeoff + mtp (default; recommended for full re-eval).",
    )
```

**Insertion 4**: Update `main()` to dispatch by mode. The existing
bake-off flow currently runs unconditionally. Wrap it:

```python
    # Existing flow (kv_cache + tps + concurrent) — gate behind mode
    if args.mode in ("bakeoff", "all"):
        if not args.omlx_only:
            mlx_results = run_endpoint(MLX_PROXY_URL, "mlx-proxy", models, args)
            all_results.extend(mlx_results)

        if not args.omlx_only and not args.mlx_only and not args.dry_run:
            print(f"\n  Switching endpoints — Metal reclaim wait ...", end=" ", flush=True)
            _evict_mlx(SMALLEST_MLX)
            _wait_mlx_memory(30.0, timeout_s=90.0)
            time.sleep(METAL_RECLAIM_WAIT)
            print("ok")

        if not args.mlx_only:
            omlx_results = run_endpoint(OMLX_URL, "omlx", models, args)
            all_results.extend(omlx_results)

    # New flow (MTP probe) — gate behind mode
    if args.mode in ("mtp", "all"):
        # MTP probe needs both endpoints; ignore --mlx-only / --omlx-only
        # for this phase (it requires both by design).
        print("\n" + "=" * 70)
        print("MTP Probe (TASK_OMLX_REEVAL_V2)")
        print("=" * 70)
        mtp_results = bench_mtp(args)
        all_results.extend(mtp_results)
```

**Insertion 5**: Output file name reflects whether this is a full re-eval
or partial run. Find the existing `out_path = RESULTS_DIR / f"omlx_bakeoff_{ts}.json"`
line and update:

```python
    suffix = {
        "bakeoff": "bakeoff",
        "mtp": "mtp",
        "all": "reeval",
    }[args.mode]
    out_path = RESULTS_DIR / f"omlx_{suffix}_{ts}.json"
```

**Verify O-5**:

```bash
# Dry-run for the new mode
python3 tests/benchmarks/bench_omlx.py --mode mtp --dry-run
# Expected: prints 3-size × 3-condition matrix.

python3 tests/benchmarks/bench_omlx.py --mode all --dry-run
# Expected: prints bakeoff plan + MTP plan.

python3 tests/benchmarks/bench_omlx.py --mode bakeoff --dry-run
# Expected: existing behavior unchanged.

# Syntax check
python3 -c "import sys; sys.path.insert(0, 'tests/benchmarks'); import bench_omlx; print('OK')"

# Ruff
ruff check tests/benchmarks/bench_omlx.py
ruff format --check tests/benchmarks/bench_omlx.py
```

**Rollback O-5**: `git checkout tests/benchmarks/bench_omlx.py`

### O-6 — Run the re-evaluation

```bash
# Confirm both servers still up
curl -sf http://localhost:8085/v1/models > /dev/null && echo "oMLX OK" || { echo "RESTART OMLX"; exit 1; }
curl -sf http://localhost:8081/health > /dev/null && echo "mlx-proxy OK" || { echo "RESTART mlx-proxy"; exit 1; }

# Pre-warm 4-bit baseline on mlx-proxy (otherwise first measurement pays cold-load)
curl -s -X POST http://localhost:8081/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model": "mlx-community/Qwen3.6-27B-4bit",
         "messages": [{"role": "user", "content": "warmup"}],
         "max_tokens": 8, "temperature": 0}' > /dev/null
sleep 5

# Run the full re-evaluation. Estimated wall-clock:
#   bakeoff phase: 40-60 min (matches original P5-FUT-013 cost)
#   MTP phase:      15-25 min (9 cells × ~90s avg + cooldowns)
#   Total:         55-85 min
python3 tests/benchmarks/bench_omlx.py --mode all 2>&1 \
    | tee /tmp/omlx-reeval-run-$(date -u +%Y%m%dT%H%M%SZ).log

# Confirm result file landed
ls -la tests/benchmarks/results/omlx_reeval_*.json | tail -1
```

**Failure handling during the run** (this is unchanged from V1, listed
here for the executing agent's reference):

- **oMLX crashes mid-bake-off** → record the crash log tail. This is
  itself a finding about v0.3.10 stability on M4 Pro 64 GB. The decision
  matrix has a cell for it.
- **mlx-proxy 503 (admission control rejection)** → likely oMLX
  consuming memory simultaneously. Solution: stop oMLX between phases
  (`pkill -f "omlx serve"`), let memory reclaim 60s, restart oMLX before
  the MTP phase. Record this as an operational note.
- **Empty MTP-on output** → v0.3.10 release notes explicitly fix the
  "OpenClaw/Codex empty replies" case (#1348). If still occurring at
  v0.3.10, file an oMLX issue with the request payload, note in results,
  and gate decision treats this as MTP-failure-on-M4-Pro.
- **MTP-on TPS is LOWER than MTP-off** → not a script bug; can happen
  if MTP draft acceptance rate is poor on the prompt + model + temp
  combination. Record and proceed. The decision matrix handles this case.
- **Output length much shorter than max_tokens** → model hit a stop
  token early. Re-run with a stop-suppressing prompt addition or accept
  shorter outputs and record. Don't pad results with synthetic data.

### O-7 — Write the analysis Markdown

After O-6, write `tests/benchmarks/results/omlx_reeval_<ts>.md` (matching
timestamp). The analysis is structured with **mandatory judgment
questions**, not free-form prose. The executing agent MUST answer each
explicitly.

Template:

````markdown
# OMLX v0.3.10 Re-Evaluation — Results

**Date:** YYYY-MM-DD
**Task:** TASK_OMLX_REEVAL_V2
**Predecessor:** TASK_OMLX_BAKEOFF_FULL (P5-FUT-013, 2026-04-25, RETIRE outcome)
**oMLX version under test:** <captured from `omlx --version`>
**Hardware:** M4 Pro Mac Mini, 64 GB unified, macOS <version>
**Results JSON:** tests/benchmarks/results/omlx_reeval_<ts>.json
**Run log:** /tmp/omlx-reeval-run-<ts>.log (not committed)

## TL;DR

<One sentence summarizing the decision-matrix outcome, e.g.,
"oMLX v0.3.10 fixes the KV-cache and memory-accounting bugs but MTP
speedup did not clear the 1.5× gate on M4 Pro 64 GB; recommend DEFER on
MTP and PROBE-AGAIN on KV-cache TTFT for tools-specialist workspace."
or
"oMLX v0.3.10 PASSES on all four dimensions; recommend writing
TASK_OMLX_MTP_PROMOTE_V1.md and a separate TASK_OMLX_KV_SIDECAR_V1.md.">

## Headline numbers

| Dimension | 2026-04-25 (v0.3.8.dev2) | This run (v0.3.10) | Verdict |
|---|---|---|---|
| TPS — Llama-3.2-3B | mlx-proxy 37.5, omlx 37.7 | ?? | <unchanged / improved / worse> |
| TPS — Qwen3-Coder-30B | omlx OOM (failed) | ?? | <fixed / still fails> |
| KV-cache warm TTFT | omlx WORSE than cold (+31%) | ?? | <fixed / still broken> |
| Concurrent throughput | omlx 1.9× on 3B only | ?? | <better / same / worse> |
| MTP speedup (NEW) | n/a | ?? | <≥1.5× PASS / <1.5× FAIL> |

## Required Judgment Questions

The executing agent MUST answer each of these explicitly. "Inconclusive"
is an acceptable answer with reasoning. Hand-waving is not.

### Q1: Did warm TTFT beat cold this time? (The original cancel-trigger)

<Look at the KV-cache test results. Pull the warm and cold TTFT for each
model. State whether warm beats cold and by what margin. If still
warm-slower-than-cold, this contradicts v0.3.8 release notes and warrants
filing an oMLX issue with the request shape used.>

Per-model comparison:
- Llama-3.2-3B: cold ??s, warm ??s, delta ??%
- phi-4: cold ??s, warm ??s, delta ??%
- Qwen3-Coder-30B-A3B: cold ??s, warm ??s, delta ??%

Interpretation: <one paragraph>

### Q2: Did the 22 GB Qwen3-Coder-30B model load this time?

<This is the v0.3.10 OMLX_MAX_PROCESS_MEMORY fix. Either the model
loaded and produced TPS, or it didn't. Record clearly. If it loaded,
note free memory before and after the load — the new "inflight load
scales with memory pressure" behavior should be observable.>

Free memory before load: ?? GB
Free memory after load: ?? GB
Model loaded successfully: <yes / no>
If yes: TPS = ?? on coding prompt
If no: error mode = <OOM / hang / 503 / other>

### Q3: Did MTP produce ≥1.5× TPS speedup at temp=0?

<Look at the omlx_mtp condition vs omlx_control condition. State
absolute TPS for each size, ratio of treatment/control, and whether
the ≥1.5× gate is met at any size, all sizes, or no sizes.>

| Size | Control TPS | MTP TPS | Speedup ratio | ≥1.5× gate |
|---|---|---|---|---|
| short  | ?? | ?? | ??× | PASS / FAIL |
| medium | ?? | ?? | ??× | PASS / FAIL |
| long   | ?? | ?? | ??× | PASS / FAIL |

Also compare against the **production fleet 4-bit baseline** (different
quantization than MTP target — captures the practical decision):

| Size | mlx-proxy 4-bit TPS | oMLX MTP TPS | Practical speedup |
|---|---|---|---|
| short  | ?? | ?? | ??× |
| medium | ?? | ?? | ??× |
| long   | ?? | ?? | ??× |

Quality contamination check: do the `output_prefix` values for each
condition match at temp=0? If they diverge by more than the first 1-2
tokens, the comparison is contaminated by quality drift, not pure
speedup. Note explicitly.

### Q4: Did concurrent throughput improve on models that fit?

<v0.3.8.dev2 only showed concurrency benefit on 3B. v0.3.9 added
PoolingCache / BatchPoolingCache. Check whether the 14 GB phi-4 model
now shows >1.5× speedup under 4 concurrent workers.>

| Model | Serial elapsed | Concurrent elapsed | Speedup |
|---|---|---|---|
| Llama-3.2-3B | ?? | ?? | ??× |
| phi-4 (14 GB) | ?? | ?? | ??× |
| Qwen3-Coder-30B-A3B (22 GB) | ?? | ?? | ??× |

### Q5: Did oMLX crash, hang, or produce malformed outputs at any point?

<Stability is a first-class outcome. List every error, every timeout,
every retry. Bake-off cost in wall-clock time for crashes/restarts.
A "fast and correct" outcome at higher numerics still loses to a
"slower but stable" baseline if instability blocks production use.>

Crashes during run: <count, summary>
Timeouts (REQUEST_TIMEOUT exceeded): <count, summary>
Empty outputs: <count, summary>
Server restarts required: <count>

## Decision Matrix

The four-dimensional outcome maps to one of seven cells. Pick exactly one.

| TPS | KV-cache | Concurrent | MTP | → Decision |
|---|---|---|---|---|
| equiv/lower | works | better | ≥1.5× | **PROMOTE_FULL** — oMLX becomes MTP side-car, write TASK_OMLX_MTP_PROMOTE_V1.md, schedule KV-side-car probe |
| equiv/lower | works | better | <1.5× | **PROMOTE_KV** — oMLX becomes a KV-cache side-car for tools-specialist only, write TASK_OMLX_KV_SIDECAR_V1.md, defer MTP per gate |
| equiv/lower | works | same/worse | ≥1.5× | **PROMOTE_MTP** — oMLX side-car for MTP models only, write TASK_OMLX_MTP_PROMOTE_V1.md |
| equiv/lower | broken | any | ≥1.5× | **PROBE_AGAIN_NARROWLY** — MTP only, no KV reliance; small follow-on task to confirm MTP stability over 100+ requests before promote |
| equiv/lower | broken | same/worse | <1.5× | **DEFER** — update OMLX_DECISION.md noting v0.3.10 fixed memory but not KV/MTP-on-M4-Pro; close P5-MTP-001 again; oMLX uninstalled |
| any | any | any | ANY (with crashes) | **DEFER_STABILITY** — instability blocks integration regardless of dimensional wins; file oMLX issues; re-evaluate at next release |
| stable + all fixed + MTP big win | — | — | — | **REOPEN_FULL_BAKEOFF** — the dimensions warrant a full P5-FUT-013-v2 evaluation against current production, separate task |

### Selected cell: <NAME>

### Rationale

<Two to four sentences justifying the cell selection against the
recorded data above. This is the load-bearing paragraph of the analysis
— Chris reads this and acts on it.>

## Limitations

- Single measurement per cell in MTP phase. Variance unknown. Production
  promotion would require N≥3 with median.
- 4-bit vs 8-bit-MTP base model is not an apples-to-apples MTP isolation.
  The 8-bit non-MTP MLX equivalent of Qwen3.6-27B (if published) would
  tighten the test. The `Jundot/Qwen3.6-27B-oQ4` exists but does NOT
  carry MTP weights — only `-mtp`-suffixed Jundot variants do.
- macOS Sequoia (15.x) required for oMLX. Untested on macOS 14 because
  oMLX won't run there.
- M4 Pro 64 GB only. M3 Ultra 512 GB results published by the oMLX
  maintainer are not transferable. The Ultra has 800 GB/s memory
  bandwidth vs M4 Pro's 273 GB/s — a 3× gap that disproportionately
  affects MoE decode and large-prompt prefill.
- One run, one day, one hardware unit. If the result is borderline,
  schedule a follow-on run at a different time of day to account for
  thermal variation.
- 4-bit was deliberately skipped in this probe. The Jundot oQ4 variant
  is non-MTP, and the production-fleet 4-bit baseline is already
  captured. Adding 4-bit MTP would require waiting for the maintainer
  to publish a `-mtp` variant at 4-bit, which doesn't exist as of audit.

## Decision

<One paragraph. PROMOTE_FULL / PROMOTE_KV / PROMOTE_MTP / DEFER /
DEFER_STABILITY / PROBE_AGAIN_NARROWLY / REOPEN_FULL_BAKEOFF — exactly
one. State the next task to write (or "no follow-on").>
````

### O-8 — Update `OMLX_DECISION.md`

**APPEND** a new section. Do NOT modify the existing 2026-04-25 section.

```markdown

---

## Re-evaluation 2026-05-XX (TASK_OMLX_REEVAL_V2)

**Trigger:** oMLX v0.3.10 release notes claim fixes for three of the
four findings that drove the 2026-04-25 RETIRE decision
(RotatingKVCache attention dilution, OMLX_MAX_PROCESS_MEMORY enforcement,
OOM under sustained load). Native MTP support shipped in v0.3.9 via
ml-explore/mlx-lm PR #990 — the same unblock path P5_ROADMAP P5-FUT-SPEC
was waiting on.

**Scope:** Full four-dimensional re-evaluation (TPS, KV-cache TTFT,
concurrent throughput, MTP speedup) using the existing bench_omlx.py
scaffold from the 2026-04-25 run, extended with a new MTP probe mode.

**Versions tested:**
- oMLX: v0.3.10 (vs v0.3.8.dev2 in original run)
- mlx-proxy: unchanged from original run
- Portal 5: v7.0.x (vs v6.x at original run)

**Results files:**
- `tests/benchmarks/results/omlx_reeval_<ts>.json`
- `tests/benchmarks/results/omlx_reeval_<ts>.md` (analysis)

**Headline:** <COPY THE TL;DR FROM THE .md FILE>

**Decision matrix cell:** <COPY FROM THE .md FILE>

**Disposition of production inference:** UNCHANGED. mlx-proxy remains
the primary inference server. <If PROMOTE_*: oMLX runs as a side-car on
:8085 for the scope defined in the corresponding promotion task. If
DEFER / DEFER_STABILITY / PROBE_AGAIN: oMLX <uninstalled / left idle for
follow-up probe> per O-10.>

**Open items moved or closed:**
- P5-FUT-013: <stays RETIRED / reopened / superseded>
- P5-FUT-SPEC: <BLOCKED / UNBLOCKED via oMLX / unchanged>
- P5-MTP-001: <LOW / MEDIUM / HIGH / closed>
- <Any new follow-on P5-FUT-* item>
```

### O-9 — Update `P5_ROADMAP.md`

For each of P5-FUT-013, P5-FUT-SPEC, P5-MTP-001, append a dated
sub-bullet that points to the re-evaluation and states the priority
change (if any). Example for the FAIL/DEFER case:

```markdown
### P5-FUT-013: OMLX Migration

[existing content preserved]

**Update 2026-05-XX (TASK_OMLX_REEVAL_V2):** oMLX v0.3.10 full
re-evaluation completed. Result: <decision cell name>. Status: REMAINS
RETIRED. See OMLX_DECISION.md "Re-evaluation 2026-05-XX" section and
`tests/benchmarks/results/omlx_reeval_<ts>.md` for detail. Next
re-evaluation trigger: oMLX v0.4.x major release OR Mac Studio
hardware tier (128 GB+).

### P5-FUT-SPEC: Speculative Decoding

[existing content preserved]

**Update 2026-05-XX (TASK_OMLX_REEVAL_V2):** MTP via oMLX v0.3.10
probed. Result: <speedup ratio range>; gate <PASS/FAIL>. <If PASS:
Path C unblocked via oMLX MTP side-car; TASK_OMLX_MTP_PROMOTE_V1.md
written. If FAIL: P5-FUT-SPEC remains BLOCKED on Path A (mlx-lm PR #990
in upstream mlx-lm) or Path B (dflash-mlx).>

### P5-MTP-001: Multi-Token Prediction

[existing content preserved]

**Update 2026-05-XX (TASK_OMLX_REEVAL_V2):** <If MTP gate PASS:
priority promoted from LOW to MEDIUM; integration design in
TASK_OMLX_MTP_PROMOTE_V1.md. If FAIL: confirmed LOW; speed gain on
M4 Pro 64 GB does not clear the production-promotion gate.>
```

### O-10 — Conditional cleanup

**Cell == PROMOTE_FULL / PROMOTE_KV / PROMOTE_MTP**:

```bash
# Leave oMLX installed; it stays as a side-car candidate.
# Write the appropriate promotion task skeleton.

cat > TASK_OMLX_MTP_PROMOTE_V1.md << 'EOF'  # only if PROMOTE_FULL or PROMOTE_MTP
# TASK: OMLX MTP Side-Car Promotion (SKELETON)

**Predecessor:** TASK_OMLX_REEVAL_V2 (decision cell: PROMOTE_*)
**Status:** SKELETON — design before execution

## Scope
Integrate oMLX v0.3.10 as a side-car on :8085 for MTP-bearing models.
mlx-proxy on :8081 retains primary inference.

## Design questions to resolve
1. Workspace scope: start with one (auto-coding) or roll out incrementally?
2. Memory accounting: combined budget across both inference servers must
   not exceed M4 Pro 64 GB minus OS overhead minus Docker.
3. launch.sh: oMLX brought up alongside mlx-proxy; healthcheck cadence;
   crash-restart policy. Mirror embedding service pattern (/scripts/embedding-server.py).
4. Failover: if oMLX is down, dispatch falls back to mlx-proxy with the
   non-MTP variant. portal_pipeline router needs the non-MTP fallback
   hint per workspace entry.
5. Storage: avoid duplicate model pulls. Decide between (a) symlink HF
   cache (current probe approach) or (b) extending launch.sh
   pull-mlx-models with MTP-variant awareness.

## Out of scope
- Replacing mlx-proxy.
- oMLX serving any non-MTP model. The 2026-04-25 and 2026-05-XX evals
  both show mlx-proxy ≥ oMLX on TPS for non-MTP inference.
EOF

cat > TASK_OMLX_KV_SIDECAR_V1.md << 'EOF'  # only if PROMOTE_FULL or PROMOTE_KV
# TASK: OMLX KV-Cache Side-Car for tools-specialist (SKELETON)

**Predecessor:** TASK_OMLX_REEVAL_V2 (decision cell: PROMOTE_FULL or PROMOTE_KV)
**Status:** SKELETON — design before execution

## Scope
Route tools-specialist workspace dispatch through oMLX on :8085
specifically to exploit its prefix-reuse KV cache for agentic-coding
traffic. Other workspaces stay on mlx-proxy.

## Design questions
1. Does ToolACE-2.5 benefit measurably from prefix reuse in actual
   tools-specialist traffic, vs the synthetic 5-turn test? Need real-world
   trace replay.
2. Routing: portal_pipeline gets a new backend type or an endpoint
   override on the tools-specialist workspace entry?
3. KV cache directory: where on disk, how large the budget, eviction
   policy. Defaults are likely fine but worth confirming on M4 Pro.

## Out of scope
- KV-cache routing for any non-agentic workspace.
- Replacing mlx-proxy primary role.
EOF
```

**Cell == DEFER**:

```bash
# Stop oMLX
pkill -f "omlx serve" || true
brew services stop omlx 2>/dev/null || true

# Uninstall oMLX cleanly
brew uninstall omlx
brew untap jundot/omlx

# Free the 30 GB MTP model (keep the production 4-bit model — it's used
# by Portal 5's bench-qwen36-27b workspace)
rm -rf "${HOME}/.omlx/models/Qwen3.6-27B-oQ8-mtp"

# Remove the symlink and empty parent dir
rm -f "${HOME}/.omlx/models/hf-cache"
rmdir "${HOME}/.omlx/models" 2>/dev/null || true
rmdir "${HOME}/.omlx" 2>/dev/null || true

echo "oMLX uninstalled. ~30 GB freed. mlx-proxy continues as primary inference."
```

**Cell == DEFER_STABILITY**:

Same as DEFER, plus update `KNOWN_LIMITATIONS.md` with a new entry:

```markdown
- **oMLX (jundot/omlx) on M4 Pro 64 GB**: v0.3.10 evaluation showed
  instability under <describe the failure pattern>. See OMLX_DECISION.md
  "Re-evaluation 2026-05-XX" and `tests/benchmarks/results/omlx_reeval_<ts>.md`.
  Re-evaluate at next major release (v0.4.x) or upon Mac Studio
  hardware-tier upgrade. Do not propose as inference-stack component
  in the interim.
```

**Cell == PROBE_AGAIN_NARROWLY**:

```bash
# Leave oMLX installed but stopped. Don't write a promote skeleton yet —
# the next task is a stability sub-probe.

pkill -f "omlx serve" || true

cat > TASK_OMLX_MTP_STABILITY_V1.md << 'EOF'
# TASK: OMLX MTP Stability Probe (SKELETON)

**Predecessor:** TASK_OMLX_REEVAL_V2 (decision cell: PROBE_AGAIN_NARROWLY)
**Status:** SKELETON — design before execution

## Scope
MTP-only sub-probe: 100+ sequential requests at long output size
through oMLX with MTP enabled, recording every error, every timeout,
every output anomaly. The single-shot v2 run showed MTP gain but did
not exercise sustained load.

## Pass criterion
≥98% successful response rate AND no oMLX crashes over 100 requests
AND maintained MTP speedup (no degradation in last 25 requests vs first 25).
EOF
```

**Cell == REOPEN_FULL_BAKEOFF**:

This is the unlikely-but-possible case where all four dimensions improve
substantially and the original P5-FUT-013 retire decision warrants
reconsideration in full. Write `TASK_OMLX_BAKEOFF_V2.md` skeleton with
methodology equivalent to `TASK_OMLX_BAKEOFF_FULL.md` (which is in the
repo at the top level) but against v0.3.10. This is a meaningfully
larger task than this probe and gets its own roadmap entry.

### O-11 — Commit

```bash
# Final verification before commit
ruff check tests/benchmarks/bench_omlx.py
ruff format --check tests/benchmarks/bench_omlx.py
pytest tests/unit/ -q --tb=short  # no regressions in unrelated test files

# Stage everything
git add tests/benchmarks/bench_omlx.py \
        tests/benchmarks/results/omlx_reeval_*.json \
        tests/benchmarks/results/omlx_reeval_*.md \
        OMLX_DECISION.md \
        P5_ROADMAP.md

# Conditional adds based on cell
[ -f TASK_OMLX_MTP_PROMOTE_V1.md ] && git add TASK_OMLX_MTP_PROMOTE_V1.md
[ -f TASK_OMLX_KV_SIDECAR_V1.md ] && git add TASK_OMLX_KV_SIDECAR_V1.md
[ -f TASK_OMLX_MTP_STABILITY_V1.md ] && git add TASK_OMLX_MTP_STABILITY_V1.md
[ -f TASK_OMLX_BAKEOFF_V2.md ] && git add TASK_OMLX_BAKEOFF_V2.md

# KNOWN_LIMITATIONS update only for DEFER_STABILITY
git diff --quiet KNOWN_LIMITATIONS.md || git add KNOWN_LIMITATIONS.md

git commit -m "probe(omlx): v0.3.10 full re-evaluation against P5-FUT-013

oMLX v0.3.10 release notes claim fixes for three of the four findings
that drove the 2026-04-25 RETIRE decision: RotatingKVCache attention
dilution (v0.3.8), OMLX_MAX_PROCESS_MEMORY enforcement on batched/VLM
engines (v0.3.10), OOM under sustained load (v0.3.10). Native MTP
support shipped in v0.3.9 via mlx-lm PR #990.

This task re-evaluated all four dimensions on M4 Pro 64 GB:
  1. TPS (single-shot, 3 models, 3 runs each)
  2. KV-cache warm/cold TTFT (5-turn conversation, 3 rounds)
  3. Concurrent throughput (4 workers, same models)
  4. MTP speedup at temp=0 (3 output sizes, Jundot/Qwen3.6-27B-oQ8-mtp)

Outcome: <decision cell>. See OMLX_DECISION.md Re-evaluation 2026-05-XX
section and tests/benchmarks/results/omlx_reeval_*.md for full analysis.

mlx-proxy retains production inference role throughout this probe. No
workspace_routing, persona, or portal_pipeline change."

git tag v7.0.x-omlx-reeval
```

---

## Post-milestone success indicators

After this task lands, all should hold:

1. `tests/benchmarks/results/omlx_reeval_<ts>.json` exists with all four dimensions captured (kv_cache, tps, concurrent, mtp sections).
2. `tests/benchmarks/results/omlx_reeval_<ts>.md` exists with all five required judgment questions explicitly answered and a decision-matrix cell selected.
3. `OMLX_DECISION.md` has a new "Re-evaluation 2026-05-XX" section appended; the 2026-04-25 section is preserved verbatim.
4. `P5_ROADMAP.md` has dated update bullets on P5-FUT-013, P5-FUT-SPEC, P5-MTP-001.
5. Cell-specific artifact present: promotion-task skeleton(s), stability-probe skeleton, full-bake-off-v2 skeleton, or KNOWN_LIMITATIONS update — depending on cell.
6. mlx-proxy still on :8081, serving production. No portal_pipeline or workspace_routing change.
7. **If DEFER / DEFER_STABILITY**: `brew list | grep omlx` empty; `~/.omlx/` removed or contains only `hf-cache` symlink; the 30 GB MTP model is deleted.
8. **If any PROMOTE_***: oMLX still installed via Homebrew; MTP model still on disk; promotion-task skeleton committed.
9. `pytest tests/ -q` passes. No regressions to unrelated tests.
10. `ruff check tests/benchmarks/bench_omlx.py` and `ruff format --check tests/benchmarks/bench_omlx.py` clean.
11. `git log --oneline -3` shows the probe commit and tag `v7.0.x-omlx-reeval`.

If any of (1)-(11) fail, roll back via:

```bash
git reset --hard pre-omlx-reeval-v2
git tag -d pre-omlx-reeval-v2 v7.0.x-omlx-reeval 2>/dev/null
# Plus the conditional cleanup steps from O-10 if oMLX was installed.
```

---

## Open questions to resolve at task execution time

These are flagged for the executing agent. The author of this task could
not verify them without an actual oMLX install — they are assumptions
that should be validated, not facts.

1. **Exact MTP enable knob for oMLX v0.3.10's OpenAI endpoint.** This task
   assumes `extra_body.speculative_decoding = "mtp"` and `"off"` for
   control. Verify against `https://github.com/jundot/omlx` README /
   docs at task execution time. If the actual surface is `extra_body.mtp = true`
   or a per-model config file flag or auto-enable-by-suffix-only,
   adjust O-4 and O-5 accordingly. **Do not improvise undocumented
   flags.**

2. **Whether `Jundot/Qwen3.6-27B-oQ8-mtp` auto-enables MTP by suffix
   and cannot be disabled at request level.** If MTP is enabled by
   model rather than request, the control measurement on this exact
   model becomes impossible. Fallback: use `Jundot/Qwen3.6-27B-oQ8`
   (no -mtp suffix; same maintainer, same quantization, no MTP weights)
   as the control. Pull this as a contingency in O-3 if storage permits.
   *Note: I could not confirm an oQ8 non-MTP variant exists at this
   maintainer; if it doesn't, the control falls back to the
   `Jundot/Qwen3.6-27B-oQ4` 4-bit non-MTP variant, with an explicit
   note that the comparison conflates MTP with quantization.*

3. **Whether oMLX exposes `usage.completion_tokens`** in its OpenAI-shaped
   responses. The probe uses this for TPS calculation. Fallback to
   `len(content) / 4` already coded; not blocking.

4. **Memory contention if both mlx-proxy and oMLX hold 16+ GB models
   concurrently during the MTP cell sequence.** The MTP cell uses
   ~30 GB on oMLX (the MTP model) AND ~16 GB on mlx-proxy (the 4-bit
   baseline) = 46 GB combined. M4 Pro has 64 GB. Headroom is 18 GB before
   OS + Docker. Should fit, but `MLX_MEMORY_HEADROOM_GB` (default 10) may
   reject the mlx-proxy load if oMLX is at ceiling. Fallback: stop oMLX
   between the MTP cell's three conditions (sacrifices isolation;
   document the choice in results).

5. **Quality contamination between 4-bit baseline and 8-bit MTP target.**
   The TPS comparison conflates "MTP speedup" with "8-bit base model
   speed differential vs 4-bit". The probe captures `output_prefix`
   (first 200 chars at temp=0) to allow a manual quality cross-check
   between conditions. If the outputs diverge meaningfully at
   deterministic temperature, the gate-decision write-up MUST call this
   out explicitly.

6. **Whether v0.3.10's "OpenClaw/Codex empty replies" fix (#1348) holds
   for non-reasoning Qwen3.5 (model_type qwen3_5 per the Jundot model
   card).** The release note mentions Qwen / Llama. If the MTP target
   exhibits empty replies during smoke (O-4), the fix didn't generalize
   to this model and the probe stops early.

---

## Follow-on tasks (NOT this task — recorded for visibility)

Conditional on which decision cell is selected. None of these are
written in this task; they are SKELETONS produced in O-10 if applicable.

1. **TASK_OMLX_MTP_PROMOTE_V1.md** — only if PROMOTE_FULL or PROMOTE_MTP.
2. **TASK_OMLX_KV_SIDECAR_V1.md** — only if PROMOTE_FULL or PROMOTE_KV.
3. **TASK_OMLX_MTP_STABILITY_V1.md** — only if PROBE_AGAIN_NARROWLY.
4. **TASK_OMLX_BAKEOFF_V2.md** — only if REOPEN_FULL_BAKEOFF.
5. **TASK_DFLASH_MLX_PROBE_V1.md** — independent of this task's outcome;
   the other unblock path for P5-FUT-SPEC. Worth doing if this probe's
   MTP dimension fails and the unblock urgency remains.

---

*End of TASK_OMLX_REEVAL_V2.md*
