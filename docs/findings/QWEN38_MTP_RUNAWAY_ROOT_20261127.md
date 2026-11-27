# Qwen3.8-27B-oQ4e-mtp Runaway Reasoning — Root Cause Analysis & Live A/B Design

**Date:** 2026-11-27
**Lane:** `lane/researcher2`
**Related:** `KNOWN_LIMITATIONS.md` (`P5-OMLX-QWEN38-MTP-001`), `coding_task/ab_engine.py`, `coding_task/ab_loop.py`, `coding_task/ab_loop.out`, `coding_task/reason_ollama-gguf.txt`, `coding_task/reason_omlx-mtp.txt`
**Live status:** Static analysis + forensic log audit only; **no live requests sent** during this investigation (quiet-host rule during full QAT). Live confirmation commands are in §6 and implemented in [`coding_task/qwen38_mtp_ab.py`](../../coding_task/qwen38_mtp_ab.py).

---

## Executive Summary

Forensic comparison of the live server logs from the identical `ab_engine.py` probe (2026-11-27 01:01–01:15 CST) exposed a **38-token prompt divergence** between the two engines on the exact same OpenAI `/v1/chat/completions` payload (no `chat_template_kwargs`, no tools, identical sampling):

| Engine & model | Live log prompt tokens | Live outcome | Opening reasoning style |
| --- | ---: | --- | --- |
| **Ollama 0.40.18** `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k` (`renderer=qwen3.8`, `parser=qwen3.5`) | **131** (`/opt/homebrew/var/log/ollama.log:33472`) | `finish=stop`, 4,699 tok, 29 reasoning lines, 17,603-char answer | Fluent prose (`"The user is asking me to give my best complete answer..."`) |
| **oMLX 0.8.4** `Qwen3.8-27B-oQ4e-mtp` (`VLMBatchedEngine` + Lightning MTP) | **169** (`~/.omlx/logs/server.log`, all 7 runs) | `finish=length` (12,000 tok) 7/7, `content=""`, 714 reasoning lines (614 unique), never emits `</think>` | Telegraphic notes (`"We need respond to user: ... Oververbosity 9; code likely long."`) |

Offline tokenization with `/Volumes/data01/omlx-models/Qwen3.8-27B-oQ4e-mtp`'s tokenizer reproduces both counts **exactly**:

- `apply_chat_template(msgs, add_generation_prompt=True)` (default `reasoning_effort='xhigh'`): **169 tokens**
- `apply_chat_template(msgs, add_generation_prompt=True, reasoning_effort='medium')`: **131 tokens** (byte-for-byte identical to the prompt without the `xhigh` preamble)
- `apply_chat_template(msgs, add_generation_prompt=True, reasoning_effort='low')`: **157 tokens**
- `apply_chat_template(msgs, add_generation_prompt=True, enable_thinking=False)`: **133 tokens**

**Top hypothesis (Rank 1, high confidence):** oMLX renders `chat_template.jinja`, whose line 47 defaults `reasoning_effort` to **`xhigh`** whenever omitted, prepending the 38-token instruction `"Reasoning effort is set to xhigh. Please think carefully through the task, validate key assumptions, consider plausible alternatives, and prioritize correctness, consistency, and clarity in the final answer.\n\n"` into the system prompt. Ollama 0.40.18's native Go `renderer=qwen3.8` **does not** emit that `xhigh` preamble when `think` / `reasoning_effort` is unset (or boolean `think: true`), rendering the 131-token `medium` prompt instead. Under `xhigh` on an open-ended prompt (`"Give your best complete answer..."`), Qwen3.8 enters an expansive telegraphic planning spiral from token #1 (before any MTP verify cycle runs) and exhausts the 12k–32k token budget inside `<think>`.

**Code-path audit of Lightning MTP at `temp > 0`:** oMLX 0.8.4's `batch_generator.py` implements **exact Leviathan/Chen stochastic rejection sampling** (`_verify_on_support` + `_stochastic_verify_tokens`) over matching filtered `p` and `q` distributions, and `presence_penalty=1.5` (which bypassed the sparse/coarse-3-bit draft fast path) still failed 3/3. MTP draft acceptance on the failing runs was healthy (70.2–82.3%, 2.49–4.05 tok/cycle, 25.9–32.5 tok/s). A secondary co-factor (quantization of `lm_head` at 4-bit g64 without imatrix vs Unsloth GGUF's `Q6_K` `output.weight`, or non-row-exact verify kernels) remains testable via Arms **A1** (MTP OFF) and **A2/A4** (131-token `medium` prompt, MTP ON).

---

## 1. Static Diffs & Evidence

### 1.1 Chat Template: oMLX `chat_template.jinja` vs Unsloth GGUF vs Ollama `renderer=qwen3.8`

**Files inspected (read-only):**
- oMLX checkpoint: `/Volumes/data01/omlx-models/Qwen3.8-27B-oQ4e-mtp/chat_template.jinja` (170 lines, 8,952 B; identical copy embedded in `tokenizer_config.json:285`).
- Ollama GGUF manifest: `/Volumes/data01/ollama/models/manifests-v2/hf.co/unsloth/Qwen3.8-27B-GGUF/Q4_K_M-ctx96k`:
  - `config` blob (`sha256-e23528f1...`): `{"model_format":"gguf","model_family":"qwen35","model_families":["qwen35"],"model_type":"27.3B","file_type":"Q4_K_M","renderer":"qwen3.8","parser":"qwen3.5"}`
  - `template` blob (`sha256-b507b9c2...`, 13 B): `{{ .Prompt }}`
  - `params` blob (`sha256-d31cc8b3...`, 18 B): `{"num_ctx":98304}`
  - GGUF embedded `tokenizer.chat_template` in `sha256-322e194ff7...` (9,993 B, Unsloth's published template).

**Key lines in oMLX `chat_template.jinja` (lines 45–56 and 163–170):**
```jinja
{%- set reasoning_instructions = '' %}
{%- if enable_thinking is undefined or enable_thinking is true %}
    {%- set resolved_reasoning_effort = reasoning_effort|default('xhigh') %}
    {%- if resolved_reasoning_effort not in ('xhigh', 'medium', 'low') %}
        {{- raise_exception('Unexpected reasoning effort ' ~ reasoning_effort ~ '. Supported types are xhigh (default), medium, and low.') }}
    {%- endif %}
    {%- if resolved_reasoning_effort == 'xhigh' %}
        {%- set reasoning_instructions = 'Reasoning effort is set to xhigh. Please think carefully through the task, validate key assumptions, consider plausible alternatives, and prioritize correctness, consistency, and clarity in the final answer.' %}
    {%- elif resolved_reasoning_effort == 'low' %}
        {%- set reasoning_instructions = 'Reasoning effort is set to low. Keep your thinking brief and focused, moving directly to the conclusion without unnecessary elaboration.' %}
    {%- endif %}
{%- endif %}
...
{%- if add_generation_prompt %}
    {{- '<|im_start|>assistant\n' }}
    {%- if enable_thinking is defined and enable_thinking is false %}
        {{- '<think>\n\n</think>\n\n' }}
    {%- else %}
        {{- '<think>\n' }}
    {%- endif %}
{%- endif %}
```

**Unified diff (`omlx/chat_template.jinja` vs `gguf/tokenizer.chat_template`):**
- Both templates share the **exact same** `reasoning_effort|default('xhigh')`, `reasoning_instructions` text, system wrapper (`<|im_start|>system\n` ... `<|im_end|>\n`), user wrapper, and generation prompt (`<|im_start|>assistant\n<think>\n` vs `<think>\n\n</think>\n\n`).
- Unsloth's GGUF Jinja adds only four differences (none affecting a single `system` + `user` no-tools turn):
  1. Merges multiple leading `system`/`developer` messages (`num_sys`, `merged_system`).
  2. Maps `resolved_reasoning_effort == 'high'` → `'xhigh'`.
  3. Drops the `No user query found in messages.` guard.
  4. Validates `tool_call.name` and rejects unparsed JSON-string `tool_call.arguments`.

**Crucial runtime divergence (Ollama does NOT run the GGUF Jinja template):**
Ollama 0.40.18 logs on model load (`/opt/homebrew/var/log/ollama.log:33455`):
```text
time=2026-11-27T01:01:07.913-06:00 level=INFO source=images.go:431 msg="template selection" model=hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k selected=renderer_parser renderer=qwen3.8 parser=qwen3.5 go_template="[completion vision tools thinking]" chat_template="[tools thinking completion vision]" harmony=null renderer_parser="[completion vision tools thinking]"
```
Ollama's built-in Go `renderer=qwen3.8` takes precedence over the GGUF `tokenizer.chat_template`. Although the Ollama binary embeds both `"Reasoning effort is set to xhigh..."` and `"Reasoning effort is set to low..."` strings for explicit effort tiers, when `/v1/chat/completions` is called **without `reasoning_effort`** (as in `ab_engine.py`), Ollama's `qwen3.8` renderer does **not** inject the `xhigh` system preamble:
```text
# /opt/homebrew/var/log/ollama.log:33472, 33475, 34301–34302
slot   operator(): id  0 | task 0 | new prompt, n_ctx_slot = 98304, n_keep = 4, task.n_tokens = 131
slot init_sampler: id  0 | task 0 | init sampler, took 0.01 ms, tokens: text = 131, total = 131
slot print_timing: id  0 | task 0 | prompt eval time =    1395.01 ms /   131 tokens (   10.65 ms per token,    93.91 tokens per second)
slot print_timing: id  0 | task 0 |        eval time =  379772.43 ms /  4699 tokens (   80.84 ms per token,    12.37 tokens per second)
```
Whereas oMLX rendered the exact same `ab_engine.py` request (and all 6 `ab_loop.py` requests) through `chat_template.jinja` with `reasoning_effort` unset → `xhigh`:
```text
# ~/.omlx/logs/server.log (2026-11-27 00:27:14 – 01:15:19, 7/7 identical prompt length)
Chat completion: model=Qwen3.8-27B-oQ4e-mtp, 12000 tokens in 463.15s (25.9 tok/s), prompt: 169, finish_reason=length, max_tokens=12000, request_max_tokens=12000
```
**169 − 131 = 38 tokens** — the exact token length of `Reasoning effort is set to xhigh. Please think carefully through the task, validate key assumptions, consider plausible alternatives, and prioritize correctness, consistency, and clarity in the final answer.\n\n`.

Note on the QAT `s4-auto-coding-core` runs through OWUI → Pipeline (with tools):
- On oMLX (`~/.omlx/logs/server.log`, 2026-11-27 00:04:50): `Reserved prefill capacity for 10846 tokens` → 31,312 generated tokens (`finish=filter` on Pipeline abort).
- On Ollama (`/opt/homebrew/var/log/ollama.log:43148`, 01:53:55, after routing to Ollama): `task.n_tokens = 10190` (different tool-schema rendering + no `xhigh` preamble).

---

### 1.2 Sampling & `generation_config.json` vs Seat Sampling

| Source | `temperature` | `top_p` | `top_k` | `min_p` | `presence_penalty` | `repeat_penalty` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| oMLX `Qwen3.8-27B-oQ4e-mtp/generation_config.json` | `1.0` | `0.95` | `20` | *(unset)* | *(unset)* | *(unset)* |
| Unsloth GGUF `general.sampling.*` metadata | `1.0` | `0.95` | `20` | *(unset)* | *(unset)* | *(unset)* |
| `config/model_card_expectations.yaml` `qwen3.8` (`thinking`) | `1.0` | `0.95` | `20` | `0.0` | `0.0` | `1.0` |
| `config/model_card_expectations.yaml` `qwen3.8` (`instruct`) | `0.7` | `0.8` | `20` | `0.0` | `1.5` | `1.0` |
| `config/portal.yaml` `auto-coding` (`think: true`) | `1.0` | `0.95` | `20` | `0.0` | `0.0` | `1.0` |
| Live Ollama log (`ab_engine.py`, line 33468–33470) | `1.000` | `0.950` | `20` | `0.000` | `0.000` | `1.000` |
| `ab_engine.py` & `ab_loop.py` `current` arm | `1.0` | `0.95` | `20` | `0.0` | `0.0` | *(default 1.0)* |

**Key finding on sampling:**
1. There is **no sampling-parameter mismatch** between `generation_config.json`, `auto-coding`, Ollama's live `ab_engine.py` run, and oMLX's live `ab_engine.py` run. All four used `1.0 / 0.95 / 20 / 0.0 / presence 0.0 / repeat 1.0`. (Although Ollama's `/v1` historically ignored request `top_k`, GGUF `general.sampling.top_k = 20` ensured Ollama's sampler chain ran `top_k = 20, top_p = 0.950, min_p = 0.000, temp = 1.000`.)
2. Why `presence_penalty=1.5` (`ab_loop.py` arm `presence15`, 3/3 `finish=length`) did not stop the runaway:
   - `coding_task/reason_omlx-mtp.txt` has **614 unique non-empty lines out of 714** (49,208 chars). The model is not stuck in a token-level repetition loop — it is continuously designing and writing a complete Python schema-to-dataclass generator + test harness inside `<think>`.
   - Furthermore, `omlx.scheduler.make_logits_processors` defaults `presence_context_size = 20` tokens (`omlx/scheduler.py:3882-3897`), and `ab_loop.py` did not pass `repetition_context_size` (which only widens `repetition_context_size`, not `presence_context_size`).

---

### 1.3 oMLX Host Configuration (`~/.omlx/*.json`)

- **`~/.omlx/model_settings.json` (`models["Qwen3.8-27B-oQ4e-mtp"]`)**:
  - Sampling fields (`temperature`, `top_p`, `top_k`, `min_p`, `presence_penalty`, `repetition_penalty`): **all absent** (request values win; `force_sampling: false`).
  - Template / thinking fields (`enable_thinking`, `chat_template_kwargs`, `reasoning_parser`): **all absent**; `thinking_budget_enabled: false`.
  - Speculative / acceleration flags: **`"mtp_enabled": true`**, `"vlm_mtp_enabled": false`, `"dflash_enabled": false`, `"specprefill_enabled": false`, `"turboquant_kv_enabled": false`, `"qwen35_ane_prefill_enabled": false`, `"activation_fp16_enabled": false`.
  - Note: sibling entry `Qwen3.8-27B-4bit` has `enable_thinking: false`, `dflash_enabled: true`, `mtp_enabled: false`, and instruct sampling (`0.7/0.8/20/presence 1.5`).
- **`~/.omlx/settings.json`**:
  - Global `sampling`: `temperature: 1.0, top_p: 0.95, top_k: 0, repetition_penalty: 1.0, max_tokens: 262144, max_context_window: 262144`.
  - `cache`: `enabled: true, gdn_ssd_split_enabled: true, gdn_sidecar_precision: "fp32"`.
- **`~/.omlx/model_profiles.json`**:
  - Defines exposed LoRA profiles `Qwen3.8-27B-oQ4e-mtp:opencode` and `:pi` (both `enable_thinking: false`, `temperature: 0.8`, `top_p: 1.0`). Neither applies to bare `Qwen3.8-27B-oQ4e-mtp`.

---

### 1.4 Pipeline Request Differences Between oMLX and Ollama

Audited `portal/platform/inference/router/validation.py` (`_inject_ollama_options`, lines 431–570; `_inject_omlx_options`, lines 573–623), `portal/platform/inference/ollama_native.py` (`to_native_request`, lines 199–240), and `config/portal.yaml`:

| Field / behavior | Pipeline → **Ollama** (`/api/chat` via `OllamaNativeTransport`) | Pipeline → **oMLX** (`/v1/chat/completions`) |
| --- | --- | --- |
| `think: true` (`auto-coding`, `auto-reasoning::deep`) | Sends `"think": true` (boolean) on `/api/chat`; omits `reasoning_effort`. Ollama `renderer=qwen3.8` treats boolean `true` as thinking ON **without** the `xhigh` preamble (`medium`). | Sends `chat_template_kwargs: {"enable_thinking": true}` with **no `reasoning_effort`**. Qwen3.8 `chat_template.jinja:47` defaults to **`reasoning_effort='xhigh'`**, injecting the 38-token `xhigh` preamble. |
| `think: false` (`auto-compliance`, `auto-daily::deep`, `auto-coding::heavy`) | Sends `"think": false`. | Sends `chat_template_kwargs: {"enable_thinking": false}`. `chat_template.jinja:46` skips `reasoning_instructions` completely and closes `<think>\n\n</think>\n\n`. |
| `seat.reasoning_effort` | Only mapped for `"none"` or `"low"/"medium"/"high"` via `_think_value`; not set on `auto-coding`. | `_inject_omlx_options:592-598` already supports injecting `chat_template_kwargs["reasoning_effort"]` from workspace `reasoning_effort:` in `config/portal.yaml` — currently unset on `auto-coding` and `auto-reasoning::deep`. |
| Sampling keys | `options.{temperature, top_p, top_k, min_p, repeat_penalty, presence_penalty}` | Top-level `{temperature, top_p, top_k, min_p, repetition_penalty, presence_penalty}` |
| Prior evidence in `config/portal.yaml` | `auto-coding` seated on Ollama GGUF (`realuse_s5s7s10_20261030b`, 15/16, `think: true`). | `auto-coding::heavy` (line 1500, `Qwen3.8-27B-oQ4e-mtp`) already noted on **2026-10-22**: *"coder-seat A/B screen: PASS think-off (arm A); think-on failed (arm B)"*. |

**Note on `auto-reasoning::deep`:** `config/backends.yaml:992` still aliases `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` → `Qwen3.8-27B-oQ4e-mtp` in `omlx-reasoning`, and `auto-reasoning::deep` has `think: true` with no `reasoning_effort` set — identical exposure to `auto-coding` before mitigation `P5-OMLX-QWEN38-MTP-001`.

---

## 2. oMLX 0.8.4 Lightning MTP & Sampling Code-Path Audit

### 2.1 Active Engine & Speculative Path

Verified from `~/.omlx/logs/server.log` (2026-11-27 00:04:43, 01:07:29, 01:37:02):
```text
Speculative backend selected for /Volumes/data01/omlx-models/Qwen3.8-27B-oQ4e-mtp: Lightning MTP (model_type=qwen3_5, active)
mlx-vlm MTP sanitize patch applied for /Volumes/data01/omlx-models/Qwen3.8-27B-oQ4e-mtp
mlx-vlm runtime MTP patch applied for /Volumes/data01/omlx-models/Qwen3.8-27B-oQ4e-mtp
VLMBatchedEngine loaded: /Volumes/data01/omlx-models/Qwen3.8-27B-oQ4e-mtp
```
`Qwen3.8-27B-oQ4e-mtp` (`architectures: ["Qwen3_5ForConditionalGeneration"]`, `model_type: "qwen3_5"`, `text_config.mtp_num_hidden_layers: 1`) runs on **`VLMBatchedEngine`** using **Lightning MTP** (`omlx/patches/mlx_lm_mtp/batch_generator.py` + `omlx/patches/mlx_vlm_mtp/qwen35_vlm_runtime.py`). It does **not** use `omlx/speculative/vlm_mtp.py` (`vlm_mtp_enabled: false`).

Live MTP telemetry from `~/.omlx/logs/server.log` during the failing runs shows healthy acceptance and speedup throughout all 12,000–31,312 tokens (not an accept-rate collapse):
- QAT runaway (`uid=0`, 00:19:45): `tokens=31312 cycles=7726 tok/cycle=4.05 accept=14590/17738 (82.3%) copy=8997/9919 in 1417`
- `ab_loop.py` rep 0–2 `current` (`presence=0.0`): `accept=77.4%–80.4%`, `tok/cycle=3.15–3.30`, `31.3–32.5 tok/s`
- `ab_loop.py` rep 0–2 `presence15` (`presence=1.5`): `accept=72.3%–79.5%`, `tok/cycle=2.63–3.19`, `26.5–30.8 tok/s`
- `ab_engine.py` (`uid=0`, 01:15:19): `tokens=12000 cycles=4818 tok/cycle=2.49 accept=7130/10162 (70.2%) copy=48/98 in 14` (`25.9 tok/s`)

### 2.2 Stochastic Acceptance Math at `temp > 0` (Exact / Lossless)

Inspected `omlx/patches/mlx_lm_mtp/batch_generator.py` and `omlx/utils/sampling.py`:

1. **Draft sampler matches target sampler (`batch_generator.py:3067-3092`):**
   ```python
   def _resolve_draft_sampler(gen_batch: Any, state: _MtpState):
       ...
       target = _resolve_sampler(gen_batch)
       state.draft_sampler = make_sampler(
           temp=getattr(target, "temp", _DRAFT_SAMPLER_TEMP),
           top_p=getattr(target, "top_p", _DRAFT_SAMPLER_TOP_P),
           top_k=getattr(target, "top_k", _DRAFT_SAMPLER_TOP_K),
           min_p=getattr(target, "min_p", 0.0),
           min_tokens_to_keep=getattr(target, "min_tokens_to_keep", 1),
       )
   ```
   *(Note: the comment on `_MtpState.draft_sampler` at lines 882–889 is stale and describes an older `temp=0.6` sharper drafter; the live code matches the target's `temp`, `top_p`, `top_k`, `min_p`.)*

2. **Sparse top-k + coarse 3-bit draft head (`batch_generator.py:3370-3469`, `1848-1886`, `1939-2020`):**
   - When `temp=1.0, top_p=0.95, top_k=20, min_p=0.0` and `procs is None`, `_sparse_top_k(sampler)` returns `20` (`batch_generator.py:4254-4264`).
   - Because `lm_head` is a quantized `nn.QuantizedLinear` (`tie_word_embeddings=False`), `_coarse_draft_head(model)` builds a 3-bit (`g128`) copy of `lm_head` to shortlist 64 candidates, rescores those 64 with the real 4-bit `lm_head` (`exact - logsumexp(exact)`), then `_sample_candidates_fused` filters top-20 + top-p=0.95 + `1/temp`, draws via inverse CDF, and stores `(vocab_ids, logq)` in `SparseDraftQ`.
   - Crucially, `logq` is the **exact normalized density** from which the draft token was actually drawn.

3. **Leviathan/Chen verification & residual sampling (`batch_generator.py:4267-4346`):**
   ```python
   # _stochastic_verify_tokens_sparse (lines 4283-4293)
   ids = top_k_indices(combined_lp, top_k)
   vals = mx.take_along_axis(combined_lp, ids, axis=-1).astype(mx.float32)
   order = mx.argsort(-vals, axis=-1)
   vals = mx.take_along_axis(vals, order, axis=-1)
   ids = mx.take_along_axis(ids, order, axis=-1)
   if 0.0 < top_p < 1.0:
       probs = mx.exp(vals)
       vals = mx.where(mx.cumsum(probs, axis=-1) - probs < top_p, vals, -float("inf"))
   scaled = vals * (1.0 / temp)
   logp = scaled - mx.logsumexp(scaled, axis=-1, keepdims=True)  # (k+1, top_k)
   return _verify_on_support(ids, logp, drafts, draft_accept_lps)
   ```
   ```python
   # _verify_on_support (lines 4320-4338)
   ratio = p_at - q_at
   u = mx.random.uniform(shape=(k,))
   acc = mx.logical_or(ratio >= 0, mx.log(u) < ratio)
   m_arr = mx.cumprod(acc.astype(mx.int32)).sum().reshape(1)
   p_sup = mx.exp(logp[:k])
   ...
   res = mx.maximum(p_sup - q_sup, 0.0)
   z = res.sum(axis=-1, keepdims=True)
   res_dist = mx.where(z > 0, res, p_sup)
   res_pos = mx.random.categorical(mx.log(res_dist))
   res_samples = mx.take_along_axis(ids[:k], res_pos[:, None], axis=-1).squeeze(-1)
   ```
   - Outside `ids[:k]`, target `p == 0`, so `max(p - q, 0) == 0` identically; restricting residual sampling to the target's top-20 support is **mathematically exact**.
   - **Empirical elimination of the sparse/coarse fast path:** In `ab_loop.py` arm `presence15` (`presence_penalty=1.5`), `draft_procs` is non-empty, forcing `sparse_k = 0` and `coarse = None` (`batch_generator.py:3371-3372`). That run used the dense full-vocab path (`_sample_draft_with_logprobs` + `_stochastic_verify_tokens` lines 4427–4473) and **still hit `finish=length` 3/3**.

4. **Non-sampling MTP surface (verify kernels + GDN rollback):**
   - `batch_generator.py:2262-2266`: `_set_verify_qmm_armed(True, row_exact=False)` — `Qwen3.8-27B` is not opted into `_omlx_mtp_row_exact_verify` (only Qwen4-Exp is), so multi-row verifies run custom `qwen35_verify_qmm` (`sg8`/`split-K`/`msg`/`mma`), `qwen35_gdn_verify_fused` (fused Metal GDN recurrence + lazy deferred replay via `_omlx_gdn_pending` and `ArraysCache.commit_speculation`), and `qwen35_verify_attention` (`omlx_qwen_verify_ragged_sdpa`).
   - `qwen35_verify_qmm.py` notes fp32 lane-strided K accumulation differs at bf16 tail-ULP vs 1-row decode; `qwen35_gdn_verify_fused.py` targets bit-exactness on M3+ GPUs.
   - Note that the first two emitted tokens (`main_tok`, `next_main_tok`) come from standard prefill + 1-token forward (`_post_init_mtp`, lines 3511–3541) **before** any multi-row verify or GDN rollback runs. Yet `coding_task/reason_omlx-mtp.txt` already opens with `"We need respond to user:"` on tokens 1–5.

5. **MTP head norm weights on disk (ruled out as a bug):**
   Direct read of BF16 norm tensors from `/Volumes/data01/omlx-models/Qwen3.8-27B-oQ4e-mtp/model-0000*.safetensors`:
   - `language_model.mtp.norm.weight`: mean `2.2520` (backbone `model.norm.weight`: `1.9441`)
   - `mtp.layers.0.self_attn.q_norm.weight`: mean `1.7908` (backbone `layers.3.q_norm`: `1.2301`)
   - `mtp.layers.0.self_attn.k_norm.weight`: mean `1.7794` (backbone `layers.3.k_norm`: `1.2202`)
   - `mtp.layers.0.post_attention_layernorm.weight`: mean `1.2063` (backbone `layers.3`: `0.8927`)
   All MTP head norms are properly +1 shifted (`norm_repair.py` margin check `anchor - head > 0.4` never triggers; consistent with 70–82% accept rate).

6. **Reasoning parser (`omlx/api/thinking.py`):**
   - `prompt_opens_thinking` (`thinking.py:116-163`) checks the last 3 prompt token IDs for `think_start_id` (`248068`, `<think>`). Both 169-token (`xhigh`) and 131-token (`medium`) prompts end with `[248045, 74455, 198, 248068, 198]` (`<|im_start|>assistant\n<think>\n`), so `start_in_thinking=True`.
   - `extract_thinking(..., truncated=True, start_in_thinking=True)` (`thinking.py:221-245`) keeps an unclosed think block in `reasoning_content` and leaves `content=""` on `finish_reason="length"`. Verification on `coding_task/reason_omlx-mtp.txt` confirms `"</think>"` never appeared anywhere in the 49,208-char output — the parser is faithful; the model never closed thinking.

---

## 3. Checkpoint Quantization Comparison (`oQ4e-mtp` vs Unsloth `Q4_K_M`)

Inspected `/Volumes/data01/omlx-models/Qwen3.8-27B-oQ4e-mtp/{config.json,oq_imatrix_report.json,model.safetensors.index.json}` and GGUF tensor headers of `sha256-322e194ff7...`:

| Component | oMLX `Qwen3.8-27B-oQ4e-mtp` (oMLX `v0.6.0.dev1`, Aug 2026) | Ollama Unsloth `Q4_K_M` (`sha256-322e194f...`) |
| --- | --- | --- |
| `lm_head` (`output.weight`) | **4-bit affine g64**, **NOT imatrix-calibrated** (`missing: ['language_model.lm_head', 'language_model.model.embed_tokens']`) | **`Q6_K`** (6.56 bpw) |
| `embed_tokens` (`token_embd`) | 4-bit affine g64, not imatrix-calibrated | `Q4_K` |
| GDN gates (`in_proj_a`, `in_proj_b`) | 5-bit affine g64 (early layers) / 4-bit (later layers) | **`Q8_0`** (`ssm_alpha`, `ssm_beta`) |
| GDN `out_proj` / `in_proj_qkv` | 5-bit affine g64 (166 total 5-bit overrides) / 4-bit | `Q5_K` / `Q6_K` |
| FFN projections | 4-bit affine g64 (imatrix `oqe_code_multilingual`, 128×512) | `Q4_K` / `IQ4_XS` / `Q5_K` |
| `mtp.fc` | BF16 on disk (re-quantized to 4-bit g64 at runtime by `_quantize_mtp_fc` when `_coarse_draft_head` activates) | *(no MTP head)* |

---

## 4. Ranked Hypotheses & Discriminating Live Arms

| Rank | Hypothesis | Confidence | Evidence FOR | Evidence AGAINST | Decisive Live Arm |
| ---: | --- | --- | --- | --- | --- |
| **1** | **Chat template `reasoning_effort='xhigh'` default mismatch** (oMLX renders 169 tok w/ `xhigh` preamble; Ollama `renderer=qwen3.8` renders 131 tok w/o preamble = `medium`) | **High** | • Proven live in logs: **169 vs 131 prompt tokens** on identical `ab_engine.py` request (exact 38-tok delta = `chat_template.jinja:52` `xhigh` instruction).<br>• Telegraphic style (`"We need respond..."`, `"Oververbosity 9"`) starts at token 1, before MTP verify cycles run.<br>• Upstream Qwen3.8 docs/reports confirm `xhigh` causes 6–8× token expansion (31.8k tok/task cited in `FINDING_OMLX081_INTAKE.md:27`) and unbounded semantic self-validation loops.<br>• Explains why `think: false` seats (`auto-compliance`, `auto-coding::heavy`) pass on this exact checkpoint (`chat_template.jinja:46` skips `reasoning_instructions`), and why `presence_penalty=1.5` failed (614/714 unique lines). | • Does not by itself prove whether the 4-bit `lm_head` also worsens `xhigh` telegraphic drift.<br>• Unproven live until Arm A2/A4 runs. | **Arm A2** (`chat_template_kwargs: {"reasoning_effort": "medium"}`, MTP ON) and **Arm A4** (raw `/v1/completions` w/ byte-exact 131-tok Ollama prompt, MTP ON). If A2/A4 finish `stop` with `</think>` + full answer, **H1 is confirmed and MTP stays ON**. |
| **2** | **Quantization degradation (`oQ4e` early dev1 build: un-imatrixed 4-bit `lm_head` + 4/5-bit GDN gates vs Unsloth `Q6_K` `output.weight` + `Q8_0` `ssm_alpha/beta`)** | **Medium-Low** | • `lm_head` is 4-bit g64 without imatrix vs `Q6_K` on GGUF; poor `</think>` calibration or subtle logit distortion could amplify `xhigh` overthinking or degrade grammar.<br>• Built on early `oMLX v0.6.0.dev1`. | • `think: false` seats (`auto-compliance`, `auto-coding::heavy`) and shorter turns (50–778 tok on 2026-11-27 08:29–08:44) complete `finish=stop` cleanly on this exact checkpoint. | Confirmed **only if** Arms **A1** (MTP OFF) AND **A2/A4** (131-tok `medium` prompt) ALL still hit `finish=length` while **A5** (Ollama GGUF) finishes `stop`. |
| **3** | **Serving harness: Lightning MTP verify kernels / GDN deferred rollback** (`qwen35_verify_qmm` `sg8`/`split-K`, `qwen35_gdn_verify_fused`, `row_exact=False`) | **Low** | • Multi-row verify runs custom mixed 4/5-bit QMM + lazy GDN deferred replay over 48 linear layers for 3,800–7,900 cycles per runaway; non-row-exact bf16 tail-ULP drift is possible. | • Stochastic acceptance math in `batch_generator.py` is exact Leviathan/Chen.<br>• `presence_penalty=1.5` bypassed `_coarse_draft_head` + `SparseDraftQ` (dense path) and still failed 3/3.<br>• Degraded telegraphic style starts on tokens 1–4 before verify drift accumulates.<br>• Live accept rate stayed 70–82% through 12k–31k tokens. | **Arm A1** (MTP OFF, baseline 169-tok prompt). If A1 passes `stop` while A0 fails 3/3, **H3 is confirmed**. If A1 also hits `length`, MTP is exonerated. |
| **4** | **Sampling parameters (`temp=1.0, top_p=0.95, top_k=20, min_p=0, presence=0`)** | **Very Low** | • Lowering temperature (`0.6`, Qwen thinking precise-coding profile) narrows the tail and may curb overthinking. | • Live passing Ollama control used the **exact same** `1.0 / 0.95 / 20 / 0 / 0` (`/opt/homebrew/var/log/ollama.log:33468-33470`).<br>• Matches `generation_config.json` and `qwen3.8` card thinking mode.<br>• `presence_penalty=1.5` already failed 3/3 (`ab_loop.out`). | **Arm A3** (`temp=0.6, top_p=0.95, top_k=20, min_p=0, presence=0` on oMLX MTP, baseline 169-tok prompt). Tests whether temperature sharpening alone rescues `xhigh`. |

---

## 5. How to Toggle MTP & Template in oMLX 0.8.4

- **Per-request `chat_template` override:** Not supported in oMLX 0.8.4 (`omlx/server.py:8589` explicitly rejects `chat_template`; `ChatCompletionRequest` has no `chat_template` field).
- **Per-request `reasoning_effort` (Arm A2):** Supported directly via `chat_template_kwargs: {"enable_thinking": true, "reasoning_effort": "medium"}` (or top-level `reasoning_effort: "medium"`). Verified offline to produce the exact 131-token prompt rendered by Ollama's `renderer=qwen3.8`.
- **Toggling `mtp_enabled` (Arm A1):** `mtp_enabled` is a load-time engine construction setting (`qwen35_vlm_runtime.py:307-309`). Toggling it via oMLX's admin API automatically updates `~/.omlx/model_settings.json` and triggers `requires_reload` auto-unload (`omlx/admin/routes.py:3566-3592, 3781-3795`):
  - **Toggle OFF (before A1):**
    ```bash
    OMLX_KEY=$(python3 -c 'import json; print(json.load(open("/Users/chris/.omlx/settings.json"))["auth"]["api_key"])')
    curl -sf -X PUT "http://localhost:8085/admin/api/models/Qwen3.8-27B-oQ4e-mtp/settings" \
      -H "Authorization: Bearer $OMLX_KEY" -H "Content-Type: application/json" \
      -d '{"mtp_enabled": false}'
    curl -sf -X POST "http://localhost:8085/v1/models/Qwen3.8-27B-oQ4e-mtp/unload" \
      -H "Authorization: Bearer $OMLX_KEY" || true
    ```
  - **Revert ON (immediately after A1):**
    ```bash
    curl -sf -X PUT "http://localhost:8085/admin/api/models/Qwen3.8-27B-oQ4e-mtp/settings" \
      -H "Authorization: Bearer $OMLX_KEY" -H "Content-Type: application/json" \
      -d '{"mtp_enabled": true}'
    curl -sf -X POST "http://localhost:8085/v1/models/Qwen3.8-27B-oQ4e-mtp/unload" \
      -H "Authorization: Bearer $OMLX_KEY" || true
    ```

---

## 6. Live A/B Harness & Verdict Decision Tree

Implemented at [`coding_task/qwen38_mtp_ab.py`](../../coding_task/qwen38_mtp_ab.py) (placed under `coding_task/` because `scripts/probes/` does not exist and `unwired_scripts` is at ceiling `25/25`).

**Arms:**
- **A0** (N=3): oMLX `Qwen3.8-27B-oQ4e-mtp` baseline as-is (`/v1/chat/completions`, no `chat_template_kwargs`, `1.0/0.95/20/0/0`, MTP ON → 169 prompt tok).
- **A1** (N=3): Same request as A0, **MTP OFF** (guarded behind `--mtp-already-off`; script prints exact toggle/revert commands and refuses to edit oMLX settings itself).
- **A2** (N=3): oMLX MTP ON with `chat_template_kwargs={"enable_thinking": true, "reasoning_effort": "medium"}` (exact 131-token prompt parity with Ollama `renderer=qwen3.8`).
- **A3** (N=3): oMLX MTP ON with Qwen precise-coding thinking sampling (`temp=0.6, top_p=0.95, top_k=20, min_p=0, presence=0`, baseline 169-tok prompt).
- **A4** (N=3): oMLX MTP ON via raw `/v1/completions` with byte-identical hand-rendered 131-token Ollama prompt (`stop=["<|im_end|>", "<|endoftext|>"]`, baseline sampling).
- **A5** (N=1): Ollama GGUF control (`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k`, baseline sampling).

**Expected verdict matrix:**
1. **A2 & A4 pass (`finish=stop`, `</think>` present, content > 0) while A0 fails:** **H1 confirmed** — set `reasoning_effort: medium` on thinking-on Qwen3.8 oMLX seats (`auto-coding`, `auto-reasoning::deep`) in `config/portal.yaml` and re-enable the `omlx-coding` alias to recover ~2× MTP speed.
2. **A1 passes while A0 & A2 fail:** **H3 confirmed** — bug is in Lightning MTP verify/rollback (`qwen35_verify_qmm` / `qwen35_gdn_verify_fused`); keep MTP off or report upstream to `jundot/omlx`.
3. **A3 passes while A0 & A2 fail:** **H4 confirmed** — lower thinking temperature to `0.6` on oMLX Qwen3.8.
4. **A0–A4 all fail while A5 passes:** **H2 confirmed** — `oQ4e-mtp` checkpoint/quant (un-imatrixed 4-bit `lm_head`) is defective for thinking mode; evaluate a newer Qwen3.8 MLX MTP build with 6/8-bit `lm_head`.
