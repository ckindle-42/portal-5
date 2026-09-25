# Task: Seat–vendor fit — test every production seat against its model's own contract

**Opened:** 2026-09-25. **Continues:** WFE-0.6 and WFE-0.7 in `docs/TASK_WORKSPACE_FITNESS_EVAL_V1.md`.
**Revised:** 2026-09-25 (evening) — delivery and harness repair. **Read "Current state" first; everything under "History" was measured before the repair and is superseded where the two disagree.**

## Current state (2026-09-25 evening) — read before running anything

> **Superseded for execution by `docs/TASK_SEAT_SAMPLING_AB_V1.md`** (2026-09-25,
> late): the operator switched production seats to card sampling by purpose
> (security exempt) and replaced Ollama `presence_penalty` with
> `repeat_penalty: 1.05`. S2 now A/Bs card (incumbent) against the prior config;
> S3–S5 carry over there. This file remains the method reference.

### What was wrong, and is now fixed

Nothing below failed loudly — every request returned 200. Each one silently made
a measurement describe something other than the configured seat.

**Production (what users were actually served)**

| Defect | Effect | Fix |
|---|---|---|
| Ollama `/v1` drops `options` and has no `top_k`/`min_p`/`repeat_penalty`; forces temperature/top_p to 1.0 when omitted | **Every Ollama-served seat ran at temperature 1.0 / top_p 1.0** with the tag's baked top_k etc. — never at its `portal.yaml` sampling; `think:true` was dropped | `portal/platform/inference/ollama_native.py`: Ollama backends answered from native `/api/chat` behind the unchanged OpenAI surface; parity-verified against `/v1` (P5-OLLAMA-V1-SAMPLING-001) |
| Unregistered `-ctx32k` hints | `auto-coding::fast-repair` and `::uncensored-fast` were served **Qwen3.6-35B HauhauCS**, not kat-coder / orcarouter | tags registered in `ollama-coding`; `hint_unroutable` FAIL in the auditor + UAT gate (P5-HINT-FALLBACK-001) |
| `auto-general-uncensored` on the base tag; `supports_tools: false` | ran at Ollama's default context, not 8192; its six declared tools were never offered | hint → `:Q4_K_M-ctx8k` (the "creation failed" rollback was a case mismatch); tool probe 3/3 → `supports_tools: true` |
| `tools-specialist::fast` had no ctx tag | default context, not 8192 | `gemma4:e4b-it-qat-ctx8k` created + registered in `general` |
| IDE-direct oMLX (`./launch.sh coder-reap288`) sends no sampling | REAP-288 ran on oMLX globals (temp 1.0, top_k 0, no repetition penalty) | `scripts/omlx_seat_defaults.py` writes a single-seat model's sampling as oMLX per-model defaults (run by `sync-config` and `coder-reap288`) |
| p40 (opencode → thebrain Ollama `/v1`, Portal-independent) sends no sampling | gpt-oss-sonnet ran at 1.0/1.0, not its tag's 0.4/0.9 | per-model `options` in `opencode.jsonc` (captured on the wire; no Portal code in that path) |

Verified live after deploy: a caller `top_k=1` collapses three seeds to one
output through `:9099`; OWUI → pipeline → Ollama works; both coding variants
serve their configured models; both ctx8k seats load at 8192.

**Consequence for everything already measured:** no earlier seat A/B, WFE or
UAT number for an Ollama-served seat measured the seat's configuration, and
none for an oMLX seat had its repeat penalty. Treat them as evidence about the
*model*, not the *seat*. The one S2 result in the log (laguna) is **void** — see
below.

**Production behaviour changed today.** Ollama-served seats now run at their
declared sampling for the first time — mostly temperature 0.1–0.3 where they
had been running at 1.0. That is exactly the near-greedy regime this task
suspects of causing loops, so S2 on the Ollama seats is now more urgent, not
less. Watch for loops/repetition in real use until it has run.

**Harness (WFE) — defects that produced invalid rows**

| Defect | Effect | Fix |
|---|---|---|
| Stall / wall / turn budget overridden by a checker PASS (runner **and** `--rescore`) | a 900s stall reported PASS | `BUDGET_EXHAUSTED` always stands; checker verdict kept as `evidence.checker_outcome` |
| Agentic answer without the literal completion signal was re-sent with the assistant message last | the model wrote a second answer that replaced the first (33/1150 archived rows), or 400'd as HARNESS_ERROR | a text-only turn ends the run, as in production; `evidence.completion_signal_missing` records it |
| Turn cap only flagged when no text was ever produced | loops that narrated between tool calls hid the loop signal | every turn-cap exhaustion is `BUDGET_EXHAUSTED` |
| `run_id` carried no sampling; overrides read from env on every row | a card arm of the same model added 0 rows ("already present") and never ran; a resume without the env var mixed arms | **variant arms** in the plan (below); overrides stored on each row; resume on a different engine aborts |
| Seat without `think` resolved to the card's `harness_policy` | laguna / uncensored-fast / reap288 measured with thinking OFF; production runs them ON | a seat with no `think` runs `native` — nothing sent, as production |
| oMLX arms sent `repeat_penalty` (oMLX reads `repetition_penalty`) | every oMLX arm ran without its loop guard | both names sent; production already mapped it |
| Ollama arms posted to `/v1` | top_k/min_p/repeat_penalty never reached the model | Ollama arms use production's `to_native_request` translation |
| 4096 output cap when a seat has no `predict_limit` (production sends none) | manufactured TRUNCATED rows, worst on thinking arms | 32768 runaway-only cap; `sampling.max_tokens_source` records which cap applied |
| No oMLX memory management; no oMLX version in the fingerprint | an arm could run beside the previous arm's weights; pooled oMLX versions | oMLX restarted to an empty pool before each arm; `engine_version` stamped |
| HTTP errors recorded without the engine's body | a context overflow read like a harness bug | body kept in the HARNESS_ERROR note |
| Settings auditor never walked variants; compared baked tags, not served values | most specialised seats unaudited; false FAILs | variants audited; `served_vs_card` (WARN) + `hint_unroutable` (FAIL); oMLX inventory; granite 4.1 not treated as reasoning |

### Keeping it true (automatic)

- `scripts/engine_contract_check.py` — proves, per running engine version, that
  every sampling key and `think` in both directions visibly change the model's
  output through production's own request builders, and (Ollama) that the
  adapter answers exactly as `/v1`. Probe models: `config/engine_contract.yaml`.
- `scripts/engine_autoupdate.py` — daily launchd job
  (`com.portal5.engine-update`, installed by `./launch.sh up`): re-runs the
  contract whenever an engine version changed by any route; weekly (sooner on a
  security fix, or `--now`) installs the newest non-pre-release of Ollama and
  oMLX, gates it on the contract, rolls back and records the rejected version on
  failure. The macOS data01 popup is detected, requested via Pushover and waited
  for (P5-ENGINE-TCC-001). Ollama is now on 0.34.4 through this path.
- UAT refuses to start (`tests/uat/settings_gate.py`) unless the contract is
  current, no production seat is unroutable/absent, and OWUI injects no sampling
  of its own (a caller's values win in the pipeline, so an OWUI default would
  override every seat).

## Method (per seat) — revised

1. **Card contract** as before (`config/model_card_expectations.yaml`).
2. **Baseline:** `uv run python -m tests.wfe.settings_audit` — `served_vs_card`
   lists what each seat is *actually served* per key (seat value, else the
   engine default) against its card. 47 WARN on 2026-09-25; that list is the S2
   work queue. Re-run it before each seat — it reads live engine state.
3. **One seat, one campaign, arms as plan variants** (no env vars):

   ```yaml
   workloads:
     auto-coding::laguna:
       home: coding
       discovery: [compliance_agentic]
       arms:
         incumbent: Laguna-XS-2.1-4bit            # the seat as production serves it
         challengers:
           - {model: Laguna-XS-2.1-4bit, label: card, sampling: {temperature: 1.0, top_p: 1.0, top_k: 20}}
           - {model: Laguna-XS-2.1-4bit, label: seat-nothink, think: false}
   ```

   Each variant is its own arm (`<tag>@<label>-<sha8>`) with its own run_ids and
   stored overrides; `report.py` compares each against the incumbent. A variant
   whose sampling includes a key the engine cannot apply is BLOCKED before its
   first request (on Ollama only `presence_penalty`, which its sampler ignores).
   Template: `tests/wfe/plans/s2_laguna_rerun_omlx.yaml` (dry-run and a live
   smoke row verified).
4. **Engine:** serve on the engine production uses — a priority-10 oMLX alias
   means oMLX: `WFE_ENGINE=omlx WFE_CHAT_BASE_URL=http://127.0.0.1:8085`. The
   campaign aborts if resumed on another engine.
5. **Decide by purpose** (unchanged): deterministic lanes may keep low
   temperature only if the card arm shows no gain; agentic/coding lanes score
   pass rate **and** `BUDGET_EXHAUSTED` (turn cap, stall) — loops are the hunted
   failure; creative lanes add blinded review.
6. **Apply winners** in `config/portal.yaml`, `./launch.sh sync-config`, rebuild
   the pipeline image (portal.yaml is baked in; backends.yaml is mounted — a
   restart suffices for it), verify one live request through `:9099`.
7. **Record** on the card entry and in the result log below.

Rules still in force: one request in flight; stack up; back up checkpoints
before clearing; before blaming a model, render its template, raw-generate, and
compare with what the engine returned.

## Work items — revised

### S0 — auditor: DONE 2026-09-25
Served-vs-card check, oMLX inventory, variants, granite 4.1 regex, routability.
Remaining auditor FAILs are not delivery bugs: `sampling_hot` on
`auto-extract-uncensored` (0.6) and `auto-documents` (0.5) against the
documents-lane 0.4 ceiling — lane-policy questions for S2 now that the value is
really served; `auto-security::purpleteam-exec` `tools_unsupported`
(operator's); `persona:nemotronlightning` pin absent (pre-existing).

### S1 — cards: CLOSED (see History).

### S2 — A/B the seats, in this order
1. **`auto-coding::laguna` rerun** — `tests/wfe/plans/s2_laguna_rerun_omlx.yaml`
   (seat / card / seat-nothink). Replaces the void result.
2. **Seats with no explicit `think` whose card says off** —
   `auto-coding::uncensored-fast`, `auto-coding::reap288` (IDE-only; needs the
   stack down: `./launch.sh coder-reap288 --warm-only` path). Arms: native vs
   `think: false`. Decide and then **pin `think` explicitly** in portal.yaml so
   the harness and production can never diverge on it again.
3. **Ollama-served seats**, now that their sampling is real — highest traffic
   first: `auto-general-uncensored`, `auto-data`, `auto-research`,
   `auto-reasoning`, `auto-council`, `auto-vision`, `compliance-reading`, the
   `auto-coding` Ollama variants, `auto-music` / `auto-extract-uncensored`.
4. **oMLX-served seats**: `auto-compliance`, `auto-reasoning::deep`,
   `auto-coding` (+ bigfix, cad), `auto`, the granite4.1 seats.
5. `auto-security` chat seat: unchanged rule — no model change without the S3
   `scan_code` comparison.

### S3 — VulnLLM as a specialist tool: unchanged (see History).

### S4 — carried-over queue: unchanged (see History); rerun anything measured on
Ollama before 2026-09-25 evening before using it as seat evidence.

### S5 — UAT pass after S2 lands (the overhaul)
The settings gate makes UAT refuse unsound runs; what UAT must now exercise:
- every section on the seats whose served settings changed today (all
  Ollama-served seats) — they are behaving differently from every earlier UAT;
- loops/repetition on low-temperature seats (the suspected failure) and
  turn-cap exhaustion in agentic sections;
- `think: true` seats on Ollama now actually reason (latency and token budget);
- the two re-routed coding variants and the two ctx8k seats (first UAT on the
  intended models);
- OWUI display of reasoning: the pipeline promotes Ollama `reasoning` deltas to
  content (review item C-1) and some templates (lfm2.5) emit inline `<think>`;
- multi-turn tool conversations through OWUI (tool-result turns now travel the
  native path).

### Open operator decisions
- **`keep_alive`** — never delivered by `/v1`, still not forwarded (every model
  unloads on Ollama's server default). Deliver the per-workspace values? The
  pipeline default is `-1` (pin forever), which would hold memory oMLX cannot
  reclaim.
- **`presence_penalty` on Ollama seats** (`auto-general-uncensored`, `auto-data`
  and four others at 1.5) — Ollama's sampler ignores it; move those seats to oMLX
  or drop the key.
- **`tool_choice=required`** has never applied on Ollama seats (Ollama ignores
  it everywhere).
- **oMLX 0.7.0rc1** is on the tap as "stable"; the updater skips pre-releases
  (`--allow-prerelease` to take it deliberately).

## Result log
| Date | Seat | Arm A (seat) | Arm B (card) | Decision |
|---|---|---|---|---|
| 2026-09-25 | `auto-security` (VulnLLM, CWE set) | 15/18, 3/3 FP | 17/18, 0/3 FP (trained prompt + card sampling) | S3 (tool) |
| 2026-09-25 | `auto-coding::laguna` (Laguna-XS-2.1, oMLX) | 24/29 PASS, 0 turn-cap | 19/29 PASS, 2 turn-cap + 16K-token runaway turns (1.0/20/1.0) | **VOID** — arm A ran thinking OFF (production: on) and without its repeat_penalty (oMLX ignored the key); the stall-masking and completion-signal defects also applied. Rerun: S2 item 1 |

---

# History (pre-repair — superseded where it conflicts with "Current state")

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

## Result log (pre-repair copy — see the current log above)

## 2026-09-25 — reversion, S1 completion, and re-plan before any further run

A same-day attempt (`d51dd29a`) was reverted (`97f915b8`,
`docs/TASK_SEAT_VENDOR_FIT_V1_REVERSION_NOTES_20260925.md`). Root cause: it
skipped straight to a config edit for `auto-security` — retagging the chat
seat from VulnLLM-R to `glm-4.7-flash:Q4_K_M` on generic tool-reliability
evidence, bundled into the same commit as the `scan_code` tool, 11 routing
"rebless" edits, and a description rewrite. That is exactly the move
`auto-security`'s own workspace description warns against (glm-4.7-flash's
tool-reliability win was explicitly recorded as *untested for this
workspace's analytical job*), and it is not what §2/S3 of this doc specify
(a seat-specific `scan_code`-comparison run before any chat-seat swap). No
seat-specific A/B for the security chat seat has been run. **The
`auto-security` chat-seat model must not change until that comparison runs.**
Only S0 had actually executed before the revert; S1-S4 were not attempted.

This entry closes S1 (card research) and corrects the audit baseline S2
planning was going to use. No model swaps or campaign runs were made.

### S1 — card research, closed
Every family with a live `model_hint` (base workspace or variant) now has a
card entry in `config/model_card_expectations.yaml`, most either a direct
vendor `generation_config.json`/README value or a traced `base_model`
lineage where the finetuner's own card was gone or gated:
`qwen3` (split into `qwen3`/`qwen3-coder`/`qwen3-coder-next`/`qwen3-vl`,
fixing the old shadowing), `qwen3.5/3.6/3.8`, `gemma4`, `granite-4.1/4.2`,
`phi4`, `deepseek-r1`, `lfm2`, `laguna`, `mimo`, `vulnllm`, `gpt-oss`,
`glm-4.7-flash`, `nemotron-3.5-lightning`, `mistral-small`, `llama`,
`hermes`, `kat-coder`, `nex-n2`, `tongyi`, and new lineage-only entries
`baronllm`, `ornith`, `north-mini-code`, `omnicoder`, `agentworld`,
`supergemma4`. Only `command-r` remains `research-debt` (no live
`model_hint` currently uses it — folded 2026-09-12). Card sources and dates
are recorded per entry; several are marked `verified-lineage` rather than
`verified-card` where the finetune's own repo was unreachable and the base
model's card stands in — that distinction is preserved in the registry, not
collapsed into a false "verified-card".

### Corrected served-vs-card baseline
A serving-aware re-diff (production `think`/`think_profiles` resolution +
oMLX-native vs alias detection, against the now-complete registry) found:
**39 seats deviate from their card, 11 match** — worse than this doc's
original 30/4 estimate, because most of the fleet was previously resolving
to the generic `qwen3` entry or no entry at all. Matches: `auto`,
`auto-general-uncensored` (huihui-Qwen3.6 bakes no sampling → served
defaults happen to equal instruct card), `auto-daily`, `auto-coding::lite`,
`auto-coding::northmini` (no card — `NO-CARD`, not a real match, see below),
`auto-creative`, `auto-reasoning`, `auto-council`, `auto-data`, `auto-math`,
`auto-audio`. Every deviating seat is temperature 0.1-0.3 (occasionally
0.5-0.6) against a card of 0.6-1.0, consistent with the doc's original
"near-greedy decoding" hypothesis — this is now confirmed for the full
fleet, not a 30-seat sample. Full per-seat table generated by the script
below (not committed — regenerate before S2, since Ollama/oMLX inventory
changes between sessions).

Three seats still have **no** card even after S1: `auto-coding::northmini`
(North-Mini-Code has a card now — this was a stale sample, re-verify),
`auto-coding::uncensored` and `auto-coding::ornith` had cards added this
session (`omnicoder`, `ornith`) — re-run the diff to confirm they now
resolve. `auto-uncensored-throwaway::ornith15` needs the `ornith` key too
(GGUF metadata confirms lineage: Ornith-1.5-35B-A3B + Qwen3.6-35B-A3B
abliterated base).

### Harness defect found — fix before any S2 rerun
`tests/wfe/runner.py:1026`: when a turn raises `StreamStalledError` (900s
stream stall, `WFE_STALL_S`), `execute_turn()` sets
`outcome_override = BUDGET_EXHAUSTED`, but `_finalize_outcome()` only
downgrades to `BUDGET_EXHAUSTED` `if outcome != Outcome.PASS` — i.e. if the
checker finds a PASS-shaped artifact on disk from a prior turn's partial
work, the stall is silently discarded and the row reports `PASS`. This is
not hypothetical: it is the exact failure the reversion notes recorded in
`s2_seat_vendor_omlx_seat_v1` row 1
(`auto-coding|Qwen3-Coder-30B-A3B-Instruct-4bit|coding|code-cli-args|r0`,
900.5s, `StreamStalledError` after the 885s ceiling, reported PASS). A stall
must always override a checker PASS — the model did not actually finish.
**Fix `_finalize_outcome` before trusting any coding/agentic PASS count from
a rerun of that campaign**, and re-score `s2_seat_vendor_omlx_seat_v1`'s one
completed row once fixed rather than assuming its PASS is real.

### S0 items this session did NOT touch (still open, in current `main`)
- `_REASONING_TAG_RE` in `tests/wfe/settings_audit.py` still matches
  `granite4\.[12]`, so `granite4.1:8b`/`granite4.1:30b` still raise
  `reasoning_uncontrolled` (confirmed live: `bench-granite41-8b`,
  `bench-granite41-30b`). Per this doc's S0 and the granite-4.1 card
  (`prompt_contract`: "No thinking/reasoning mode"), that pattern should
  exclude 4.1 and match only `granite4\.2`.
- oMLX-served hints for **bench** workspaces (not production workspaces —
  those already resolve via `backends.yaml` aliases) still report
  `hint_absent`: `bench-qwen38-flash-next-reap288`
  (`Qwen3.8-Flash-Next-REAP-288-MLX-4bit`) and
  `bench-nex-n25-mini-uncensored` (`Nex-N2.5-mini-Uncensored-MLX-4bit`) are
  raw oMLX-served ids with no Ollama tag and no `backends.yaml` alias
  pointing at them; `installed_tags()` in `settings_audit.py` only reads
  Ollama `/api/tags` + declared aliases, not oMLX's own `/v1/models`
  inventory, so it can't see them. Confirmed live: both ids exist in
  `GET :8085/v1/models`.
- No `qwen3-vl` card existed before this session; it now has one
  (`recommended_sampling` 0.7/0.8/20/1.0/1.5, sourced from
  `Qwen/Qwen3-VL-32B-Instruct`) — `auto-vision` now reports real `FAIL`
  deviations instead of `card_research_debt`.
- Two persona pins are dangling (`persona:nemotronlightning` →
  `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M`;
  `persona:qwen38coder-dflash` → `Qwen3.8-27B-4bit`) and one compliance
  council seat is unregistered (`mistral-small3.2:24b-instruct-2506-q4_K_M`
  not in `backends.yaml`) — pre-existing, unrelated to this task, flagged
  for whoever owns persona/council maintenance.

### Re-plan for S2 (not started)
1. Fix the `runner.py:1026` stall-masking defect first (S2 harness
   precondition, not optional).
2. Do **not** batch multiple seats/arms in one campaign+commit the way the
   reverted attempt did. One seat, one A/B, one decision entry in the
   Result log, per this doc's own Method — that is what makes each change
   auditable and revertable independently.
3. `auto-security` base seat: no chat-seat model change without the S3
   `scan_code`-comparison run (candidates with tools that can call
   `scan_code`, scored against the trained-detector baseline) — not a
   generic tool-reliability re-use of the 2026-07-16 P5-AUTOSEC-RESELECT
   evidence, which this workspace's own description already disclaims for
   this exact purpose.
4. Re-run the served-vs-card diff immediately before S2 kickoff (fleet
   inventory drifts session to session — this session alone changed the
   registry's match rate 3x).
