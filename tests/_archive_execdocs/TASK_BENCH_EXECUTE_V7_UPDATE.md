# TASK: Bench-Execute Doc Refresh + Pipeline-Bench Skip Mechanism

**Task ID:** TASK_BENCH_EXECUTE_V7_UPDATE
**Version target:** v7.0.0 (lands alongside or immediately after `TASK_MODEL_REFRESH_V7`)
**Priority:** Normal — blocks the first post-V7 bench run from producing clean results
**Category:** Documentation refresh + small mechanism add
**Protected files touched:** None (`tests/PORTAL5_BENCH_EXECUTE_V1.md`, `tests/benchmarks/bench_tps.py`, `config/backends.yaml`)
**Repo HEAD at audit time:** `d579f88` (2026-05-27)
**Estimated risk:** Low — doc edits + ~15 lines of additive Python + 1 new YAML block. No production behavior change.

---

## Why this task exists

`tests/PORTAL5_BENCH_EXECUTE_V1.md` is the operator-and-agent runbook
for `python3 tests/benchmarks/bench_tps.py --mode all`. It's the bridge
from "task added bench workspaces" to "bench numbers exist in Grafana".

Audit at HEAD `d579f88` shows the doc is **stale even before V7**:

| Symptom | Doc claims | HEAD reality |
|---|---|---|
| Header total workspace count | "44 (19 auto-* + 25 bench-*)" | 43 (19 auto + 23 bench + 1 tools-specialist) |
| Bench table row count | 25 | 24 |
| `bench-llama4-scout` listed | ✓ in table (line 63), `--workspace` example (line 254), "Known Behavior Notes" bullet (line 364) | **REMOVED at HEAD** by commit `9c657b3` ("chore(fleet): remove Llama-4-Scout — 57GB Metal OOM crashes M4 Pro on bench") |
| `tools-specialist` production workspace | Not mentioned | Promoted to production (TASK 12a912a, 2026-05-24) |
| Document audit date | "HEAD, 2026-05-23" | Last commit is 2026-05-27 |
| Dry-run expected counts | "MLX models: 43 / Workspaces: 44" | At HEAD: 43 MLX / 43 workspaces |

After `TASK_MODEL_REFRESH_V7` lands, the gap grows:

- 6 new bench workspaces (3 text-benchable, 3 speech-only)
- The 3 speech workspaces (`bench-voxtral-realtime`, `bench-voxtral-tts`,
  `bench-granite-speech`) are deliberately **excluded from
  `WORKSPACE_PROMPT_MAP`** in V7 T6 — but `_config_workspaces()` reads
  `workspace_routing` directly and ignores `WORKSPACE_PROMPT_MAP`, so
  `bench_pipeline()` will iterate them anyway, fall back to the "general"
  prompt, dispatch text to streaming-ASR/TTS models, and produce
  meaningless TPS numbers that pollute the Grafana dashboard.

This task closes both gaps:

1. **Mechanism fix**: add `pipeline_bench_skip:` list to `backends.yaml`
   and respect it in `_config_workspaces()`. This is the missing
   workspace-level analog of the existing `bench_skip: true` flag on
   model entries (line 1006 of `bench_tps.py`, currently undocumented and
   unused).
2. **Doc refresh**: bring `PORTAL5_BENCH_EXECUTE_V1.md` current with
   v7.0.0 — remove Llama-4-Scout references, add the 6 V7 entries with
   correct "do-bench"/"skip-bench" disposition, add `tools-specialist`,
   update header counts and dry-run expectations, document the new
   skip mechanism.

---

## Why the skip mechanism instead of doc-only "do not include"

Three viable approaches, evaluated:

| Approach | Pros | Cons | Verdict |
|---|---|---|---|
| Doc-only "do not include" warning + manual `--workspace` filter | Zero code | Fragile; bench-execution agent or operator might miss it; resume from partial run re-introduces the issue | Reject |
| New CLI flag `--exclude-workspace` (comma list) | Generic | Still requires the operator to remember to pass it every run; not self-documenting | Reject |
| New `pipeline_bench_skip:` list in `backends.yaml` + auto-respect in `_config_workspaces()` | Config-driven, self-documenting, auto-enforced for every bench run including `--retry-failed`. Mirrors the existing `bench_skip` flag pattern on model entries. | ~15 lines of new code; needs doc to explain | **Pick** |

The `pipeline_bench_skip:` list is a flat list of workspace IDs, NOT a
schema change to `workspace_routing` (which is `key: list[str]` and
cannot carry per-workspace flags without restructuring). A sibling block
in the same YAML file is the minimum-invasive option.

---

## Architecture decisions enumerated

| ID | Decision |
|----|----------|
| B1 | **Mechanism, not policy.** This task adds the `pipeline_bench_skip:` machinery and seeds it with the 3 V7 speech workspaces. Whether future bench workspaces opt out of pipeline-mode benching is a per-task decision — the mechanism is general. |
| B2 | **No change to `workspace_routing` schema.** The skip list is a sibling block. Adding flags inside `workspace_routing` would require dict-of-dict rewrites of every existing entry. |
| B3 | **Direct-mode model benches still run.** `pipeline_bench_skip` only affects `bench_pipeline()` (the workspace iteration). The underlying MLX models still get exercised by `bench_direct()` against the MLX proxy. For speech models that means: direct-mode load+TPS numbers are still collected (and remain meaningless since text prompts don't exercise ASR/TTS) — but the **pipeline** workspace-level dispatch is skipped. **Per B6 below, the V7 speech model entries also need `bench_skip: true` on the `mlx_models[]` side to skip direct mode as well.** |
| B4 | **`--workspace <id>` filter still overrides the skip list.** If an operator explicitly passes `--workspace bench-voxtral-realtime`, that's an intentional probe and `pipeline_bench_skip` should be ignored for that single workspace. The check happens before the skip filter. |
| B5 | **Documentation tone**: the doc is read by a bench-execution agent, not by a human. Keep instructions imperative, counts current, examples runnable. No marketing prose. |
| B6 | **Belt-and-suspenders for speech models**: the 3 speech model entries already gain `pipeline_bench_skip` here. ALSO add `bench_skip: true` to their `mlx_models[]` entries in `config/backends.yaml`. Direct-mode TPS for a streaming ASR or TTS via text prompts is meaningless — covering both modes is the responsible default. This requires a small T1.5 edit to V7 if V7 has not yet landed, or a documented amendment if V7 already landed without it. |
| B7 | **Grafana dashboard updater is data-driven**: no hardcoded counts in `scripts/update_grafana_benchmarks.py`. Confirmed at line 526 (only thing it bumps is the dashboard `version` integer). No change needed there. |
| B8 | **Date stamp the doc audit**: change "HEAD, 2026-05-23" to "HEAD <commit-sha-at-merge>, <YYYY-MM-DD>" so future stale-check is mechanical. |

---

## Pre-flight checklist

Run BEFORE any edits land:

1. Confirm V7 status. Two cases:
   - **V7 already merged**: HEAD now has 29 bench workspaces (24 + 6 V7 additions). The doc refresh in this task targets that state.
   - **V7 still in flight**: this task should be staged on the V7 branch. Do not merge to main until V7 lands.
   ```bash
   git log --oneline -20 | grep -iE "v7\.0\.0|TASK_MODEL_REFRESH_V7|feat:.*v7"
   python3 -c "import yaml; cfg=yaml.safe_load(open('config/backends.yaml')); bench=[k for k in cfg['workspace_routing'] if k.startswith('bench-')]; print(f'{len(bench)} bench workspaces')"
   # Expect 24 (V7 not merged) or 30 (V7 merged)
   ```

2. Confirm Llama-4-Scout removal is in:
   ```bash
   grep -c "bench-llama4-scout\|llama4-scout\|Llama-4-Scout" config/backends.yaml portal_pipeline/router_pipe.py config/personas/*.yaml
   # Expect 0 — model was removed at HEAD by commit 9c657b3
   grep -c "bench-llama4-scout\|llama4-scout\|Llama-4-Scout" tests/PORTAL5_BENCH_EXECUTE_V1.md
   # Expect ≥3 — those are the stale references this task removes
   ```

3. Confirm `bench_tps.py` `_config_workspaces()` location:
   ```bash
   grep -n "def _config_workspaces" tests/benchmarks/bench_tps.py
   # Expect: 1098:def _config_workspaces() -> list[str]:
   ```

4. Confirm bench-execute doc length:
   ```bash
   wc -l tests/PORTAL5_BENCH_EXECUTE_V1.md
   # Expect 383 lines
   ```

---

## Safety gate

```bash
git tag pre-bench-execute-refresh
```

---

## Task index

| # | Task | Files | Risk | Verify |
|---|------|-------|------|--------|
| B1 | Add `pipeline_bench_skip:` list to `config/backends.yaml`. Seed with the 3 V7 speech workspace IDs. | `config/backends.yaml` | Low | YAML parses; block is a flat list of strings. |
| B2 | Add `bench_skip: true` to the 3 V7 speech `mlx_models[]` entries in `config/backends.yaml`. Belt-and-suspenders for direct mode. | `config/backends.yaml` | Low | YAML parses; 3 entries flagged. |
| B3 | Patch `_config_workspaces()` in `tests/benchmarks/bench_tps.py` to respect `pipeline_bench_skip`. | `tests/benchmarks/bench_tps.py` | Low | Unit test added; existing tests pass. |
| B4 | Add unit test for the skip mechanism. | `tests/unit/test_bench_skip.py` (new file) | None (test only) | `pytest tests/unit/test_bench_skip.py` passes. |
| B5 | Rewrite `tests/PORTAL5_BENCH_EXECUTE_V1.md` to v7.0.0 state. Remove Llama-4-Scout references. Add V7 entries with correct dispositions. Add `tools-specialist`. Update counts. Document the new skip mechanism. | `tests/PORTAL5_BENCH_EXECUTE_V1.md` | Low (doc only) | All counts in doc match output of `--dry-run`. |
| B6 | Commit + verify. | git | None | `pytest tests/unit/`, `ruff check`, `bench_tps.py --dry-run` all green. |

Files touched: 4 (1 new test file, 3 edits).

---

## Per-task detail

### B1 — Add `pipeline_bench_skip:` to `config/backends.yaml`

**Location**: Append to `config/backends.yaml` after the existing
`speculative_decoding:` block (last block in the file).

If `TASK_MODEL_REFRESH_V7` has landed `embedding_candidates:` in the same
location, append AFTER that block instead.

```yaml
# ── Pipeline-mode bench skip list ─────────────────────────────────────────
# Workspaces that exist in workspace_routing for routing/dispatch reasons
# but should NOT be exercised by bench_tps.py in pipeline mode. The
# bench_tps.py text-prompt harness cannot meaningfully exercise streaming
# ASR, TTS, or other audio-modality models — running them produces noise
# that pollutes the Grafana benchmarks dashboard.
#
# Mirrors the existing bench_skip: true flag on mlx_models[] entries
# (which excludes direct-mode benching). pipeline_bench_skip is the
# workspace-level analog.
#
# An explicit --workspace <id> filter on bench_tps.py overrides this list
# (operator wants to probe that specific workspace intentionally).
#
# Speech / audio-modality benches should be exercised by
# TASK_SPEECH_SHOOTOUT_V1.md (deferred — see P5_ROADMAP.md
# P5-FUT-SPEECH-002), which uses a dedicated audio-prompt driver, not
# bench_tps.py.
pipeline_bench_skip:
- bench-voxtral-realtime    # Mistral streaming ASR — audio-modality probe required
- bench-voxtral-tts         # Mistral TTS — audio-output probe required
- bench-granite-speech      # IBM ASR with keyword biasing — audio-modality probe required
```

**Verify B1**:

```bash
python3 -c "
import yaml
cfg = yaml.safe_load(open('config/backends.yaml'))
skip = cfg.get('pipeline_bench_skip', [])
assert isinstance(skip, list), f'Expected list, got {type(skip)}'
expected = {'bench-voxtral-realtime', 'bench-voxtral-tts', 'bench-granite-speech'}
assert set(skip) == expected, f'Mismatch: {set(skip) ^ expected}'
print(f'OK — pipeline_bench_skip has {len(skip)} entries')
"
```

**Rollback B1**: `git checkout config/backends.yaml`

### B2 — Add `bench_skip: true` to the 3 speech model entries

**Context**: V7 T1.4 / T1.5 / T1.6 added the speech model entries. This
task adds `bench_skip: true` to each, so `bench_direct()` also skips them
(line 1006 of `bench_tps.py` already respects this flag).

**Location**: `config/backends.yaml`, in the `mlx-apple-silicon` backend's
`mlx_models:` list. Find the 3 entries V7 added; add the new field
alongside existing fields. Order within an entry does not matter for YAML.

```yaml
  - id: mlx-community/granite-speech-4.1-2b
    memory_gb: 4
    big_model: false
    is_vlm: false
    supports_tools: false
    bench_skip: true     # ← ADD THIS LINE
    notes: "IBM Granite Speech 4.1 2B ..."

  - id: mlx-community/Voxtral-4B-TTS-2603-mlx-6bit
    memory_gb: 4
    big_model: false
    is_vlm: false
    supports_tools: false
    bench_skip: true     # ← ADD THIS LINE
    notes: "Mistral Voxtral 4B TTS 2603 ..."

  - id: mlx-community/Voxtral-Mini-4B-Realtime-2602-4bit
    memory_gb: 3
    big_model: false
    is_vlm: false
    supports_tools: false
    bench_skip: true     # ← ADD THIS LINE
    notes: "Mistral Voxtral Mini 4B Realtime 2602 ..."
```

**Verify B2**:

```bash
python3 -c "
import yaml
cfg = yaml.safe_load(open('config/backends.yaml'))
mlx = next(b for b in cfg['backends'] if b['id'] == 'mlx-apple-silicon')['mlx_models']
flagged = [m['id'] for m in mlx if m.get('bench_skip')]
expected = {
    'mlx-community/granite-speech-4.1-2b',
    'mlx-community/Voxtral-4B-TTS-2603-mlx-6bit',
    'mlx-community/Voxtral-Mini-4B-Realtime-2602-4bit',
}
assert set(flagged) == expected, f'Mismatch: have {set(flagged)}, want {expected}'
print(f'OK — {len(flagged)} models flagged bench_skip')
"
```

**Note**: If V7 has not yet landed, B2 is skipped and the corresponding
field is added directly to V7's T1.4 / T1.5 / T1.6 entries when V7
authors them. Either way the result is the same.

**Rollback B2**: `git checkout config/backends.yaml`

### B3 — Patch `_config_workspaces()` in `bench_tps.py`

**Location**: `tests/benchmarks/bench_tps.py`, function `_config_workspaces`
at line 1098.

**Current** (lines 1098-1106):

```python
def _config_workspaces() -> list[str]:
    """All workspace IDs from backends.yaml, sorted by primary backend group.

    Sorting by the first group in each workspace's routing list keeps the same
    backend active across consecutive tests, minimising model swaps.
    """
    cfg = _load_backends_config()
    routing: dict[str, list[str]] = cfg.get("workspace_routing", {})
    return sorted(routing.keys(), key=lambda ws: (routing[ws][0] if routing[ws] else "", ws))
```

**Replace with**:

```python
def _config_workspaces() -> list[str]:
    """All workspace IDs from backends.yaml, sorted by primary backend group.

    Sorting by the first group in each workspace's routing list keeps the same
    backend active across consecutive tests, minimising model swaps.

    Workspaces listed in the top-level `pipeline_bench_skip:` list are
    excluded — see backends.yaml for rationale. The exclusion does NOT
    apply when bench_pipeline() is called with an explicit workspace
    filter (operator-driven probe overrides config-level skip).
    """
    cfg = _load_backends_config()
    routing: dict[str, list[str]] = cfg.get("workspace_routing", {})
    skip = set(cfg.get("pipeline_bench_skip", []))
    return sorted(
        (ws for ws in routing.keys() if ws not in skip),
        key=lambda ws: (routing[ws][0] if routing[ws] else "", ws),
    )
```

**Then** update `bench_pipeline()` at line 2398 to honor `--workspace`
override. Find:

```python
    workspaces = _config_workspaces()
    if workspace_filter:
        workspaces = [w for w in workspaces if w == workspace_filter]
```

**Replace with**:

```python
    if workspace_filter:
        # Explicit operator filter overrides pipeline_bench_skip — operator
        # wants to probe this specific workspace intentionally.
        cfg = _load_backends_config()
        routing: dict[str, list[str]] = cfg.get("workspace_routing", {})
        workspaces = [workspace_filter] if workspace_filter in routing else []
    else:
        workspaces = _config_workspaces()
```

**Verify B3** (smoke):

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from tests.benchmarks.bench_tps import _config_workspaces
ws = _config_workspaces()
print(f'_config_workspaces() returned {len(ws)} entries')
skip = {'bench-voxtral-realtime', 'bench-voxtral-tts', 'bench-granite-speech'}
leaked = skip & set(ws)
assert not leaked, f'Skip leaked through: {leaked}'
print('OK — skip list honored in _config_workspaces()')
"
```

**Rollback B3**: `git checkout tests/benchmarks/bench_tps.py`

### B4 — Unit test for the skip mechanism

**New file**: `tests/unit/test_bench_skip.py`

```python
"""Tests for the pipeline_bench_skip mechanism in bench_tps.py.

The skip list lives in config/backends.yaml top-level and is honored by
_config_workspaces(). An explicit --workspace filter passed to
bench_pipeline() overrides the skip.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _make_cfg(skip_list: list[str] | None = None) -> dict:
    """Build a minimal backends.yaml-shaped config for testing."""
    cfg = {
        "backends": [],
        "workspace_routing": {
            "auto": ["mlx", "general"],
            "auto-coding": ["mlx", "coding"],
            "bench-something": ["mlx", "coding"],
            "bench-voxtral-realtime": ["mlx", "general"],
            "bench-granite-speech": ["mlx", "general"],
        },
        "defaults": {"fallback_group": "general"},
    }
    if skip_list is not None:
        cfg["pipeline_bench_skip"] = skip_list
    return cfg


def test_skip_list_excludes_workspaces() -> None:
    from tests.benchmarks import bench_tps

    skip = ["bench-voxtral-realtime", "bench-granite-speech"]
    with patch.object(bench_tps, "_load_backends_config", return_value=_make_cfg(skip)):
        ws = bench_tps._config_workspaces()
    assert "bench-voxtral-realtime" not in ws
    assert "bench-granite-speech" not in ws
    # Non-skipped workspaces still present
    assert "auto" in ws
    assert "auto-coding" in ws
    assert "bench-something" in ws


def test_skip_list_absent_means_no_filter() -> None:
    """A missing pipeline_bench_skip key should not filter anything."""
    from tests.benchmarks import bench_tps

    with patch.object(bench_tps, "_load_backends_config", return_value=_make_cfg(None)):
        ws = bench_tps._config_workspaces()
    assert "bench-voxtral-realtime" in ws
    assert "bench-granite-speech" in ws


def test_skip_list_empty_means_no_filter() -> None:
    """An empty pipeline_bench_skip list should not filter anything."""
    from tests.benchmarks import bench_tps

    with patch.object(bench_tps, "_load_backends_config", return_value=_make_cfg([])):
        ws = bench_tps._config_workspaces()
    assert "bench-voxtral-realtime" in ws
    assert "bench-granite-speech" in ws


def test_real_backends_yaml_has_consistent_skip_list() -> None:
    """Integration check against the real backends.yaml.

    Every workspace listed in pipeline_bench_skip must exist in
    workspace_routing — otherwise it's a typo. Inverse not required:
    workspace_routing may legitimately contain workspaces not in the
    skip list.
    """
    cfg = yaml.safe_load((PROJECT_ROOT / "config" / "backends.yaml").read_text())
    skip = set(cfg.get("pipeline_bench_skip", []))
    routing = set(cfg.get("workspace_routing", {}).keys())
    orphans = skip - routing
    assert not orphans, f"pipeline_bench_skip references unknown workspaces: {orphans}"
```

**Verify B4**:

```bash
pytest tests/unit/test_bench_skip.py -v
# expect 4 passed
pytest tests/unit/ -q --tb=short
# all other unit tests still pass
```

**Rollback B4**: `rm tests/unit/test_bench_skip.py`

### B5 — Rewrite `PORTAL5_BENCH_EXECUTE_V1.md`

This is the biggest edit. Walk through the doc in order, applying the
specific changes below. Do NOT do a wholesale rewrite — the doc is
already structured correctly, only the data/numbers/examples need
refreshing.

#### B5.1 — Header counts table (lines 17-25)

**Before**:

```markdown
## What Gets Benchmarked

Counts are derived at run time from `config/backends.yaml` and `config/personas/`. The current catalog (HEAD, 2026-05-23) is:

| Tier | Count |
|---|---|
| MLX models (T1) | 43 |
| Ollama models (T2) | 27 |
| Pipeline workspaces | 44 (19 auto-* + 25 bench-*) |
| Personas | 110 |
| **Total tests** | **~224** |
```

**After** (V7 post-merge state):

```markdown
## What Gets Benchmarked

Counts are derived at run time from `config/backends.yaml` and
`config/personas/`. The current catalog (HEAD, <FILL IN AT MERGE TIME:
short-sha, YYYY-MM-DD>) is:

| Tier | Count |
|---|---|
| MLX models (T1) | 49 (46 benched, 3 skipped via `bench_skip: true`) |
| Ollama models (T2) | 27 |
| Pipeline workspaces | 50 (19 auto-* + 29 bench-* + 1 tools-specialist + 1 auto-router; 3 bench-* skipped via `pipeline_bench_skip`) |
| Personas | 116 |
| **Total tests** | **~240** |

The skipped MLX entries and skipped workspaces are speech-modality models
that cannot be meaningfully exercised by the text-prompt bench harness —
see TASK_SPEECH_SHOOTOUT_V1 (deferred). The skip is config-driven; no
operator flag needed.
```

If V7 has NOT landed at the time of this task's execution, use the
pre-V7 counts (43 MLX / 43 workspaces / 110 personas / 24 bench) and
adjust the speech-skip language to refer only to the mechanism.

#### B5.2 — Bench workspace table (lines 49-70)

**Remove** the `bench-llama4-scout` row (line 63). Add a one-line
historical note above the table:

```markdown
> Historical note: `bench-llama4-scout` (Llama-4-Scout-17B MLX) was removed
> at HEAD by commit `9c657b3` after 57 GB Metal OOM crashes on M4 Pro.
> Do not re-add without a hardware-tier change.
```

**Append** the 6 V7 entries to the table:

```markdown
| bench-apriel-nemotron | reasoning | Apriel-Nemotron-15B-Thinker-8bit MLX (ServiceNow+NVIDIA) |
| bench-qwen36-27b-ud | coding | unsloth/Qwen3.6-27B-UD-MLX-4bit (Unsloth Dynamic 2.0 probe) |
| bench-qwen36-35b-a3b-ud | coding | unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit (Unsloth Dynamic 2.0 probe) |
| bench-voxtral-realtime | (skipped — speech) | Voxtral-Mini-4B-Realtime-2602-4bit MLX |
| bench-voxtral-tts | (skipped — speech) | Voxtral-4B-TTS-2603-mlx-6bit MLX |
| bench-granite-speech | (skipped — speech) | granite-speech-4.1-2b MLX |
```

#### B5.3 — Auto workspace table (lines 35-46)

The doc lists "auto" workspaces but does NOT list `tools-specialist`.
Add it to the auto-workspace section since it's a production workspace,
not a `bench-*`. Insert a single row:

```markdown
| tools-specialist | coding | ToolACE-2.5-Llama-3.1-8B MLX (production tool-calling specialist) |
```

#### B5.4 — Dry-run expected counts (lines 138-143)

**Before**:

```markdown
Expected output:
\```
MLX models:    43
Ollama models: 27
Workspaces:    44
Personas:      110
Total to test: ~224 (mode=all)
\```
```

**After** (V7 post-merge):

```markdown
Expected output (V7 post-merge):
\```
MLX models:    46 (3 skipped via bench_skip)
Ollama models: 27
Workspaces:    47 (3 skipped via pipeline_bench_skip)
Personas:      116
Total to test: ~236 (mode=all)
\```
```

If V7 has NOT landed, leave the pre-V7 numbers and add a TODO comment
that this section gets refreshed when V7 lands.

#### B5.5 — `--workspace` example with stale ID (line 254)

**Before**:

```bash
# Retest one workspace
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace bench-llama4-scout --runs 3
```

**After**:

```bash
# Retest one workspace
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace bench-qwen3-coder-next --runs 3
```

(`bench-qwen3-coder-next` is the new example because it's the same size
class as the removed Scout — 46 GB MoE — and exercises the same memory-
reclaim pressure path that the example was originally written to
demonstrate.)

Add a new example immediately after, showing how to **probe** a skipped
speech workspace:

```bash
# Probe a workspace that is in pipeline_bench_skip (operator override)
# The --workspace filter overrides the skip list — useful for one-off
# checks that the workspace exists and dispatches correctly, even though
# the resulting TPS number is meaningless for a speech model.
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace bench-voxtral-realtime --runs 1
```

#### B5.6 — "Known Behavior Notes" section (lines 362-374)

**Remove** the Llama-4-Scout bullet (line 364) entirely.

**Update** the V7 vision models bullet (line 367) to remove the
"same path as Llama-4-Scout" reference. Replace with:

```markdown
- **V7 vision models** (`bench-nemotron-omni`, `bench-olmocr2`, `bench-nanonets-ocr2`): run via mlx-vlm. `bench-nemotron-omni` is ~15GB MoE — needs ~25GB free. OCR models (`bench-olmocr2`, `bench-nanonets-ocr2`) are bench-only; not promoted to production routing.
```

**Add** new bullets at the end of the section:

```markdown
- **V7 reasoning candidate** (`bench-apriel-nemotron`): ServiceNow+NVIDIA dense 15B with native `<think>...</think>` traces (8-bit MLX, ~16 GB). For apples-to-apples TPS vs other reasoning workspaces, the same 512-token budget + `enable_thinking=False` injection applies as for `bench-laguna` and `bench-phi4-reasoning`.

- **V7 Unsloth UD quant probes** (`bench-qwen36-27b-ud`, `bench-qwen36-35b-a3b-ud`): paired with stock 4-bit counterparts (`bench-qwen36-27b`, `bench-qwen36-35b-a3b`) for head-to-head quality probe. Run the UD entry **immediately after** its stock counterpart in the size-ordered sweep (the `--order size` default does this automatically — both pairs share the same `memory_gb`). Both entries inherit `chat_template_override: qwen3.6` from backends.yaml so `patch-qwen-templates.py` handles them identically.

- **V7 speech workspaces** (`bench-voxtral-realtime`, `bench-voxtral-tts`, `bench-granite-speech`): listed in `config/backends.yaml` `pipeline_bench_skip:`. The default `--mode all` run **skips these workspaces in pipeline mode and skips their MLX model in direct mode** (`bench_skip: true` on the model entry). Operator can still probe them via `--workspace <id>` (overrides the skip list), but the text-prompt harness cannot exercise streaming ASR / TTS meaningfully — actual speech benchmarking is deferred to TASK_SPEECH_SHOOTOUT_V1 (see P5_ROADMAP.md P5-FUT-SPEECH-002).

- **`tools-specialist` workspace**: production workspace promoted in commit 12a912a (2026-05-24). Wired to `ToolACE-2.5-Llama-3.1-8B-4bit-mlx`. In `WORKSPACE_PROMPT_MAP` as "coding" (closest match for the tool-calling CC-01 baseline). Earlier dashboard runs may show this workspace as "general" — that's a pre-V7 drift fix.
```

#### B5.7 — Document the new skip mechanism in a new subsection

Insert a new subsection between "Pre-Flight Checklist" (line 93) and
"Execution" (line 149), titled "Skip Mechanism Reference":

```markdown
## Skip Mechanism Reference

`bench_tps.py` honors two config-driven skip lists in
`config/backends.yaml`:

1. **`mlx_models[].bench_skip: true`** — excludes an MLX model from
   **direct mode** (the `bench_direct()` iterator at line 1006). The
   model still loads on demand if a pipeline workspace dispatches to it,
   but the standalone load+TPS probe is skipped.

2. **`pipeline_bench_skip: [<ws-id>, ...]`** — top-level list. Excludes
   workspaces from **pipeline mode** (the `bench_pipeline()` iterator).
   The workspace still exists in `workspace_routing` for production
   dispatch; the bench just doesn't iterate it.

Use BOTH for speech / audio-modality models so neither mode runs them.
Both flags are overridden by an explicit `--workspace <id>` or
`--model <id>` filter — operator probes win.

Inspect the current state:

\```bash
python3 -c "
import yaml
cfg = yaml.safe_load(open('config/backends.yaml'))
mlx = next(b for b in cfg['backends'] if b['id'] == 'mlx-apple-silicon')['mlx_models']
direct_skip = [m['id'] for m in mlx if m.get('bench_skip')]
pipeline_skip = cfg.get('pipeline_bench_skip', [])
print(f'Direct-mode skip ({len(direct_skip)}):')
for m in direct_skip: print(f'  - {m}')
print(f'Pipeline-mode skip ({len(pipeline_skip)}):')
for w in pipeline_skip: print(f'  - {w}')
"
\```

Adding a new skipped model:

1. Set `bench_skip: true` on its `mlx_models[]` entry in `backends.yaml`.
2. Set `pipeline_bench_skip:` to include any workspace IDs that dispatch
   to it.
3. Run the inspect command above to confirm the new entries are picked up.
4. Re-run the dry-run plan (`--dry-run`) to verify the totals decrement.
```

#### B5.8 — Update document audit date

At the top of "What Gets Benchmarked", change "HEAD, 2026-05-23" to
"HEAD <commit-sha-at-task-merge>, <YYYY-MM-DD>". Use the actual commit
sha and date of when this task lands.

#### B5.9 — Final Deliverables section (lines 375-383)

Update the result count expectation:

**Before**:

```markdown
1. `tests/benchmarks/results/bench_tps_<timestamp>Z.json` exists with ≥220 results
```

**After**:

```markdown
1. `tests/benchmarks/results/bench_tps_<timestamp>Z.json` exists with ≥230 results (V7 post-merge: 46 direct MLX + 27 Ollama + 47 workspaces + 116 personas ≈ 236; minor variance from network/timeouts is normal)
```

**Verify B5**: 

```bash
# All stale Llama-4-Scout references purged from the doc
grep -c "llama4-scout\|Llama-4-Scout" tests/PORTAL5_BENCH_EXECUTE_V1.md
# Expect: 1 (the single historical note added in B5.2) or 0 if no historical note

# V7 entries all present
for ws in bench-apriel-nemotron bench-qwen36-27b-ud bench-qwen36-35b-a3b-ud \
         bench-voxtral-realtime bench-voxtral-tts bench-granite-speech \
         tools-specialist; do
    grep -q "$ws" tests/PORTAL5_BENCH_EXECUTE_V1.md && echo "OK: $ws" || echo "MISSING: $ws"
done

# Skip mechanism documented
grep -q "pipeline_bench_skip" tests/PORTAL5_BENCH_EXECUTE_V1.md && echo "OK: skip mechanism documented"

# Date is current (no longer "2026-05-23")
grep "2026-05-23" tests/PORTAL5_BENCH_EXECUTE_V1.md && echo "FAIL: stale date" || echo "OK: date updated"
```

**Rollback B5**: `git checkout tests/PORTAL5_BENCH_EXECUTE_V1.md`

### B6 — Commit and verify

```bash
# Already tagged pre-bench-execute-refresh at the start.

# Final verification:
python3 -c "
import yaml, sys
sys.path.insert(0, '.')
from tests.benchmarks.bench_tps import _config_workspaces
cfg = yaml.safe_load(open('config/backends.yaml'))
# Skip list present
skip = cfg.get('pipeline_bench_skip', [])
assert skip, 'pipeline_bench_skip is empty or missing'
# Skip list honored
ws = _config_workspaces()
leaked = set(skip) & set(ws)
assert not leaked, f'Skip leaked: {leaked}'
print(f'OK — pipeline_bench_skip honors {len(skip)} entries')
print(f'OK — _config_workspaces returns {len(ws)} entries (skipping {len(skip)})')
# Direct-mode skip also present on those models
mlx = next(b for b in cfg['backends'] if b['id'] == 'mlx-apple-silicon')['mlx_models']
direct_skip = {m['id'] for m in mlx if m.get('bench_skip')}
print(f'OK — direct-mode bench_skip flagged on {len(direct_skip)} models')
"

# Tests:
pytest tests/unit/test_bench_skip.py -v
pytest tests/unit/ -q --tb=short

# Ruff:
ruff check tests/benchmarks/bench_tps.py tests/unit/test_bench_skip.py
ruff format --check tests/benchmarks/bench_tps.py tests/unit/test_bench_skip.py

# Bench-tps dry-run plan should show reduced counts:
python3 tests/benchmarks/bench_tps.py --mode all --order size --dry-run 2>&1 | head -10

# Stage and commit:
git add config/backends.yaml \
        tests/benchmarks/bench_tps.py \
        tests/unit/test_bench_skip.py \
        tests/PORTAL5_BENCH_EXECUTE_V1.md

git commit -m "feat(bench): pipeline_bench_skip mechanism + bench-execute doc refresh

MECHANISM:
- Add top-level pipeline_bench_skip: list to config/backends.yaml.
  Workspace-level analog of the existing bench_skip: true flag on
  mlx_models[] entries.
- Patch _config_workspaces() in tests/benchmarks/bench_tps.py to
  honor pipeline_bench_skip. Explicit --workspace filter overrides.
- Seed skip list with V7 speech workspaces (bench-voxtral-realtime,
  bench-voxtral-tts, bench-granite-speech) — text-prompt harness
  cannot meaningfully exercise streaming ASR/TTS models.
- Set bench_skip: true on the 3 V7 speech mlx_models[] entries
  (belt-and-suspenders — direct-mode skip in addition to pipeline).
- Add tests/unit/test_bench_skip.py with 4 test cases.

DOC REFRESH (tests/PORTAL5_BENCH_EXECUTE_V1.md):
- Remove stale bench-llama4-scout references (model removed at HEAD
  by commit 9c657b3, 57GB Metal OOM).
- Update header counts to v7.0.0 state.
- Add V7 bench entries to the workspace table with correct dispositions.
- Add tools-specialist to the auto-workspace section (promoted in
  commit 12a912a, was previously missing from doc).
- Update dry-run plan expected output.
- Replace stale --workspace example.
- Add 'Skip Mechanism Reference' subsection documenting both flags.
- Refresh audit date to current HEAD."

git tag v7.0.0-bench-refresh
```

---

## Post-milestone success indicators

After this task lands, all should hold:

1. `pytest tests/unit/test_bench_skip.py -v` passes 4/4.
2. `pytest tests/ -q` passes — no regressions.
3. `ruff check .` and `ruff format --check .` pass.
4. `python3 -c "import yaml; cfg=yaml.safe_load(open('config/backends.yaml')); print(cfg['pipeline_bench_skip'])"` shows 3 entries.
5. `python3 tests/benchmarks/bench_tps.py --mode all --dry-run` shows reduced workspace count (49 → 46 in pipeline mode) and reduced MLX direct count (49 → 46).
6. `python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace bench-voxtral-realtime --dry-run` still includes the workspace (operator override works).
7. `grep -c "llama4-scout\|Llama-4-Scout" tests/PORTAL5_BENCH_EXECUTE_V1.md` is ≤1 (only the historical note).
8. `tests/PORTAL5_BENCH_EXECUTE_V1.md` mentions all 6 V7 bench workspaces and `tools-specialist`.
9. The doc's "Skip Mechanism Reference" section exists and documents both flags.
10. Document audit date is current (post-merge sha + date).
11. First post-V7 bench run produces a results JSON with ~236 entries (vs ~224 pre-V7) and zero results for the 3 skipped speech workspaces in pipeline mode and zero for the 3 skipped speech models in direct mode.

If any of (1)-(11) fail, roll back via:

```bash
git reset --hard pre-bench-execute-refresh
git tag -d pre-bench-execute-refresh v7.0.0-bench-refresh
```

---

## Follow-on tasks (NOT this task — recorded for visibility)

1. **TASK_SPEECH_SHOOTOUT_V1.md** — design and implement the dedicated
   speech-benchmark driver (`tests/audio_probe.py` or similar) that
   exercises Voxtral-Realtime, Voxtral-TTS, Granite-Speech with audio
   prompts. Score on WER (ASR), F1 (keyword biasing), TTFT (streaming),
   and subjective Likert (TTS). Implements P5-FUT-SPEECH-002.
2. **TASK_BENCH_TPS_FACTORING_V1.md** — if `pipeline_bench_skip` proves
   useful, generalize to a `bench_modes_skip:` per-workspace dict that
   allows fine-grained skip-direct / skip-pipeline / skip-persona. Defer
   until a second skip-case emerges.
3. **TASK_GRAFANA_DASHBOARD_V7.md** — update the Grafana dashboard
   layout for v7.0.0 to:
   - Color-code UD vs stock 4-bit quant probes for head-to-head comparison.
   - Add a dedicated panel for Apriel-Nemotron vs Magistral-Small-2509
     (the auto-mistral promotion candidate path).
   - Hide the 3 skipped speech workspaces from the default view.

---

*End of TASK_BENCH_EXECUTE_V7_UPDATE.md*
