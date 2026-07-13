# Known Limitations

Architectural and design constraints that are currently unresolved. Resolved items are not listed here — see git log for history.

---

## CAD / 3D Printing

### CadQuery and build123d Unusable on linux/arm64
- **ID**: P5-CAD-ARM64-001
- **Description**: CadQuery ≥2.4 and build123d both require `cadquery-ocp` / `ocp` (OpenCASCADE Python bindings), which has no pre-built wheels for `linux/arm64`. Installing either package in `Dockerfile.mcp` on Apple Silicon fails at build time.
- **Impact**: Python-native parametric CAD (`.box()`, `.extrude()` style) is unavailable inside the MCP containers. The `auto-cad` workspace uses OpenSCAD instead, which runs headlessly and has no platform restriction.
- **Mitigation**: Use OpenSCAD via the `render_openscad` tool for parametric geometry. Use `trimesh` (installed) for procedural mesh manipulation. If CadQuery is required in future, it must be built from source (multi-hour OCP compile) or sourced from a community arm64 wheel when one becomes available.
- **Do not re-add** `cadquery` or `build123d` to `Dockerfile.mcp` without first verifying an arm64 wheel exists — the build will silently succeed on x86 CI and fail on this hardware.

---

## Security

### Code Sandbox Requires Privileged Container
- **ID**: P5-ROAD-SEC-001
- **Description**: The `dind` (Docker-in-Docker) service runs with `privileged: true`. Docker-in-Docker cannot function without host kernel capabilities.
- **Impact**: In hardened environments, a compromised sandbox container could potentially escape to host.
- **Mitigation**: Disable the code sandbox by removing `mcp-sandbox` and `dind` from `docker-compose.yml`, or apply host-level controls (AppArmor/seccomp on the Docker daemon).

### No Built-in Multi-User Rate Limiting
- **ID**: P5-ROAD-031
- **Description**: Open WebUI has no per-user rate limiting. A single user in a multi-user deployment can exhaust server resources.
- **Mitigation**: Deploy behind a reverse proxy (nginx, Traefik) with rate limiting, or use Open WebUI's admin controls for per-user quotas.

---

### Devstral 2509 Upgrade Blocked — Model Not Published
- **ID**: P5-BENCH-DEVSTRAL-2509
- **Description**: `lmstudio-community/Devstral-Small-2509-MLX-4bit` was not found on
  HuggingFace as of TASK_BENCH_COVERAGE_V1 (2026-05-21). bench-devstral remains pinned
  to the 2507 (July 2025) variant.
- **Operator action**: Re-run Change 0 verification when the 2509 card appears.

### meta3 (Metasploitable3-Windows) — Scenario Coverage + SPL Precision Gaps
- **ID**: P5-SEC-META3-001
- **Description**: As of commit `cdf080e` (2026-07-04), meta3 (vmid 113, `portal-lab-meta3-win2k8`,
  10.10.11.10) has a real, working evidence pipeline — IIS logs (`web:access`), FTP logs
  (`ftp:access`), and Process Creation events (`windows:security`, 4688 auditing enabled
  live on the box) all collect, ship, and confirm-index correctly. Two gaps remain,
  found while building that pipeline:
  1. **Scenario coverage.** The current 7 `meta3_*` scenarios (`exec_chain.py::SCENARIOS`)
     cover only a subset of meta3's documented vulnerable services. Cross-referenced against
     https://github.com/rapid7/metasploitable3/wiki/Vulnerabilities: still unscripted —
     GlassFish deploy RCE (CVE-2011-0807, admin/sploit creds, port 4848/8080/8181), Struts
     (CVE-2016-3087) and Tomcat manager (CVE-2009-3843/4189, sploit/sploit creds, port 8282),
     Jenkins unauthenticated script console (port 8484), ManageEngine (CVE-2015-8249, port
     8020), Apache Axis2 (CVE-2010-0219, via Tomcat), WebDAV HTTP PUT shell upload (port
     8585), PHPMyAdmin (CVE-2013-3238, port 8585), Ruby on Rails web console (CVE-2015-3224,
     port 3000), JMX (CVE-2015-2342, port 1617), WordPress NinjaForms (CVE-2016-1209, port
     8585), `psexec` weak-password (port 445/139), RDP standard-auth (port 3389). WinRM
     weak-password (port 5985, `vagrant`/`vagrant`) is confirmed live-reachable and is
     already incidentally exercised by our own collection code — a dedicated scenario for it
     would need to be distinguishable from monitoring traffic in the resulting evidence.
  2. **SPL query precision.** `siem/spl_detections.yaml`'s SPL for meta3's own
     `detect_ground_truth` techniques doesn't match meta3's actual traffic shape yet:
     `T1059`/`T1059.004`/`T1548.001`/`T1068`/`T1210`/`T1021.002` are all written against
     `sourcetype="linux:auditd"` fields (copied from the vulhub/Linux template), which will
     never match the `windows:security` 4688 process-creation data now genuinely available
     for meta3 — needs Windows-appropriate SPL (`EventCode=4688`, `NewProcessName=`,
     `CommandLine=`, `Account=`) added, likely as OS-aware variants rather than blind
     replacement, since the same technique IDs are also scored against true Linux vulhub
     targets. `T1190`'s existing SPL (payload-substring matching: `passwd`, `../`,
     `UNION SELECT`, `jndi:`, `.php`, `cmd=`) also doesn't match meta3's actual traffic —
     verified live via `--replay-captured-red` on `meta3_full_chain`: real `web:access` data
     is shipped and indexed, but none of meta3's exploit traffic (plain `GET /`, JSON-body
     `POST /_search`, out-of-band FTP backdoor trigger) contains those literal substrings, so
     it still reports `synthetic-fallback` despite genuine live data being present.
- **Operator action**: Treat as a content-authoring task (new `exec_chain.py::SCENARIOS`
  entries with `target_host=_LAB_META3`, `detect_ground_truth`, `red_prompt` tool_hints; new
  or OS-variant SPL entries in `siem/spl_detections.yaml`), not a plumbing fix — the
  collection/shipping/replay infrastructure itself is confirmed working end-to-end. meta3 has
  a documented history of crashing under load (`qmpstatus: internal-error`, recovered via
  hard stop+start) even from routine investigation traffic, not just live exploitation —
  budget for that when scripting new scenarios against it.

### Blue Detection Quality — Wrong MITRE ID Reporting on Correct Evidence
- **ID**: P5-SEC-BLUE-MITRE-001
- **Description**: With the Splunk telemetry pipeline confirmed working end-to-end (commits
  `306df2a`/`cdf080e`), the root problem motivating this whole investigation is now isolated:
  blue models receive correct, live telemetry and still frequently report the wrong MITRE
  sub-technique ID. Diagnosed via `--replay-captured-red` (zero live lab time, 5 trials each
  condition on `kerberoast_to_da`): `sylink/sylink:8b` correctly identified `T1558.003`
  (Kerberoasting) in only 4/5 trials without any reference material in its prompt, with one
  clean miss (`T1543.002`, unrelated). Fixed (commit `8ee6d37`) by surfacing
  `siem/spl_detections.yaml`'s existing per-technique descriptions to the blue model via
  `BLUE_INITIAL_PROMPT` (previously only used to build red's evasion-feedback prompt, never
  shown to blue) — moved to 5/5 correct with the reference table present.
  **This is a real but modest improvement, not a fix for the underlying problem**: `T1003.006`
  (DCSync) was never correctly identified in either condition despite live evidence being
  present in both, and the false-positive rate (extra wrong techniques reported alongside the
  correct one) was unaffected by the fix.
- **Operator action**: Needs further diagnosis on why DCSync specifically never gets identified
  even with reference material present (event field naming? insufficient distinguishing detail
  in the normalized `EventCode=4662 Properties=... Account=...` telemetry line? model capability
  ceiling for an 8B model on this specific technique?), and separately, work on reducing false
  positives (the model over-reports plausible-but-wrong techniques alongside a correct one).
  `--replay-captured-red` makes this cheap to iterate on — no live lab time needed per trial.

## Infrastructure

### ComfyUI Runs Outside Docker
- **Description**: ComfyUI runs on the host (not in Docker) to access MPS/CUDA directly. Required for image/video generation performance.
- **Impact**: Manual setup required outside `./launch.sh up`. On a fresh machine, ComfyUI must be installed separately.
- **Mitigation**: `./launch.sh install-comfyui` handles setup on supported platforms. See `docs/COMFYUI_SETUP.md`.

### Voice Cloning (fish-speech) Requires Separate Installation
- **Description**: Voice cloning via `fish-speech` is not in the Docker stack — requires host-side installation.
- **Impact**: Voice cloning unavailable; TTS works via the included `kokoro-onnx` engine.
- **Mitigation**: `kokoro-onnx` provides TTS out of the box. See `docs/FISH_SPEECH_SETUP.md` for fish-speech.

### `pytest portal` Leaves Real Write-Through Test Artifacts
- **Description**: Some `portal/modules/security/tests/` tests write through the real goal/playbook journal path (`portal/modules/security/core/field_journal/`) and checkpoint path (`portal/modules/security/core/results/checkpoints/`) instead of a `tmp_path`-redirected one, violating the `tmp_path` testing rule (`CLAUDE.md` Testing Rules).
- **Impact**: Running `pytest portal` locally dirties the working tree — new dated entries under `field_journal/` and a modified `field_journal/_index.json`, plus files under `results/checkpoints/`.
- **Mitigation**: `results/checkpoints/` is gitignored. `field_journal/` holds real committed history so it is intentionally *not* gitignored — run `git status` after `pytest portal` and `git checkout -- portal/modules/security/core/field_journal/_index.json` (plus `git clean` any new dated entries) before staging a commit. See `CLAUDE.md` Testing Rules.
- **Fix (open)**: Route the journal writer through a fixture-injected path in the offending tests so `pytest portal` is side-effect-free like `pytest tests/unit`.

---

## Models

### auto-math Workspace — Reasoning Block Support
- **ID**: P5-MATH-001
- **Status**: ✅ RESOLVED (V8 model refresh — 2026-06-10)
- **History**: Original limitation was `Qwen2.5-Math-7B-Instruct` (MLX, no `reasoning_content` blocks). Model replaced in V8 by `phi4-mini-reasoning` (RL-trained, Phi-4-Mini-Reasoning, ~2.5GB). The new model has `emits_reasoning: True` — math reasoning appears in the collapsible thinking panel.
- **Alternative**: For even heavier reasoning, `auto-reasoning` (DeepSeek-R1-0528-Qwen3-8B) also separates reasoning content.

### baronllm text_only tool output — auto-security MCP tools non-functional
- **ID**: P5-TOOL-001
- **Description**: `huihui_ai/baronllm-abliterated` (formerly auto-security primary; VulnLLM-R-7B is now the model_hint primary as of SECURITY_FLEET_REVIEW_2026-06, though baronllm remains in the security pool) outputs tool-call JSON embedded in the `content` field of Ollama's `/v1/chat/completions` response rather than in the structured `tool_calls` field. Ollama's llama.cpp backend does not parse this as a function-call delta. Result: the pipeline's `_dispatch_tool_call` path is never triggered for auto-security requests that attempt MCP tool use.
- **Evidence**: `audit-tools 2026-06-18` probe — outcome `text_only`, content: `{"name":"get_current_time","parameters}:{ "city": "Paris" }`. UAT TV-02 (execute_python proof) and TV-03 (classify_vulnerability) both show tool not dispatched. Previous `supports_tools: true` marking (TASK_TOOL_AUDIT_V2) was a false positive from Ollama template header inspection, not a live response probe.
- **Impact**: Auto-security cannot use `execute_bash`, `execute_python`, `classify_vulnerability`, or any pipeline-dispatched MCP tool. TV-02 grades as WARN (non-critical assertion). Prose security analysis and code audits still work (text generation is unaffected).
- **Resolution path**: (a) Fix baronllm's Ollama chat template to emit proper `tool_calls` structure — this requires inspecting the model's tokenizer_config and Ollama template to align with llama.cpp's tool-call parsing; OR (b) Replace baronllm with a model in the auto-security chain that passes the live probe (e.g., qwen3.5-abliterated:9b was confirmed tool_call in a prior audit).
- **Status**: ✅ RESOLVED 2026-06-20 (TASK_TOOLCALL_FIX_LOCKIN_V1). A corrected tool-calling chat template makes baronllm emit structured `tool_calls`. Fleet `--audit-tools` confirmed outcome=`tool_call` and the security chain scored 8/8 1.00 WIN. Resolution path (a) — template fix — was taken; no model swap required. `supports_tools` flipped to `true` in `config/backends.yaml` (both entries), backed by the live probe. The same template fix also recovered HauhauCS (no_tool → tool_call).
- **Do not re-enable** `supports_tools: true` for baronllm without running `python3 tests/portal5_persona_matrix.py --audit-tools --workspace auto-security` or the direct Ollama probe and confirming outcome=`tool_call`. *(This gate was satisfied by the 2026-06-20 fleet audit.)*

### Asteroids Bench Score Variance Is the Benchmark's Purpose
- **ID**: P5-BENCH-001
- **Description**: The CC-01 Asteroids bench (`bench-*` workspaces) intentionally surfaces raw model differences on a fixed task. All bench personas share an identical creative-coder system prompt — score variance reflects model capability, not a test harness defect.
- **Operator action**: Use bench scores as model-selection signal. A model scoring ≤3/5 on CC-01 is not a candidate for `auto-coding` HTML generation tasks.

### Tool Preselection — Candidate 1B Models Cannot Rank Tools
- **ID**: P5-TOOLPRESELECT-001
- **Status**: BUILT NOT DEPLOYED — exhausted, closed (TASK_BUILD_TOOL_PRESELECT_V1 Phase 2 gate, 2026-07-12; extended diagnostic pass same day before final halt)
- **Description**: `portal/platform/inference/tool_preselect/` implements query-level tool-schema preselection — a small fast model ranks a workspace's tools by relevance to the user's turn so only the top-K schemas are sent to the primary model. The module, config surface, parser, and metrics are built and unit-tested (54 tests, 90% coverage), shipped feature-flagged off (`PORTAL5_TOOL_PRESELECT=0`, default).
- **Evidence — initial pass (2 candidates × 2 techniques):** `hf.co/openbmb/MiniCPM5-1B-GGUF:Q4_K_M` (base) and `hf.co/ewinregirgojr/MiniCPM5-1B-Agentic-Tooluse-GGUF:Q4_K_M` (tool-tuned fine-tune). Natural-language ranking prompt: both models spent their entire token budget on unrequested reasoning and never emitted a ranking. Grammar-constrained JSON output (the same technique the production LLM workspace router uses successfully — `router/routing.py::_route_with_llm`): both produced syntactically valid but semantically nonsensical rankings (sequential counting, out-of-range indices).
- **Evidence — extended pass, before concluding the initial result was final** (5 additional theories, all on the MiniCPM5 candidates plus a third, differently-lineaged model):
  1. *System-prompt framing* ("you are a ranking function, do not reason") — MiniCPM5 ignored it and kept reasoning in its `thinking` channel regardless; still never converged within any reasonable token budget (tested to 300 tokens of pure thinking, no answer).
  2. *`think: false`* (Ollama's native reasoning-suppression option) — produces an instant answer, but a content-empty one: reordering the tool list so the correct answer moved from position 1 to position 8 still returned "1" — proof the model wasn't reading the tool list at all in this mode, just emitting a positional default.
  3. *Single-choice simplification* (pick the one best tool, not a ranked list) — same positional-default failure under `think: false`.
  4. *Few-shot in-context examples* — broke the pure positional default (stopped always answering "1") but still picked wrong answers; some genuine but unreliable engagement.
  5. *Different model lineage* — `qwen2.5:1.5b` (this project's own proven compact performer for a structurally similar task, the LLM workspace router — see `docs/ADMIN_GUIDE.md`'s Router Configuration section) scored 3/5 on trivial single-choice cases (real signal, not positional bias) but **1/5 on the actual multi-item top-K ranking task** — at or below random chance for a 3-of-10 selection. The easier single-choice framing didn't generalize to the real task.
- **Conclusion**: 3 distinct models, 7 distinct elicitation techniques, all converge on the same result — no model tested at ~1-2B scale can perform this specific ranking task reliably, regardless of prompt framing, output-format constraint, or reasoning-mode control. This is a genuine capability gap at this scale for this task, not a fixable prompting/format artifact.
- **Impact**: None on production — the feature has never been enabled on any workspace and the fallback invariant (`preselected == effective_tools` on any failure) means even a hypothetical accidental enable would degrade to a no-op, not a broken tool call.
- **Resolution path**: Revisit only with a materially larger (3B+) or purpose-built tool-ranking model — sub-2B is now empirically ruled out across three attempts, not just theorized. The built Phase 1+2 code (config, prompt builder, resilient parser, Ollama-call integration, metrics, self-healing auto-disable state) is reusable as-is — only `PORTAL5_TOOL_PRESELECT_MODEL` needs to point at a model that actually passes the ranking task.
- **Do not** re-attempt promotion without first re-running `cli_probe.py` against the new candidate and confirming a plausible top-K ranking (e.g. `web_search` ranking above `execute_bash` for an information-lookup query) on at least 5 varied scenarios, not a single spot-check.

---

## MLX Inference Proxy — RETIRED (commit 3a0c58e)

The MLX inference proxy and all its limitations (single-model eviction,
cold-boot 503 windows, admission control, deploy staleness) no longer
apply. All chat inference runs through Ollama (:11434). MLX is retained
only for speech (:8918), transcription (:8924), embeddings (:8917), and
reranking (:8925) — those have their own sections.

## Model Parity — Specialist models lost in the MLX→Ollama migration

Two production specialist models were MLX-only safetensor builds with no
verified GGUF equivalent. The migration (3a0c58e) remapped their
workspaces to general-purpose GGUF substitutes:

| Workspace(s) | Original (MLX) | Now served (Ollama GGUF) | Gap |
|---|---|---|---|
| `auto-security` (blueteam variant), `bench-foundation-sec` | Foundation-Sec-8B-Reasoning (Cisco, purpose-trained defender cybersec: CVE→CWE, MITRE ATT&CK, SOC triage) | Foundation-Sec-8B-Reasoning Q8_0 GGUF (Cisco fdtn-ai, first-party, ~8.5GB) | RESTORED (P5-FUT-PARITY-001) |
| `tools-specialist`, `bench-toolace25` | ToolACE-2.5-Llama-3.1-8B (Team-ACE, BFCL-topping tool-caller) | granite4.1:8b (general tool-tagged, BFCL V3 68.27, first-party IBM) | ACCEPTED — granite4.1:8b adopted; ToolACE-2.5 dropped (P5-FUT-PARITY-001 closed) |

**Status — Foundation-Sec:** RESTORED to auto-security's 'blueteam' variant production primary
via the first-party Cisco GGUF `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0`
(TASK_PARITY_FOUNDATION_SEC_V1, direct swap, no bench gate — consistent with how
the original MLX→Ollama migration set models by assumption; this restores the
pre-migration primary).

**Status — ToolACE:** RESOLVED (accepted). granite4.1:8b adopted as the
tools-specialist model by operator decision; ToolACE-2.5 evaluated and dropped
(no verified ToolACE-2.5 GGUF confirmed; self-quant + Ollama tool-template risk
not justified). P5-FUT-PARITY-001 is CLOSED/DONE — both specialists dispositioned
(Foundation-Sec restored, ToolACE substitute accepted).

---

## Ollama Native MLX Engine — Evaluation Findings (2026-07-01)

Ollama 0.31.1 added a built-in MLX engine (distinct from the retired standalone
`mlx_lm`/`mlx_vlm` proxy above) that claims ~90% faster Gemma 4 via multi-token
prediction (MTP). This section documents a same-day evaluation of that engine
plus a broader catalog sweep for MLX equivalents of the fleet. **No production
config was changed** — `config/backends.yaml` was reverted, all pulled MLX
models (4 Ollama-native + 16 HF-sourced, ~254GB total) were deleted, and disk
usage is back at baseline (`hf-cache` exactly 280GB, matching pre-evaluation).

### P5-MLX-EVAL-001 — GGUF fleet regressed slightly on 0.31.1; MTP is MLX-engine-only
- **Description**: Ollama 0.31.1's claimed MTP speedup applies only when Ollama
  selects its own MLX engine subprocess (triggered by official `-mlx`-tagged
  models). Our entire GGUF fleet routes through `llama-server` regardless of
  Ollama version — confirmed via server log (`spec common_specu: no
  implementations specified for speculative decoding`). Separately, the GGUF
  fleet got measurably *slower* after the 0.31.1 upgrade (~5-11% across 15+
  models tested, clean warm-up-matched methodology). Tested `num_batch=512`
  (pre-upgrade default) vs 0.31.1's auto-selected 1024/2048 — **zero
  measurable difference**, ruling out batch-size as the cause. Root cause is
  presumably the bundled llama.cpp engine version bump itself; no known
  workaround.
- **Impact**: None today (no config changed). Documented so a future Ollama
  upgrade isn't mistaken for a routing/pipeline regression.

### P5-MLX-EVAL-002 — Ollama's official gemma4 `-mlx` tags are not drop-in swaps
- **Description**: `gemma4:{e2b,e4b,12b}-mlx` (Ollama's own curated library
  tags) showed real, large gains over our current `gemma4:{e2b,e4b,12b}-it-qat`
  GGUF models: +93%, +61%, +30% respectively (clean, isolated, warm-up-matched
  benching). However `ollama show` reveals these are **not the same
  checkpoint in a different format** — they differ in parameter count
  (4.6B→5.2B, 7.5B→8.1B, 11.9B→12.4B), quantization scheme (Q4_0
  quantization-aware-trained vs nvfp4 post-training quant), and the 12b tag
  even reports a different architecture name (`gemma4_unified` vs `gemma4`).
  Critically, **none of the `-mlx` tags have vision or audio capability** —
  the `Projector` block present on our current QAT variants is entirely
  absent from the MLX tags.
- **Impact**: Cannot be swapped in as a pure speed upgrade. Any workspace
  routing image/audio input to `gemma4:e2b/e4b/12b-it-qat` would silently
  lose that capability if swapped to the `-mlx` tag. Output quality is also
  unverified — QAT training specifically targets low-precision quality
  retention; nvfp4 post-training quant is a different tradeoff entirely.
- **Future work needed**: (1) Audit which workspaces using these three models
  actually rely on vision/audio input vs text-only — if none do, a text-only
  swap may be viable for those specific workspaces. (2) Run a live tool-call
  probe on any candidate before promotion — never infer `supports_tools` from
  the model card (see `P5-TOOL-001` above for why). (3) Run a quality eval,
  not just TPS, before promoting — QAT vs nvfp4 is not guaranteed equivalent.
  **Do not add `gemma4:*-mlx` tags to `config/backends.yaml` until all three
  are done.**

### P5-MLX-EVAL-003 — HF-hosted MLX models are currently unreachable by the Pipeline
- **Description**: Ollama's `hf.co/` puller only accepts GGUF repos —
  confirmed directly: pulling any `mlx-community` (or other HF org) safetensors
  repo fails with `"Repository is not GGUF or is not compatible with
  llama.cpp"`. Only Ollama's own curated `ollama.com` library `-mlx` tags
  (a narrow set — currently just the `gemma4` and `qwen3.6` families) can be
  served through Ollama's MLX engine. A catalog sweep found HF `mlx-community`
  (or individual-uploader) conversions for ~56 of our 71 fleet models, and
  direct benching (bypassing Ollama entirely, via raw `mlx_lm`) showed large
  real gains for most of the 11 spot-checked (69% to +487%, one clear
  pre-existing-bug outlier, one regression — see below). **None of this is
  usable in production** — `BackendRegistry` only talks to Ollama's `:11434`
  API, and there is currently no way to route to a raw `mlx_lm`-served model.
- **Impact**: Real, measured speed gains exist for most of the catalog but
  are inaccessible without new serving infrastructure.
- **Future work needed**: A deliberate decision on whether to stand up a
  lightweight MLX serving layer (Ollama would remain the primary scheduler;
  this would NOT be a revival of the full retired proxy/watchdog/
  admission-control stack) to make these models reachable — or simply wait
  for Ollama to expand its official `-mlx` library coverage further (it grew
  from Gemma-only to Gemma+Qwen3.6 between the two testing sessions in this
  same evaluation). No infrastructure work has started; this is an
  evaluation finding only, pending a scope decision.
- **Tooling**: `tests/benchmarks/bench_mlx_hf.py` (committed) — ad hoc
  pull+bench of any HF MLX repo directly via `mlx_lm`, for future spot-checks.
  This is **not** a serving mechanism, just a one-shot benchmark tool. Do not
  build automation or hooks around it without a deliberate decision to revive
  MLX serving.
- **Not universal**: `huihui_ai/qwen3.5-abliterated:9b`'s MLX equivalent was
  measurably *slower* than GGUF (-17%). MLX gains are not guaranteed —
  verify per-model, don't assume.
- **Known outlier, not an MLX win**: `qwen3-coder-next`'s GGUF baseline was
  already flagged elsewhere in this file's history (MLX retirement commit)
  as broken under Ollama ("sharded GGUF incompatible with Ollama"). Its huge
  MLX gain in this evaluation reflects a pre-existing GGUF bug for this
  specific model, not a general MLX advantage.

### P5-MLX-EVAL-004 — Large single-blob MLX downloads hang intermittently
- **Description**: During evaluation, 3 separate large (18-26GB) downloads
  (both `ollama pull` from the official registry and `huggingface_hub`
  pulls from HF) silently stalled mid-transfer for 30+ minutes with no error
  — the blob simply stopped growing, with stale TCP `CloseWait` sockets.
  Happened on both registries, so it isn't tool-specific; likely a
  network/CDN reliability issue for large single-file transfers on this
  connection. No stalls on smaller pulls.
- **Mitigation**: A stall-detection wrapper (poll blob size every 10s, kill
  + retry after 90s with no growth) recovered every case on retry. Not
  currently a committed script — if large-model pulls become a recurring
  pain point, consider promoting this pattern into `scripts/`.

### P5-MLX-EVAL-005 — Two security-tier fine-tunes have no working MLX conversion
- **Description**: `supergemma4-26b-uncensored` (auto-security's
  `purpleteam-exec`/`redteam-deep` variants) and `huihui_ai/gemma-4-abliterated:E2b-qat`
  (auto-security's `pentest` variant) were searched across multiple HF uploaders (mlx-community,
  Jiunsong, aa221241, EZCon). Every MLX conversion found for these specific
  fine-tunes is a multimodal/vision-language checkpoint (`language_model.*`
  prefixed weights) that crashes on plain text-only `mlx_lm` load with
  `ValueError: Received N parameters not in model`.
- **Impact**: These two stay GGUF-only for the foreseeable future.
- **Do not** spend further time searching for a working MLX conversion for
  either unless a new text-only-compatible upload appears.

---

## Inference Performance

### devstral:24b Runtime VRAM Footprint (25.7 GB)
- **ID**: P5-VRAM-DEVSTRAL-001
- **Description**: devstral:24b file size is 14.3 GB but runtime Ollama resident size is ~25.7 GB due to large default context window and KV cache allocation (q8_0). This is nearly 2× the file size and can cause memory-pressure eviction of other loaded models; on M4 Pro 64 GB hardware this is non-critical (graceful CPU offload), but relevant on tighter budgets.
- **Impact**: When devstral is active, it may evict the LLM router model from VRAM. The first post-eviction routing request falls back to Layer 2 keyword scoring (correct behavior), then the router cold-loads in ~4.2s and stays warm. Subsequent requests use the LLM router normally.
- **This is graceful, not a crash**: Ollama offloads CPU layers under memory pressure rather than failing. Unlike the former MLX Metal OOM, no kernel panic occurs.
- **Mitigation**: `OLLAMA_MAX_LOADED_MODELS=3` (current default) reserves a slot for the router + 2 inference models. If devstral:24b is loading as an inference peer, its runtime footprint is the limiting factor — not the slot count. Setting `OLLAMA_MEMORY_LIMIT=42g` in the Ollama plist caps worst-case pressure; see Admin Guide → Router Configuration.

### Request-Size Cap Relies on Content-Length Only
- **ID**: P5-REQ-SIZE-001
- **Description**: The pipeline caps requests at 4 MB via `Content-Length` header check. Chunked transfer-encoded requests bypass this cap entirely — Starlette middleware is the proper fix.
- **Mitigation**: Until Starlette body-size middleware is added, operators should configure upstream proxies (nginx, OWUI) to enforce request-size limits.

### Speculative Decoding / MTP — RETIRED with the MLX proxy (commit 3a0c58e)
- **IDs**: P5-SPEC-001, P5-MTP-001, P5-MTP-PATH (all moot)
- **Status**: The MLX inference proxy that hosted `--draft-model` speculative decoding and the `speculative_decoding.draft_models` map was retired; chat inference is Ollama-only. These limitations no longer apply because the infrastructure they described no longer exists.
- **If revisited**: any future speculative-decoding / MTP work targets Ollama's native path (llama.cpp b9180+), not MLX. The bench-only MTP GGUF candidates remain in the catalog as bench entries; there is no production MLX serving path to enable.
- **P5-FUT**: evaluate `/api/chat` as `chat_url` — `/api/chat` would allow full `options` passthrough but requires changing payload/response shapes.

### phi4-reasoning:plus crashes Ollama's llama-server on this host
- **ID**: P5-MODEL-PHI4REASONING-001
- **Description**: Both `phi4-reasoning:plus` and `phi4-reasoning:plus-ctx32k` fail on direct `POST /api/generate` with `{"error":"llama-server process has terminated: signal: abort trap"}` — a local Ollama/model-file issue, not a routing or pipeline bug. Discovered during `DESIGN_PERSONA_INTENT_REMEDIATION_V1.md`'s live verification of the `phi4stemanalyst` persona's `model_pin`: the pipeline correctly resolved and requested `phi4-reasoning:plus-ctx32k` (confirmed in logs — `wanted phi4-reasoning:plus-ctx32k`), the registry's existing backend-failover mechanism correctly caught the crash and fell back to another reasoning-pool model, and honestly logged `model_hint mismatch ... response may be from wrong model` rather than silently misreporting. The routing/pin mechanism is proven correct by the other 4 personas (`magistralstrategist`, `devstral_coder`, `glm-coder`, `glm-thinker`) succeeding cleanly end-to-end.
- **Impact**: `phi4stemanalyst` currently falls back to whatever `auto-reasoning`'s pool serves instead of Phi-4-reasoning-plus, until the model file is fixed locally.
- **Mitigation**: `ollama rm phi4-reasoning:plus-ctx32k phi4-reasoning:plus && ollama pull ...` (re-pull; likely a corrupted download or an Ollama-version/GGUF incompatibility) — not attempted here since it requires a multi-GB re-download and is outside Stage P's scope (persona/routing correctness, not model-file integrity).

### 70B Dense Models Unusable for Daily Routing on M4 Pro 64GB
- **ID**: P5-SPEED-001
- **Description**: Llama-3.3-70B-Instruct-4bit and DeepSeek-R1-Distill-Llama-70B-4bit measure ~3.5 TPS warm — too slow for interactive use. 3-bit quantization (~28GB) is theoretically viable at ~9.7 TPS but not yet bench-validated.
- **Mitigation**: All daily-routed workspaces use ≤33B models. 70B variants are bench-tier only.

### Ollama /v1 ignores options.num_ctx and options.num_batch
- **ID**: P5-OLLAMA-OPTIONS-001
- **Description**: Ollama's OpenAI-compatible `/v1/chat/completions` endpoint ignores the `options` sub-object entirely (VERIFY-1 probes, 2026-06). The pipeline still injects `options.num_ctx`, `options.num_batch`, and `options.num_predict` (the latter mapped to `max_tokens` at top level per Branch I) because a future Ollama version may honor them. Currently:
  - `context_limit` per workspace (e.g. `auto-coding: 16384`) is **not enforced** — set PARAMETER num_ctx in the model's Modelfile or OLLAMA_CONTEXT_LENGTH
  - `num_batch` injection is inert — set PARAMETER num_batch in Modelfiles for prefill tuning
  - `predict_limit` is mapped to OpenAI `max_tokens` (top-level, honored) as a workaround
- **Roadmap note:** P5-FUT: evaluate `/api/chat` as `chat_url` — it honors the Ollama-native parameter set but requires changing all payload/response shapes.

---

## Shared Workspace + Auto-STT Disabled (TASK-WORKSPACE-001)

- **Voice-input via microphone is disabled.** `AUDIO_STT_ENGINE` is empty by default, which disables auto-transcription of both file uploads and microphone recordings. Re-enabling it re-enables auto-transcribe-on-upload. The global toggle is OWUI's only knob.
- **Existing MCPs not migrated to /workspace.** `mcp-documents`, `mcp-tts`, and `mcp-comfyui` still write to `${AI_OUTPUT_DIR}` flat. New MCPs use `/workspace/generated/<category>/`. Both layouts coexist; migration is opportunistic.
- **Permissions assume single-host deployment.** 0775 mode on workspace directories assumes operator-owned files and compatible Docker UIDs. Multi-tenant or hardened hosts need explicit UID mapping.
- **No retention policy.** `${AI_OUTPUT_DIR}` grows unbounded. `./launch.sh workspace-clean --age=Nd` is a planned but not yet implemented command.

---

## Diarized Transcription (TASK-TRANSCRIBE-001)

- **Pyannote model gating.** Diarization requires accepting HuggingFace user agreements for `pyannote/segmentation-3.0` and `pyannote/speaker-diarization-3.1`. Without `HF_TOKEN` in `.env` and licenses accepted, diarization calls return 500.
- **Overlapping speech.** Pyannote 3.1 underperforms when multiple speakers talk simultaneously. Segments are assigned to a single speaker by maximum overlap.
- **Speaker count drift on long recordings.** For recordings >15–30 min, pyannote may split one speaker into two IDs after long silence gaps. Pass `num_speakers=N` if known.
- **OWUI tool-call timeout for long files.** OWUI's default MCP timeout is shorter than processing time for files >5 min. Raise `TOOL_SERVER_REQUEST_TIMEOUT` (e.g., 1800s) or use the direct endpoint at `:8924`.
- **MLX path is macOS-only.** `scripts/mlx-transcribe.py` requires Apple Silicon. The Docker `whisper_mcp.py` fallback (faster-whisper + pyannote on CPU/CUDA) is the cross-platform alternative.

---

## OWUI Audio Drop UX (TASK-OWUI-AUDIO-DROP-001)

- **OWUI internal 60s tool-call ceiling.** Some OWUI builds enforce a hard internal timeout on tool execution that `AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA` does not affect (open-webui/open-webui#16902). When this fires, the tool completes server-side but the persona never sees the result. Use `scripts/transcribe_and_complete.sh` for files with wall time >60s.
- **WEBUI_SECRET_KEY rotation invalidates OAuth tokens.** If `.env` is regenerated and the secret key changes, all MCP OAuth tools need re-authentication.
- **Microphone voice input remains disabled.** Unchanged from TASK-WORKSPACE-001 trade-off.

---

---

## Models Out of M4 Pro 64 GB Budget

The following models were evaluated and explicitly **refused** from the Portal 5
catalog. They exceed the M4 Pro 64 GB unified memory ceiling at the lowest
quality-preserving quantization. Do not re-propose without a cluster scaling
plan (P5_ROADMAP Stage 3 vLLM node).

**Guardrail for future Claude sessions**: before recommending any MoE model
with total params > 100B on a 64 GB M4 Pro budget, compute the 4-bit weight
footprint. If > 50 GB, refuse and reference this section. Mac Studio 128 GB+
is the path for these models.

| Model | 4-bit MLX resident | Why refused |
|-------|--------------------|-------------|
| `mlx-community/MiniMax-M2-4bit` | ~129 GB | 230B-A10B MoE. 4-bit weight footprint alone exceeds 64 GB before any KV cache. |
| `mlx-community/MiniMax-M2.5-4bit` (and Uncensored variant) | ~129 GB | Same architecture as M2. |
| `mlx-community/MiniMax-M2.7-4bit-mxfp4` | ~129 GB | mxfp4 does not reduce the dense-weight component substantially. |
| `thetom-ai/MiniMax-M2.7-ConfigI-MLX` (mixed-precision) | ~87 GB | Aggressive Config-I 2-bit on expert MLPs, still over 64 GB. |
| `mlx-community/DeepSeek-V4-Flash` (community 4-bit) | ~142 GB | 284B-A13B MoE FP4+FP8 base. |
| `mlx-community/DeepSeek-V4-Pro` (community 4-bit) | ~800 GB | 1.6T total params. |
| `mlx-community/Kimi-K2-Instruct-0905-mlx-4bit` (Instruct + Thinking) | ~578 GB | 1T total MoE, 32B active. |
| `mlx-community/Kimi-K2-Instruct-0905-mlx-DQ3_K_M` | ~450 GB | Mixed 3-4 bit still over budget. |
| GLM-5 (Z.AI flagship) | 192+ GB at 4-bit | 744B params; not yet in MLX. |
| `huihui-ai/Huihui-GLM-5.1-abliterated` (754B) | 377+ GB at 4-bit | Same bucket as GLM-5 — abliterated variant, total params far exceed 64 GB. |

**P5-MODEL-64GB principle**: MoE active-parameter count governs decode *speed*, but total parameters govern *whether it fits* — 64 GB gates on total, not active. The April-2026 headline releases (DeepSeek-V4-Flash 284B/13B active, Kimi-K2.6 1T/32B active) are verified real but excluded on this basis. They become relevant only at the cluster Stage-3 / Mac-Studio tier on the roadmap.

### V8 Catalog Deferred (insufficient hardware)

| Model | Est Size | Reason Deferred |
|-------|----------|-----------------|
| `sjakek/Nex-N2-Pro` | ~230GB | 397B total, 17B active — far exceeds 64 GB even at Q1. |
| `DeepSeek-R1-0528` (full) | ~400GB | 671B full model. 8B distill variant added (V8 bench-r1-0528-qwen3-8b). |
| `Harness-1` (full capability) | n/a | Requires Chroma vector DB + external search state harness. Standalone model (gpt-oss-20B fine-tune) added to V8 bench-harness1. |

*Last updated: 2026-06-10*
