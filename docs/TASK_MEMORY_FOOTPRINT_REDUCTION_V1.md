# TASK_MEMORY_FOOTPRINT_REDUCTION_V1

**Status:** OPEN — partly executed 2026-09-23; remaining items await operator decisions (§7).
**Done 2026-09-23:** T1 ComfyUI removed (agent + dir; outputs archived to
`~/AI_Output/images/comfyui_archive/`) · T2 powermetrics fixed + deployed (663 MB → 9.7 MB) ·
T11 data-mcp DuckDB bounded + self-scaling (4 GB starting cap, spills to disk; on OutOfMemory the
same query is retried automatically at 4× steps up to min(`DATA_MCP_MEMORY_CEILING` or ½ RAM,
75% of free RAM), then the cap resets; `DATA_MCP_THREADS` 4, `DATA_MCP_MAX_CONNS` 4 LRU.
History: no session ever persisted, largest data file 178 KB) · vl-retrieval idle-exit added **opt-in**
(`VL_IDLE_EXIT_SECONDS`, default 0 — operator: may be used frequently) · T14 + disk cleanup:
dind dangling images 44.7 GB, build cache 19.8 GB, playwright-mcp image 3.9 GB, dropped-frontend
volumes ~0.75 GB, retired-service logs 45 MB.
**Opened:** 2026-09-23, on the operator's question: *"are we actually using everything
we have installed and enabled, or is cleanup needed?"*
**Box:** M4 Pro, 64 GB unified memory (`hw.memsize` 68719476736), `iogpu.wired_limit_mb` 57344.
**Scope:** all resident services — Docker stack, launchd host services, inference engines.
**Out of scope (by operator instruction):** cyber/security subsystems. They are measured
for the totals only (§3.4) and are not judged here.

---

## 1. Summary

The problem is not the number of MCP servers. When idle, every MCP process (Docker or host)
uses 50–140 MB. The memory goes to three places:

1. **Model-backed services that load on first use and never release.** Music (MiniMax, ~22 GB),
   speech (up to 5 TTS/ASR models), transcription, VL retrieval, oMLX and the Ollama router
   classifier all stay resident indefinitely after one request. None of them has an idle unload.
   Only `vl-retrieval` calls `mx.clear_cache()` at all.
2. **The Docker Desktop VM holds memory the containers are not using.** Host footprint is
   **11 GB**. Inside the VM, only **3.8 GB** is in use; **6.9 GB** is Linux buffer/page cache
   that is not returned to macOS.
3. **Inference headroom is sized for multiple users:** Ollama `NUM_PARALLEL=4`,
   `MAX_LOADED_MODELS=5`.

There are also three dead or broken items: the **ComfyUI** launch agent (removed feature, still
auto-starts), the **powermetrics daemon** (broken parser, buffer grows without bound, reports
0 W), and the **Telegram/Slack bots**, which auto-start because tokens exist in `.env`.
Separately, the Telegram bot **writes its bot token to the Docker logs**.

When this snapshot was taken, the box was under real memory pressure: **7.5 of 8 GB swap used**,
**22.3 GB in the compressor**, and 0.4 GB free.

---

## 2. Usage reality (what the project is actually used for)

| Signal | Value | Source |
|---|---|---|
| Last Open WebUI chat | **2026-08-31** | `webui.db` `chat.updated_at` |
| OWUI chats, last 7 / 30 / 90 days | **0 / 9 / 101** | same |
| 90-day chat pattern | mostly one chat per persona → UAT sweeps, not daily use | `chat.models` |
| Last 30 days, by workspace | auto-music ×5 (2026-08-28), auto ×2, auto-data, auto-council | same |
| OWUI knowledge bases / files / memories | 2 / 158 / 26 | `knowledge`, `file`, `memory` tables |
| Pipeline request volume | dominated by `bench-*` workspaces (e.g. `bench-toolace25` 29k, `bench-granite41-30b` 10k) | `metrics_state.json` |
| Steady real client of the pipeline | opencode (`opencode.jsonc` → `:9099`) | config |
| Grafana | admin last seen 2026-09-21 — in use | `grafana.db` |
| Telegram / Slack bots | logs show only idle polling / session setup; no evidence of message handling | `docker logs` |

**Reading:** the box is used for IDE coding (opencode → pipeline), benchmarking and occasional
media generation. The chat surface (122 personas, 47 routed workspaces, OWUI RAG) is rarely used.
That should decide what is always-on and what is on-demand.

---

## 3. Measured footprint — snapshot 2026-09-23 12:40 CDT, stack freshly up (`./launch.sh up`)

### 3.1 System

| Metric | Value |
|---|---|
| Wired | 32.1 GB |
| Active / inactive | 6.5 / 6.3 GB |
| Free | 0.4 GB |
| Compressor (stored → occupied) | 22.3 → 17.9 GB |
| Swap | **7.5 / 8.0 GB used** |

### 3.2 Inference engines (the dominant consumers)

| Engine | Resident now | Residency policy | Note |
|---|---|---|---|
| Ollama — router classifier `gemma-4-E4B-it-OBLITERATED` | **5.7 GB** | `keep_alive: -1` (pinned forever; expires 2319) | `portal/platform/inference/router/routing.py:675`, `router/lifespan.py:171` |
| Ollama — `gemma4:26b-a4b-it-q4_K_M-ctx32k` | 19.3 GB | default 5 min | normal |
| Ollama global | — | `NUM_PARALLEL=4`, `MAX_LOADED_MODELS=5`, `KV_CACHE_TYPE=q8_0`, `GPU_OVERHEAD=20 GiB` | `/Library/LaunchDaemons/com.portal5.ollama.plist` |
| oMLX 0.6.4 (`homebrew.mxcl.omlx`) | **4.4 GB** (a 7B model, 4 requests total since start) | `idle_timeout_seconds: None` → never unloads | `~/.omlx/settings.json`; still live in routing (priority-10 `omlx-coding`, plus oMLX entries in 5 of 7 groups) |

### 3.3 Docker Desktop (engine 29.8.0)

| Metric | Value |
|---|---|
| VM allocation | `MemoryMiB` 16384, `SwapMiB` 2048 |
| **Host footprint of VM process** | **11 GB** |
| Inside VM (`free -m`) | used 3.8 GB, **buff/cache 6.9 GB**, available 11.9 GB |
| Sum of `docker stats` | ~6.3 GB (non-cyber ~4.2 GB) |

Per-container, idle:

| Container | Mem | Assessment |
|---|---|---|
| open-webui | **1.88 / 2 GB cap** | at its limit; loads `BAAI/bge-reranker-v2-m3` in-process (`RAG_RERANKING_MODEL`, compose l.251) |
| mcp-memory | 399 MB | used by OWUI memory path |
| dind | 304 MB | backs the code sandbox |
| grafana | 237 MB | in use |
| portal-pipeline | 225 MB | core |
| prometheus | 222 MB | feeds Grafana |
| searxng | 199 MB | only for `mcp-research` / web search |
| mcp-rag | 127 MB | proxies to host vl-retrieval |
| browser (Obscura) | 81 MB | IDE-exposed |
| mcp-tts | 68 MB | **thin proxy** → host :8918 |
| telegram | 66 MB | **unused bot** |
| mcp-cad-render | 59 MB | no recent use |
| mcp-whisper | 58 MB | **thin proxy** → host :8924 (+ faster-whisper fallback) |
| mcp-documents | 57 MB | used |
| mcp-sandbox | 54 MB | used |
| mcp-research | 54 MB | low use |
| mcp-reranker | 51 MB | only in-repo consumer is `portal/modules/security/core/bully/organ.py` |
| slack | 43 MB | **unused bot** |

### 3.4 Host launchd services (footprint, process tree)

| Service | Idle footprint | Loads models? | Releases them? |
|---|---|---|---|
| `homebrew.mxcl.omlx` | **4446 MB** | yes | **no** (no idle timeout) |
| `com.portal5.comfyui` | **493 MB** | — | **dead feature** |
| `portal5-powermetrics` (LaunchDaemon, root) | **639 MB** (grew 630→663 MB in ~90 min) → **9.7 MB after fix** | — | **FIXED 2026-09-23** (§4.3) |
| compliance-mcp | 139 MB | — | — |
| mlx-transcribe | 71 MB | Parakeet + Sortformer (`scripts/mlx-transcribe.py:89-113`) | **no** |
| pipeline-mcp | 66 MB | — | — |
| mflux | 64 MB | image models **in a subprocess per job** | **yes** ✓ |
| video-mlx | 62 MB | LTX **in a subprocess per job** | **yes** ✓ |
| data-mcp, wiki-mcp | 62 MB each | — | — |
| music-minimax | 61 MB | MiniMax-Music3 pipeline, in-process (`music_minimax_mcp.py:109-122`), ~22 GB working set | **no** — held until restart |
| embedding (:8917) | 48 MB | Qwen3-Embedding-0.6B (small) | no |
| mlx-speech (:8918) | 40 MB | Kokoro-82M, Qwen3-TTS ×2, higgs-audio-v2-3B q8, Qwen3-ASR-1.7B (`scripts/mlx-speech.py:60-117`, dict cache) | **no** — every model ever used stays |
| vl-retrieval (:8942) | 40 MB idle → **4835 MB 30 min later, after first use (measured)** | Qwen3-VL-Embedding-2B + Qwen3-VL-Reranker-2B (mxfp8) | partial: `mx.clear_cache()` per request + optional recycle after N requests; no idle unload, `VL_MX_CACHE_LIMIT_MB` default 0 |
| cyber host MCPs (6) | ~62 MB each, ~375 MB total | — | out of scope |

**Idle totals:** host services ≈ 6.0 GB (4.4 GB is oMLX). After one of each media/speech/RAG
action, add an **estimated 30+ GB** that stays resident: music ~22 GB (measured 2026-08-28),
speech models ~6 GB (estimated from parameter counts), VL 2B+2B ~4–5 GB (estimated) and
transcription ~2 GB (estimated). Measure these in T0.

---

## 4. Findings

### 4.1 Metal/MLX doesn't release memory (confirmed pattern)
- Only `scripts/vl-retrieval-server.py` touches the MLX allocator (`mx.clear_cache()` l.236,
  `mx.set_cache_limit` l.459). `mlx-speech`, `mlx-transcribe`, `embedding-server-mlx` and
  `music_minimax_mcp` never do, so MLX's Metal buffer cache grows to its high-water mark and stays.
- Even `mx.clear_cache()` plus dropping references is not reliably enough on Metal. Wired
  buffers can persist until the process exits. **The only pattern in the repo that reliably
  returns memory is process exit**: mflux and video-mlx run each job in a subprocess, and both
  sit at ~60 MB between jobs.
- **Implication:** for heavy models, prefer *exit on idle* (launchd `KeepAlive` restarts a fresh
  ~60 MB process) or *subprocess per job* over in-process unload.

### 4.2 Docker Desktop VM retention (confirmed)
- 11 GB host footprint vs 3.8 GB actually used in the guest. The 6.9 GB guest page cache is
  memory macOS cannot reclaim while the VM holds it.
- The VM is sized at 16 GB for a stack whose containers use ~4–6 GB.
- Levers, in order of cost: (a) lower `MemoryMiB` (e.g. 10–12 GB) so the guest cache has a
  lower ceiling; (b) fewer containers (§4.5); (c) periodic `drop_caches` in the VM. **Measure
  whether the host footprint actually falls** before relying on it, since that depends on the
  VM returning free pages; (d) evaluate a runtime with dynamic memory reclaim (e.g. OrbStack) —
  larger decision, separate task.

### 4.3 powermetrics daemon is broken and leaking (confirmed)
- `/usr/local/bin/portal5-powermetrics` (same logic as `scripts/portal5-powermetrics.py`)
  splits samples on lines starting with `<?xml`. The daemon socket reports
  `samples_1min: 0`, `current_w: 0.0`, so that boundary is never matched. `buf` is never reset
  and grows forever; footprint 639 MB and rising.
- **Root cause (confirmed 2026-09-23 against a real capture):** two bugs.
  (1) `powermetrics -f plist` ends each sample `</plist>\n\x00<?xml…`. The NUL means no line
  ever starts with `<?xml`, so `buf` is never reset. That is the leak: the daemon restarted
  01:23 and was at 639 MB by 12:40, roughly 1.4 GB/day, which then sits compressed or in swap.
  (2) Values are milliwatts as `<real>` under `cpu_power`/`gpu_power`/`ane_power`. The parser
  only matched `<integer>`, lacked `cpu_power`, and mapped `combined_power` (the CPU+GPU+ANE
  total) to CPU. So even with (1) fixed, no sample would have parsed.
- **Fixed in repo** (`scripts/portal5-powermetrics.py`, test
  `tests/unit/test_powermetrics_daemon.py`): split on `</plist>` with NULs stripped; buffer
  capped at `MAX_BUFFER_LINES`; `<real>|<integer>` parsing of the per-engine keys; unused
  `interrupts` sampler dropped. Checked against the real capture: cpu+gpu+ane = 33.43 W, which
  equals powermetrics' own `combined_power` of 33434.8 mW. **Deploy needs sudo:**
  `sudo ./launch.sh install-powermetrics`.
- Side effect: the energy/cost telemetry (`portal/platform/inference/router/power.py`,
  Grafana `deploy/grafana/portal5_cost.json`) has been recording 0 W.

### 4.4 Dead or unused but auto-started
- **ComfyUI** — removed from the project (MFLUX replaced it), but
  `~/Library/LaunchAgents/com.portal5.comfyui.plist` has `RunAtLoad`+`KeepAlive`, runs
  `~/ComfyUI/main.py` on :8188 (493 MB, `~/ComfyUI` 1.9 GB on disk, 8.7 MB error log).
- **Telegram + Slack bots** — `launch.sh` l.127-134 enables their profiles whenever tokens
  exist in `.env` (`TELEGRAM_ENABLED=true`, `SLACK_ENABLED=true`). No usage evidence.
- **Leaked credential:** `portal_channels/telegram/bot.py:193` sets root logging to INFO, so
  `httpx` logs every `getUpdates` URL **including the bot token**. Fix by setting the `httpx`
  logger to WARNING, and rotate the token.

### 4.5 Duplicate or low-value surfaces
- **Transcription is exposed twice:** `mcp-whisper` (container proxying host :8924) and
  `mlx_transcribe` (host) are both `expose_to_pipeline: true`.
- **`mcp-tts`** is a container proxying host :8918.
- **Three retrieval backends:** host embedding :8917 (OWUI RAG + mcp-memory), host
  vl-retrieval :8942 (mcp-rag), reranker container :8925 (security-only consumer). Plus OWUI's
  own in-process reranker. With RAG this rarely used, the always-on part is fine; the
  never-released part (§4.1) is not.
- **`cad_render`, `mcp-research` + SearXNG** have no recent usage. They are candidates for
  opt-in compose profiles.

### 4.6 Config and doc drift found along the way
- `video_mlx` has `default_enabled: false` in `config/portal.yaml`, but
  `config/modules.generated.yaml` has `video: enabled: true` and its launch agent runs.
- `CLAUDE.md` says "Single tier — Ollama". oMLX is live in routing (§3.2).
- Open WebUI is at 1.88 of its 2 GB cap, so it risks OOM kills under load.

---

## 4.7 Second sweep (2026-09-23 13:10) — further memory issues and risks

**Confirmed (measured):**

| # | Issue | Evidence | Size |
|---|---|---|---|
| S1 | **IDE MCP fan-out:** every agent session starts its own copy of every user-level MCP server, and each `uvx`/`npm exec` wrapper stays resident as a parent process | 2 Claude Code sessions, ZCode, Codex each running a full set | **~3.5 GB total** |
| S1a | portainer MCP runs **twice per session** (`portainer` + `portainer-ubuntu`) | 2 × (wrapper ~40 MB + server ~105 MB) | ~290 MB per Claude session |
| S1b | ZCode holds **two sets** of portainer/kasm/synology (18 h and 11 h old) under one `zcode-cli` | pids 64190-64387 (18 h), 32466-32729 (11 h) | ~385 MB stale set |
| S1c | Orphaned Serena dashboard tray process, 5 days old, parent `launchd` | pid 7931 | 100 MB |
| S1d | Per Claude Code session: serena + pyright ~225 MB, context7 ~87, docker ~84, fetch ~87, git ~79, filesystem ~74, kasm ~89, synology ~98 | process tree | **~1.1 GB per session** |
| S2 | **vl-retrieval kept 4.8 GB after one use**, as predicted in §4.1 | 40 MB → 4835 MB | 4.8 GB |
| S3 | **Open WebUI at 1.89 / 2.0 GB while idle.** One RAG/rerank request will likely OOM-kill it | `docker stats`, OOMKilled=false so far | cap risk |
| S4 | **powermetrics installer doesn't restart a running daemon.** `launchctl load -w` on a loaded job is a no-op; the new code only ran after `launchctl kickstart -k` | `scripts/lib/services.sh` `_launch_install_powermetrics` | correctness |

**Potential (found in code, not yet triggered):**

| # | Issue | Where | Risk |
|---|---|---|---|
| P1 | **data-mcp DuckDB has no `memory_limit`.** DuckDB defaults to **80% of system RAM per database instance** (~51 GB here), and each session is its own instance. Connections in `_conns` are never evicted. data-mcp runs host-native (launchd), so no Docker cap applies | `portal/modules/data/tools/data_mcp.py:58,94-98` | **High:** a large CSV/Parquet query can push the box into swap |
| P2 | compliance `_bundle_cache` is keyed by document digest and never evicted | `portal/modules/compliance/core/assessment_source.py:91-120` | Low: slow growth per distinct revision |
| P3 | mlx-speech `_tts_models` dict: every model ever requested stays (see §4.1) | `scripts/mlx-speech.py:100-117` | High after use |
| P4 | music-minimax `_pipeline_cache` (see §4.1) | `music_minimax_mcp.py:109-122` | ~22 GB after use |

**Checked and bounded (no action):** web-search cache (`_SEARCH_CACHE_MAX` + TTL), music `_JOBS`
(capped), browser MCP (idle reaper), sandbox sessions (disk cap `SANDBOX_SESSION_MAX_BYTES`),
pipeline metrics dicts (bounded by model count), powermetrics history deques (`maxlen`).

**Non-portal apps (for context):** ZCode Electron ~0.85 GB, ChatGPT/Codex ~1.4 GB, WindowServer
1.0 GB.

**Disk inside the Docker VM:** `portal5-dind` holds 14 dangling `<none>` images, 55 GB, which
bloats the VM disk image.

### Added tasks
- **T10 — IDE MCP fan-out.** Decide which user-level MCPs each agent really needs (D11); dedupe
  portainer to one instance; kill the stale ZCode set and the orphaned Serena dashboard; consider
  running heavy shared MCPs once as HTTP servers instead of one stdio copy per session.
- **T11 — data-mcp limits.** `SET memory_limit` (e.g. 4 GB, env-configurable) and `threads` on
  every connection; cap `_conns` with LRU eviction plus close. Test: a query over the limit
  errors instead of swapping.
- **T12 — OWUI headroom.** Raise the cap or drop the in-process reranker (D9) before any RAG use.
- **T13 — Installer restart.** Make `_launch_install_powermetrics` run
  `launchctl kickstart -k system/com.portal5.powermetrics` after copying.
- **T14 — dind image prune** (`docker exec portal5-dind docker image prune`), disk only.

## 5. Where the memory can come back

| # | Change | Idle saving | Post-use saving | Risk |
|---|---|---|---|---|
| 1 | Idle-exit for music-minimax | — | **~22 GB** | first song after idle pays load time |
| 2 | Idle-exit / unload for mlx-speech, mlx-transcribe, vl-retrieval | — | ~10–13 GB (est.) | cold-start latency |
| 3 | oMLX `idle_timeout_seconds` (e.g. 600) | **4.4 GB** | same | cold start on oMLX lanes |
| 4 | Ollama `NUM_PARALLEL` 4→1 (or 2), `MAX_LOADED_MODELS` 5→2–3 | KV per loaded model shrinks ~2–4× | same | concurrent bench modes must set their own values |
| 5 | Router classifier `keep_alive -1` → e.g. 30 min | **5.7 GB** when chat idle | same | first routed request after idle is slower |
| 6 | Docker VM 16→10–12 GB, and/or cache drop | up to ~4–7 GB | same | verify no container OOM |
| 7 | Remove ComfyUI agent | 0.5 GB | — | none |
| 8 | Fix or disable powermetrics | 0.6 GB (and growing) | — | none |
| 9 | Disable bots | 0.1 GB | — | none if unused |
| 10 | Opt-in profiles: cad-render, research+searxng; fold whisper/tts proxies | ~0.4 GB + fewer VM processes | — | features need `--profile` to enable |

Items 1–6 are where the gigabytes are. Items 7–10 are hygiene.

---

## 6. Tasks

Each task: one commit, per-commit gate
`uv run pytest tests/unit/ -q && uv run ruff check . && uv run ruff format --check .`.
Re-run the §3 census after each group.

**T0 — Repeatable memory census (do first).** Add a script that prints §3 (system `vm_stat`/swap,
Ollama `/api/ps`, oMLX `/api/status`, Docker VM host footprint vs guest `free -m`,
`docker stats`, launchd process-tree footprints). Run it three times: idle, after one of each
action (song, TTS, transcription, RAG query, image), and 30 min later. That produces the real
post-use numbers that replace the estimates in §3.4.

**T1 — Remove ComfyUI.** `launchctl bootout gui/$(id -u)/com.portal5.comfyui`, delete the plist.
Archive or delete `~/ComfyUI` (operator decision). Confirm nothing in `launch.sh`/`scripts/`
recreates it (grep found none).

**T2 — powermetrics.** Verify the NUL-separator hypothesis with a raw
`powermetrics -f plist -n 2`. Fix the boundary detection and cap `buf`. Reinstall to
`/usr/local/bin`. Acceptance: socket shows `samples_1min > 0`, non-zero watts, and a flat
footprint over 1 h. Alternative: disable the daemon if cost telemetry isn't wanted.

**T3 — Idle release for model-backed host services.** Target music-minimax, mlx-speech,
mlx-transcribe and vl-retrieval (embedding is optional, it's small). Preferred mechanism:
**exit the process after N idle minutes** and let launchd `KeepAlive` restart it lean. Fallback:
drop references + `gc.collect()` + `mx.clear_cache()`. Make N an env var per service.
Acceptance: T0 census shows each back to ~60 MB footprint within N+1 min of the last request.

**T4 — oMLX idle timeout.** Set `idle_timeout_seconds` in `~/.omlx/settings.json` (host
config, not in repo). Document it in the oMLX fact-unit. Acceptance: `/api/status`
`loaded_models` empties after the timeout.

**T5 — Ollama residency.** Operator picks the values (§7). Edit
`/Library/LaunchDaemons/com.portal5.ollama.plist` and reload. Change the classifier
`keep_alive` in `routing.py`/`lifespan.py` to a config value, not a hardcoded -1. Check which
benches depend on `NUM_PARALLEL>1` (engine H2H "ollama concurrent" mode) and give them an
explicit override.

**T6 — Docker VM.** Lower `MemoryMiB` to the operator-chosen value. Test a periodic
`drop_caches` and record whether the VM's host footprint drops (T0). Raise OWUI's cap or
remove its in-process reranker (§7).

**T7 — Channel bots.** Per operator decision, set `TELEGRAM_ENABLED`/`SLACK_ENABLED=false` or
keep. Either way: set the `httpx` logger to WARNING in `portal_channels/telegram/bot.py` and
`portal_channels/slack/bot.py`, rotate the Telegram token, and purge old container logs
(`docker compose rm` recreates the container).

**T8 — Surface consolidation.** Per operator decision: move `mcp-cad-render`,
`mcp-research`+`searxng` (and `mcp-reranker`, whose only consumer is security-scoped) behind
compose profiles. Retire `mcp-whisper` in favour of `mlx_transcribe`, or keep one transcription
tool surface. Update `config/portal.yaml` and run `./launch.sh sync-config`, then update the
affected fact-units (Rule 12).

**T9 — Drift fixes.** Reconcile `video_mlx` `default_enabled` with the module's enabled state.
Correct the CLAUDE.md inference-tier statement.

---

## 7. Operator decisions needed

| # | Decision | Options |
|---|---|---|
| D1 | Idle window before model-backed services release | 5 / 10 / 30 min |
| D2 | Ollama `NUM_PARALLEL` / `MAX_LOADED_MODELS` | 1/2, 2/3, keep 4/5 |
| D3 | Router classifier residency | pinned (now), 30 min, 5 min default |
| D4 | Docker VM memory | 16 (now) / 12 / 10 GB; evaluate an alternative runtime? |
| D5 | Telegram / Slack bots | keep / disable |
| D6 | cad-render, research+SearXNG, reranker | always-on / opt-in profile / remove |
| D7 | Transcription surfaces | keep both / keep `mlx_transcribe` only |
| D8 | powermetrics / cost telemetry | fix / disable |
| D9 | OWUI in-process reranker | keep (raise cap to 3 GB) / drop reranking |
| D10 | `~/ComfyUI` directory | delete / archive |
| D11 | User-level MCPs per agent (portainer ×2, kasm, synology, serena, docker, context7, fetch, git, filesystem) | keep all / trim per agent / shared HTTP instances |

---

## Appendix A — Disk (not memory, found during the walk)

| Item | Size |
|---|---|
| Docker volumes (199, 1 active) | 69.8 GB reclaimable |
| Docker images | 28.9 GB reclaimable; stale: `portal-5-playwright-mcp` 3.9 GB (replaced by Obscura); `portal-5-portal-telegram`/`-slack` 1.8 GB each |
| Docker build cache | 15.9 GB reclaimable |
| Volumes from dropped frontends | `portal-5_librechat-*`, `portal-5_anythingllm-data`, `portal-5_huggingchat-mongodb` |
| `~/.omlx/cache` (SSD KV cache) | 93 GB |
| Ollama model store | 906 GB (see `scripts/model_cleanup_audit.py`) |
| `~/ComfyUI` | 1.9 GB |
| Stale logs in `~/.portal5/logs` | `mlx-proxy*` (31 MB, retired), `comfyui-error.log` (8.7 MB), `acestep-server.log`, `music-mcp.log` |

## Appendix B — Excluded (cyber scope, measured only)

`mcp-security` (2.04 GB idle, the largest container), `mcp-binresearch`, `mcp-proxmox`, and
the host MCPs `mitre`, `detections`, `detection`, `vulnintel`, `icsot`, `netforensics`. The
`mcp-reranker` consumer and the model oMLX happened to have loaded are also security-side.
Review these separately under the same §4.1/§4.2 lens.
