# Task: Seat–vendor fit — test every production seat against its model's own contract

**Opened:** 2026-09-25. **Continues:** WFE-0.6 and WFE-0.7 in `docs/TASK_WORKSPACE_FITNESS_EVAL_V1.md`.

## Why this task exists

On 2026-09-24 and 2026-09-25, five apparent model failures turned out to be failures of configuration, engine or prompt:

| Apparent failure | Real cause |
|---|---|
| Laguna "never worth its weight" | the XS.2 build cannot stop after a tool call on this stack (fixed: XS-2.1, `a84782ff`) |
| MiMo tool calls "broken" | Ollama's llama.cpp template path mis-parses its GGUF; oMLX is clean |
| WFE non-Ollama arms "loop" | the runner dropped `repeat_penalty`/`top_k`/`min_p` and never applied `system_prompt_append` (fixed, `a84782ff`) |
| granite 4.2 "worse than 4.1" | probed at temperature 0 against a card that ships 1.0; its reasoning was invisible on `/v1`; on the fixed harness it tied |
| VulnLLM "invents CWEs on clean code" | we used a targeted detector as a free-form chat model. With its trained prompt and card sampling it scored 17/18 with 0/3 false positives, against 15/18 and 3/3 with ours |

The registry `config/model_card_expectations.yaml` now records vendor sampling and prompt contracts for 13 families (added this session: qwen3.8, qwen3.5, qwen3.6, qwen3, gemma4, granite-4.1, laguna, mimo, vulnllm, deepseek-r1, lfm2, phi4). A served-settings diff of every production seat against those cards found:

- **4 match** (auto-daily, auto-audio, auto-reasoning, auto-math, plus nemotron).
- **About 30 deviate**, nearly all in the same direction: temperature 0.1–0.3 where the vendor ships 0.6–1.0, and `top_k` 40 where it ships 20.
- **13 have no card yet.**

Qwen's guidance warns that near-greedy decoding on Qwen3.x causes performance loss and endless repetition, which is the loop failure seen repeatedly in these benches. None of the deviations has ever been tested.

**Doctrine (operator, 2026-09-25):** adopt vendor settings only when they are verified better *for what the workspace is for*. Evidence comes before any change. Old configuration is replaced when the new one wins, not preserved for its own sake.

## Method (per seat)

1. **Card contract:** `model_card_expectations.yaml` has `recommended_sampling` (plus `recommended_sampling_modes` when the card gives several), `prompt_contract`, thinking behaviour, max context, and a source URL with date.
2. **A/B in the seat:** the same WFE lane, the same seat context (`workspace::variant` ids resolve exactly as production does), n=3.
   - Arm A: seat settings (the default).
   - Arm B: `WFE_SAMPLING='<card json>'`, plus `WFE_THINK=true|false` when the card's thinking default differs from the seat.
   - Both overrides are stamped into every row.
   - Serve on the engine production uses for that seat. Check `backends.yaml` aliases: a `priority: 10` oMLX alias means oMLX, so set `WFE_ENGINE=omlx`.
3. **Decide by purpose:**
   - **Deterministic lanes** (compliance, security classification, documents, extraction) may keep low temperature *only* if arm B shows no gain. Score answer stability as well as pass rate.
   - **Agentic and coding lanes:** pass rate plus turn-cap exhaustion. Loops are the failure being hunted.
   - **Creative and general chat lanes:** the WFE creative/research suites plus human review.
4. **Apply winners** in `config/portal.yaml`, run `./launch.sh sync-config`, rebuild the pipeline image (`portal.yaml` and the personas are baked in; only `backends.yaml` is mounted), and verify one live request through `:9099`.
5. **Record** the result on the card entry (`behavioral_quirks`) and in this file's result log.

## Work items, in priority order

### S0 — auditor fixes (no model calls)
- `tests/wfe/settings_audit.py` compares the card only with *baked* tag params. Add a check of the **served** workspace sampling against the card (the diff behind the numbers above), and report `prompt_contract` presence.
- Family matching misses `granite4.1:*` tags against the `granite-4.1` key. Normalise separators, and give `qwen3-vl` its own entry so it no longer inherits the qwen3-coder card.
- oMLX-served hints (REAP-288, Nex-N2.5-MLX, `Qwen3.8-27B-4bit`) are reported `hint_absent`/`persona_pin_absent` because the auditor checks only Ollama. Also check oMLX `/v1/models`.
- Granite 4.1 has no thinking mode, so drop its `reasoning_uncontrolled` flags (they belong to granite 4.2).

### S1 — cards still owed (research only)
- kat-coder, nex-n2, qwen3-vl, tongyi, hermes, mistral-small, command-r, llama.
- The finetune seats with no family key: agentworld-35b, Ornith-1.0/1.5, omnicoder2, North-Mini-Code, HauhauCS/Huihui abliterations, baronllm.
- For each, record the base-model card plus the finetuner's own guidance.

### S2 — A/B the seats that carry traffic
| Seat | Model | Seat settings | Card | Lane / suite |
|---|---|---|---|---|
| `auto-compliance` | Qwen3.8-27B | 0.3 / 0.95, think off | instruct 0.7 / 0.8 / 20 | compliance_agentic + research |
| `auto-reasoning::deep` | Qwen3.8-27B | 0.6 / 0.95, think on | thinking 1.0 / 0.95 / 20 | deep-lane runner (archived `deep_lane/`), with harder prompts |
| `auto` | qwen3.5-9B abliterated | 0.6 / 0.95, think off | instruct 0.7 / 0.8 / 20, presence 1.5 | research + creative |
| `auto-coding` (+ heavy, uncensored-agentic, spl, bigfix, cad) | qwen3-coder family | 0.1–0.2 / 0.9 / 40 | 0.7 / 0.8 / 20, repeat 1.05 | coding + compliance_agentic |
| `auto-council` | qwen3.6-27B | 0.2 / 0.9 / 40, think off | 1.0 / 0.95 / 20 (thinking) | council judgment probe |
| `compliance-reading` | gemma4 26B | 0.3 / top_k 20 | 1.0 / 0.95 / 64 | compliance reading cases (module acceptance) |
| `auto-security::redteam*/purpleteam*` | qwen3.5-9B / gemma4 / qwen3.6 | 0.1–0.3 | per card | security bench (pentest suites) |
| `auto-music`, `auto-extract-uncensored` | lfm2.5 | 0.8 and 0.6 | 0.2 / top_k 80 / repeat 1.05 | their own probes |
| `tools-specialist`, `auto-documents`, `auto-image`, `auto-video` | granite4.1:8b | 0.2–0.5 | greedy (IBM sets no sampling) | coding + research |

### S3 — VulnLLM as a specialist tool (operator chose option B, 2026-09-25)
- Add a `scan_code` tool to the security MCP (`portal/modules/security/tools/security_mcp.py`). It wraps VulnLLM with its exact trained prompt (`reasoning_user_prompt` + `new_policy` CWE list + `our_cot`, from github.com/ucsb-mlsec/VulnLLM-R `vulscan/utils/sys_prompts.py`), card sampling (0.7 / 0.8 / 20, repeat 1.05) and 3,072 max tokens. It parses `## Final Answer / #judge / #type` into structured output.
- Choose the `auto-security` chat-seat model on evidence: candidates with tools that can call `scan_code`. VulnLLM leaves the chat seat.
- Acceptance: the 6-snippet CWE set (archived `fixtures/engine_h2h/security_prompts.json`) through the tool gives ≥ 17/18 and 0/3 clean false positives, and one live request through the pipeline shows the chat model calling the tool.
- Diversity follow-up: MiMo (high precision: 11/15, 0 FP) as a second reviewer alongside VulnLLM (high recall) in `auto-security::blueteam-council`. Score recall and precision of the pair against each alone.

### S4 — carried-over queue
1. Laguna-XS-2.1 at card sampling vs seat sampling (the first A/B; result below).
2. granite 4.2 rerun at card settings on the fixed harness, against 4.1.
3. VulnLLM GGUF → mradermacher `i1` (imatrix) build, same size.
4. Qwen3.8 builds on `auto-compliance`: unsloth UD-Q4_K_XL and ISTA-DASLab GSQ-RCO IQ3_S (11.8GB, stock Ollama) against our Q4_K_M. Fit the native `qwen3.8` renderer where the build allows.

## Instruments (all in-repo)
- `tests/wfe/campaign.py`:
  - `WFE_SAMPLING` (replaces seat sampling, keeps `max_tokens`) and `WFE_THINK`, both stamped per row.
  - `WFE_ENGINE` + `WFE_CHAT_BASE_URL` for oMLX.
  - Arms after the first need `--append`.
- `tests/wfe/runner.py`: `workspace::variant` context; sends every resolved sampling key; applies `system_prompt_append`.
- `uv run python -m tests.wfe.settings_audit`: config and card audit.
- Rules: one request in flight; stack up; back up checkpoints before clearing; and before blaming a model, render its official template, raw-generate, and compare with what the engine returned. Both the XS.2 and MiMo "failures" lived in the engine layer.

## Result log
| Date | Seat | Arm A (seat) | Arm B (card) | Decision |
|---|---|---|---|---|
| 2026-09-25 | `auto-security` (VulnLLM, CWE set) | 15/18, 3/3 FP | 17/18, 0/3 FP (trained prompt + card sampling) | S3 (tool) |
| 2026-09-25 | `auto-coding::laguna` (Laguna-XS-2.1, oMLX, think off) | 24/29 PASS, 0 turn-cap | 19/29 PASS, 2 turn-cap + 16K-token runaway turns (1.0/20/1.0) | keep seat sampling (0.2/40/0.9) |
| 2026-09-25 | `scan_code` live replay (6 snippets × 3, case CWE shortlist) | 12/15 positive CWE hits, 0/3 clean false positives | 0 parse-error rows; default unshortlisted replay was 8/15 positive hits, 0/3 clean false positives | historical 17/18 result not reproduced in this live replay; retain as follow-up evidence |
| 2026-09-25 | `scan_code` live replay after caller-shortlist fix (6 snippets × 3) | 15/15 positive CWE hits, 0/3 clean false positives | 18/18 rows parsed; caller shortlist preserved CWE-601/89/798/502 descriptions | S3 acceptance reproduced; retain prior unfavorable replay above as the regression receipt |
