# Landscape 2026Q3 — three-bench rollup

Base research commit `e776b3a9` is an ancestor of the tree this task ran on.
Live HEAD at P0 was `1aefe218`. Discover receipt:
`tests/benchmarks/results/landscape_2026Q3_p0_discover.json`.

No workspace default, persona pin, roster tag, or live `.env` value was changed.
`AUK_*` keys were added to `.env.example` only. The AuK server was added to
`config/portal.yaml` `mcp_fleet` on port 8940.

## Phase outcomes

| Phase | Status | Commit | Receipt |
|---|---|---|---|
| P0 discover | OK | `7499bb20` | `tests/benchmarks/results/landscape_2026Q3_p0_discover.json` |
| P1 AuK | OK | `2553339e` | `tests/benchmarks/results/auk_probe_20260922T021217Z.md` |
| P2 Qwen-Image-Edit-2509 | OK | `9c8d0103` | `tests/benchmarks/results/qwen_image_edit_2509_probe_20260922T072017Z.md` |
| P3 Granite Switch | OK | `7cbeb295` | `tests/benchmarks/results/granite_switch_compliance_20260922T025400Z.md` |

## Gates

All three operator gates are PENDING. Nothing in this task promotes a model.

- P1. Listen to the eight seat-relevant WAVs listed in the AuK report and score 1–5. Mechanical seat rate was 8/8. The task prose counted seven; the item list marks eight, including enhancement.
- P2. View the output pairs under `tests/benchmarks/results/qwen_edit_2509_outputs/`. Mechanical rates were baseline 6/6 and 2509 10/10.
- P3. Read the factuality and policy tables. Guiding threshold, not applied: boilerplate catch 12/34 (35.3%) is above the 30% tuning line and below the 50% ship line, and the SUPPORTED false-positive rate 65/141 (46.1%) is above the 30% reject line.

## What remains on disk

- `~/.portal5/auk/ckpts` — about 50 GB (torch checkpoints plus the converted MLX layout). The launchd service `com.portal5.auk` is running on port 8940.
- `~/.portal5/granite-switch/granite-switch-4.1-3b-preview` — about 7.8 GB. Bench venv only. Not an MCP.
- `tests/benchmarks/fixtures/auk_corpus` — about 752 KB.
- `tests/benchmarks/fixtures/qwen_edit_corpus` — about 5.1 MB.
- `tests/benchmarks/fixtures/compliance_edges_183.json` — about 652 KB.
- Nothing was removed by a rollback. P1 and P2 and P3 all completed.

## Disagreements with the task file

- AuK's MLX CLI is `python -m auk_mlx.cli` (`--instruction`, `--audio`, `--output`, `--flash`), not `inference_mlx.py --task`. Weights are converted once with `auk_mlx.convert`. The venv is Python 3.12 because SciPy 1.15 on Python 3.10 fails dyld on this OS.
- Seated speech is `POST /v1/audio/speech`, not `POST /synthesize`. Corpus clips came from Kokoro `af_heart` and `am_adam`, plus Qwen3 voice design for the reference.
- mflux 0.19.1 already maps the seated tag `qwen-image-edit` to `Qwen/Qwen-Image-Edit-2509`. The August arm is the HF repo `Qwen/Qwen-Image-Edit` with `--base-model qwen-image-edit`. The 2509 arm is the built-in alias `qwen-edit-2509`. The string `qwen-image-edit-2509` is not an alias. Multi-image inputs use `--image-paths`.
- System `python3` is 3.14. Granite Switch 0.1.0 requires Python >=3.11 and <3.14, so the bench venv is Homebrew Python 3.11. MPS was available.
- The row-mismatch keywords in the task match zero edges. The eight policy targets are the negative verdicts that are not the boilerplate pattern.

## Follow-up tasks (drafts only — not created)

- Promote AuK speech editing on port 8940 into a media workspace after the operator scores the eight clips.
- After viewing the pairs, decide whether the seated `qwen-image-edit` tag should stay on Qwen-Image-Edit-2509 (where mflux 0.19.1 already points it) or be pinned back to the August repo. This task did not flip the tag.
- Do not wire Granite Switch into the compliance module on these numbers. A tuning task is the follow-up only if the operator still wants the adapter.

## Operator summary

```
LANDSCAPE 2026Q3 THREE-BENCH TASK — COMPLETE

Base:  e776b3a9
Head:  7cbeb295 (phase commits); the rollup commit is the child of that
Files: 3 receipts, 1 rollup, 3 phase commits, 1 docs-currency commit

P1 AuK MLX spike:
  status: OK
  mechanical seat rate: 8/8
  operator gate: PENDING

P2 Qwen-Image-Edit-2509 probe:
  status: OK
  invocation case: alias qwen-edit-2509; August baseline is HF Qwen/Qwen-Image-Edit
  per-arm mechanical: baseline 6/6, 2509 10/10
  operator gate: PENDING

P3 Granite Switch compliance verifier:
  status: OK
  factuality boilerplate catch: 12/34 (35.3%)
  factuality SUPPORTED false-positive: 65/141 (46.1%)
  policy row-mismatch catch: 0/8 (0%)
  operator gate: PENDING

Follow-up tasks (drafts only, NOT created by this task):
  - Promote AuK on :8940 after the listen gate.
  - Keep or pin back the seated qwen-image-edit tag after the view gate.
  - Do not ship Granite Switch into compliance on a 46% supported false-positive rate.

Rule 12 docs currency: AW=pass, BS=pass
sync-config idempotent: yes
```
