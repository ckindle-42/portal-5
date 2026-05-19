# Vendored Chat Templates

These Jinja templates patch known bugs in the official Qwen 3.5 and 3.6 chat
templates. They are bundled with Portal 5 so the project owns its own copy and
the patch is reproducible.

## Source

- Upstream: https://huggingface.co/froggeric/Qwen-Fixed-Chat-Templates
- Author: froggeric (HuggingFace)
- License: Apache-2.0 (inherited from Qwen / Alibaba Cloud)

## What the patches fix

| Symptom on Portal 5 | Root cause | This template's fix |
|---|---|---|
| Tool calls fail / crash on `mlx_lm.server` / `mlx_vlm.server` | Python-only Jinja filters `\|items`, `\|safe` | Replaced with direct dict iteration + type-aware serialization |
| Empty `<think></think>` blocks in conversation history waste ctx | Official template emits them unconditionally | Skipped when `reasoning_content` is empty |
| `developer` role rejected | Official template only accepts `system` | Mapped to system role |
| Qwen 3.6 `</thinking>` hallucination breaks parser (3.6 file only) | Parser splits on `</think >` only | Detects which closing tag was emitted; splits accordingly |
| No runtime thinking toggle | None | `<|think_on|>` / `<|think_off|>` accepted in system/user content |

## Update procedure

If the upstream publishes a corrected revision, run from repo root:

```bash
# 1. Edit the pinned commit in scripts/patch-qwen-templates.py UPSTREAM_COMMIT
# 2. Re-fetch + re-stamp SHA256SUMS:
./scripts/patch-qwen-templates.py --refetch
# 3. Re-run the patcher on all configured models:
./launch.sh patch-qwen-templates
# 4. Run UAT on each affected workspace:
python3 tests/portal5_uat_driver.py --workspace auto --runs 1
```

## How models opt in

Each MLX model entry in `config/backends.yaml` may carry an optional
`chat_template_override: qwen3.5` or `chat_template_override: qwen3.6` field.
Models without this field are left untouched. The override is applied by
`scripts/patch-qwen-templates.py`; the corresponding model directory's
`chat_template.jinja` is replaced (original backed up to
`chat_template.jinja.portal5-backup`) and `tokenizer_config.json["chat_template"]`
is updated in place.
