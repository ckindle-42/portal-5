# Task: verify the 2026-09-25 card-sampling switch, seat by seat

**Opened:** 2026-09-25. **Continues:** `docs/TASK_SEAT_VENDOR_FIT_V1.md` (S2–S5), which
remains the method reference. **Executor:** a coding agent, unattended between
operator checkpoints. **Read "Rules" before running anything.**

## What changed, and why this task exists

Until `b76db906` (2026-09-25) no Ollama-served seat ever received its
`portal.yaml` sampling: Ollama's `/v1` forced temperature/top_p to 1.0 and dropped
top_k/min_p/repeat_penalty. The 0.1–0.3 temperatures in `portal.yaml` were never
what users got, and serving them for the first time put the fleet in the
near-greedy regime Qwen's card warns causes endless repetition.

**Operator decision, 2026-09-25:** switch production seats to their vendor
card's sampling now, *by purpose*. Then A/B each one against its prior config and
revert the losers. The decision covered three points:

- **Security seats** were first exempt. On the operator's follow-up request
  (2026-09-25) they got the same treatment for **engine settings only**:
  sampling, template and think checks. System prompts, models and tools were
  left untouched. See "Security seats" below.
- **By-purpose exceptions:**
  - `auto-compliance`, `compliance-reading`: deterministic lane, settled 0.3 policy.
  - `auto-image`, `auto-video`: granite card is greedy; the job is creative prompt-writing.
  - `auto-music`: LFM card 0.2; the job is lyrics.
  - `auto-nemotron`: NVIDIA's card is a unified 1.0/0.95, but the seat follows an
    unsloth thinking/instruct split. The unsloth page now 404s, so that split is
    unverified. See B6.
- **Kept on every changed seat:** the `min_p` / `repeat_penalty` loop guards
  wherever the card is silent on them.
- **`presence_penalty` on Ollama** is a measured no-op. On the production Ollama
  seats whose card asks for 1.5, it was replaced by `repeat_penalty: 1.05`
  (`frequency_penalty` works on Ollama too, but workspace sampling cannot declare
  it; see C4). Seats: `auto-general-uncensored`, `auto-council`, `auto-data`,
  `auto-uncensored-throwaway` (+`::ornith15`), `auto-vision`,
  `auto-coding::uncensored`. Bench workspaces had the key dropped with no
  substitute.
- The two Qwen3.8 coding seats (`::uncensored-fast`, `::reap288`) had no `think`
  pin, so they were thinking natively. Both now have **`think: false`** plus the
  card's **instruct** mode, as the project's evidence and history call for:
  - REAP-288's bench seat ran `think: false` on purpose ("code repair, not a
    reasoning task"). The flag was lost when it became a variant (`5703b5e8`).
  - The Qwen3.x default `<think>` loops or exhausts the token budget on lanes
    that don't need reasoning. auto-compliance looped for 300+ lines on
    2026-08-31. See memory `feedback_thinking_model_needs_think_false`.
  - The settings auditor resolves a seat without a pin to its native mode
    (reasoning model → thinking card).

### Now vs prior (the A/B arms)

"Now" is what production serves after this change. "Prior" is the full sampling
block to pass as a variant arm's `sampling:` (an override *replaces* the seat's
keys, so guards are restated). Regenerate from `git show <this commit>~1:config/portal.yaml`
if in doubt.

| Seat | Engine | Now served (card) | Prior arm (`sampling:` override) |
|---|---|---|---|
| `auto-extract-uncensored` | ollama | `{temperature: 0.2, top_p: 0.95, top_k: 80, repeat_penalty: 1.05}` | `{temperature: 0.6, top_p: 0.95, repeat_penalty: 1.05}` |
| `auto-general-uncensored` | ollama | `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.0, repeat_penalty: 1.05}` | see B4 (penalty arms) |
| `auto-uncensored-throwaway` | ollama | `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.0, repeat_penalty: 1.05}` | `{temperature: 0.8, top_p: 0.95, top_k: 50, min_p: 0.02}` |
| `auto-uncensored-throwaway::gemma4-heretic` | ollama | `{temperature: 1.0, top_p: 0.95, top_k: 64, min_p: 0.0, repeat_penalty: 1.0}` | `{temperature: 0.8, top_p: 0.95, top_k: 50, min_p: 0.02}` |
| `auto-uncensored-throwaway::ornith15` | ollama | `{temperature: 1.0, top_p: 0.95, top_k: 20, min_p: 0.0, repeat_penalty: 1.05}` | `{temperature: 0.8, top_p: 0.95, top_k: 50, min_p: 0.02}` |
| `auto-coding` | omlx | **reverted** to `{temperature: 0.2, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.05}`: card lost on tool calls (see Tool verification) | card `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}`, A/B unblocked (C6 done) |
| `auto-coding::laguna` | omlx | `{temperature: 1.0, top_p: 1.0, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.2, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.05}` |
| `auto-coding::uncensored` | ollama | `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.2, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.05}` |
| `auto-coding::uncensored-agentic` | ollama | `{temperature: 1.0, top_p: 0.95, top_k: 40, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.2, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.05}` |
| `auto-coding::fast-repair` | ollama | `{temperature: 1.0, top_p: 0.95, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.2, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.05}` |
| `auto-coding::uncensored-fast` (think: false) | ollama | `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.2, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.05}` |
| `auto-coding::heavy` | ollama | `{temperature: 1.0, top_p: 0.95, top_k: 40, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.2, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.05}` |
| `auto-coding::ornith` | ollama | `{temperature: 1.0, top_p: 0.95, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.6, top_p: 0.95, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` |
| `auto-coding::reap288` (think: false) | omlx | `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.6, top_p: 0.95, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` |
| `auto-spl` | ollama | `{temperature: 1.0, top_p: 0.95, top_k: 40, repeat_penalty: 1.1}` | `{temperature: 0.2, top_p: 0.95, repeat_penalty: 1.1}` |
| `auto-bigfix` | omlx | **reverted** to `{temperature: 0.1, top_p: 0.9, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` | card, A/B unblocked (C6 done) |
| `auto-cad` | omlx | **reverted** to `{temperature: 0.2, top_p: 0.9, top_k: 40, repeat_penalty: 1.1}` (`top_k` now bounded) | card, A/B unblocked (C6 done) |
| `tools-specialist` | omlx | `{temperature: 0.0, top_p: 0.95, repeat_penalty: 1.0}` | `{temperature: 0.6, top_p: 0.95, repeat_penalty: 1.0}` |
| `tools-specialist::fast` | ollama | `{temperature: 1.0, top_p: 0.95, top_k: 64, repeat_penalty: 1.0}` | `{temperature: 0.6, top_p: 0.95, repeat_penalty: 1.0}` |
| `auto-reasoning::deep` | omlx | `{temperature: 1.0, top_p: 0.95, top_k: 20, min_p: 0.0, repeat_penalty: 1.1}` | `{temperature: 0.6, top_p: 0.95, top_k: 20, min_p: 0.0, repeat_penalty: 1.1}` |
| `auto-council` | ollama | `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.0, repeat_penalty: 1.05}` | see B4 |
| `auto-documents` | omlx | `{temperature: 0.0, top_p: 0.9, top_k: 40, min_p: 0.05}` | `{temperature: 0.5, top_p: 0.9, top_k: 40, min_p: 0.05}` |
| `auto-research` | ollama | `{temperature: 0.7, top_p: 0.95, top_k: 40, min_p: 0.02}` | `{temperature: 0.6, top_p: 0.95, top_k: 40, min_p: 0.02}` |
| `auto-vision` | ollama | `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.5, top_p: 0.9, top_k: 40, min_p: 0.05}` |
| `auto-data` | ollama | `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.0, repeat_penalty: 1.05}` | see B4 |

### Security seats (engine settings, 2026-09-25)

Template and engine check (neutral probes, all on the production engine):

| Model (engine) | Seats | Tools render | Think control | Notes |
|---|---|---|---|---|
| VulnLLM-R-7B-4bit (oMLX) | base, blueteam-orchestrated, blueteam-council | ✓ | no separate reasoning channel either way | ignores the contrived system-word probe |
| granite-4.1-8b-mxfp8 (oMLX) | blueteam | ✓ | no thinking mode (as carded) | ignores the contrived system-word probe |
| Huihui-Qwen3.5-9B-abliterated-mlx-4bit (oMLX) | redteam, purpleteam, purpleteam-deep | ✓ | honoured (off: 0 reasoning; on: reasons) | system ✓ |
| Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit (oMLX) | pentest | ✓ | honoured | system ✓ |
| baronllm-abliterated ctx8k (Ollama) | uncensored | ✓ | no thinking (think:true → 400; seat sends false) | declined the system-word probe |
| supergemma4-26b-uncensored ctx64k (Ollama) | redteam-deep, purpleteam-exec | ✓ (direct probe 3/3 clean) | honoured | `supports_tools: false` is deliberate: driver-dispatched, looped with tools in context on UAT 2026-06-27, which was measured under the old `/v1` delivery. Operator-held. |

Sampling now vs prior. Loop guards are kept where the card is silent.
`pentest` keeps `repeat_penalty 1.1` as the thinking-chain guard (the card says
1.0), which is the auditor's one remaining deviation there. `pentest` uses the
qwen3.6 `thinking_precise_coding` mode, because its job is an exec loop.

| Seat | Now served (card) | Prior arm |
|---|---|---|
| `auto-security`, `::blueteam-orchestrated`, `::blueteam-council` (VulnLLM) | `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.3, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.1}` |
| `::uncensored` (baronllm) | `{temperature: 0.6, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.1}` | temperature 0.3, rest same |
| `::pentest` (qwen3.6, think on) | `{temperature: 0.6, top_p: 0.95, top_k: 20, min_p: 0.0, presence_penalty: 0.0, repeat_penalty: 1.1}` | `{temperature: 0.3, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.1}` |
| `::blueteam` (granite, greedy) | `{temperature: 0.0, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.1}` | temperature 0.3, rest same |
| `::redteam`, `::purpleteam`, `::purpleteam-deep` (qwen3.5 9B, think off, oMLX honours presence) | `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.05, presence_penalty: 1.5, repeat_penalty: 1.0}` | `{temperature: 0.3, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.1}` |
| `::redteam-deep` (supergemma4) | `{temperature: 1.0, top_p: 0.95, top_k: 64, min_p: 0.05, repeat_penalty: 1.1}` | `{temperature: 0.3, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.1}` |
| `::purpleteam-exec` (supergemma4) | `{temperature: 1.0, top_p: 0.95, top_k: 64, min_p: 0.05, repeat_penalty: 1.1}` | `{temperature: 0.1, top_p: 0.9, top_k: 20, min_p: 0.05, repeat_penalty: 1.1}` |

`auto-coding::northmini` had `top_k: 40` pinned so it did not inherit the base's
new 20; nothing else about it changed.

## Rules (non-negotiable; from CLAUDE.md, memory, and the parent task)

1. **One request in flight, one bench at a time.** Never run two campaigns or a
   campaign beside UAT. Stack up (production-like), except arms that need the
   stack down (REAP-288 IDE path).
2. **Back up any checkpoint before clearing or overwriting it** (`cp` to a dated
   name first, unconditionally).
3. **One seat → one campaign → one decision → one commit.** Never batch config
   changes across seats (the reverted `d51dd29a` did exactly that).
4. **`auto-security*`: engine settings only.** Sampling A/B is B8. Do not change
   system prompts, models or tool lists. S3's `scan_code` comparison gates the
   chat-seat model, and `purpleteam-exec`'s `tools_unsupported` FAIL is the
   operator's to decide (that FAIL cleared 2026-09-25: supergemma4 re-verified
   `supports_tools: true`, so the pipeline now offers purpleteam-exec its tools;
   the next lab UAT must confirm the live exec loop). Use the benign probe set (the colour, arithmetic and
   weather-tool probes in `tests/wfe/settings_audit.py`) for template checks.
   Run the security bench directly in the main session (not a subagent).
5. **Before blaming a model:** render its template, raw-generate, and compare
   with what the engine returned. Most past "model failures" were engine,
   config, or harness faults.
6. **Serve on the production engine.** A priority-10 oMLX alias means oMLX:
   `WFE_ENGINE=omlx WFE_CHAT_BASE_URL=http://127.0.0.1:8085`.
7. Use `uv run` for every pytest/ruff/mypy/python. Use a 300000–400000 ms
   timeout on `git push` (the pre-push hook takes about 4 minutes).
8. If an engine restart is needed, use the clean paths (`launchctl kickstart`,
   `./launch.sh`), never `kill -9` on Ollama/oMLX or the drivers.

## A — Preconditions (do once, before B)

- [ ] **A1** `git log -1` includes this task's commit. Rebuild the pipeline
      image (`./launch.sh rebuild`), because `portal.yaml` is baked into it.
      Verify with a live request through `:9099` that the new seat sampling is
      served (e.g. `auto-coding::laguna`, `auto-vision`).
- [ ] **A2** `uv run python scripts/engine_contract_check.py`: PASS on both engines.
- [ ] **A3** `uv run python -m tests.wfe.settings_audit`: the only FAIL is
      `auto-security::purpleteam-exec tools_unsupported` (operator-held).
      Save the output as the baseline in the result log.
- [ ] **A4** Before the first run, check that Docker images are not older than
      HEAD for pipeline-affecting commits.

## B — A/B campaigns (in this order)

Template: `tests/wfe/plans/s2_laguna_rerun_omlx.yaml` (incumbent = seat as
served now; `prior` arm; optional `think` arm). Copy it per seat into
`tests/wfe/plans/s2_<seat>.yaml`, taking `home` and `discovery` from
`tests/wfe/workloads.yaml` (or the lane table in the parent task), n=3. Always
`--dry-run` first.

**Decide by purpose** (parent task, Method §5):

- Agentic and coding lanes: pass rate **and** `BUDGET_EXHAUSTED` (turn cap,
  stall). Loops are the failure being hunted.
- Deterministic lanes: pass rate plus answer stability.
- Creative and general lanes: suite plus blinded review.

A tie keeps the card (the operator's default). A clear loss for the card
reverts that seat to its prior block. Record every decision in the result log
below and on the card entry's `behavioral_quirks` in
`config/model_card_expectations.yaml`.

- [ ] **B1 `auto-coding::laguna`** — the plan is ready (`s2_laguna_rerun_omlx.yaml`,
      campaign id `s2_laguna_rerun_omlx_v2`, 126 rows). Voids the old result.
- [ ] **B2 think check: `auto-coding::uncensored-fast` (Ollama), `auto-coding::reap288` (oMLX, stack down: `./launch.sh coder-reap288 --warm-only`)**.
      Both are pinned `think: false` with the instruct card (incumbent). Arms:
      - `prior` (the table's prior block, `think: false`);
      - `think: true` with the thinking card `{temperature: 1.0, top_p: 0.95, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}`.

      Caveat: uncensored-fast's only WFE result (9/9 coding, `wfe_full_20260911`)
      ran before `8ccaa84a`, when `think: false` was a silent no-op on Ollama
      `/v1`. It was therefore measured *thinking* (and at 1.0/1.0). The think-on
      arm is a real contender there, not a formality. Flip the pin only on a clear
      win with no rise in `BUDGET_EXHAUSTED`. Also check the other seats with no
      `think` pin whose models may think by default (`::ornith`, `::fast-repair`),
      and pin them the same way.
- [ ] **B3 Ollama seats**, highest traffic first: `auto-general-uncensored` and
      `auto-data` (B4 arms), `auto-research`, `auto-council` (B4), `auto-vision`,
      then the `auto-coding` Ollama variants (`::heavy`, `::uncensored-agentic`,
      `::fast-repair`, `::uncensored`, `::ornith`), `auto-spl`,
      `auto-extract-uncensored`, `tools-specialist::fast`, and the
      `auto-uncensored-throwaway` family.
- [ ] **B4 presence substitute calibration** (the Qwen3.6 seats
      `auto-general-uncensored`, `auto-council`, `auto-data`; carry the result to
      `auto-uncensored-throwaway`, `auto-vision`, `auto-coding::uncensored`).
      Arms on the instruct card base `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.0}`:
      `+repeat_penalty 1.05` (incumbent), `+repeat_penalty 1.0` (no guard),
      `+repeat_penalty 1.1`. Also test `frequency_penalty` if C4 lands first.
      A `presence_penalty` arm is BLOCKED on Ollama by design. Score repetition
      (loops, `BUDGET_EXHAUSTED`) as well as pass rate. `auto-council`'s judgment
      probe is its home lane.
- [ ] **B5 oMLX seats:** `auto-coding` (+`auto-bigfix`, `auto-cad`),
      `auto-reasoning::deep` (deep-lane prompts), `tools-specialist` and
      `auto-documents` (greedy 0.0 on granite4.1:8b; watch for greedy loops in
      long documents, which is the specific risk of the card here).
- [ ] **B6 by-purpose exceptions** (these kept their prior config; A/B the card
      as the *challenger*):
  - `auto-compliance` (card instruct 0.7/0.8/20 vs seat 0.3/0.95).
  - `compliance-reading` (card 1.0/0.95/64 vs 0.3/top_k 20; use the module
    acceptance cases, and keep `ACCEPTANCE_RUN=1` rules).
  - `auto-image`/`auto-video`/`auto-music` (card vs seat, blinded review of
    the produced prompts and lyrics).
  - `auto-nemotron`: first resolve the source conflict (NVIDIA unified 1.0/0.95
    vs the seat comment's unsloth 0.6/0.95 thinking / 0.2 instruct; find the
    unsloth source or record it as unverifiable), then A/B.
- [ ] **B8 security seats** (engine settings only; Rule 4). Highest risk
      first: the driver-parsed seats whose output a driver or multi-hop pipeline
      parses. These are `::purpleteam-exec` (0.1 → 1.0) and the rigid 5-phase
      `::redteam`/`::purpleteam`/`::purpleteam-deep`. Score format adherence and
      parse success as well as the bench outcome; the higher temperatures threaten
      these first. Then `::pentest` (exec loop, turn-cap exhaustion), the VulnLLM
      seats (the archived 6-snippet CWE set: recall plus clean false positives;
      card+trained prompt already scored 17/18, 0/3 FP vs 15/18, 3/3), `::blueteam`
      (greedy) and `::uncensored`. Use the existing security bench / UAT sections
      for these lanes. If a structured seat loses, revert it alone.
- [ ] **B7 apply winners** per seat:
  1. Edit `config/portal.yaml` (keep the `# 2026-09-25` marker line, amended with
     the decision).
  2. Run `./launch.sh sync-config`.
  3. Rebuild the pipeline.
  4. Send one live request through `:9099`.
  5. Commit (one seat per commit).

## Tool verification (2026-09-25, done)

Every production seat that declares tools was probed on its production engine
at its exact served sampling and `think`: 4 calls each, a neutral weather-tool
question. The flag check also covered the council seats and every model id
whose flags disagreed across groups: 3 single calls plus a tool-result turn
each. One request was in flight at a time, with the stack up. Results:

- **Clean** (4/4, or 3/3 + a clean tool-result turn): every Ollama seat, and on
  oMLX laguna, pentest, blueteam, the VulnLLM seats (4/4 on retry; the first
  pass got HTTP 409 while models were loading), tools-specialist, documents,
  image, video, compliance and `auto`.
- **Single misses at card temperature:** `auto-security::uncensored` (Baron,
  0.6) and `auto-research` (Nex-N2, 0.7), each 3/4. Worth watching in B3/B8;
  not a flag error.
- **Qwen3-Coder on oMLX** (`auto-coding`, `auto-bigfix`, `auto-cad`): 2–3 of 4 at
  the card sampling. The model sometimes skips the `<tool_call>` opener, and
  oMLX's `mlx_lm` `qwen3_coder` parser then returns the call as text. Reverted to
  the prior sampling (6/6, 6/6, 7/8) — P5-OMLX-QWEN3CODER-TOOLTEXT-001. Ollama
  parses the same model 3/3 at 0.7.
  Resolved by C6: the pipeline now recovers these calls whatever the sampling.
- **`phi4-mini-reasoning`**: 0/3, and it is correctly `supports_tools: false`.
- **Flags corrected to `true`** (probe or same-weights sibling):
  - supergemma4 (base + `-ctx64k`; also 3/3 multi-turn exec-shaped runs, no
    loop, at purpleteam-exec's sampling), which clears the auditor's last FAIL;
  - LFM2.5-Gaston (base + `-ctx8k`) and DeepSeek-R1-0528-Qwen3-8B (base + `-ctx64k`);
  - these ids, which had a group-split `false`: Nex-N2-mini (both), granite4.1:30b
    (both), qwen3-coder:30b, gpt-oss:20b, omnicoder2:9b, Gemma-4-31B-JANG,
    gemma-4-abliterated E2b, HauhauCS `:Q4`, gemma4:12b-it-qat,
    qwen3-coder-next:latest, Coder-Next-abliterated, VulnLLM `Q4_K_M` and Ornith-1.0.

  The router keeps **one** flag per model id (last entry wins), so a per-group
  split never did what its comments said.
- **Unverified, left as-is:** 11 ids that are not installed and have no installed
  sibling. They still carry split flags, which is harmless while they're not
  installed; re-probe any of them before use:
  - `portal5/qwen3.6-27b-mtp:q8_0-drafted`, `gemma4:e2b-it-qat`, `gemma4:31b-it-qat`
  - FastContext-4B, `devstral:24b`, Qwopus3.6-27B, GLM-4.7-Flash-REAP-23B,
    bartowski Qwen3.6-27B
  - `cybersecqwen-4b-toolfix`, `huihui_ai/qwen3-abliterated:14b-v2`, `devstral-small-2`

## C — Code items

- [x] **C6 Qwen3-Coder tool-call salvage** (P5-OMLX-QWEN3CODER-TOOLTEXT-001),
      done 2026-09-25 in the pipeline (`salvage_text_tool_calls` /
      `TextToolCallHoldback`, streaming and non-streaming,
      `portal5_tool_calls_recovered_total`). Acceptance met: 200/200 probe calls
      as `tool_calls` through the pipeline on oMLX (card 0.7, seat, and 1.2),
      `./scripts/smoke_stream.sh` PASS. Finding: the loss is prompt-shaped, not
      temperature-driven. Some pipeline prompts lost the opener on every attempt
      at the seat's 0.2, so the low-temperature revert was never a real
      mitigation. Next: the card vs prior A/B for `auto-coding`/`auto-bigfix`/
      `auto-cad` is unblocked; tool reliability no longer depends on it.

- [ ] **C1 S3: VulnLLM `scan_code` tool** — spec in the parent task §S3. It goes
      in `portal/modules/security/tools/security_mcp.py`:
  - VulnLLM's exact trained prompt: `reasoning_user_prompt` + `new_policy` CWE list
    + `our_cot` from `ucsb-mlsec/VulnLLM-R vulscan/utils/sys_prompts.py`.
  - Card sampling 0.7/0.8/20, rep 1.05; 3072 max tokens.
  - Parses `## Final Answer / #judge / #type`.
  - Acceptance: ≥17/18 on the archived 6-snippet CWE set, 0/3 clean false
    positives, and one live pipeline request in which the chat model calls the tool.
  - **The tool only**: no chat-seat model change, no sampling edits, no
    unrelated routing edits in the same commit (see
    `docs/TASK_SEAT_VENDOR_FIT_V1_REVERSION_NOTES_20260925.md`). The chat-seat
    comparison that follows is the operator's go/no-go.
- [ ] **C2 `tool_choice=required` on Ollama** is ignored on every endpoint
      (KNOWN_LIMITATIONS). Inventory which seats and personas rely on it
      (`grep -rn tool_choice portal/ config/`). Report where a single-tool schema
      already narrows the call and where it does not. Propose; don't implement
      forcing without operator sign-off.
- [ ] **C3 oMLX admin key for the harness** (item 21): wire an oMLX admin API
      key (`.env.example` + the WFE runner's oMLX drain) so arms unload models
      instead of restarting oMLX. Keep the restart path as a fallback.
- [ ] **C4 `frequency_penalty` in workspace sampling:**
      `router/validation.py` resolves a fixed key list that omits it, although
      the Ollama native adapter forwards it. Add it end-to-end: resolver,
      `LANE`/auditor served check, WFE `_keys`, engine contract probe. It's the
      additive analogue of presence, and the B4 calibration needs it.
- [ ] **C5 unregistered derived tags from `apply-params`:** it now covers
      variants (this task's commit), but a newly created `-ctxNk` tag still has
      to be hand-registered in `backends.yaml`, or the router falls back
      silently (`hint_unroutable`). Either register it in the same run or make
      the command print the exact `backends.yaml` stanza to add.

## D — Carried-over queue (S4)

- [ ] **D1** granite 4.2 rerun at card settings on the fixed harness, against 4.1.
- [ ] **D2** VulnLLM mradermacher `i1` (imatrix) GGUF, same size, against the current quant.
- [ ] **D3** Qwen3.8 builds on `auto-compliance`: unsloth UD-Q4_K_XL and
      ISTA-DASLab GSQ-RCO IQ3_S against the current Q4_K_M.
- Anything measured on Ollama before 2026-09-25 evening is not seat evidence; rerun it.

## E — UAT overhaul (S5), after B lands

Write the scenarios the parent task lists (§S5). Add these:

- A loop/repetition check on every seat whose sampling changed in this task.
- Reasoning display in OWUI: the pipeline promotes Ollama `reasoning` deltas, and
  lfm2.5 emits a raw inline `<think>` (item 19). Record how OWUI renders both.
- Multi-turn tool conversations over the native path.

`tests/uat/settings_gate.py` must pass before any section runs. UAT sections
run sequentially, never in parallel.

## Operator-held (do not act; surface in the report)

- `keep_alive` delivery (operator is monitoring).
- `auto-security::purpleteam-exec` declares tools its model is marked as not
  supporting.
- oMLX 0.7.0rc1 early adoption (the updater skips pre-releases; `--allow-prerelease`).
- p40 (thebrain): top_k/min_p/repeat_penalty can only be set by baking them into the tag there.
- At the next Ollama upgrade: does the macOS data01 popup still appear?

## Result log

| Date | Seat | Arms (n=3) | Result | Decision / commit |
|---|---|---|---|---|
| | | | | |
