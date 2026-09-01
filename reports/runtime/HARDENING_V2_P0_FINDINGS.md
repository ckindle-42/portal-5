# TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2 — P0 live discovery

<!-- evidence header (C3 standard) -->
- **command**: manual discovery session — probes recorded inline below
- **inputs**: HEAD `764197c1`→`1052e5a6` (this task's commits), live host stack
- **resolved versions**: mlx 0.32.2, mlx-vlm 0.6.17, mlx-embeddings 0.1.0,
  transformers 5.16.1, torch 2.13.0, torchvision 0.28.0, phonemizer 3.4.0,
  lancedb (installed), Python 3.13.12
- **host / timestamp**: darwin arm64 / 2026-09-01

---

## Live state at task start

| item | state |
|---|---|
| `:8942` VL server | **UP** — `/ready` `{ready:true, embed_model: mlx-community/Qwen3-VL-Embedding-2B-mxfp8, dim:2048}`. (V4's P0 found it down; it has since been started.) |
| `:8917` embedding | UP — `/health` `{status:ok, loaded:true, backend:mlx}` |
| `PORTAL5_LANCE_DIR` | unset → default `/Volumes/data01/portal5_lance`; `/Volumes/data01` **is** mounted (`os.path.ismount` True) |
| venv vs uv.lock | **no drift** — `uv sync --all-extras --frozen --check` exit 0, 182 packages. The V4-era 133-undeclared-package fork is resolved (`e62d3dca`). |
| Ollama `/api/ps` | no models loaded |

## C1 — import sweep of the reconciled venv → **`matplotlib` is NOT a real gap**

Swept every `portal/**/*.py` (package tree) and every `scripts/*.py` (all imports
anywhere in the file, including inside function bodies — the class `matplotlib`
was said to fall into). 15 modules resolve to nothing in the venv. **All 15 are
one of:**

- **Docker-MCP deps, declared in `Dockerfile.mcp`**: `matplotlib` (line 78),
  `mpl_toolkits`, `trimesh` (75), `build123d` (102), `docling` / `pypdf`
  (rag_mcp — Docker :8921), `pandas` (data_mcp — Docker :8939). CAD render is a
  Docker MCP (`:8926`), and `matplotlib>=3.8.0` sits right next to
  `trimesh[easy]` / `pyrender` in `Dockerfile.mcp` — i.e. **exactly where the
  trisurf fallback in `cad_render_mcp.py:104` runs**. The drop from host
  `pyproject.toml` was correct.
- **`sys.path`-injected local modules**: `bench_lab_exec` (tests/benchmarks on
  path), `bully_*_run` (sibling scripts), `lib` (scripts/lib).
- **retired**: `sentence_transformers` (embedding-server.py CPU arm), `evtx`
  (`corpus_ingest.py`, bench tooling), `ruamel` (`reconcile_security_arm.py`,
  dev), `minimax_mlx_model` (vendored).

**Conclusion:** the method critique in C1 stands (a source grep cannot see
function-body / failure-path imports — the sweep here does), but it produced **no
actionable host fix**. `matplotlib` is declared where its code runs. P2's
"declare matplotlib" is moot; recorded here rather than adding a speculative
host dependency.

## A2 — lance guard reproduced and fixed

`require_lance_dir` returned from a `p.is_dir()` short-circuit *before* the mount
check, so a stray `/Volumes/<vol>/portal5_lance` tree on the boot disk passed
silently; a bare `/Volumes/<vol>` dir also passed (`and not volume.is_dir()`).
Host repro of the stray-tree case needs `mkdir` under root-owned `/Volumes`
(operator `!` step) — the unit test reproduces the exact state by patching
`os.path.ismount` / `Path.is_dir`. Fixed in `764197c1`: mount check is now first
and unconditional. `tests/unit/test_lance_guard.py` (6 cases).

## Remaining P0 items (carried into the measurement phase)

- Memory reconciliation against T8's 73/216/193 (C2) — the store has no on-disk
  home yet (`PORTAL5_LANCE_DIR` unset, only the presnapshot tarball at the
  volume root). Needs the restore + `graph_memory` count probe.
- Score-dict dump for the two failing P8 queries (B1 diagnosis confirm/refute) —
  needs the P4 corpus + a live `kb_search` with instrumentation.
- Per-stage `kb_search` latency split — needs live instrumentation.
- A4 concurrency measurement (N = 2/3/5 overlapping `kb_search`).
