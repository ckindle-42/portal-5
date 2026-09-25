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

- **Exempt:** every `auto-security*` seat (safety-guard risk; seat rule from
  S3 stands), plus these by-purpose exceptions:
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
| `auto-coding` | omlx | `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.2, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.05}` |
| `auto-coding::laguna` | omlx | `{temperature: 1.0, top_p: 1.0, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.2, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.05}` |
| `auto-coding::uncensored` | ollama | `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.2, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.05}` |
| `auto-coding::uncensored-agentic` | ollama | `{temperature: 1.0, top_p: 0.95, top_k: 40, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.2, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.05}` |
| `auto-coding::fast-repair` | ollama | `{temperature: 1.0, top_p: 0.95, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.2, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.05}` |
| `auto-coding::uncensored-fast` (think: false) | ollama | `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.2, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.05}` |
| `auto-coding::heavy` | ollama | `{temperature: 1.0, top_p: 0.95, top_k: 40, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.2, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.05}` |
| `auto-coding::ornith` | ollama | `{temperature: 1.0, top_p: 0.95, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.6, top_p: 0.95, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` |
| `auto-coding::reap288` (think: false) | omlx | `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.6, top_p: 0.95, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` |
| `auto-spl` | ollama | `{temperature: 1.0, top_p: 0.95, top_k: 40, repeat_penalty: 1.1}` | `{temperature: 0.2, top_p: 0.95, repeat_penalty: 1.1}` |
| `auto-bigfix` | omlx | `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.1, top_p: 0.9, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` |
| `auto-cad` | omlx | `{temperature: 0.7, top_p: 0.8, top_k: 20, repeat_penalty: 1.05}` | `{temperature: 0.2, top_p: 0.9, repeat_penalty: 1.1}` |
| `tools-specialist` | omlx | `{temperature: 0.0, top_p: 0.95, repeat_penalty: 1.0}` | `{temperature: 0.6, top_p: 0.95, repeat_penalty: 1.0}` |
| `tools-specialist::fast` | ollama | `{temperature: 1.0, top_p: 0.95, top_k: 64, repeat_penalty: 1.0}` | `{temperature: 0.6, top_p: 0.95, repeat_penalty: 1.0}` |
| `auto-reasoning::deep` | omlx | `{temperature: 1.0, top_p: 0.95, top_k: 20, min_p: 0.0, repeat_penalty: 1.1}` | `{temperature: 0.6, top_p: 0.95, top_k: 20, min_p: 0.0, repeat_penalty: 1.1}` |
| `auto-council` | ollama | `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.0, repeat_penalty: 1.05}` | see B4 |
| `auto-documents` | omlx | `{temperature: 0.0, top_p: 0.9, top_k: 40, min_p: 0.05}` | `{temperature: 0.5, top_p: 0.9, top_k: 40, min_p: 0.05}` |
| `auto-research` | ollama | `{temperature: 0.7, top_p: 0.95, top_k: 40, min_p: 0.02}` | `{temperature: 0.6, top_p: 0.95, top_k: 40, min_p: 0.02}` |
| `auto-vision` | ollama | `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.05, repeat_penalty: 1.05}` | `{temperature: 0.5, top_p: 0.9, top_k: 40, min_p: 0.05}` |
| `auto-data` | ollama | `{temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.0, repeat_penalty: 1.05}` | see B4 |

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
4. **Do not touch `auto-security*` sampling or models.** S3's `scan_code`
   comparison gates the chat-seat model; `purpleteam-exec`'s `tools_unsupported`
   FAIL is the operator's to decide.
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
- [ ] **B7 apply winners** per seat:
  1. Edit `config/portal.yaml` (keep the `# 2026-09-25` marker line, amended with
     the decision).
  2. Run `./launch.sh sync-config`.
  3. Rebuild the pipeline.
  4. Send one live request through `:9099`.
  5. Commit (one seat per commit).

## C — Code items

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
