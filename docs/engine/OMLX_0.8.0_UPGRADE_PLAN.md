# oMLX 0.7.3 → 0.8.0 upgrade plan (prepared 2026-11-19, no live changes made)

Incumbent: **oMLX 0.7.3** (last verified stable; `docs/ENGINE_H2H_RESULTS_20261113.md`,
`docs/ENGINE_GRADE_20261115.md` still grade 0.7.3 as the incumbent). Target: **oMLX 0.8.0**,
released 2026-11-18 ([v0.8.0](https://github.com/jundot/omlx/releases/tag/v0.8.0), commit
`7fad36c`, `prerelease: false`), after [v0.8.0rc1](https://github.com/jundot/omlx/releases/tag/v0.8.0rc1)
(2026-11-12) and the 0.7.4.dev1 dev releases. This is the engine's next major release line
after 0.7.0 (2026-10-01 upgrade, `docs/reports/ENGINE_UPGRADE_20261001.md`).

Everything below is written from the release notes/PRs, the GitHub release asset list, and
repo code read at HEAD on this lane. Nothing here has touched the live engine — the live
ladder is §4 and is the orchestrator's.

## 1. What changed between 0.7.3 and 0.8.0

### 1.1 API / CLI / config surface

No endpoint, CLI verb or settings-file rename is announced in the release notes. The
behaviour changes that Portal code makes assumptions about:

| Change | Reference | Portal impact |
| --- | --- | --- |
| `reasoning_effort: "none"` / `"off"` now turn thinking **off** (previously mapped to `low`, i.e. thinking stayed on) | [#5151](https://github.com/jundot/omlx/pull/5151) | Portal never sends `reasoning_effort:none` to oMLX: `_apply_reasoning_effort` converts it to `think:False` first (`portal/platform/inference/router/validation.py:322-327`), and the oMLX adapter maps think to `chat_template_kwargs.enable_thinking` (`validation.py:526-530`). The tiers Portal does forward (`low/medium/high` → `chat_template_kwargs.reasoning_effort`, `validation.py:505-511`) are unaffected. Seats that send an explicit effort will now get the OpenAI meaning end-to-end. |
| Thinking defaults are now read by **rendering the chat template** (GLM-4.6V, GLM-OCR report thinking on) | commit `44b0525` | Our oMLX fleet has no GLM models (grep of `config/backends.yaml`: GLM tags exist only in Ollama groups). For every model where a workspace sets `think`, Portal still injects `enable_thinking` explicitly, so engine-side default detection is a no-op for us. Only matters for direct IDE clients on a template-declares-thinking model. |
| INT8 Activation Prefill stays off unless a model opts in, with its own SSD cache blocks | [#5108](https://github.com/jundot/omlx/issues/5108) | If any host `~/.omlx/model_settings.json` entry had INT8 activation prefill enabled, its effective prefill path changes. Check the host file before/after (autoupdate backs both settings files up). |
| New global setting **Concurrent Request Priority** (default `Balanced`: keeps running streams ≥10 tok/s, cuts new-prompt TTFT 26%); short request arriving during a long prefill starts after the running chunk | [#5164](https://github.com/jundot/omlx/pull/5164), [#5160](https://github.com/jundot/omlx/pull/5160), [#5175](https://github.com/jundot/omlx/pull/5175) | Production keeps `max_concurrent_requests: 8`. Fanout/concurrency behaviour (TASK_FANOUT_CONCURRENCY_V1) changes shape — re-verify, don't re-tune blind (§4 step 5). |
| New Advanced setting **Keep GPU Awake After Requests**, 5 min default | [#5085](https://github.com/jundot/omlx/pull/5085) | Idle-unload accounting and the load guard's quiet-path reads (`portal/platform/inference/load_guard.py`) see the engine one setting different. GPU warmth is not residency, but verify idle unload still fires (KNOWN_LIMITATIONS "oMLX unload accounting can over-wait"). |
| Supervised console log keeps only warnings/errors under `brew services` and the macOS app | [#5179](https://github.com/jundot/omlx/pull/5179) | Our service is the Portal LaunchAgent (`com.portal5.omlx`, `OMLX_SUPERVISED=launchd`), whose full log goes to `/opt/homebrew/var/log/omlx.log` via the plist — unchanged. Watchdog log-tail behaviour unaffected. |
| New **Prefill Accelerator** (NVIDIA CUDA helper / DGX Spark / second Mac), enabled per model after Global Settings → Advanced → Enable Distributed Inference + Cluster pairing | [#5065](https://github.com/jundot/omlx/pull/5065), [#5163](https://github.com/jundot/omlx/pull/5163), [#5195](https://github.com/jundot/omlx/pull/5195), guide `docs/experimental/prefill-accelerator.md` | Off by default; single-M4-Pro host, no CUDA helper, no second Mac — do not enable. Listed so nobody "cleans up" the new settings keys. |
| New **oQh** quantization option ("Rotated codes" in the oQe section; output names end in `h`, e.g. `Qwen3.5-9B-oQ2.5h`); oQe itself more accurate at same size; >memory Qwen3.5/3.6 quantizable | [#5317](https://github.com/jundot/omlx/pull/5317), [#5292](https://github.com/jundot/omlx/pull/5292), [@keefar in #5332](https://github.com/jundot/omlx/pull/5332) | No Portal seat names an oQh checkpoint. A re-quant is a model change with its own A/B gate (MODEL_SEAT_PROCESS), not part of this upgrade. |
| **Tool-call parsing fixes**: array parameters split across JSON fragments are merged; tool names like `read` counted only in call position; coded error for an empty `tool_calls` finish; gpt-oss keeps completed messages on a malformed last header | [#5345](https://github.com/jundot/omlx/pull/5345), [#4433](https://github.com/jundot/omlx/pull/4433)/[#5161](https://github.com/jundot/omlx/issues/5161), [#5139](https://github.com/jundot/omlx/pull/5139), [#5224](https://github.com/jundot/omlx/issues/5224) | Same class as the 0.7.0 parallel-tool-call finding (no `index` on streamed deltas; fixed in `portal/platform/inference/router/streaming.py:359-362`, `_indexed_tool_calls`, and `:1029`). Server-side parse behaviour changed → smoke_stream + tool-turn rows must re-prove it (§4). |
| **Memory/ceiling**: unloading a model no longer disturbs still-loaded models (Metal wired limit stays); compiled-grammar cache capped at 1 GiB; MoE expert offload keeps resident experts under prefill pressure | [#5165](https://github.com/jundot/omlx/issues/5165), [#4321](https://github.com/jundot/omlx/issues/4321), [#4842](https://github.com/jundot/omlx/pull/4842) | #5165 changes the counter dynamics the load guard reads (P5-LOADGUARD-SWAP-001 reads `current_model_memory` direction during swaps; KNOWN_LIMITATIONS "oMLX unload accounting can over-wait") — the swap race may now behave differently, re-test. Grammar cap: the Pipeline sends no `response_format`/schema to oMLX (grep of `validation.py`), so this lands on IDE-direct clients only. |
| **Speculative decoding**: top-p MTP verify picks from top 512 candidates; DFlash drafter context kept on exact prefix hits; DFlash2 +10% (4 requests); `~` drafter path expansion fix; DSpark drafter batches verify across requests | [#5313](https://github.com/jundot/omlx/pull/5313), commit `22f2c43`/[#5344](https://github.com/jundot/omlx/pull/5344), [#5212](https://github.com/jundot/omlx/pull/5212), [#5154](https://github.com/jundot/omlx/pull/5154) | The omlx-coding MTP side-car seat (`Qwen3.8-27B-oQ4e-mtp`) and the DFlash2 seat (`Qwen3.8-27B-4bit`, `dflash_max_ctx: 65536` in host `~/.omlx/model_settings.json`, `config/backends.yaml:627-641`) change acceptance/throughput dynamics — bench rows stale after upgrade (§4 step 5). |
| **Speed**: Qwen 8-request decode +38% (#5309), two long requests +30% (#5090), 6-req 8-bit +16% (`b5c7793`); DeepSeek V4.1 prefill +44% (#5031), cold-shader first decode +269% (#5025); Affine KV decode up to +58% at long context (#5095), attention-sink prefill ~4x (#5088/#5101); short-prompt loops keep prefix-cache hits (#5324); image prefix hashing ~4x cheaper (#5202) | as cited | Every oMLX decode/prefill number in the repo (bench rows, h2h tables, ENGINE_GRADE) is measured on 0.7.x and goes stale for these seats. The prefix-cache limitation entry (2026-10-21, measured on 0.7.2) should be re-measured, not assumed. |
| **Benchmarks**: batch wider than Max Concurrent Requests no longer inflates tg TPS; code benchmarks no longer hang; Max Tokens Override for local accuracy runs | [#5312](https://github.com/jundot/omlx/pull/5312), `bf28cd6`, [#5189](https://github.com/jundot/omlx/pull/5189) | Comparability caveat for any before/after delta: pre-upgrade rows with batch>8 may have been inflated; the fix makes post-upgrade rows more honest, so a raw delta conflates engine speed with the fix. |
| **Dependencies**: transformers up to 5.22 | [#5131](https://github.com/jundot/omlx/pull/5131) | Risk item: `Laguna-XS-2.1-4bit` ships custom `modeling_laguna.py`/`configuration_laguna.py` that oMLX loads natively (`portal_wiki/archive/unit-model-catalog-laguna-xs-2-4bit.md`). A transformers major-line bump is exactly what breaks custom-code checkpoints — Laguna is a **priority-10 live production seat** (`config/backends.yaml:598-604`), so its canary is mandatory (§4 step 4). |
| **Model lists survive bad files** (skip unreadable safetensors header / HF refs file); Qwen3-Reranker scores no longer tie at 1.0 | [#5379](https://github.com/jundot/omlx/pull/5379), [#5329](https://github.com/jundot/omlx/pull/5329), [#5207](https://github.com/jundot/omlx/pull/5207) | `/v1/models` composition could differ if a previously-listed conversion had a bad file it now skips. `portal trace` alias hops re-prove the list (`portal/platform/inference/cli/trace/engines.py:139-145,177-188`). The :8942 VL reranker is a separate host service, not an oMLX seat — #5207 does not touch it. |

### 1.2 Distribution

Release assets (GitHub API, checked 2026-11-19): `omlx-0.8.0-cp311-cp311-macosx_15_0_universal2.whl`,
`...cp312...`, `...cp313...` (~41 MB each) plus two DMGs (macOS 26/27, macOS 15 Sequoia).
The wheel names match what the venv installer expects exactly
(`scripts/omlx_venv_install.py:_release_asset`, pattern
`omlx-<ver>-<tag>-<tag>-macosx_15_0_universal2.whl`, python tags cp311/cp312/cp313) — **no
installer change needed**. The updater's stable-release pick (`scripts/engine_autoupdate.py:328-336`)
skips `0.8.0rc1`/`0.7.4.dev1` by tag regex and returns `0.8.0`; `_PRERELEASE`
(`scripts/engine_autoupdate.py:462`) does not match `0.8.0`; `_semver` ordering puts
`(0,8,0) > (0,7,3) > (0,7,4)` (`scripts/check_updates.py:94-97`).

## 2. What in Portal touches each change (file:line, HEAD `15af4cd6f`)

**Upgrade path**
- `scripts/engine_autoupdate.py` — `omlx_latest()` :328-336 (stable pick), `_PRERELEASE` :462,
  `_update_target()` :465-481 (skips rejected), `omlx_upgrade()` :371-395 (staged venv wheel →
  restart → model-count wait), `omlx_backup()`/`omlx_restore()` :353-363 (both
  `~/.omlx/settings.json` and `~/.omlx/model_settings.json`), `_omlx_restart()` :339-350
  (venv `launchctl kickstart -k` vs `brew services restart`), `_await_visible()` :238-261
  (data01 TCC popup, 30 min then rollback), `omlx_point_at()` :409-439 (rollback),
  `omlx_prune()` :398-406, weekly/security gating `main()` :650-681. State
  `~/.portal5/engine_update.json`; launchd `deploy/launchd/com.portal5.engine-update.plist`.
- `scripts/check_updates.py` — `check_omlx()` :330-366 (`_release_gap("jundot/omlx", …)` :359,
  version read from the active venv python :332-350, brew symlink fallback :353-357),
  `_semver` :94-97, `_release_gap` prerelease filter :238-244.
- `scripts/omlx_venv_install.py` — `_release_asset()` :117-127 (wheel-name match), `_python_tag()`
  :102-114, `install_release_wheel()` :145-153, `stage_venv_upgrade()` :167-173,
  `relocate_venv_entrypoints()` :175-186, `activate_venv()` :189-202; **new** `venv_service_active()`
  :24-34 and `omlx_restart_command()` :37-43 (this lane).

**Contract probes** (the gate that accepts or rejects 0.8.0)
- `scripts/engine_contract_check.py` — `_omlx_version()` :417-427 (reads `/api/status`
  `version`), `_needs_probe()` :436-440 (served ≠ installed forces a re-probe — covers a
  manual upgrade too), `check_omlx()` :443-461 (`/v1/models` discovery + delivery probes),
  `_delivery()` :112-171 (top_k/min_p/top_p/temperature/seed/repeat/presence/max_tokens/think,
  with the presence-penalty escalation 2.0→5.0→10.0 introduced because 0.7.0's numerics
  needed >2.0, :137-147), `_gemma4_tool_format()` :178-220 (raw `<|tool_call>` leak probe,
  added for the p2-wave34 OWUI leak on 2026-11-19). Probe models: `config/engine_contract.yaml`
  (omlx: `huihui-ai--Huihui-Qwen3.5-9B-abliterated-mlx-4bit`, `gemma-4-26b-a4b-it-QAT-4bit`).
- State `~/.portal5/engine_contract.json`; the daily `--if-changed` run re-proves on ANY
  version change (engine_autoupdate `main()` :661-666).

**Request building (what Portal sends 0.8.0)**
- `portal/platform/inference/router/validation.py` — `_inject_omlx_options()` :494-536:
  `repetition_penalty` naming :522-524, `stream_options.include_usage` :513-514, sampling
  setdefaults :516-520, think → `chat_template_kwargs.enable_thinking` :526-530, effort tiers →
  `chat_template_kwargs.reasoning_effort` :505-511, `thinking_budget` passthrough
  `_apply_omlx_thinking_budget` :348-350; `_apply_reasoning_effort()` :310-332 (`none` →
  `think:False`, so #5151 cannot change our wire shape). Note: `thinking_budget` is
  **unprobed** by the contract check — a 0.8.0 change there would be silent (UNPROVEN §5).

**Routing/fallback (oMLX → Ollama GGUF cascade)**
- `config/backends.yaml` — oMLX entries: `omlx-local` :581-589 (holding, no routing),
  `omlx-coding` :591-655 (priority 10; Qwen3-Coder-30B, Laguna-XS-2.1, Qwen3.8-27B-oQ4e-mtp,
  Huihui-Qwen3.6-27B, Qwen3.8-27B DFlash2 :627-641), `omlx-reasoning` :799-848 (DeepSeek-R1
  deepseek_r1 parser seat :792-818), `omlx-general` :681-778, `omlx-security` :850-892,
  `omlx-creative` :894-901. Priority-10 alias blocks translate the production GGUF
  `model_hint`s to oMLX names, so an oMLX-served workspace falls back to its Ollama GGUF tag
  automatically when oMLX is unhealthy (`get_backend_candidates` order + `_hint_fallback`).
- `portal/platform/inference/router/backend_introspect.py` — `_omlx_model_loaded()` :116,
  `free_ollama_for_omlx()` :151, `make_room_for_omlx()` :211-217 (Ollama residents freed for
  oMLX admission).

**Memory / ceiling**
- `portal/platform/inference/load_guard.py` — `_omlx_prefill_zone()` :116-138 (reads
  `memory.prefill_safe_zone_ratio`), `/api/status` + admin reads/unloads
  (`_omlx_status` :806-817, `_omlx_used` :827, `_omlx_idle_models` :916, `_omlx_loading` :980,
  `_omlx_foreign_active` :1016), unload-counter direction logic per P5-LOADGUARD-SWAP-001.
- `scripts/omlx_memory_tier.py` (tiers; `launch.sh:57` writes `balanced` on every up;
  restart now service-aware, this lane). Ceiling limitation: P5-OMLX-CEILING-001
  (`portal_wiki/canonical/unit-known-limitations-omlx-balanced-ceiling.md`) — balanced's
  ceiling moves with free memory; `LOAD_GUARD_CEILING_GB` is the fixed-budget knob.

**Seat defaults / chat-template patcher (run by `./launch.sh sync-config`)**
- `scripts/omlx_seat_defaults.py` — writes single-seat models' resolved sampling into
  `~/.omlx/model_settings.json` (`_FIELDS` :48-55, `seat_defaults()` :70-103, `apply()` :106-125
  merge semantics: only keys it previously managed are removed, unmanaged keys — including
  0.8.0's new per-model keys — survive). Restart now targets the live service (this lane,
  :149-151).
- `scripts/omlx_chat_template_patch.py` — Gemma 4 post-tool no-think anchor
  (`patch_text()` :53-61, marker :40, unload of patched loaded models :73-99). 0.8.0's
  template-render thinking-default change does not remove the patched branch; idempotent,
  re-run after upgrade. Ollama side of the same gap: `portal/platform/inference/ollama_native.py`.

**Tool parsers (the silent-loss trap)**
- `scripts/omlx/deepseek_r1_tool_parser.py` + `scripts/install_omlx_parsers.sh` (venv-aware
  target discovery :15-25) + watchdog self-check `scripts/omlx-watchdog.sh:67-92`.
  A wheel upgrade replaces site-packages wholesale and silently drops the parser — that
  already happened once on `brew upgrade` (P5-FANOUT-001, 2026-09-25). **Must re-run after
  every upgrade**, venv or brew.

**launchd / startup**
- `deploy/launchd/com.portal5.omlx.plist` — `ProgramArguments`: `__OMLX_VENV__/bin/python
  -m omlx.cli serve` (entrypoint unchanged in 0.8.0 per release notes; verify at first
  restart — UNPROVEN), `ProcessType: Standard` with the comment that Background cut MoE
  decode ~56% (2026-11-15, `docs/ENGINE_GRADE_20261115.md`), `OMLX_SUPERVISED=launchd`,
  log `/opt/homebrew/var/log/omlx.log`. `deploy/launchd/com.portal5.omlx-watchdog.plist` +
  `scripts/omlx-watchdog.sh` (probe `/v1/models`, two-failure restart of the active label).
- `scripts/lib/util.sh` launch-path restarts are already venv-aware :779-783, :795-799.

**Read-only observability**
- `portal/platform/inference/cli/trace/engines.py` — `omlx_hop()` :177-188 reads
  `/v1/models/status` `final_ceiling`; model lists :139-145. Sections wired in
  `portal/platform/inference/cli/trace/command.py` :32-50.

**WFE / bench harness**
- `tests/wfe/campaign.py` — `OMLX_BASE` :318-322 (`/health` `engine_pool`), `drain_omlx()`
  :328+ (**fixed this lane**: it restarted brew unconditionally; with the venv LaunchAgent
  holding :8085 a brew restart drains nothing — bench rows would measure a previous arm's
  resident weights — and can start a port-conflicting crash loop). `scripts/uat_engines.py`
  is the per-seat canary runner.

## 3. Code changes

### 3.1 Made BEFORE the upgrade (this lane, with unit tests)

1. `scripts/omlx_venv_install.py` — `venv_service_active()` + `omlx_restart_command()`: one
   helper that returns the restart command for whichever oMLX service is live (venv
   LaunchAgent `com.portal5.omlx` vs brew `jundot/omlx/omlx`).
2. `scripts/omlx_seat_defaults.py`, `scripts/omlx_memory_tier.py` — restarted oMLX via
   `brew services restart` unconditionally (pre-cutover stragglers; the live service is the
   venv LaunchAgent, verified `launchctl print` on this host). On the upgrade path
   sync-config runs seat defaults; a changed file would have restarted the *fallback*
   service while the live one kept stale in-memory settings. Now both restart the live
   service.
3. `tests/wfe/campaign.py` `drain_omlx()` — same fix: a brew restart while the venv agent
   holds :8085 drains no residents (WFE arms would measure paging beside a previous arm's
   weights) and can start a second oMLX that crash-loops on the busy port. This is on the
   orchestrator's post-upgrade retest path, so it had to land before the upgrade.
4. Tests: `tests/unit/test_omlx_service_restart.py` (9 tests: venv-active probe, both
   restart branches, seat-defaults/memory-tier/wfe-drain wiring, dry-run no-restart,
   empty-pool skip).

Deliberately NOT changed (and why):
- `scripts/engine_autoupdate.py` restart branch :339-350 — already venv-aware; refactoring
  it onto the new helper would be a drive-by. (Pre-existing minor duplication of the label
  constants with `omlx-watchdog.sh`, `scripts/lib/util.sh` — noted, not touched.)
- Wheel/installer/semver logic — verified against the real 0.8.0 release assets and tag
  list (§1.2); nothing to fix.
- No new contract-check probe was added for `thinking_budget`/effort tiers: a behavioural
  probe whose 0.8.0 semantics I cannot validate offline risks a false REJECT that blocks
  the whole upgrade. Listed in §4/§5 instead (stop, don't improvise).

### 3.2 Changes that can only FOLLOW the upgrade (live, orchestrator)

1. `bash scripts/install_omlx_parsers.sh` — re-applies the DeepSeek parser into the fresh
   site-packages (pointless before: it would no-op against the old install).
2. `./launch.sh sync-config` — re-runs seat defaults + the Gemma template patcher against
   0.8.0 (idempotent).
3. Contract check against 0.8.0 (§4 step 1) — the accept/reject decision itself.
4. Verify host `~/.omlx/model_settings.json` extras survived the upgrade restart:
   `dflash_max_ctx: 65536` on the DFlash2 seat, any tool-parser stamps
   (`tokenizer_config.json` on disk in `/Volumes/data01/omlx-models/` survives, but verify).
5. `uv run python scripts/omlx_seat_defaults.py --dry-run` — confirm no seat-default churn
   from resolved-sampling changes before letting sync-config write.
6. Re-measure the prefix-cache limitation record (0.8.0 claims short-prompt loops keep
   hits — the 2026-10-21 record is 0.7.2-era).
7. Re-test the load-guard swap shape (P5-LOADGUARD-SWAP-001) — #5165 changed unload vs
   wired-limit behaviour the guard's counter-direction read depends on.
8. Bench/WFE re-runs (§4 step 5).

## 4. Live retest/bench plan for the orchestrator (smallest first)

Quiet host, nothing in flight (the autoupdater defers on its own while a WFE/UAT runs).
`uv run` everywhere; commands run from the live checkout (not this worktree).

**Step 0 — preflight (no engine contact beyond reads)**
```bash
uv run python -c "from scripts.engine_autoupdate import omlx_latest; print(omlx_latest())"
cat ~/.portal5/engine_update.json | python3 -m json.tool | head -30
uv run python scripts/engine_contract_check.py --if-changed omlx   # expect [SKIP] unless version changed
```
Expected: `0.8.0` from the first command; `rejected` in state does not contain `0.8.0`;
contract shows the last 0.7.3 verification. If `0.8.0` is in `rejected`, clear it only
after understanding why it was rejected (it will not be retried otherwise).

**Step 1 — the upgrade, contract-gated, automatic rollback**
```bash
uv run python scripts/engine_autoupdate.py --now omlx
```
- **Worked**: log shows `omlx: updating 0.7.3 -> 0.8.0`, `omlx: switched=True`, then
  `[OK] omlx 0.8.0` with every probe `ok` (delivery keys, think both ways, gemma4 native
  tool call parsed), then `omlx updated 0.7.3 -> 0.8.0`; history entry
  `{"from": "0.7.3", "to": "0.8.0", "contract_rc": 0, "result": "updated"}` in
  `~/.portal5/engine_update.json`.
- **Did not work**: `[FAIL] omlx …` probe lines + Pushover + history `rolled_back` with
  `rollback_rc`, `0.8.0` appended to `rejected` (engine back on 0.7.3 — verify with
  `uv run python -c "import scripts.engine_autoupdate as ea; print(ea.omlx_running())"`).
  `result: awaiting_approval` = the data01 popup is waiting — click Allow on the Mac
  within 30 min or it rolls back. `result: install_failed`/`release_unavailable` = the
  wheel/stage step; nothing changed live.

**Step 1b — parser reinstall (mandatory, silent-loss trap)**
```bash
bash scripts/install_omlx_parsers.sh
bash scripts/omlx-watchdog.sh && bash scripts/omlx-watchdog.sh   # second pass confirms
tail -5 ~/.portal5/logs/omlx-watchdog.log
```
Expected: `installed: …/mlx_lm/tool_parsers/deepseek_r1.py` and no `PARSER CHECK FAILED`
line. Skip this and the DeepSeek council-operator seat loses tool calls with no error.

**Step 2 — read-only trace (engines, aliases, workspaces)**
```bash
uv run portal trace --section engines --section aliases --section workspaces
```
- **Worked**: `omlx status PASS … final_ceiling readable` (ceiling value may differ from
  0.7.3's — record it), alias hops follow the engine's model list, workspaces end-to-end
  PASS with oMLX-served seats actually served by oMLX.
- **Did not work**: `omlx status FAIL final_ceiling absent` (status schema change — diff
  `GET :8085/api/status` and `/v1/models/status` against 0.7.3 before proceeding); alias
  hop failures (a conversion dropped out of `/v1/models` — #5379 now skips bad files).

**Step 3 — streaming smoke (live stack)**
```bash
./scripts/smoke_stream.sh
```
Must pass: 0.8.0 changed server-side tool-call streaming/merging (#5345) and stream
preparation (#5140); this gate exercises `_inject_omlx_options` bodies through a real
0.8.0 stream. A failure here with tool-call deltas is the #5345/#4433 class — capture the
smoke output, roll back (§ROLLBACK), and take the transcript to an issue.

**Step 4 — per-seat canary on each oMLX-served workspace**
```bash
uv run python scripts/uat_engines.py --only auto-coding
uv run python scripts/uat_engines.py --only auto-reasoning
uv run python scripts/uat_engines.py --only auto-security
uv run python scripts/uat_engines.py --only auto-data
uv run python scripts/uat_engines.py --only auto-compliance
```
(plus any other workspace whose `portal trace --section workspaces` hop shows an
`omlx-*` backend served). Look for: structured `tool_calls` (no raw markup in content),
`think:false` honoured post-tool (template patch), `reasoning_content` present on
thinking seats, sane refusal behaviour on security seats. Highest-risk seats, in order:
Laguna-XS-2.1 (custom modeling code under transformers 5.22 — if it fails to load, that
alone is a rollback trigger), the DFlash2 seat (drafter path/prefix changes; confirm
`dflash_max_ctx` still honoured), Qwen3.8-27B-oQ4e-mtp (MTP verify window), DeepSeek-R1
(parser reinstall), Gemma-4-26B QAT (gemma4 parser), Huihui/VulnLLM security seats.
Also re-verify one load-guard admission during an oMLX model swap (P5-LOADGUARD-SWAP-001
shape) and read `portal5_load_guard_headroom_bytes` / `portal5_load_guard_ceiling_bytes`
on the Model Management dashboard — #5165 changed unload/wired-limit behaviour.

**Step 5 — bench/WFE rows to re-run (only seats the release could change)**
Re-run, smallest first:
- **Tool-turn WFE rows for oMLX-served seats only** (text_tool_calls-graded): server-side
  parsing changed (#4433, #5345, #5139). Ollama-side rows are untouched — do not re-run.
- **Decode throughput rows for the oMLX coding seats** (Qwen3.8-27B oQ4e-mtp,
  Qwen3-Coder-30B-A3B, Huihui-Qwen3.6-27B): Qwen batched-decode changes (#5309, #5090) and
  MTP verify (#5313) shift these numbers by design — the incumbent numbers are stale.
- **Long-context rows** (compliance reading / `compliance-reading-overflow`): Affine KV
  speedups (#5095, #5088) and prefix-cache fixes (#5324, #5314) change TTFT/throughput at
  64K+.
- **Fanout/concurrency rows** (TASK_FANOUT_CONCURRENCY_V1 shape): Concurrent Request
  Priority default (#5164) + long-prompt prep no longer stalling streams (#5140).
Comparability caveat when comparing to pre-upgrade rows: #5312 stopped tg-TPS inflation
for batch > Max Concurrent Requests, so part of any delta is the measurement fix, not the
engine. Do not adopt or drop a seat on numbers that conflate the two.
What does NOT need re-running: Ollama-only seats, media/embedding rows (separate host
services), rows for seats whose config and traffic the release cannot touch.

## 5. UNPROVEN (what this lane could not verify)

- 0.8.0 keeps the shapes Portal reads: `/health` `engine_pool.model_count`,
  `/api/status` `version`, `/v1/models/status` `final_ceiling`, `/admin/api/login`,
  the unload endpoints, and the `-m omlx.cli serve` entrypoint — reasoned from the
  release notes (no API/CLI renames announced) and the unchanged wheel-based install;
  proven live by steps 1-2 (the updater's model-count wait and the trace both read them).
- `think:false` / `enable_thinking`, `reasoning_effort` tiers, gemma4 native tool-call
  parsing, presence-penalty escalation on 0.8.0 numerics — the contract check decides;
  not runnable from this lane.
- Laguna-XS-2.1 loads under transformers 5.22 (custom-code checkpoint) — flagged risk;
  canary in step 4.
- `thinking_budget` delivery is unprobed by the contract check on ANY version — if 0.8.0
  changed it, nothing gates it; adding a probe needs its 0.8.0 semantics validated live
  first.
- All speed numbers quoted from the release notes are upstream's hardware (M3/M5
  Ultra/Max), not this M4 Pro — nothing here predicts local deltas.
