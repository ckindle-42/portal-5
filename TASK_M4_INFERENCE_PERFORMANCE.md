# TASK_M4_INFERENCE_PERFORMANCE.md

**Milestone:** M4 — Inference performance
**Scope:** `CAPABILITY_REVIEW_V1.md` §6.2 OMLX evaluation, §6.8 speculative decoding via mlx-lm `--draft-model`
**Estimated effort:** 4-6 weeks (2-4 weeks for OMLX bake-off, 1-2 weeks for speculative decoding)
**Dependencies:** M1 ideally shipped (reasoning passthrough). M2 and M3 are independent — can run in parallel with this work.
**Companion files:** `CAPABILITY_REVIEW_V1.md`, `P5_ROADMAP.md` (P5-FUT-013 OMLX evaluation entry exists but unstarted)

**Why this milestone:**
- **Prompt caching is the perceived "snappiness" gap.** A 64K-context conversation with 10 turns reprocesses 64K × 10 = 640K tokens of prompt today, even though only ~10K are new each turn. OMLX's two-tier KV cache (RAM + SSD) reportedly drops TTFT from 30-90s to 1-3s on repeated context.
- **Speculative decoding gives 2-3× speedup on existing models with no new training.** mlx-lm 0.21+ supports `--draft-model`. Llama-3.2-1B (already lightweight) is a natural draft for Qwen3-Coder-30B and Llama-3.3-70B.
- **Continuous batching** in OMLX serves multiple concurrent requests on shared model weights — relevant if Portal 5 ever serves a household or small team.

**Success criteria:**
- TTFT on warm conversations drops measurably (target: 5-10× improvement on repeated-context turns).
- TPS on Qwen3-Coder-30B improves by ≥1.5× with speculative decoding enabled.
- A documented decision: replace mlx-proxy with OMLX, augment with OMLX, or stay with mlx-proxy + spec-decoding for now.
- No regression in existing acceptance tests.

**Protected files touched:** `scripts/mlx-proxy.py`, `tests/benchmarks/bench_tps.py`, `config/backends.yaml`, `deploy/`.

---

## Architecture Decisions

### A1. Two-track approach

This milestone runs **two parallel tracks** rather than a sequential commitment:

- **Track 1 (fast, low-risk):** Speculative decoding via mlx-lm `--draft-model`. ~1 week. Drops into existing mlx-proxy. Bench-validated. Ships independently.
- **Track 2 (slower, larger commitment):** OMLX side-by-side evaluation. 3-4 weeks. Bake-off vs current proxy. Decision at the end about whether to migrate.

Track 1 ships value within the milestone window even if Track 2 concludes "stay with mlx-proxy."

### A2. Speculative decoding model selection

mlx-lm draft model requirement: same tokenizer family as target. Candidates:

| Target | Draft candidate | Tokenizer compat | Memory cost |
|---|---|---|---|
| Qwen3-Coder-30B-A3B-Instruct-8bit (~22GB) | mlx-community/Qwen2.5-0.5B-Instruct-4bit | ✅ Qwen tokenizer | ~0.5GB |
| Llama-3.3-70B-Instruct-4bit (~40GB) | mlx-community/Llama-3.2-1B-Instruct-4bit | ✅ Llama-3 tokenizer | ~1GB |
| Devstral-Small-2507-MLX-4bit (~15GB) | (no Mistral 1B in MLX yet) | — | skip |
| Magistral-Small-2509-MLX-8bit (~24GB) | mlx-community/Mistral-7B-Instruct-mlx (too big to be useful) | — | skip |

**M4 focus:** Qwen and Llama families (the two most-used in the stack). Mistral and others deferred until smaller draft models are MLX-converted.

### A3. OMLX evaluation method

Side-by-side install, **separate port**, run for 2 weeks of bench + manual quality checks.

**Test matrix:**
- All 18 text-only MLX models in current catalog
- 3 prompt categories (coding, reasoning, general)
- 3 conversation lengths (single-turn, 5-turn, 20-turn — KV cache impact)
- 2 concurrency levels (1 request, 4 concurrent — continuous batching impact)

**Decision criteria** (must satisfy all):
- TPS parity or better on every model (no regressions)
- TTFT improvement on repeated-context turns ≥3× (the headline benefit)
- Admission control compatibility (MODEL_MEMORY checks must port over)
- VLM routing (mlx_lm ↔ mlx_vlm switch) preserved or replaced with equivalent
- Big-model evict mode preserved (or unnecessary because OMLX handles differently)
- mlx-lm version compatibility — OMLX uses its own fork; verify qwen3_next architecture works

**Fallback decision tree:**
- All criteria met → migration plan (M4-T08)
- TPS regression on any model → augment-only (run OMLX for caching, mlx-proxy for hot path)
- Major incompatibility (admission control, VLM, big-model) → stay with mlx-proxy + spec-decoding only

### A4. KV cache persistence semantics

OMLX's SSD KV cache writes to disk on session end, restores on session start. For Portal 5's request model:

- Each chat completion = a session
- Sessions sharing prefix (system prompt + history) share cache
- Cache hit detection via prefix hash
- Cache invalidation on system prompt change

Storage budget: ~50KB per 1K tokens of cached prefix (FP16). 100MB SSD per ~2M cached tokens. Set `OMLX_KV_CACHE_DIR=/Volumes/data01/portal5_omlx_cache` with 5GB cap.

---

## Task Index

| ID | Title | File(s) | Effort |
|---|---|---|---|
| **Track 1: Speculative decoding (~1-2 weeks)** | | | |
| M4-T01 | Pull draft models into MLX catalog | `config/backends.yaml`, `scripts/mlx-proxy.py` | 2 hours |
| M4-T02 | Add `draft_model` field to MLXState start_server | `scripts/mlx-proxy.py` | 2-3 days |
| M4-T03 | Per-target draft-model mapping config | `config/backends.yaml` | 1 day |
| M4-T04 | Bench speculative decoding impact | `tests/benchmarks/bench_tps.py`, results commit | 2-3 days |
| M4-T05 | Roll out spec-decoding to Qwen3-Coder-30B and Llama-3.3-70B | `scripts/mlx-proxy.py`, `config/backends.yaml` | 2 days |
| **Track 2: OMLX evaluation (~3-4 weeks)** | | | |
| M4-T06 | Install OMLX side-by-side (port 8085) | `deploy/omlx/`, `launch.sh` | 3-5 days |
| M4-T07 | Map OMLX configuration to current admission control + VLM routing | `deploy/omlx/config.yaml` | 5-7 days |
| M4-T08 | Bench OMLX vs current mlx-proxy (full matrix) | `tests/benchmarks/bench_omlx.py` (new), results commit | 1-2 weeks |
| M4-T09 | Decision document: replace, augment, or hold | `OMLX_DECISION.md` (new) | 2-3 days |
| M4-T10 | Migration plan (conditional on M4-T09) | `TASK_M4B_OMLX_MIGRATION.md` (new) — only if T-09 says go | 3-5 days writing |
| **Cross-track** | | | |
| M4-T11 | Documentation | `docs/HOWTO.md`, `KNOWN_LIMITATIONS.md`, `CHANGELOG.md`, `P5_ROADMAP.md` | 1 day |

---

## Track 1: Speculative Decoding

### M4-T01 — Pull Draft Models into MLX Catalog

**Files:** `config/backends.yaml`, `scripts/mlx-proxy.py`

**Diff** in `config/backends.yaml` MLX models list:
```yaml
      # ── Draft models for speculative decoding (M4 Track 1) ──────────────
      - mlx-community/Qwen2.5-0.5B-Instruct-4bit          # ~0.5GB, Qwen tokenizer
      - mlx-community/Llama-3.2-1B-Instruct-4bit          # ~1GB, Llama-3 tokenizer
```

**Diff** in `scripts/mlx-proxy.py` MODEL_MEMORY:
```diff
+    # Draft models — additive cost when enabled with --draft-model
+    "mlx-community/Qwen2.5-0.5B-Instruct-4bit": 0.5,
+    "mlx-community/Llama-3.2-1B-Instruct-4bit": 1.0,
```

**Pull:**
```bash
hf download mlx-community/Qwen2.5-0.5B-Instruct-4bit \
    --local-dir /Volumes/data01/models/mlx-community/Qwen2.5-0.5B-Instruct-4bit
hf download mlx-community/Llama-3.2-1B-Instruct-4bit \
    --local-dir /Volumes/data01/models/mlx-community/Llama-3.2-1B-Instruct-4bit
```

**Verify:**
```bash
ls /Volumes/data01/models/mlx-community/Qwen2.5-0.5B-Instruct-4bit/
ls /Volumes/data01/models/mlx-community/Llama-3.2-1B-Instruct-4bit/

# Sanity check: drafts can produce output independently
python3 -c "
from mlx_lm import load, generate
model, tokenizer = load('mlx-community/Qwen2.5-0.5B-Instruct-4bit')
out = generate(model, tokenizer, prompt='Hello', max_tokens=10, verbose=False)
print(repr(out))
"
# Expect: a brief coherent string
```

**Commit:** `feat(catalog): add Qwen2.5-0.5B and Llama-3.2-1B as draft models for spec-decoding`

---

### M4-T02 — `draft_model` Field on Server Start

**File:** `scripts/mlx-proxy.py`

**Goal:** when starting an `mlx_lm.server` for a target model, optionally include `--draft-model <draft_path>` if the target is configured to use one.

**Diff** in `start_server` (around line 800):

```python
# Build a target → draft model mapping. Loaded from config/backends.yaml at startup.
DRAFT_MODEL_MAP = _load_draft_model_map()


def _load_draft_model_map() -> dict[str, str]:
    """Read config/backends.yaml for `speculative_decoding.draft_models` map."""
    try:
        cfg = yaml.safe_load(open(_backends_yaml_path()).read())
        return cfg.get("speculative_decoding", {}).get("draft_models", {})
    except Exception:
        return {}


def start_server(stype: str, model: str = "") -> int:
    # ... existing setup ...
    cmd = [
        "python3", "-m", f"mlx_{stype}.server",
        "--model", model,
        "--host", "127.0.0.1",
        "--port", str(LM_PORT if stype == "lm" else VLM_PORT),
    ]

    # NEW: speculative decoding via draft model
    draft_model = DRAFT_MODEL_MAP.get(model, "")
    if stype == "lm" and draft_model:
        # Verify draft model exists locally before passing
        if _model_exists_locally(draft_model):
            cmd.extend(["--draft-model", draft_model])
            # Optional: tune speculative decoding parameters
            num_draft = os.environ.get("MLX_NUM_DRAFT_TOKENS", "4")
            cmd.extend(["--num-draft-tokens", num_draft])
            print(f"[proxy] speculative decoding enabled: target={model} draft={draft_model} num_draft={num_draft}")
            # Add draft model memory to admission control accounting
            # (handled in _check_memory_for_model — see M4-T03 changes)
        else:
            logger.warning("Draft model %s not found locally; skipping spec decoding for %s",
                          draft_model, model)

    # KV cache quantization (existing logic)
    if stype == "lm":
        # ... existing --kv-cache-quantization runtime guard ...

    # ... rest of start_server unchanged ...


def _model_exists_locally(model_id: str) -> bool:
    """Check if model is in local HF cache."""
    cache_path = Path(os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))) / "hub"
    # Simplest check: model dir exists in /Volumes/data01/models too (Portal 5 convention)
    portal5_models = Path(os.environ.get("PORTAL5_MODELS_DIR", "/Volumes/data01/models"))
    p = portal5_models / model_id
    return p.is_dir() or any(cache_path.glob(f"models--{model_id.replace('/', '--')}**"))
```

**Update `_check_memory_for_model`** (around line 864) to include draft model memory:

```python
def _check_memory_for_model(model: str, freed_by_stop_gb: float = 0.0) -> tuple[bool, str]:
    needed = MODEL_MEMORY.get(model, MEMORY_UNKNOWN_DEFAULT_GB)

    # NEW: include draft model memory if speculative decoding is configured
    draft = DRAFT_MODEL_MAP.get(model, "")
    if draft:
        needed += MODEL_MEMORY.get(draft, 0.5)  # default 0.5GB for unknown drafts

    available = _get_available_memory_gb() + freed_by_stop_gb
    headroom = MEMORY_HEADROOM_GB
    if needed + headroom > available:
        return (
            False,
            f"Model needs ~{needed:.1f}GB (incl draft) + {headroom:.0f}GB headroom; "
            f"only {available:.1f}GB available. "
            "Stop ComfyUI or unload Ollama models first.",
        )
    return True, ""
```

**Verify:**
```bash
# Smoke: ensure existing single-model load still works without draft (no entry in DRAFT_MODEL_MAP yet)
./launch.sh restart-mlx
sleep 30
curl -s -X POST http://localhost:8081/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model": "mlx-community/Llama-3.2-3B-Instruct-8bit", "messages": [{"role":"user","content":"hi"}], "max_tokens": 10}'
# Expect: works (no draft applied because DRAFT_MODEL_MAP is empty)
```

**Commit:** `feat(mlx-proxy): support --draft-model when target is in DRAFT_MODEL_MAP`

---

### M4-T03 — Per-Target Draft-Model Mapping

**File:** `config/backends.yaml`

Add a new top-level section:

```yaml
# Speculative decoding (M4 Track 1)
# Maps target_model_id → draft_model_id. Both must be in the MLX models list.
# When the target is loaded by mlx-proxy, --draft-model is appended to the
# command. Speculative decoding requires tokenizer compatibility — only same-family pairs.
speculative_decoding:
  draft_models:
    # Qwen family (Qwen tokenizer)
    "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit": "mlx-community/Qwen2.5-0.5B-Instruct-4bit"
    "mlx-community/DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit": "mlx-community/Qwen2.5-0.5B-Instruct-4bit"
    "mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit": "mlx-community/Qwen2.5-0.5B-Instruct-4bit"
    "Jackrong/MLX-Qwopus3.5-27B-v3-8bit": "mlx-community/Qwen2.5-0.5B-Instruct-4bit"
    "Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit": "mlx-community/Qwen2.5-0.5B-Instruct-4bit"
    "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit": "mlx-community/Qwen2.5-0.5B-Instruct-4bit"
    # Llama family (Llama-3 tokenizer)
    "mlx-community/Llama-3.3-70B-Instruct-4bit": "mlx-community/Llama-3.2-1B-Instruct-4bit"
    "mlx-community/Dolphin3.0-Llama3.1-8B-8bit": "mlx-community/Llama-3.2-1B-Instruct-4bit"
    # Big-model variants intentionally excluded — Qwen3-Coder-Next 80B doesn't share
    # tokenizer with available drafts; revisit when a Qwen3-Coder draft model exists.
```

**Verify:**
```bash
python3 -c "
import yaml
cfg = yaml.safe_load(open('config/backends.yaml'))
sd = cfg.get('speculative_decoding', {}).get('draft_models', {})
print(f'Speculative decoding pairs: {len(sd)}')
for tgt, drf in sd.items():
    print(f'  {tgt[:60]:60s} → {drf}')
"

./launch.sh restart-mlx
sleep 30

# Trigger Qwen3-Coder-30B load and verify --draft-model is in the command line
ps aux | grep mlx_lm.server | grep -- "--draft-model"
# Expect: at least one process running with --draft-model flag
```

**Commit:** `feat(routing): per-target draft-model map for 8 large MLX models`

---

### M4-T04 — Bench Speculative Decoding Impact

**File:** `tests/benchmarks/bench_tps.py`, new comparison script

The existing bench runs whatever's loaded. To bench spec-decoding's impact:
1. Run baseline (no drafts) — collect TPS for the 8 target models in `speculative_decoding.draft_models`
2. Enable spec-decoding for those models (commit M4-T03)
3. Re-run bench
4. Compare

Add `--spec-decoding-tag` arg to bench_tps to label the run:

```python
parser.add_argument(
    "--spec-decoding-tag",
    type=str,
    default="",
    help="Label this run as 'spec_decoding=on/off' for later comparison",
)

# In _init_output, include the tag in the JSON metadata:
result_metadata = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "spec_decoding": args.spec_decoding_tag or "unspecified",
    # ... existing metadata ...
}
```

**Run:**
```bash
# Step 1: baseline (no spec-decoding — temporarily empty draft_models in YAML)
python3 -c "
import yaml
cfg = yaml.safe_load(open('config/backends.yaml'))
cfg.setdefault('speculative_decoding', {})['draft_models'] = {}
yaml.safe_dump(cfg, open('config/backends.yaml.no_drafts', 'w'))
"
mv config/backends.yaml config/backends.yaml.with_drafts
mv config/backends.yaml.no_drafts config/backends.yaml
./launch.sh restart-mlx
sleep 30
python3 tests/benchmarks/bench_tps.py --runs 3 --order size --spec-decoding-tag off

# Step 2: with spec-decoding
mv config/backends.yaml.with_drafts config/backends.yaml
./launch.sh restart-mlx
sleep 30
python3 tests/benchmarks/bench_tps.py --runs 3 --order size --spec-decoding-tag on

# Step 3: compare
python3 - <<'EOF'
import json, glob
results = []
for f in sorted(glob.glob('tests/benchmarks/results/bench_tps_*.json'))[-2:]:
    with open(f) as fp:
        results.append((f, json.load(fp)))

# Pair by (model, prompt_category)
by_model_off = {(r['model'], r['prompt_category']): r['avg_tps']
                for r in results[0][1]['results']
                if r.get('runs_success') and r.get('avg_tps')}
by_model_on = {(r['model'], r['prompt_category']): r['avg_tps']
               for r in results[1][1]['results']
               if r.get('runs_success') and r.get('avg_tps')}

print(f"{'Model':<70} {'Off':>8} {'On':>8} {'Speedup':>8}")
for k in sorted(by_model_off.keys() & by_model_on.keys()):
    off = by_model_off[k]
    on = by_model_on[k]
    speedup = on / off if off else 0
    flag = "✓" if speedup >= 1.5 else "·" if speedup >= 1.1 else "✗"
    print(f"{flag} {k[0][:65]:<65} {k[1]:<5} {off:>8.1f} {on:>8.1f} {speedup:>7.2f}×")
EOF
```

**Decision rule for M4-T05:**
- Targets with ≥1.5× speedup AND no quality regression: keep spec-decoding enabled
- Targets with 1.1-1.5×: marginal; keep enabled (small win, no downside)
- Targets with <1.1× or quality regression: remove from `speculative_decoding.draft_models` map

**Commit:** `feat(bench): spec-decoding impact comparison; commit before/after baselines`

---

### M4-T05 — Roll Out Spec-Decoding (Conditional)

**File:** `config/backends.yaml`

Based on M4-T04 results, prune the `speculative_decoding.draft_models` map to only the targets that benefited. For each removed entry, document why in a comment:

```yaml
speculative_decoding:
  draft_models:
    "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit": "mlx-community/Qwen2.5-0.5B-Instruct-4bit"
    "mlx-community/Llama-3.3-70B-Instruct-4bit": "mlx-community/Llama-3.2-1B-Instruct-4bit"
    # Disabled (no significant speedup, see bench_tps_<date>):
    #   DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit (1.05×)
    #   Dolphin3.0-Llama3.1-8B-8bit (1.02× — already small)
```

**Verify:**
```bash
./launch.sh restart-mlx
sleep 30

# Verify Qwen3-Coder still produces correct output
curl -s -X POST http://localhost:9099/v1/chat/completions \
    -H "Authorization: Bearer $PIPELINE_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "auto-coding",
        "messages": [{"role":"user","content":"Write a Python function to merge two sorted lists."}],
        "max_tokens": 250
    }' | jq -r '.choices[0].message.content'
# Expect: correct merge function
```

**Commit:** `feat(routing): enable speculative decoding on validated target models (Track 1 ship)`

---

## Track 2: OMLX Evaluation

### M4-T06 — Install OMLX Side-by-Side

**File:** `deploy/omlx/Dockerfile` (or host-native), `launch.sh`

OMLX install (host-native, similar to mlx-proxy.py):

```bash
# In a separate venv to avoid conflicting with mlx-proxy's mlx-lm version
python3 -m venv /Volumes/data01/omlx-venv
source /Volumes/data01/omlx-venv/bin/activate
pip install omlx  # actual package name TBD — check github.com/jundot/omlx
```

Add to `launch.sh` a parallel start command:

```bash
# OMLX evaluation install — runs on port 8085 alongside mlx-proxy on 8081
start-omlx() {
    if [ ! -d "/Volumes/data01/omlx-venv" ]; then
        echo "OMLX not installed. Run: python3 -m venv /Volumes/data01/omlx-venv && source ... && pip install omlx"
        return 1
    fi
    /Volumes/data01/omlx-venv/bin/omlx serve \
        --config deploy/omlx/config.yaml \
        --port 8085 \
        --host 127.0.0.1 \
        --kv-cache-dir /Volumes/data01/portal5_omlx_cache \
        --max-process-memory 30 \
        > ~/.portal5/logs/omlx.log 2>&1 &
    echo "OMLX started on port 8085"
}
```

**Verify:**
```bash
./launch.sh start-omlx
sleep 60                               # initial model registration may take longer
curl -s http://localhost:8085/health | jq .
curl -s http://localhost:8085/v1/models | jq '.data | length'
# Expect: model count > 0
```

**Note on isolation:** OMLX runs in a separate venv with its own mlx-lm fork. This means it can be active simultaneously with mlx-proxy without conflict. Memory budget: limit OMLX to 30GB via `--max-process-memory` so admission control on mlx-proxy isn't broken.

**Rollback:** `./launch.sh stop-omlx; rm -rf /Volumes/data01/omlx-venv /Volumes/data01/portal5_omlx_cache`

**Commit:** `feat(deploy): OMLX side-by-side install on port 8085 (eval phase)`

---

### M4-T07 — Map Configuration to OMLX

**File:** `deploy/omlx/config.yaml` (new)

Map current admission control + VLM routing semantics to OMLX equivalents.

```yaml
# Portal 5 OMLX evaluation configuration
# Equivalent to scripts/mlx-proxy.py for the bake-off period.

server:
  host: 127.0.0.1
  port: 8085

# KV cache configuration — the headline OMLX feature
kv_cache:
  enabled: true
  hot_max_gb: 4         # in-RAM tier (LRU)
  cold_dir: /Volumes/data01/portal5_omlx_cache
  cold_max_gb: 5        # SSD tier (LRU)
  ttl_hours: 168        # 7 days

# Admission control — OMLX equivalent of MODEL_MEMORY checks
admission_control:
  max_total_memory_gb: 30           # ceiling for OMLX process memory
  per_model_memory_gb:              # mirror MODEL_MEMORY from mlx-proxy.py
    "mlx-community/Qwen3-Coder-Next-4bit": 46.0
    "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit": 22.0
    "lmstudio-community/Devstral-Small-2507-MLX-4bit": 15.0
    "mlx-community/Dolphin3.0-Llama3.1-8B-8bit": 9.0
    "mlx-community/Llama-3.2-3B-Instruct-8bit": 3.0
    "mlx-community/phi-4-8bit": 14.0
    "mlx-community/Llama-3.3-70B-Instruct-4bit": 40.0
    "Jackrong/MLX-Qwopus3.5-27B-v3-8bit": 22.0
    "mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit": 18.0
    # ... mirror MODEL_MEMORY ...
  unknown_model_default_gb: 20

# Multi-model serving — the LRU eviction OMLX promises
multi_model:
  enabled: true
  max_loaded_models: 2              # 2 simultaneous LM models max
  pinned_models:
    - mlx-community/Llama-3.2-3B-Instruct-8bit   # Pin the LLM router model — never evict

# VLM routing — equivalent to mlx-proxy.py VLM_MODELS auto-switch
vlm_routing:
  vlm_models:
    - mlx-community/Qwen3-VL-32B-Instruct-8bit
    - mlx-community/gemma-4-31b-it-4bit
    - mlx-community/gemma-4-e4b-it-4bit
    - Jiunsong/supergemma4-26b-abliterated-multimodal-mlx-4bit
    - mlx-community/Llama-3.2-11B-Vision-Instruct-abliterated-4-bit
    - dealignai/Gemma-4-31B-JANG_4M-CRACK
  auto_detect: true                 # OMLX inspects model architecture to decide engine

# Speculative decoding — OMLX has its own DFlash; check if compatible with our drafts
speculative_decoding:
  enabled: true
  engine: dflash                    # "dflash" or "draft_model"
  draft_models:
    "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit": "mlx-community/Qwen2.5-0.5B-Instruct-4bit"
    "mlx-community/Llama-3.3-70B-Instruct-4bit": "mlx-community/Llama-3.2-1B-Instruct-4bit"

# Continuous batching — concurrent request handling on shared model
batching:
  enabled: true
  max_concurrent: 4
  max_batch_tokens: 8192
```

**Note:** The exact YAML schema may differ from OMLX's actual config format — verify against the OMLX docs at install time and adjust. The intent here is the *mapping* between Portal 5 concepts and OMLX equivalents.

**Verify (after starting OMLX with this config):**
```bash
# Memory ceiling enforced
ps -o pid,rss,command -p $(pgrep -f omlx) | awk '{print $2/1024/1024 " GB"}'
# Expect: under 30GB

# Models discoverable
curl -s http://localhost:8085/v1/models | jq '.data | length'

# Admission control rejects oversize
curl -s -X POST http://localhost:8085/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model": "mlx-community/Qwen3-Coder-Next-4bit", "messages": [{"role":"user","content":"hi"}]}' \
    | jq -r '.error'
# Expect: error citing memory ceiling (since 46GB > 30GB cap on the OMLX process)
```

**Commit:** `feat(omlx): config mapping for admission control, VLM routing, batching`

---

### M4-T08 — Bench OMLX vs mlx-proxy (Full Matrix)

**File:** `tests/benchmarks/bench_omlx.py` (new)

Bench against both endpoints and produce comparison report.

```python
"""Portal 5 — OMLX vs mlx-proxy bake-off benchmark.

Runs the same workload against:
  - http://localhost:8081 (mlx-proxy)
  - http://localhost:8085 (omlx)

Captures TPS, TTFT, total wall-time, KV cache hit rate (OMLX-side metric),
and memory pressure for each. Outputs side-by-side JSON.

Run after:
  ./launch.sh restart-mlx
  ./launch.sh start-omlx
  sleep 60
"""
import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

MLX_PROXY_URL = "http://localhost:8081"
OMLX_URL = "http://localhost:8085"
RESULTS_DIR = Path(__file__).parent / "results"

# Test matrix
MODELS = [
    "mlx-community/Llama-3.2-3B-Instruct-8bit",
    "mlx-community/Dolphin3.0-Llama3.1-8B-8bit",
    "mlx-community/phi-4-8bit",
    "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",
    "Jackrong/MLX-Qwopus3.5-27B-v3-8bit",
    "lmstudio-community/Devstral-Small-2507-MLX-4bit",
    # Add more as memory permits
]

PROMPTS = {
    "coding": "Write a Python function to compute the nth Fibonacci number with memoization.",
    "reasoning": "If a train leaves Boston at 8am going 60mph and another leaves NYC at 9am going 80mph, when do they meet (assume 200 miles)?",
    "general": "Explain the OSI 7-layer model with one example protocol per layer.",
}

# 5-turn conversation for KV cache test
CONVERSATION = [
    {"role": "system", "content": "You are a helpful assistant. Be concise."},
    {"role": "user", "content": "What is functional programming?"},
    {"role": "assistant", "content": "Functional programming is a paradigm based on..."},  # mock
    {"role": "user", "content": "Give me an example in Haskell."},
    {"role": "assistant", "content": "Here's a Haskell example..."},
    {"role": "user", "content": "Now translate to TypeScript."},
]


async def _bench_one(client, base_url, model, messages, max_tokens=200):
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "stream": False}
    t0 = time.monotonic()
    try:
        r = await client.post(f"{base_url}/v1/chat/completions", json=body, timeout=300)
        elapsed = time.monotonic() - t0
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}", "elapsed": elapsed}
        data = r.json()
        usage = data.get("usage", {})
        completion = usage.get("completion_tokens", 0)
        prompt = usage.get("prompt_tokens", 0)
        return {
            "elapsed": elapsed,
            "completion_tokens": completion,
            "prompt_tokens": prompt,
            "tps": completion / elapsed if elapsed > 0 else 0,
        }
    except Exception as e:
        return {"error": str(e), "elapsed": time.monotonic() - t0}


async def bench_endpoint(base_url, label):
    print(f"\n=== Benchmarking {label} ({base_url}) ===")
    results = []
    async with httpx.AsyncClient() as client:
        for model in MODELS:
            print(f"\n--- {model} ---")
            for prompt_cat, prompt in PROMPTS.items():
                # Single-turn
                msgs = [{"role": "user", "content": prompt}]
                out = await _bench_one(client, base_url, model, msgs)
                out.update({"endpoint": label, "model": model, "category": prompt_cat, "turns": 1})
                results.append(out)
                print(f"  {prompt_cat} (1 turn): {out.get('tps', 0):.1f} TPS, {out.get('elapsed', 0):.1f}s")

                # Multi-turn (KV cache test)
                out = await _bench_one(client, base_url, model, CONVERSATION)
                out.update({"endpoint": label, "model": model, "category": "multi-turn", "turns": 5})
                results.append(out)
                print(f"  multi-turn (5 turns): {out.get('tps', 0):.1f} TPS, {out.get('elapsed', 0):.1f}s")

                # Settle between models
                await asyncio.sleep(3)
    return results


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mlx-only", action="store_true")
    parser.add_argument("--omlx-only", action="store_true")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = {
        "timestamp": ts,
        "results": [],
    }

    if not args.omlx_only:
        output["results"].extend(await bench_endpoint(MLX_PROXY_URL, "mlx-proxy"))
    if not args.mlx_only:
        output["results"].extend(await bench_endpoint(OMLX_URL, "omlx"))

    out_path = RESULTS_DIR / f"omlx_bakeoff_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n✓ Results: {out_path}")

    # Quick summary
    print("\n=== Summary ===")
    by_endpoint = {}
    for r in output["results"]:
        if r.get("error"):
            continue
        key = (r["endpoint"], r["model"], r["category"])
        by_endpoint[key] = r.get("tps", 0)

    print(f"{'Model':<60} {'Cat':<12} {'mlx-proxy':>10} {'OMLX':>8} {'Δ':>6}")
    keys = sorted({(k[1], k[2]) for k in by_endpoint})
    for model, cat in keys:
        mlx = by_endpoint.get(("mlx-proxy", model, cat), 0)
        omlx = by_endpoint.get(("omlx", model, cat), 0)
        delta = (omlx / mlx - 1) * 100 if mlx > 0 else 0
        flag = "✓" if delta > 10 else "·" if delta > -10 else "✗"
        print(f"{flag} {model[:58]:<58} {cat:<12} {mlx:>10.1f} {omlx:>8.1f} {delta:>+5.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
```

**Run schedule (over 1-2 weeks):**

| Run | Conditions | Goal |
|---|---|---|
| 1 | Cold OMLX, cold mlx-proxy, sequential | Baseline TPS |
| 2 | Warm OMLX, warm mlx-proxy, sequential | Steady-state TPS |
| 3 | OMLX 5-turn convo, mlx-proxy 5-turn convo | KV cache impact |
| 4 | OMLX 4 concurrent, mlx-proxy serial | Continuous batching impact |
| 5 | After 1 week of normal usage — KV cache fill | Real-world cache hit rate |
| 6 | Stress: 100 sequential requests | Memory leak / drift detection |
| 7 | Big-model: Qwen3-Coder-Next-4bit on each | Big-model handling parity |
| 8 | VLM: Qwen3-VL-32B-Instruct-8bit on each | VLM auto-switch |

**Capture for each run:**
- TPS per (model, category)
- TTFT (time to first token)
- Wall-clock total
- Memory pressure (`memory_pressure` macOS command)
- Any errors / OOMs
- For OMLX specifically: cache hit rate from `/admin/metrics`

**Commit (each run):**
```
test(omlx): bake-off run N — <conditions> — <topline finding>
```

---

### M4-T09 — Decision Document

**File:** `OMLX_DECISION.md` (new)

After M4-T08 runs complete (~2 weeks elapsed), produce the decision document.

Template:

```markdown
# OMLX Migration Decision (P5-FUT-013)

**Decision date:** YYYY-MM-DD
**Decision maker:** Operator (Chris)
**Bake-off period:** YYYY-MM-DD through YYYY-MM-DD
**Bake-off result files:** tests/benchmarks/results/omlx_bakeoff_*.json

## Decision

[REPLACE | AUGMENT | HOLD]

## Evidence summary

### TPS comparison (head-to-head, average across 5 runs)

| Model | mlx-proxy TPS | OMLX TPS | Δ |
|---|---|---|---|
| Llama-3.2-3B-Instruct | ... | ... | ... |
| Phi-4-8bit | ... | ... | ... |
| Qwen3-Coder-30B-A3B | ... | ... | ... |
| ...

### TTFT on repeated context (5-turn conversation)

| Model | mlx-proxy TTFT | OMLX TTFT (cold) | OMLX TTFT (warm) | Δ (warm) |
|---|---|---|---|---|
| ...

### Concurrency (4 parallel requests)

| Model | mlx-proxy serial | OMLX concurrent | Throughput Δ |
|---|---|---|---|

### Compatibility checks

- [ ] All 18 text-only MLX models in catalog work on OMLX
- [ ] All 8 VLM models work on OMLX
- [ ] Big-model evict mode equivalent works (Qwen3-Coder-Next-4bit, Llama-3.3-70B, Qwen3-VL-32B)
- [ ] Admission control rejects oversize loads (no OOMs in stress run)
- [ ] qwen3_next architecture works (mlx-lm version compatibility)
- [ ] Tool-calling support compatible with M2 pipeline integration

### Risks / observations

- ...

## Recommendation rationale

(2-3 paragraphs explaining the decision)

## Next steps

If REPLACE:
- See `TASK_M4B_OMLX_MIGRATION.md` for the migration plan
- Estimated migration effort: ...
- Cutover date target: ...

If AUGMENT:
- OMLX runs alongside mlx-proxy on port 8085 indefinitely
- Specific traffic pattern to route to OMLX: ...
- mlx-proxy remains primary for: ...

If HOLD:
- OMLX uninstalled
- Re-evaluate at OMLX version: ...
- Reasons against migration: ...
```

**Commit (after decision):** `docs(omlx): decision document — <REPLACE/AUGMENT/HOLD>`

---

### M4-T10 — Migration Plan (Conditional)

**File:** `TASK_M4B_OMLX_MIGRATION.md` (new) — only created if M4-T09 says REPLACE or AUGMENT-with-significant-traffic

If migrating: this is a separate task file that the operator commits to executing. Outline:

```markdown
# TASK_M4B_OMLX_MIGRATION.md

**Decision basis:** OMLX_DECISION.md (REPLACE | AUGMENT)
**Estimated effort:** 2-3 weeks for cutover
**Risk level:** MEDIUM (production inference path change)
**Cutover plan:** dual-stack with traffic shifting

## Phases

### Phase A: Dual-stack stabilization (1 week)
- Both mlx-proxy and OMLX running
- Pipeline routes 10% of MLX-tier traffic to OMLX (canary)
- Monitor errors, latency, quality
- Rollback if any regression detected

### Phase B: Traffic shift (1 week)
- 10% → 50% → 90% over the week
- Daily review of metrics

### Phase C: Cutover (3 days)
- 90% → 100% to OMLX
- mlx-proxy stays running for 1 week for emergency rollback
- After 1 week clean, decommission mlx-proxy

### Phase D: Cleanup
- Remove mlx-proxy code from `scripts/`
- Update HOWTO.md to reference OMLX commands only
- Update `launch.sh` to remove `start-mlx` (replaced by `start-omlx`)
- KNOWN_LIMITATIONS update: P5-MLX-* items resolved
```

(Full task file generated only when needed; not produced in M4 unless decision is REPLACE.)

---

## M4-T11 — Documentation

**Files:** `docs/HOWTO.md`, `KNOWN_LIMITATIONS.md`, `CHANGELOG.md`, `P5_ROADMAP.md`

### CHANGELOG.md

```markdown
## v6.4.0 — Inference performance (M4)

### Added (Track 1: Speculative Decoding)
- Speculative decoding via mlx-lm `--draft-model` for 8 large MLX targets
- Draft models: `mlx-community/Qwen2.5-0.5B-Instruct-4bit`, `mlx-community/Llama-3.2-1B-Instruct-4bit`
- `speculative_decoding.draft_models` map in `config/backends.yaml`
- bench_tps `--spec-decoding-tag` arg for before/after labeling

### Track 2: OMLX Evaluation (parallel)
- OMLX side-by-side install on port 8085
- Bake-off bench (`tests/benchmarks/bench_omlx.py`)
- Decision document: `OMLX_DECISION.md`

### Performance impact (Track 1)
- Qwen3-Coder-30B-A3B-Instruct-8bit: TPS +X% (was Y, now Z)
- Llama-3.3-70B-Instruct-4bit: TPS +X% (was Y, now Z)
- (...other targets per bench results...)
```

### P5_ROADMAP.md

```markdown
| P5-FUT-013 | P1 | OMLX evaluation | <DONE/IN_PROGRESS> | M4: side-by-side eval complete YYYY-MM-DD; decision: <REPLACE/AUGMENT/HOLD>; see OMLX_DECISION.md |
| P5-FUT-SPEC | P2 | Speculative decoding for large MLX targets | DONE | M4 Track 1: enabled for Qwen3-Coder-30B-A3B + Llama-3.3-70B; X% / Y% TPS gain validated. |
```

### KNOWN_LIMITATIONS.md

```markdown
### Speculative Decoding Adds Memory Cost
- **ID:** P5-SPEC-001
- **Status:** ACTIVE
- **Description:** When a target model has a draft assigned in `speculative_decoding.draft_models`, both the target and draft are loaded simultaneously. Admission control accounts for this — draft memory is added to the target's MODEL_MEMORY entry pre-flight. If the operator manually loads a target with `mlx-proxy` while memory is tight, the draft load may fail; fall back to non-spec-decoded by clearing the draft entry temporarily.

### OMLX Status — Pending Decision (M4-T09)
- **ID:** P5-OMLX-001
- **Status:** EVALUATING (until OMLX_DECISION.md is finalized)
- **Description:** OMLX runs alongside mlx-proxy on port 8085. Pipeline does not route traffic to OMLX during evaluation. Decision target: <DATE>.
```

### HOWTO.md

Add a "Performance Tuning" section:
- How to disable speculative decoding for a target (remove from `speculative_decoding.draft_models`, restart mlx-proxy)
- How to tune `MLX_NUM_DRAFT_TOKENS` (4-8 typical; higher = more aggressive speculation, more rollback cost on misses)
- How to read bench_tps results (jq queries)
- How to interpret OMLX bake-off output

**Commit:** `docs: M4 performance — HOWTO, ROADMAP, KNOWN_LIMITATIONS, CHANGELOG`

---

## Phase Regression

```bash
ruff check . && ruff format --check .

# All processes running
ps -ef | grep -E "mlx_lm|mlx_vlm|omlx" | grep -v grep | wc -l
# Expect: at least 2 (mlx-proxy active server + OMLX)

# Spec-decoding active on intended targets
ps aux | grep mlx_lm.server | grep -- "--draft-model"
# Expect: at least one process with --draft-model when Qwen3-Coder is loaded

# Memory budget
echo "MLX-proxy memory:"
ps -o pid,rss -p $(pgrep -f mlx_lm.server) 2>/dev/null
echo "OMLX memory:"
ps -o pid,rss -p $(pgrep -f omlx) 2>/dev/null
# Expect: total under 50GB (16GB headroom)

# Acceptance still passes — speculative decoding shouldn't change correctness
python3 tests/portal5_acceptance_v6.py --section S3,S11

# Bench results committed
ls tests/benchmarks/results/bench_tps_*.json | tail -3
ls tests/benchmarks/results/omlx_bakeoff_*.json
```

---

## Pre-flight checklist

- [ ] M1 has shipped (no hard dependency, but reasoning passthrough is an example streaming-pattern that helps when debugging spec-decoding chunk handling)
- [ ] Track 1 (M4-T01..T05) can ship within 1-2 weeks regardless of Track 2 progress
- [ ] Track 2 (M4-T06..T10) requires ~30GB memory headroom while OMLX is running alongside mlx-proxy — verify available capacity before starting
- [ ] OMLX repo (`github.com/jundot/omlx`) review completed; install instructions current
- [ ] Operator-side commitment: 1-2 hours per week for 2 weeks to review bake-off results and call the decision

## Post-M4 success indicators

- Track 1: Qwen3-Coder-30B-A3B and Llama-3.3-70B show TPS improvement in committed bench results
- Track 2: OMLX_DECISION.md exists with explicit REPLACE/AUGMENT/HOLD verdict
- No acceptance regression
- If REPLACE chosen: TASK_M4B_OMLX_MIGRATION.md scheduled for next sprint

## After M4 — what's next

The four-milestone plan (M1-M4) has shipped. Open items for re-evaluation:

- **M5 — Frontier capability**: §6.7 browser automation MCP + agent personas (paused per operator instruction)
- **M6 — Production hardening**: §6.10 cost tracking, §6.11 rate limits, OCR + diagram personas

Operator decides whether to commit to M5 + M6 or pause and reassess based on actual product feedback after M1-M4 are in production use.

---

*End of M4. The four-milestone roadmap (M1-M4) task files are complete:*
- *TASK_M1_UX_PERSONAS_AND_REASONING.md*
- *TASK_M2_TOOL_CALLING_ORCHESTRATION.md*
- *TASK_M3_INFORMATION_ACCESS_MCPS.md*
- *TASK_M4_INFERENCE_PERFORMANCE.md*

*M5 and M6 deferred per operator instruction; revisit after M4 ships.*
