# DFlash2 under oMLX 0.8.0: re-enable plan

## Finding: seat, history, and current state

The repository has one explicitly documented DFlash2 seat: the `qwen38coder-dflash` role on the `auto-coding` workspace, served as `Qwen3.8-27B-4bit` by `omlx-coding`. Its separate draft checkpoint is `incoai/Qwen3.8-27B-DFlash2`, installed at `/Volumes/data01/omlx-models/Qwen3.8-27B-DFlash2` (a symlink to the HF cache). The target model config declares `model_type: qwen3_5`; the draft declares `architectures: [DFlash2DraftModel]` and `model_type: qwen3`.

`0e2728827` (2026-08-26, “replace SuperQwen3.8 with Qwen3.8-27B-4bit + DFlash2 speculative decoding”) introduced this role and recorded the original context-stall mitigation (`dflash_max_ctx: 65536`) plus an earlier decode-speed and tool-call result. It explains why the seat was added, not why it was later disabled.

The requested disable commit and reason are **not established by the named sources**. The current `~/.omlx/model_settings.json` and `model_settings.json.backup-073` both have `models["Qwen3.8-27B-4bit"].dflash_enabled: false`; both also have `mtp_enabled: false`, no `dflash_draft_model`, and no `dflash_max_ctx`. No model in either snapshot has DFlash enabled. The current settings file's mtime is Nov 15, 2026 11:55, so the file records the disabled state by then; that timestamp does not establish when or why the value changed. The Nov 15 `7b26850f3` commit removes closed engine-evaluation tooling and bench routes; its diff does not disable or remove this DFlash persona or backend seat. Do not cite it as the disable commit.

## oMLX settings schema

The installed environments report oMLX `0.7.3` and `0.8.0`. The DFlash per-model field names are unchanged between their `omlx/model_settings.py` files:

| Key | Accepted value in 0.8.0 | Default / behavior |
| --- | --- | --- |
| `dflash_enabled` | Boolean | `false`; enables the DFlash path when a draft is also configured. |
| `dflash_draft_model` | Path or repository ID string | `null` uses a draft bundled under the target's `dflash/` directory. This seat's DFlash2 checkpoint is external, so set its installed path explicitly. |
| `dflash_draft_quant_enabled` | Boolean or `null` | `null`/false leaves the draft unquantized. |
| `dflash_draft_quant_weight_bits` | `2`, `4`, or `8` | Used only when draft quantization is enabled. |
| `dflash_draft_quant_group_size` | `32`, `64`, or `128` | Used only when draft quantization is enabled. |
| `dflash_draft_window_size` | Positive integer, or `null` | `null` uses the draft checkpoint's `sliding_window` (2,048 for this installed draft); the admin route normalizes nonpositive values to `null`. |
| `dflash_block_size` | Positive integer, or `null` | `null` uses the checkpoint default; the admin route normalizes nonpositive values to `null`. |
| `dflash_verify_mode` | `adaptive`, `dflash`, `off`, or `null` | `null` means `adaptive`; the legacy `ddtree` value normalizes to `adaptive`. |

The 0.8.0 compatibility map includes `qwen3_5` for its VLM engine, matching this target's config. `dflash_enabled` and native `mtp_enabled` are mutually exclusive; the target currently has MTP disabled. The engine-pool code also requires both DFlash enabled and a draft path before it marks DFlash active.

`dflash_max_ctx` is not a model-settings field in either installed Python package and is absent from both named JSON files. The 0.8.0 Python runtime contains no implementation of that setting. The repository's backend/persona comments say the historical 65,536-token limit avoided a real stall on prompts around 70K–85K, but the installed 0.8.0 settings schema does not provide that guard. Do not assume that the old comment still describes an available 0.8.0 setting.

## Proposed `model_settings.json` delta

This applies only to the `Qwen3.8-27B-4bit` entry, which backs `qwen38coder-dflash`. It is a handoff snippet, not an edit to the host file in this task:

```diff
 "deepseek_v41_engram_ssd_offload": false,
-"dflash_enabled": false,
+"dflash_draft_model": "/Volumes/data01/omlx-models/Qwen3.8-27B-DFlash2",
+"dflash_enabled": true,
 "embedding_audio_enabled": false,
```

Leave the other DFlash fields omitted: their `null` defaults use the draft's checkpoint window/block defaults and adaptive verification, with draft quantization off. Keep `mtp_enabled: false`. The draft path and model config were confirmed to exist locally; this plan does not write `~/.omlx` or reload oMLX.

## Orchestrator A/B

Run on the same quiet host, against the same oMLX model and benchmark setup. OFF is the current settings state; ON is the proposed two-key delta above, applied and loaded by the orchestrator. Capture each command's full output. The table includes `decode tok/s` for the 2,000, 8,000, and 32,000 prompt sizes; compare those values directly. DFlash is a decode optimization, so prefill tok/s is not the pass metric.

```bash
# OFF: current Qwen3.8-27B-4bit model settings
uv run python scripts/speed_bench.py --engine omlx --model Qwen3.8-27B-4bit --sizes 2000,8000,32000

# ON: after applying the proposed settings and reloading the model
uv run python scripts/speed_bench.py --engine omlx --model Qwen3.8-27B-4bit --sizes 2000,8000,32000
```

### Pass bar

- ON shows a positive decode tok/s gain over OFF on the requested sizes, larger than the run-to-run spread if the orchestrator repeats a noisy cell. Report every size and its delta; a result with any size slower is not a clean pass for the single per-model setting.
- On the actual Open WebUI → `auto-coding` → `qwen38coder-dflash` route, replay the same fixed coding tasks and tool-use probe with identical prompts, sampling settings, and tool schemas in both modes. Compare task correctness with a blinded independent reviewer. For the tool probe, confirm the expected tool is selected, the emitted `tool_calls` JSON is valid with correctly typed arguments, and the route executes the expected call. Pass requires no new correctness regressions, invalid calls, wrong tool selection, or missing/incorrect arguments with DFlash on.

The requested sizes stop at 32K. They do not retest the historical >65K DFlash stall. Since the 0.8.0 package does not expose the previously cited `dflash_max_ctx` guard while this route advertises a 262,144-token context limit, these A/B results alone do not establish safe long-context behavior. The orchestrator must resolve or explicitly accept that gap before enabling DFlash for unrestricted production prompts.
