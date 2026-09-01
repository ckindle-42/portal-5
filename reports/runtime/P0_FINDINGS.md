# P0 — Freeze, protect, understand the drift

Date: 2026-09-01 · Host: darwin arm64 · Python 3.13.12 (uv-managed)

## P0.1 — Working-venv fingerprint

`reports/runtime/venv-working-20260901T084333.txt` (252 lines, committed). Key packages
**as actually installed in `.venv`**:

| package | live venv | uv.lock (`--all-extras`) | direction |
|---|---|---|---|
| mlx | 0.32.0 | 0.31.2 | venv ahead |
| mlx-embeddings | 0.1.0 | 0.0.5 | venv ahead (has `qwen3_vl`) |
| mlx-vlm | 0.6.13 | 0.3.12 | venv ahead |
| mlx-lm | 0.31.3 | (lock) | ~ |
| mlx-audio | 0.4.8 | 0.4.8 | equal |
| transformers | 5.15.0 | 5.16.1 | **venv behind** |
| tokenizers | 0.22.2 | 0.23.1 | venv behind |
| torch | **2.13.0** | 2.11.0 | venv ahead |
| torchaudio | 2.11.0 | — | pre-existing torch/torchaudio skew in the venv |
| torchvision | **absent** | **absent** | the blocker |
| numpy | 2.5.2 | 2.4.4 | venv ahead |

**V4 Part 1 assumed torch 2.11.0. Live torch is 2.13.0** → per §1.1's own table
`torchvision==0.28.0` pins `torch==2.13.0`, so torchvision can be added with **no torch
move**. (Verify 0.28.0→2.13.0 against PyPI before locking.)

## P0.2 — Restorable venv copy

`~/.portal5/backups/venv-working-20260901T084339` (2.3 GB). Verified: its interpreter
runs and `import mlx_embeddings` succeeds. Usable as a restore source.

## P0.3 — Why `uv run --project` is not syncing  → **MECHANISM: nothing suppresses it**

- `scripts/embedding-launchd-wrapper.sh` MLX arm: `exec "$UV_BIN" run --project "$PORTAL_ROOT" python3 scripts/embedding-server-mlx.py …` — **no `--frozen`, no `--no-sync`**.
- No `[tool.uv]` table in `pyproject.toml`. No `UV_*` env in interactive shell or wrapper. `UV_PROJECT_ENVIRONMENT` unset (→ default `.venv`). `VIRTUAL_ENV` unset. uv 0.10.7.
- `uv lock --check` → **passes** (lock matches pyproject).
- `uv sync --all-extras --check` → **hard fail**: "would uninstall 133, install 74",
  including `mlx-embeddings 0.1.0→0.0.5`, `mlx 0.32.0→0.31.2`, `mlx-vlm 0.6.13→0.3.12`,
  `torch 2.13.0→2.11.0`, `transformers 5.15.0→5.16.1`. Full diff:
  `reports/runtime/sync-check-diff-20260901T084326.txt`.

**Conclusion:** `uv run` is not being *prevented* from syncing — it simply **has not
executed since the venv was hand-patched**. The live `:8917` process (PID 84047) predates
the drift. The next launchd restart runs `uv run` → syncs → **destroys the VL-capable
runtime and reverts `:8917` to `mlx-embeddings 0.0.5`**. Pinning the lock to the venv is
necessary but **not sufficient**: the wrapper must also switch to `--frozen`/`--no-sync`
plus a loud drift assertion (P1.5), because any *future* drift recurs the same way.

## P0.4 — Verbatim blocker + runtime (never separated again, §1.3)

`reports/runtime/vl-blocker-verbatim.txt`. Versions: mlx-embeddings 0.1.0, mlx 0.32.0,
mlx-vlm 0.6.13, transformers 5.15.0, torch 2.13.0, torchvision **absent**.
`mlx_embeddings.models` includes `qwen3_vl`. Load of both
`mlx-community/Qwen3-VL-Embedding-2B-mxfp8` and `Qwen/Qwen3-VL-Embedding-2B` fails:

```
  File ".../mlx_embeddings/models/qwen3_vl/processor.py", line 90, in from_pretrained
    image_processor = AutoImageProcessor.from_pretrained(
  File ".../transformers/utils/import_utils.py", line 2363, in __getattribute__
    requires_backends(cls, cls._backends)
ImportError:
AutoImageProcessor requires the Torchvision library but it was not found in your environment.
```
Wrapped by mlx-embeddings as `ValueError: Failed to initialize tokenizer or processor: …`.
Exactly V4 §1.1. Gate is on the class via `__getattribute__` → no kwarg avoids it.

## P0.5 — Accidental-sync blast radius

**NOT YET RUN** (throwaway `mlx-embeddings==0.0.5` + live `mlx` load of the `mode: mxfp8`
model). Deferred pending the scope decision below — but the sync-check diff already proves
an accidental sync reverts `mlx` to 0.31.2 as well, so the 0.0.5-loads-mxfp8 question is
about *whether `:8917` also dies*, not whether the VL path dies (it does, certainly).

## P0.6 — Live state (several V4 premises already crossed)

| item | V4 said | actual |
|---|---|---|
| `:8942` VL server | "up, `/health` empty — kill it" | **not running** (conn refused, no listener). Nothing to kill. |
| `:8917` `/ready` | implied present | **404** — only `/health` exists. `/health` non-empty, `loaded:true`, model `~/.portal5/models/Qwen3-Embedding-0.6B-mxfp8`. |
| `:8925` reranker | referenced | up, **Docker** container (127.0.0.1:8925). |
| `PORTAL5_LANCE_DIR` | "default `/Volumes/data01/portal5_lance` not mounted" | env unset; `/Volumes/data01` **is** mounted but `/Volumes/data01/portal5_lance` **does not exist at all**. Only `portal5_lance_presnapshot_20260831T233605.tgz` sits at the volume root. The KB/graph store has no on-disk home right now. |
| `~/.portal5/embedding-venv/` | "no `bin/python3`" | `bin/python3 → python3.14 → /opt/homebrew/.../python@3.14/3.14.6` (resolves). Only used when `EMBEDDING_BACKEND=cpu` (default is `mlx`), so currently dormant. Still a trap. |
| on-disk model quantization | — | `{'group_size': 32, 'bits': 8, 'mode': 'mxfp8'}` — genuine MXFP8, matches V4 §1.4. |

## The scale problem V4 did not anticipate

The venv holds **250 packages**; `uv.lock --all-extras` resolves **225**; they share only
~117. The 133 venv-only packages include a **full pyannote-audio 4.0.7 / lightning 2.6.5 /
torchmetrics diarization stack**, plus `optuna`, `scikit-learn`, `numba`, `matplotlib`,
`pip-audit`, `mlx-whisper`, `torchcodec` — accreted via manual `pip install` across the
SA5 / bench / T8-T9 sessions and never declared.

"Reconcile the lock *to* the venv" (P1) at this scale is a fork, not a mechanical step:
either promote that closure into `pyproject.toml`, or let `uv sync` remove it (risking
diarization / whisper-fallback / bench tooling). This needs an operator decision before P1.
