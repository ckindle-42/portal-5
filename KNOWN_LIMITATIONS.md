# Known Limitations

<!-- WIKI:GENERATED unit=unit-known-limitations-known-limitations -->
Architectural and design constraints that are currently unresolved. Resolved items are not listed here — see git log for history.

---
<!-- /WIKI:GENERATED -->

---

### CadQuery and build123d Unusable on linux/arm64

<!-- WIKI:GENERATED unit=unit-known-limitations-cadquery-and-build123d-unusable-on-linux-arm64 -->
- **ID**: P5-CAD-ARM64-001
- **Description**: CadQuery ≥2.4 and build123d both require `cadquery-ocp` / `ocp` (OpenCASCADE Python bindings), which has no pre-built wheels for `linux/arm64`. Installing either package in `Dockerfile.mcp` on Apple Silicon fails at build time.
- **Impact**: Python-native parametric CAD (`.box()`, `.extrude()` style) is unavailable inside the MCP containers. The `auto-cad` workspace uses OpenSCAD instead, which runs headlessly and has no platform restriction.
- **Mitigation**: Use OpenSCAD via the `render_openscad` tool for parametric geometry. Use `trimesh` (installed) for procedural mesh manipulation. If CadQuery is required in future, it must be built from source (multi-hour OCP compile) or sourced from a community arm64 wheel when one becomes available.
- **Do not re-add** `cadquery` or `build123d` to `Dockerfile.mcp` without first verifying an arm64 wheel exists — the build will silently succeed on x86 CI and fail on this hardware.

---
<!-- /WIKI:GENERATED -->

---

### Code Sandbox Requires Privileged Container

<!-- WIKI:GENERATED unit=unit-known-limitations-code-sandbox-requires-privileged-container -->
- **ID**: P5-ROAD-SEC-001
- **Description**: The `dind` (Docker-in-Docker) service runs with `privileged: true`. Docker-in-Docker cannot function without host kernel capabilities.
- **Impact**: In hardened environments, a compromised sandbox container could potentially escape to host.
- **Mitigation**: Disable the code sandbox by removing `mcp-sandbox` and `dind` from `docker-compose.yml`, or apply host-level controls (AppArmor/seccomp on the Docker daemon).
<!-- /WIKI:GENERATED -->

---

### No Built-in Multi-User Rate Limiting

<!-- WIKI:GENERATED unit=unit-known-limitations-no-built-in-multi-user-rate-limiting -->
- **ID**: P5-ROAD-031
- **Description**: Open WebUI has no per-user rate limiting. A single user in a multi-user deployment can exhaust server resources.
- **Mitigation**: Deploy behind a reverse proxy (nginx, Traefik) with rate limiting, or use Open WebUI's admin controls for per-user quotas.

---
<!-- /WIKI:GENERATED -->

---

### Devstral 2509 Upgrade Blocked — Model Not Published

<!-- WIKI:GENERATED unit=unit-known-limitations-devstral-2509-upgrade-blocked-model-not-published -->
- **ID**: P5-BENCH-DEVSTRAL-2509
- **Description**: `lmstudio-community/Devstral-Small-2509-MLX-4bit` was not found on
  HuggingFace as of TASK_BENCH_COVERAGE_V1 (2026-05-21). bench-devstral remains pinned
  to the 2507 (July 2025) variant.
- **Operator action**: Re-run Change 0 verification when the 2509 card appears.
<!-- /WIKI:GENERATED -->

---

### meta3 (Metasploitable3-Windows) — Scenario Coverage + SPL Precision Gaps

<!-- WIKI:GENERATED unit=unit-known-limitations-meta3-metasploitable3-windows-scenario-coverage-spl-precision-gaps -->
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
<!-- /WIKI:GENERATED -->

---

### RBP Benign-Corpus Breadth and Alert Fatigue

<!-- WIKI:GENERATED unit=unit-known-limitations-rbp-benign-corpus-alert-fatigue -->
- **ID**: P5-SEC-BENIGN-CORPUS-001
- **Description**: The 2026-07-26 closeout added six live, backdated benign
  cells (two each for `windows:security`, `web:access`, and `linux:auditd`)
  through the same HEC/index/provenance path as attack corpus data. The strong
  V4 arm correctly stayed silent on 2/6 and emitted four
  `ANOMALOUS_UNCLASSIFIED` notifications: measured notification precision
  33.3% and false-flag rate 66.7%. There were no confident wrong
  `CONFIRMED` verdicts.
- **Impact**: The scoreboard's previously blank alert-fatigue axis is now
  measured, but the result is not production-trustworthy on this negative
  subset. Honest anomaly escalation is safer than a false confirmation, yet
  each notification still consumes analyst attention.
- **Boundary**: Six plausibly confusable cells are a representative closeout
  subset, not an exhaustive sample of normal enterprise behavior. The 33.3%
  precision estimate must not be extrapolated beyond these fixtures; broader
  hosts, identities, time windows, applications, and routine administrative
  workflows remain unmeasured.
- **Resolution path**: Expand the benign corpus before changing verdict
  behavior, then use the typed false-flag breakdown to tune evidence and
  discriminator quality. Preserve the rule that any NOTIFY on benign activity
  remains a false flag, even when the verdict is an honest anomaly.
<!-- /WIKI:GENERATED -->

### ComfyUI Runs Outside Docker

<!-- WIKI:GENERATED unit=unit-known-limitations-comfyui-runs-outside-docker -->
- **Description**: ComfyUI runs on the host (not in Docker) to access MPS/CUDA directly. Required for image/video generation performance.
- **Impact**: Manual setup required outside `./launch.sh up`. On a fresh machine, ComfyUI must be installed separately.
- **Mitigation**: `./launch.sh install-comfyui` handles setup on supported platforms. See `docs/COMFYUI_SETUP.md`.
<!-- /WIKI:GENERATED -->

---

### Voice Cloning (fish-speech) Requires Separate Installation

<!-- WIKI:GENERATED unit=unit-known-limitations-voice-cloning-fish-speech-requires-separate-installation -->
- **Description**: Voice cloning via `fish-speech` is not in the Docker stack — requires host-side installation. The docker `tts_mcp` `clone_voice` tool requires it and errors without it.
- **Impact**: The docker-side `clone_voice` tool is unavailable without fish-speech installed.
- **Mitigation**: Voice cloning still works without fish-speech via the native `mlx-speech` service (`:8918`, `POST /v1/audio/speech` with `voice: "clone:/path/to/reference.wav"`, Qwen3-TTS Base-Clone) — verified during Slice P media bring-up (`TASK_MEDIA_BRINGUP_V1`). `kokoro-onnx` covers non-cloned TTS out of the box either way. See `docs/FISH_SPEECH_SETUP.md` for fish-speech.
<!-- /WIKI:GENERATED -->

---

### ComfyUI Model Download Commands Are Broken

<!-- WIKI:GENERATED unit=unit-known-limitations-comfyui-model-download-commands-are-broken -->
- **Description**: `./launch.sh download-comfyui-models` calls `scripts/download_comfyui_models.py`, deleted in commit `ea864cf` ("superseded by pull-wan22 / pull-qwen-image commands in launch.sh") — but neither `pull-wan22` nor `pull-qwen-image` was ever implemented; both were advertised in `launch.sh --help` with no case handler. Found during Slice P media bring-up (`TASK_MEDIA_BRINGUP_V1`).
- **Update (2026-07-29)**: `pull-wan22` is now implemented (`scripts/lib/services.sh:_launch_pull_wan22`) and live-verified for TI2V-5B, S2V-14B, and T2V-A14B model downloads. **Video generation itself is shelved regardless — see `unit-known-limitations-wan22-fp8-scaled-checkpoints-crash-on-apple-silicon-mps`.** `download-comfyui-models` now exits with a clear pointer instead of `ModuleNotFoundError`. `pull-qwen-image` is still unimplemented (image generation, tracked separately — not shelved).
- **Impact**: No `launch.sh` subcommand can download Qwen-Image models yet. Separately, the `flux-uncensored` image backend's expected checkpoint (`Flux_v8-NSFW.safetensors`) has no known working source — the old script's repo (`enhanceaiteam/Flux-Uncensored-V2`) 404s, and no other reference to that filename exists in the codebase.
- **Mitigation**: Use `./launch.sh pull-wan22` for Wan 2.2 model downloads (though see the fp8/MPS unit above before relying on the output — most of what it downloads doesn't currently run on Apple Silicon). Download Qwen-Image directly with `hf download` until `pull-qwen-image` is implemented — see `docs/COMFYUI_SETUP.md#download-models`.
<!-- /WIKI:GENERATED -->

---

### ComfyUI Cross-Model-Family Memory Exhaustion (Apple Silicon)

<!-- WIKI:GENERATED unit=unit-known-limitations-comfyui-cross-model-family-memory-exhaustion-apple-silicon -->
- **Description**: ComfyUI on MPS does not reliably evict a previously-loaded model's weights when a new workflow loads a different model family in the same long-running process. Observed live during Slice P: Flux (~22GB) followed by a Wan2.1-NSFW 14B video job (~39GB) in the same process, without a restart between them, drove swap to 66.7GB/67.6GB used and locked up the system (not just RAM pressure — genuine swap-thrashing). Recurred a second time during Slice 7's own live verification: a *tiny* wan21-nsfw job (9 frames, 5 steps) still crashed free RAM from ~45GB to ~60MB — the 14B backend's real peak usage (diffusion activation/buffer overhead) runs well above its static on-disk weight size (~39GB) regardless of frame count, close to the entire 64GB pool.
- **Impact**: Chaining image generation and large video generation (or switching between very different video model families) without restarting ComfyUI in between risks a full system lockup on 64GB unified-memory Apple Silicon hardware. The wan21-nsfw backend specifically should be treated as needing the *whole* machine, not just its weight size.
- **Mitigation**: Tier 0 (`unit-fact-media-memory-budget`) and Tier 1 (`portal/modules/media/tools/_admission.py`, `admit()`) pre-flight admission control landed in `TASK_VRAM_ADMISSION_V1` (Slice 7) — wan21-nsfw's estimate is set to 55GB (not the 39GB weight size) to reflect the observed real peak. Restart ComfyUI between large model-family switches regardless: `launchctl kickstart -k gui/$(id -u)/com.portal5.comfyui`. Tier 2 (shared cross-engine broker with Ollama) is explicitly not built — see the task's `[GATE: SCOPE]`.
<!-- /WIKI:GENERATED -->

---

### `pytest portal` Leaves Real Write-Through Test Artifacts

<!-- WIKI:GENERATED unit=unit-known-limitations-pytest-portal-leaves-real-write-through-test-artifacts -->
- **Description**: Some `portal/modules/security/tests/` tests write through the real goal/playbook journal path (`portal/modules/security/core/field_journal/`) and checkpoint path (`portal/modules/security/core/results/checkpoints/`) instead of a `tmp_path`-redirected one, violating the `tmp_path` testing rule (`CLAUDE.md` Testing Rules).
- **Impact**: Running `pytest portal` locally dirties the working tree — new dated entries under `field_journal/` and a modified `field_journal/_index.json`, plus files under `results/checkpoints/`.
- **Mitigation**: `results/checkpoints/` is gitignored. `field_journal/` holds real committed history so it is intentionally *not* gitignored — run `git status` after `pytest portal` and `git checkout -- portal/modules/security/core/field_journal/_index.json` (plus `git clean` any new dated entries) before staging a commit. See `CLAUDE.md` Testing Rules.
- **Fix (open)**: Route the journal writer through a fixture-injected path in the offending tests so `pytest portal` is side-effect-free like `pytest tests/unit`.
<!-- /WIKI:GENERATED -->

---

### Emergent Objective Loop — Curated Capability Tool Names vs Live-Dispatch Whitelist

<!-- WIKI:GENERATED unit=unit-known-limitations-emergent-objective-loop-curated-capability-tool-names-vs-live-dispatch-whitelist -->
- **ID**: P5-EMERGENT-001
- **Status**: PARTIALLY FIXED 2026-07-16 (live-verification pass, same day as discovery) — three real, root-cause fixes landed; the underlying gap class remains open for the tools not yet aliased.
- **Description**: `capability/index.py`'s curated Capability library (used by `capability.query()` and now the emergent objective loop, `TASK_EMERGENT_SLICE1_PERCEPTION_ENTRY_V1`) has two kinds of `tools` values for many entries — real Kali binary names (`nmap`, `impacket-secretsdump`, `bloodhound-ce-python`, ...) for domain-probe capabilities (`smb_probe`, `ldap_probe`, ...), or an **empty list** for several named-technique capabilities (`ad-certificate-abuse`, `kerberos-delegation`, `oauth-oidc-chain`, `file-upload-bypass`, `smb-enumeration`, and others). `lab.py::_lab_dispatch_inner`'s real live-dispatch path only recognizes a small fixed whitelist of ~15 literal tool names — neither the Kali binary names nor the empty-tools capability IDs originally matched that whitelist, so `SecurityExecutor` (Slice 1.2) dispatched them through the synthetic fallback even when the lab was fully live and reachable. A second, compounding cause was found the same day: `capability.query()`'s `applies_when` predicates (e.g. `smb_probe` requires `open_ports` to contain 445) are gated on a flat `observations["open_ports"]` list that predates `LabPerception` — `PerceptionDelta.to_observation()` didn't populate it, and `run_emergent_engagement` started with `observations={}` (no upfront perception call), so on a cold start every real-tooled AD-probe capability was starved out and only the empty-`tools` capabilities (which have no `applies_when` gate) ever matched.
- **Fixes landed** (all live-verified against the real Proxmox lab, portal-lab-dc01/srv01/vulhub, sandbox MCP `lab_exec_active:true`):
  1. `--domain-hint` threaded into `run_emergent_engagement`/CLI (was hardcoded `None`).
  2. `lab.py::_lab_dispatch_inner` now aliases the two real Kali binary names verified correct: `"nmap"` → same path as `run_nmap_scan` (confirmed real: 22/80/8080 open on `10.10.11.50`), `"impacket-GetUserSPNs"` → same path as `exploit_service`/Kerberoast (confirmed real: 3 live TGS hashes captured from `lab-srv01.portal.lab`, then a real offline `john`+rockyou.txt crack attempt inside the sandbox — 0/3 cracked, correctly scored `FAILED` not `PROVEN`, since the passwords aren't in the common wordlist).
  3. `PerceptionDelta.to_observation()` now also derives a flat `open_ports` list (`perception._extract_open_ports`, additive) from either shape the real prober can return, and `run_emergent_engagement` gained a `perception` param that seeds real initial observations before the loop starts (`goal_cli._cmd_emergent` wires this by default via the new shared `perception.default_lab_prober`, replacing a near-duplicate that used to live only in `security_mcp.py`). Confirmed live: after this fix the ranker's first pick against the AD domain moved from an empty-`tools` capability (`ad-certificate-abuse`) to a real-tooled one (`smb_probe`/`ldap_probe`'s `bloodhound-ce-python`) — proving the seed closes the starvation, though `bloodhound-ce-python` itself isn't in the alias table yet (see below).
- **Still open**: Real Kali binaries seen live but not yet aliased/verified (`bloodhound-ce-python`, `impacket-secretsdump`, `impacket-psexec`, `impacket-wmiexec`, `enum4linux-ng`, `nxc`, `responder`, `impacket-GetNPUsers`, `impacket-dacledit`, `certipy-ad`, `ldap3`, `metasploit`) and the empty-`tools` capabilities (`ad-certificate-abuse`, `kerberos-delegation`, `oauth-oidc-chain`, `file-upload-bypass`, `smb-enumeration`) still dispatch synthetic. Each remaining alias needs its exact CLI invocation verified correct (and, for stateful/destructive ones like `impacket-psexec`/`impacket-wmiexec`/`responder`, reviewed for lab safety) before wiring — not done blind, unlike the two above which were directly confirmed working first.
- **Impact**: The emergent loop's "no seeded first-move" design means the deterministic ranker can still pick a non-dispatchable capability, producing a synthetic-only trajectory even against a fully live lab, for any tool not yet in the alias table. This still slows G1 corpus sign-off (DESIGN_EMERGENT_LAB_AGENT_V2 §9) accumulating real PROVEN trajectories — every synthetic step is honestly excluded from `emergent_gaps.gaps_from_trajectory` (never contributes a false gap) and every synthetic-derived trajectory is honestly never PROVEN (AX ratchet holds), so this remains a coverage/usefulness gap, not a correctness or honesty regression.
- **Resolution path (open)**: Continue verifying and aliasing the remaining real binary names one at a time (never batch-guess CLI syntax for tools with real side effects), and separately decide what the empty-`tools` capabilities should actually dispatch to (populate `capability/index.py` or retire them). Pre-existing architecture gap in the "already-built" composition engine (DESIGN_EMERGEN

[Content truncated — see full doc]
<!-- /WIKI:GENERATED -->

---

### auto-math Workspace — Reasoning Block Support

<!-- WIKI:GENERATED unit=unit-known-limitations-auto-math-workspace-reasoning-block-support -->
- **ID**: P5-MATH-001
- **Status**: ✅ RESOLVED (V8 model refresh — 2026-06-10)
- **History**: Original limitation was `Qwen2.5-Math-7B-Instruct` (MLX, no `reasoning_content` blocks). Model replaced in V8 by `phi4-mini-reasoning` (RL-trained, Phi-4-Mini-Reasoning, ~2.5GB). The new model has `emits_reasoning: True` — math reasoning appears in the collapsible thinking panel.
- **Alternative**: For even heavier reasoning, `auto-reasoning` (DeepSeek-R1-0528-Qwen3-8B) also separates reasoning content.
<!-- /WIKI:GENERATED -->

---

### baronllm text_only tool output — auto-security MCP tools non-functional

<!-- WIKI:GENERATED unit=unit-known-limitations-baronllm-text-only-tool-output-auto-security-mcp-tools-non-functional -->
- **ID**: P5-TOOL-001
- **Description**: `huihui_ai/baronllm-abliterated` (formerly auto-security primary; VulnLLM-R-7B is now the model_hint primary as of SECURITY_FLEET_REVIEW_2026-06, though baronllm remains in the security pool) outputs tool-call JSON embedded in the `content` field of Ollama's `/v1/chat/completions` response rather than in the structured `tool_calls` field. Ollama's llama.cpp backend does not parse this as a function-call delta. Result: the pipeline's `_dispatch_tool_call` path is never triggered for auto-security requests that attempt MCP tool use.
- **Evidence**: `audit-tools 2026-06-18` probe — outcome `text_only`, content: `{"name":"get_current_time","parameters}:{ "city": "Paris" }`. UAT TV-02 (execute_python proof) and TV-03 (classify_vulnerability) both show tool not dispatched. Previous `supports_tools: true` marking (TASK_TOOL_AUDIT_V2) was a false positive from Ollama template header inspection, not a live response probe.
- **Impact**: Auto-security cannot use `execute_bash`, `execute_python`, `classify_vulnerability`, or any pipeline-dispatched MCP tool. TV-02 grades as WARN (non-critical assertion). Prose security analysis and code audits still work (text generation is unaffected).
- **Resolution path**: (a) Fix baronllm's Ollama chat template to emit proper `tool_calls` structure — this requires inspecting the model's tokenizer_config and Ollama template to align with llama.cpp's tool-call parsing; OR (b) Replace baronllm with a model in the auto-security chain that passes the live probe (e.g., qwen3.5-abliterated:9b was confirmed tool_call in a prior audit).
- **Status**: ✅ RESOLVED 2026-06-20 (TASK_TOOLCALL_FIX_LOCKIN_V1). A corrected tool-calling chat template makes baronllm emit structured `tool_calls`. Fleet `--audit-tools` confirmed outcome=`tool_call` and the security chain scored 8/8 1.00 WIN. Resolution path (a) — template fix — was taken; no model swap required. `supports_tools` flipped to `true` in `config/backends.yaml` (both entries), backed by the live probe. The same template fix also recovered HauhauCS (no_tool → tool_call).
- **Do not re-enable** `supports_tools: true` for baronllm without running `python3 tests/portal5_persona_matrix.py --audit-tools --workspace auto-security` or the direct Ollama probe and confirming outcome=`tool_call`. *(This gate was satisfied by the 2026-06-20 fleet audit.)*
<!-- /WIKI:GENERATED -->

---

### Asteroids Bench Score Variance Is the Benchmark's Purpose

<!-- WIKI:GENERATED unit=unit-known-limitations-asteroids-bench-score-variance-is-the-benchmark-s-purpose -->
- **ID**: P5-BENCH-001
- **Description**: The CC-01 Asteroids bench (`bench-*` workspaces) intentionally surfaces raw model differences on a fixed task. All bench personas share an identical creative-coder system prompt — score variance reflects model capability, not a test harness defect.
- **Operator action**: Use bench scores as model-selection signal. A model scoring ≤3/5 on CC-01 is not a candidate for `auto-coding` HTML generation tasks.
<!-- /WIKI:GENERATED -->

---

### Tool Preselection — Candidate 1B Models Cannot Rank Tools

<!-- WIKI:GENERATED unit=unit-known-limitations-tool-preselection-candidate-1b-models-cannot-rank-tools -->
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
<!-- /WIKI:GENERATED -->

---

## MLX Inference Proxy — RETIRED (commit 3a0c58e)

<!-- WIKI:GENERATED unit=unit-known-limitations-mlx-inference-proxy-retired-commit-3a0c58e -->
The MLX inference proxy and all its limitations (single-model eviction,
cold-boot 503 windows, admission control, deploy staleness) no longer
apply. All chat inference runs through Ollama (:11434). MLX is retained
only for speech (:8918), transcription (:8924), embeddings (:8917), and
reranking (:8925) — those have their own sections.
<!-- /WIKI:GENERATED -->

---

## Model Parity — Specialist models lost in the MLX→Ollama migration

<!-- WIKI:GENERATED unit=unit-known-limitations-model-parity-specialist-models-lost-in-the-mlx-ollama-migration -->
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
<!-- /WIKI:GENERATED -->

---

## Ollama Native MLX Engine — Evaluation Findings (2026-07-01)

<!-- WIKI:GENERATED unit=unit-known-limitations-ollama-native-mlx-engine-evaluation-findings-2026-07-01 -->
Ollama 0.31.1 added a built-in MLX engine (distinct from the retired standalone
`mlx_lm`/`mlx_vlm` proxy above) that claims ~90% faster Gemma 4 via multi-token
prediction (MTP). This section documents a same-day evaluation of that engine
plus a broader catalog sweep for MLX equivalents of the fleet. **No production
config was changed** — `config/backends.yaml` was reverted, all pulled MLX
models (4 Ollama-native + 16 HF-sourced, ~254GB total) were deleted, and disk
usage is back at baseline (`hf-cache` exactly 280GB, matching pre-evaluation).
<!-- /WIKI:GENERATED -->

---

### P5-MLX-EVAL-001 — GGUF fleet regressed slightly on 0.31.1; MTP is MLX-engine-only

<!-- WIKI:GENERATED unit=unit-known-limitations-p5-mlx-eval-001-gguf-fleet-regressed-slightly-on-0-31-1-mtp-is-mlx-engine-only -->
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
<!-- /WIKI:GENERATED -->

---

### P5-MLX-EVAL-002 — Ollama's official gemma4 `-mlx` tags are not drop-in swaps

<!-- WIKI:GENERATED unit=unit-known-limitations-p5-mlx-eval-002-ollama-s-official-gemma4-mlx-tags-are-not-drop-in-swaps -->
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
<!-- /WIKI:GENERATED -->

---

### P5-MLX-EVAL-003 — HF-hosted MLX models are currently unreachable by the Pipeline

<!-- WIKI:GENERATED unit=unit-known-limitations-p5-mlx-eval-003-hf-hosted-mlx-models-are-currently-unreachable-by-the-pipeline -->
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
<!-- /WIKI:GENERATED -->

---

### P5-MLX-EVAL-004 — Large single-blob MLX downloads hang intermittently

<!-- WIKI:GENERATED unit=unit-known-limitations-p5-mlx-eval-004-large-single-blob-mlx-downloads-hang-intermittently -->
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
<!-- /WIKI:GENERATED -->

---

### P5-MLX-EVAL-005 — Two security-tier fine-tunes have no working MLX conversion

<!-- WIKI:GENERATED unit=unit-known-limitations-p5-mlx-eval-005-two-security-tier-fine-tunes-have-no-working-mlx-conversion -->
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
<!-- /WIKI:GENERATED -->

---

### Importing the security bench module sets a Linux-only PROMETHEUS_MULTIPROC_DIR host-side

<!-- WIKI:GENERATED unit=unit-known-limitations-importing-the-security-bench-module-sets-a-linux-only-prometheus-multiproc-dir-host-side -->
- **ID**: P5-ENV-MULTIPROC-HOSTLEAK-001
- **Description**: `tests/benchmarks/bench_lab_exec.py` has a module-level
  `_load_env()` call that runs `os.environ.setdefault(k, v)` for every line
  in `.env` **at import time**, unconditionally. `portal/modules/security/
  core/_data.py` imports `bench_lab_exec` at its own module level, so simply
  importing anything under `portal.modules.security.core` (e.g.
  `from portal.modules.security.core._data import PER_WORKSPACE_TIMEOUT`)
  copies `.env`'s `PROMETHEUS_MULTIPROC_DIR=/dev/shm/portal_metrics` (a
  path that only exists inside the Linux Docker containers) into the
  process environment on the host. On macOS (no `/dev/shm`), any
  subsequent code that imports `portal.platform.inference.router.metrics`
  in the same process — including this security module's own
  `preinject`/`routing` imports — then crashes with
  `FileNotFoundError: /dev/shm/portal_metrics/gauge_all_<pid>.db`
  (prometheus_client's `Gauge.__init__` tries to mmap a file there).
  Reproduced live while verifying `CLOSEOUT_ALIAS_REMOVAL.md` Holdout 3's
  `DEFAULT_WORKSPACES`/`PER_WORKSPACE_TIMEOUT` canonicalization.
- **Impact**: any host-native (non-Docker) Python process that imports both
  the security bench module and the pipeline's metrics module in the same
  interpreter — `scripts/validate_system.py`'s AU/AV checks worked around
  this by stripping the var before their subprocess calls (see their code
  comments); this is likely also implicated in the `ci_local.sh` hang
  flagged earlier in this session (`pytest tests/unit portal/modules/
  security/tests` in a fresh venv) — worth checking first if that's
  revisited.
- **Not fixed here**: out of scope for the alias-closeout work. The real
  fix is either making `bench_lab_exec.py` not mutate global env as an
  import-time side effect, or making the multiprocess dir path OS-aware
  (e.g. `tempfile.gettempdir()`-based) rather than hardcoding a Linux path
  in `.env`.
<!-- /WIKI:GENERATED -->

---

### POST /v1/messages (Anthropic-compat endpoint) returns HTTP 200 with a `null` body

<!-- WIKI:GENERATED unit=unit-known-limitations-post-v1-messages-anthropic-compat-endpoint-returns-http-200-with-a-null-body -->
- **ID**: P5-ANTHROPIC-COMPAT-001
- **Description**: `handlers.anthropic_messages` (`portal/platform/inference/router/handlers.py:1159`,
  the endpoint `scripts/cc-local.sh` / Claude Code's `ANTHROPIC_BASE_URL` integration
  depends on) returns `200 OK` with a literal `null` JSON body for a plain
  non-streaming request, reproduced with both a base workspace id
  (`auto-coding`) and a persona slug (`agenticheavy`) — so it's unrelated to
  the alias-closeout/persona work in this pass, and pre-existing (zero unit
  test coverage exists for this endpoint; `/v1/chat/completions` itself
  works correctly for the same model ids, confirmed live). No server-side
  error is logged.
- **Impact**: Claude Code via `scripts/cc-local.sh` likely cannot get a real
  response today — the SDK would receive `null` where it expects an
  Anthropic Messages response object.
- **Discovered**: 2026-07-13, live-verifying `DESIGN_OPENCODE_ADDRESSING_V1.md`'s
  Step 3e CLI-contract migration (`cc-local.sh`'s default model rename).
- **Not fixed here**: root-causing `anthropic_to_openai_body`/the ASGI-loopback
  dispatch/`openai_response_to_anthropic` translation chain is a distinct
  bug outside Stage A's scope (alias/persona addressing, not the Anthropic
  wire-format translation layer). Needs its own investigation + unit tests.
<!-- /WIKI:GENERATED -->

---

### devstral:24b Runtime VRAM Footprint (25.7 GB)

<!-- WIKI:GENERATED unit=unit-known-limitations-devstral-24b-runtime-vram-footprint-25-7-gb -->
- **ID**: P5-VRAM-DEVSTRAL-001
- **Description**: devstral:24b file size is 14.3 GB but runtime Ollama resident size is ~25.7 GB due to large default context window and KV cache allocation (q8_0). This is nearly 2× the file size and can cause memory-pressure eviction of other loaded models; on M4 Pro 64 GB hardware this is non-critical (graceful CPU offload), but relevant on tighter budgets.
- **Impact**: When devstral is active, it may evict the LLM router model from VRAM. The first post-eviction routing request falls back to Layer 2 keyword scoring (correct behavior), then the router cold-loads in ~4.2s and stays warm. Subsequent requests use the LLM router normally.
- **This is graceful, not a crash**: Ollama offloads CPU layers under memory pressure rather than failing. Unlike the former MLX Metal OOM, no kernel panic occurs.
- **Mitigation**: `OLLAMA_MAX_LOADED_MODELS=3` (current default) reserves a slot for the router + 2 inference models. If devstral:24b is loading as an inference peer, its runtime footprint is the limiting factor — not the slot count. Setting `OLLAMA_MEMORY_LIMIT=42g` in the Ollama plist caps worst-case pressure; see Admin Guide → Router Configuration.
<!-- /WIKI:GENERATED -->

---

### Request-Size Cap Relies on Content-Length Only

<!-- WIKI:GENERATED unit=unit-known-limitations-request-size-cap-relies-on-content-length-only -->
- **ID**: P5-REQ-SIZE-001
- **Description**: The pipeline caps requests at 4 MB via `Content-Length` header check. Chunked transfer-encoded requests bypass this cap entirely — Starlette middleware is the proper fix.
- **Mitigation**: Until Starlette body-size middleware is added, operators should configure upstream proxies (nginx, OWUI) to enforce request-size limits.
<!-- /WIKI:GENERATED -->

---

### Speculative Decoding / MTP — RETIRED with the MLX proxy (commit 3a0c58e)

<!-- WIKI:GENERATED unit=unit-known-limitations-speculative-decoding-mtp-retired-with-the-mlx-proxy-commit-3a0c58e -->
- **IDs**: P5-SPEC-001, P5-MTP-001, P5-MTP-PATH (all moot)
- **Status**: The MLX inference proxy that hosted `--draft-model` speculative decoding and the `speculative_decoding.draft_models` map was retired; chat inference is Ollama-only. These limitations no longer apply because the infrastructure they described no longer exists.
- **If revisited**: any future speculative-decoding / MTP work targets Ollama's native path (llama.cpp b9180+), not MLX. The bench-only MTP GGUF candidates remain in the catalog as bench entries; there is no production MLX serving path to enable.
- **P5-FUT**: evaluate `/api/chat` as `chat_url` — `/api/chat` would allow full `options` passthrough but requires changing payload/response shapes.
<!-- /WIKI:GENERATED -->

---

### phi4-reasoning:plus crashes Ollama's llama-server on this host — CONFIRMED NOT a corrupted download

<!-- WIKI:GENERATED unit=unit-known-limitations-phi4-reasoning-plus-crashes-ollama-s-llama-server-on-this-host-confirmed-not-a-corrupted-download -->
- **ID**: P5-MODEL-PHI4REASONING-001
- **Description**: Both `phi4-reasoning:plus` and `phi4-reasoning:plus-ctx32k` fail on direct `POST /api/generate` with `{"error":"llama-server process has terminated: signal: abort trap"}` — a local Ollama/model-file issue, not a routing or pipeline bug. Discovered during `DESIGN_PERSONA_INTENT_REMEDIATION_V1.md`'s live verification of the `phi4stemanalyst` persona's `model_pin`: the pipeline correctly resolved and requested `phi4-reasoning:plus-ctx32k` (confirmed in logs — `wanted phi4-reasoning:plus-ctx32k`), the registry's existing backend-failover mechanism correctly caught the crash and fell back to another reasoning-pool model, and honestly logged `model_hint mismatch ... response may be from wrong model` rather than silently misreporting. The routing/pin mechanism is proven correct by the other 4 personas (`magistralstrategist`, `devstral_coder`, `glm-coder`, `glm-thinker`) succeeding cleanly end-to-end.
- **Root cause CONFIRMED (2026-07-13, TASK_MODEL_POOL_REACHABILITY_FIX.md live-confirm)**: `ollama rm phi4-reasoning:plus-ctx32k phi4-reasoning:plus`, full re-pull of `phi4-reasoning:plus` from scratch, and rebuild of both ctx-tagged variants via `ollama create` — crash reproduced identically on the freshly-pulled base model. **Not a corrupted download.** `/opt/homebrew/var/log/ollama.log` shows the abort originates in llama.cpp's device-memory-fitting path (`common_fit_params` → `common_params_fit_impl` → `common_get_device_memory_data_impl`) during model load on Ollama 0.31.1 — a real incompatibility between this GGUF and the installed llama-server build on this host (Apple Silicon Metal backend), not model-file integrity.
- **Impact**: `phi4stemanalyst` currently falls back to whatever `auto-reasoning`'s pool serves instead of Phi-4-reasoning-plus. Given the confirmed crash, the persona has been re-identified generically (no `model_pin`, no Phi-4 branding in tags/comments) rather than left claiming an identity it can't serve — it now intentionally serves `auto-reasoning`'s pool default (`DeepSeek-R1-0528-Qwen3-8B`). `config/backends.yaml`'s `reasoning` backend group intentionally does NOT include `phi4-reasoning:plus-ctx32k` — do not add it without first resolving this crash.
- **Mitigation options not yet tried**: (1) upgrade/downgrade Ollama to a different llama.cpp vendor commit and retest; (2) try a different quantization/source GGUF for Phi-4-reasoning-plus (this one may be built with a `common_fit_params` code path this Ollama build mishandles); (3) file upstream against Ollama/llama.cpp with the log excerpt above. Re-pulling alone will NOT fix it — already tried and reproduced.
<!-- /WIKI:GENERATED -->

---

### 70B Dense Models Unusable for Daily Routing on M4 Pro 64GB

<!-- WIKI:GENERATED unit=unit-known-limitations-70b-dense-models-unusable-for-daily-routing-on-m4-pro-64gb -->
- **ID**: P5-SPEED-001
- **Description**: Llama-3.3-70B-Instruct-4bit and DeepSeek-R1-Distill-Llama-70B-4bit measure ~3.5 TPS warm — too slow for interactive use. 3-bit quantization (~28GB) is theoretically viable at ~9.7 TPS but not yet bench-validated.
- **Mitigation**: All daily-routed workspaces use ≤33B models. 70B variants are bench-tier only.
<!-- /WIKI:GENERATED -->

---

### Ollama /v1 ignores options.num_ctx and options.num_batch

<!-- WIKI:GENERATED unit=unit-known-limitations-ollama-v1-ignores-options-num-ctx-and-options-num-batch -->
- **ID**: P5-OLLAMA-OPTIONS-001
- **Description**: Ollama's OpenAI-compatible `/v1/chat/completions` endpoint ignores the `options` sub-object entirely (VERIFY-1 probes, 2026-06). The pipeline still injects `options.num_ctx`, `options.num_batch`, and `options.num_predict` (the latter mapped to `max_tokens` at top level per Branch I) because a future Ollama version may honor them. Currently:
  - `context_limit` per workspace (e.g. `auto-coding: 16384`) is **not enforced** — set PARAMETER num_ctx in the model's Modelfile or OLLAMA_CONTEXT_LENGTH
  - `num_batch` injection is inert — set PARAMETER num_batch in Modelfiles for prefill tuning
  - `predict_limit` is mapped to OpenAI `max_tokens` (top-level, honored) as a workaround
- **Roadmap note:** P5-FUT: evaluate `/api/chat` as `chat_url` — it honors the Ollama-native parameter set but requires changing all payload/response shapes.

---
<!-- /WIKI:GENERATED -->

---

## Shared Workspace + Auto-STT Disabled (TASK-WORKSPACE-001)

<!-- WIKI:GENERATED unit=unit-known-limitations-shared-workspace-auto-stt-disabled-task-workspace-001 -->
- **Voice-input via microphone is disabled.** `AUDIO_STT_ENGINE` is empty by default, which disables auto-transcription of both file uploads and microphone recordings. Re-enabling it re-enables auto-transcribe-on-upload. The global toggle is OWUI's only knob.
- **Existing MCPs not migrated to /workspace.** `mcp-documents`, `mcp-tts`, and `mcp-comfyui` still write to `${AI_OUTPUT_DIR}` flat. New MCPs use `/workspace/generated/<category>/`. Both layouts coexist; migration is opportunistic.
- **Permissions assume single-host deployment.** 0775 mode on workspace directories assumes operator-owned files and compatible Docker UIDs. Multi-tenant or hardened hosts need explicit UID mapping.
- **No retention policy.** `${AI_OUTPUT_DIR}` grows unbounded. `./launch.sh workspace-clean --age=Nd` is a planned but not yet implemented command.

---
<!-- /WIKI:GENERATED -->

---

## Diarized Transcription (TASK-TRANSCRIBE-001)

<!-- WIKI:GENERATED unit=unit-known-limitations-diarized-transcription-task-transcribe-001 -->
- **Pyannote model gating.** Diarization requires accepting HuggingFace user agreements for `pyannote/segmentation-3.0` and `pyannote/speaker-diarization-3.1`. Without `HF_TOKEN` in `.env` and licenses accepted, diarization calls return 500.
- **Overlapping speech.** Pyannote 3.1 underperforms when multiple speakers talk simultaneously. Segments are assigned to a single speaker by maximum overlap.
- **Speaker count drift on long recordings.** For recordings >15–30 min, pyannote may split one speaker into two IDs after long silence gaps. Pass `num_speakers=N` if known.
- **OWUI tool-call timeout for long files.** OWUI's default MCP timeout is shorter than processing time for files >5 min. Raise `TOOL_SERVER_REQUEST_TIMEOUT` (e.g., 1800s) or use the direct endpoint at `:8924`.
- **MLX path is macOS-only.** `scripts/mlx-transcribe.py` requires Apple Silicon. The Docker `whisper_mcp.py` fallback (faster-whisper + pyannote on CPU/CUDA) is the cross-platform alternative.

---
<!-- /WIKI:GENERATED -->

---

## OWUI Audio Drop UX (TASK-OWUI-AUDIO-DROP-001)

<!-- WIKI:GENERATED unit=unit-known-limitations-owui-audio-drop-ux-task-owui-audio-drop-001 -->
- **OWUI internal 60s tool-call ceiling.** Some OWUI builds enforce a hard internal timeout on tool execution that `AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA` does not affect (open-webui/open-webui#16902). When this fires, the tool completes server-side but the persona never sees the result. Use `scripts/transcribe_and_complete.sh` for files with wall time >60s.
- **WEBUI_SECRET_KEY rotation invalidates OAuth tokens.** If `.env` is regenerated and the secret key changes, all MCP OAuth tools need re-authentication.
- **Microphone voice input remains disabled.** Unchanged from TASK-WORKSPACE-001 trade-off.

---

---
<!-- /WIKI:GENERATED -->

---

## Models Out of M4 Pro 64 GB Budget

<!-- WIKI:GENERATED unit=unit-known-limitations-models-out-of-m4-pro-64-gb-budget -->
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
<!-- /WIKI:GENERATED -->

---

### P5-EMERGENT-002 — Deterministic capability ranker can't reach oracle-bearing capabilities once any tool-declaring recon capability is a candidate

<!-- WIKI:GENERATED unit=unit-known-limitations-p5-emergent-002-deterministic-capability-ranker-can-t-reach-oracle-bearing-capabilities-once-any-tool-declaring-recon-capability-is-a-candidate -->
Found live during `TASK_SECURITY_ARM_CLOSE_LOOP_V1` Phase 8 (`goal emergent`
run against the reconciled `10.10.11.50` target, `objective_class=host_foothold`,
2026-07-16). `portal.platform.agent.decide._decide_via_deterministic_fallback`
picks a tool first (`rank.select_tools`), then finds the first candidate
capability whose `tools` list contains that tool
(`_pick_capability_for_tool`). Recon-phase service-probe capabilities (from
`capability/index.py`'s `_from_service_probes`) always declare real tools
(`curl`, `redis-cli`, …); exploit-phase capabilities from `_from_lab_targets`
and `_from_challenge_classes` — the ones carrying a real `oracle` — always
declare `tools=[]`. Once ANY tool-declaring capability is among the
candidates, `available_tools` is non-empty and the ranker takes the
tools-based branch, which structurally can never select a `tools=[]`
capability (`_pick_capability_for_tool` only matches on declared tools). The
loop lands real, live actions (confirmed: `redis_probe` → real `redis-cli`
PONG against the vulhub redis stack) but then halts on the I4 no-progress
gate because the ranker keeps re-selecting the same top recon capability
every turn — no state tracks "already probed this port", and exploit-phase
capabilities with oracles are never reachable to prove AX (state-oracle
verdict) end-to-end.

Two real, separate fixes are already applied in this task's run (both
correctness fixes, not workarounds): (1) `SecurityExecutor.execute` now
dispatches on `decision["action"]` (the semantic capability id) instead of
`decision["tool"]` (the raw binary name) — `lab.lab_dispatch`'s fn_name
routing is action-keyed, so dispatching on `tool` silently fell through to
the synthetic catch-all the moment any capability had a declared tool; (2)
`lab.py`'s `run_nmap_scan`/`nmap` fixed port list only covered AD-lab ports
and missed the WEB target's own vulhub ports (6379/8081/8983) — perception
never discovered those services even though they're live.

**Not fixed here** (deliberately out of scope for a bounded "close the loop"
task): the ranker's tool-first-then-capability selection order in
`portal/platform/agent/decide.py`/`rank.py`. That module is
discipline-agnostic platform code shared by every future agent-loop consumer
(security is only the first), so changing its selection algorithm needs its
own design pass — a "prefer exploit-phase / oracle-bearing capabilities once
recon has already observed the relevant port" policy, or a no-repeat memory
of already-attempted (capability, target) pairs — rather than a
security-scoped patch. Until fixed, a live emergent run against a target
whose exploit-phase capabilities require ports already open in the first
perception pass will halt at I4 before ever attempting the exploit.
<!-- /WIKI:GENERATED -->

---

### V8 Catalog Deferred (insufficient hardware)

<!-- WIKI:GENERATED unit=unit-known-limitations-v8-catalog-deferred-insufficient-hardware -->
| Model | Est Size | Reason Deferred |
|-------|----------|-----------------|
| `sjakek/Nex-N2-Pro` | ~230GB | 397B total, 17B active — far exceeds 64 GB even at Q1. |
| `DeepSeek-R1-0528` (full) | ~400GB | 671B full model. 8B distill variant added (V8 bench-r1-0528-qwen3-8b). |
| `Harness-1` (full capability) | n/a | Requires Chroma vector DB + external search state harness. Standalone model (gpt-oss-20B fine-tune) added to V8 bench-harness1. |

*Last updated: 2026-06-10*
<!-- /WIKI:GENERATED -->

---

### Wan 2.2 fp8_scaled Checkpoints Crash on Apple Silicon MPS (Video Generation Shelved)

<!-- WIKI:GENERATED unit=unit-known-limitations-wan22-fp8-scaled-checkpoints-crash-on-apple-silicon-mps -->
- **Description**: Every Wan 2.2 ComfyUI checkpoint published as `*_fp8_scaled.safetensors` (Comfy-Org/Wan_2.2_ComfyUI_Repackaged) crashes at inference time on this host's Apple Silicon MPS + PyTorch 2.13 + comfy_kitchen stack with `RuntimeError: Undefined type Float8_e4m3fn`, thrown from `comfy_kitchen/backends/eager/quantization.py`'s `dequantize_per_tensor_fp8` when it calls `.to(dtype=torch.float8_e4m3fn)`. Confirmed live 2026-07-29 against both `wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors` / `wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors` (T2V-A14B) and `wan2.2_s2v_14B_fp8_scaled.safetensors` (S2V-14B), each with all three `UNETLoader` `weight_dtype` options (`default`, `fp8_e4m3fn`, `fp8_e4m3fn_fast`) — same failure every time, ~5-16s into execution (model-load/first-linear-layer, not deep into sampling). `wan2.2_ti2v_5B_fp16.safetensors` (TI2V-5B) is unaffected because it is full fp16, not fp8-quantized — it generated successfully end to end (`portal_ti2v__00001_.mp4`, verified valid H.264/1024x576/8fps/5.125s).
- **Impact**: T2V-A14B and S2V-14B are unusable on this hardware via their `_fp8_scaled` checkpoints. The only working alternative is full fp16/bf16 (`wan2.2_t2v_{high,low}_noise_14B_fp16.safetensors` ~28.6GB each, `wan2.2_s2v_14B_bf16.safetensors` ~32.6GB — roughly 90GB combined, against this project's usual quantized-only model policy; this is a genuine hardware blocker rather than a quality tradeoff, but was not pursued — see Decision below). `video_mcp.py`'s `_WAN22_T2V_A14B_WORKFLOW` was also independently found to be architecturally wrong before this — it assumed a single merged checkpoint file that never existed in any maintained repo; fixed to the real two-expert MoE graph (two `UNETLoader` + two chained `KSamplerAdvanced`, node IDs matching ComfyUI's official `text_to_video_wan22_14B.json` reference workflow) in the same session, independent of the fp8 finding.
- **Decision (2026-07-29)**: Video generation is shelved for this project — Portal 5 will only operate ComfyUI **image** generation (flux/sdxl via `mcp-comfyui`), not video (`mcp-video`). The `mcp-video` container was stopped (`docker compose stop mcp-video`); it is not part of the default `./launch.sh up` set (already `profiles: [comfyui]` gated) and will not be restarted as part of normal operation. The video workflow code (TI2V-5B working, T2V-A14B workflow now architecturally correct but fp8-blocked, S2V-14B same fp8 block, Animate-14B stubbed) is left in place — designed, not deleted — in case Ollama/PyTorch/comfy_kitchen MPS support for fp8 improves later, but nothing video-related should be treated as in operation.
- **Mitigation**: None pursued. If video generation is revisited: (1) check whether a newer PyTorch/comfy_kitchen release fixes MPS float8_e4m3fn support before re-attempting fp8_scaled checkpoints, (2) if not, the fp16/bf16 download is the fallback, sized above.
- **Cleanup (2026-07-29)**: The confirmed-broken `_fp8_scaled` files (`wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors`, `wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors`, `wan2.2_s2v_14B_fp8_scaled.safetensors`, plus the S2V-only `wav2vec2_large_english_fp16.safetensors` audio encoder) were deleted from `~/ComfyUI/models/` to reclaim ~42GB — dead weight with no path to working given the shelving decision. `wan2.2_ti2v_5B_fp16.safetensors` (works) and the shared `wan2.2_vae.safetensors`/`umt5_xxl_fp8_e4m3fn_scaled.safetensors` (also used by working TI2V-5B, so proven fine — the crash is specific to the diffusion-model UNETLoader path, not every fp8-named file) were kept.
<!-- /WIKI:GENERATED -->

---

### Qwen-Image Is Memory-Safe But Produces Black Output on This Apple Silicon MPS Host

<!-- WIKI:GENERATED unit=unit-known-limitations-qwen-image-bf16-crashes-on-apple-silicon-mps -->
- **Description**: The Qwen-Image-2512 bf16 checkpoint pair (`qwen_image_2512_bf16.safetensors` 40.8GB + `qwen_2.5_vl_7b.safetensors` 16.6GB text encoder = 57.4GB static weights) crashed and rebooted this host outright on the first live `generate_image` attempt (2026-07-29) — not a graceful error, a full machine reboot (uptime reset to minutes). This is a different failure mode from the Wan2.2 `_fp8_scaled` dtype crash (`unit-known-limitations-wan22-fp8-scaled-checkpoints-crash-on-apple-silicon-mps`) — that one was a comfy_kitchen dequant `RuntimeError`, specific to `_scaled` quantized-tensor storage. This one is a memory-exhaustion crash with a *conventional*, unquantized dtype; the root cause is host memory pressure, not a PyTorch/MPS dtype bug.
- **Root cause (two parts)**: (1) 57.4GB of static weights left almost no headroom on a 64GB unified-memory machine. (2) This host's baseline usage before ComfyUI even loads a model is much higher than "64GB total" suggests: Docker Desktop's VM (`Virtualization.framework`, ~22GB RSS) and whatever Ollama models happen to be loaded (observed: two models, 10.1GB + 16.7GB = 26.8GB) routinely consume ~40-50GB before any image-generation job starts. Actual free RAM at the time of the crash was ~20.5GB — nowhere close to 57.4GB.
- **Why admission control didn't catch it**: `portal/modules/media/tools/_admission.py`'s `admit()` (`TASK_VRAM_ADMISSION_V1`, built specifically to refuse jobs before they OOM the host) had no `MEDIA_MODEL_MEMORY_GB` entry for any `qwen-image-*` model. Unknown models fall through to `MEMORY_UNKNOWN_DEFAULT_GB` (16GB) — `16 + 4 (headroom) = 20GB needed <= ~20.5GB free` passed the check, then the real 57.4GB load blew through everything. The gate existed and was correctly designed; it just had a missing data point for a newly-added model family. Fixed by adding real entries (see below) — this is the durable fix, not a one-off workaround.
- **Fix applied (2026-07-29)**:
  1. `QWEN_IMAGE_MODEL`'s default (`portal/modules/media/tools/comfyui_mcp.py`) switched from `qwen_image_2512_bf16.safetensors` to the plain (non-`_scaled`) `qwen_image_fp8_e4m3fn.safetensors` (~20.4GB, half the bf16 size) — this is NOT the same code path that crashed on Wan2.2; plain fp8 storage (no comfy_kitchen quantized-tensor wrapper) doesn't hit the `Float8_e4m3fn` dequant bug. Combined with the shared bf16 text encoder (16.6GB) and VAE (0.25GB): ~37.3GB static, a materially safer margin.
  2. `MEDIA_MODEL_MEMORY_GB` (both copies — `_admission.py` and `portal/platform/wiki/adapters/seed_facts.py`'s `unit-fact-media-memory-budget`, kept in manual sync per Rule 3) now has real entries: `comfyui:qwen-image-2512` = 45.0GB (fp8 static + margin), `comfyui:qwen-image-2512-lightning` = 46.0GB (same weights + LoRA), `comfyui:qwen-image-edit-2511` = 68.0GB.
  3. `qwen-image-edit-2511` is **left on bf16** (57.7GB static, same risk class as what crashed) — the Comfy-Org repo only offers exotic quantizations for this specific model version (`fp8mixed`, `int8_convrot`), neither attempted after the crash. Its 68GB estimate is deliberately set high enough that admission control refuses it under normal free-memory conditions on this host, rather than leaving it under-estimated waiting to crash again. A smaller verified-safe variant is open work.
  4. Added `tests/unit/test_media_admission.py::TestMediaModelMemoryDictInSyncWithWikiFact` — the two `MEDIA_MODEL_MEMORY_GB` copies had no automated drift check before this incident, despite the existing code's own docstring acknowledging the duplication risk.
- **Verification (2026-07-29)**: Confirmed the fp8 file downloaded correctly and the `split_files/<type>/` prefix was flattened (same bug class as `unit-known-limitations-comfyui-model-download-commands-are-broken`). Confirmed the admission gate works as designed: with Ollama models unloaded, `generate_image(model="qwen-image-2512")` was correctly **refused** by `admit()` when short on free RAM. Switched the text encoder default to the `_scaled` fp8 variant too (`qwen_2.5_vl_7b_fp8_scaled.safetensors`, 9.4GB vs 16.6GB bf16) after confirming — matching the TI2V-5B precedent (its `umt5_xxl_fp8_e4m3fn_scaled.safetensors` clip loads fine; the `_scaled` dequant crash is UNETLoader/diffusion-path-specific, not universal) — an isolated CLIPLoader-only test loaded and unloaded cleanly with no crash. Combined static weights dropped from 57.4GB (bf16 pair) to ~30GB (fp8 diffusion + fp8_scaled text encoder), estimate updated to 38GB (down from 45GB).
- **The memory-crash fix IS verified: with enough freed RAM (Ollama models unloaded, ~42GB free), a full `qwen-image-2512` generation ran to completion at 1024x1024/20 steps — model load, 20-step sampling, VAE decode, and file save all completed without incident, RAM never dropped below ~10GB free, no crash.** This proves the fp8+fp8_scaled combination is memory-safe on this host.
- **A second, separate, unresolved bug was found during this verification: the output image is not usable — every pixel is exactly (0,0,0), fully black, not just dark.** Isolated via a sequence of fast low-resolution (256x256) reproductions: (1) reproduces at 4 steps and 20 steps alike (rules out under-sampling); (2) reproduces using the *exact verbatim* official `qwen_image_basic_example.png` embedded workflow JSON, not just this project's hand-built graph (rules out a wiring/parameter mistake in `comfyui_mcp.py`); (3) reproduces with the text encoder swapped back to bf16, diffusion model still fp8 (rules out the `_scaled` text encoder as the cause). One diagnostic data point worth following up: an isolated `VAELoader` -> `EmptySD3LatentImage` -> `VAEDecode` test (no diffusion model in the graph at all) threw `IndexError: tuple index out of range` inside `comfy/sd.py`'s `memory_used_decode` — its shape-indexing code (`shape[3] * shape[4]`) expects a 5-dimensional (video-style, temporal-axis-included) latent tensor. ComfyUI's startup log confirms Qwen-Image's VAE loads as `WanVAE` internally (shared class with the Wan video pipeline, per `comfy/sd.py`'s architecture detection) — the full pipeline (with `KSampler` in between) does not throw this same error, so whatever `KSampler`/`ModelSamplingAuraFlow` outputs must already be shaped 5D-compatibly, but the VAE decode step is the strongest remaining suspect for where the values go to zero on this MPS backend specifically (a `WanVAE`-class decode path CUDA/MPS numerical divergence, not something fixable by checkpoint choice — this reproduced identically with both fp8_scaled and bf16 text encoders, so it's not a quantization issue at all). Not root-caused further this session — this needs either a working reference generation on non-Apple-Silicon hardware to compare intermediate tensor values against, or a deeper trace through ComfyUI's WanVAE decode implementation than is practical mid-session.
- **Current state**: `qwen-image-2512`/`qwen-image-2512-lightning` are memory-safe (verified, no crash risk) but **not usable** — every completed run produces a solid-black image regardless of quantization choice. Do not report this model as "working" to a user; the admission-control fix and the black-output bug are two independent problems, and only the first is resolved.
- **Mitigation for future large media models on this host**: Before adding any new `MEDIA_MODEL_MEMORY_GB` entry, check actual free RAM via `/system_stats` (not total RAM) and account for Docker's VM + any Ollama models likely to be loaded concurrently — do not size against the nominal 64GB. Prefer fp8 (non-`_scaled`) or other non-scaled-quantization checkpoints over bf16 where available; verify the specific `_scaled` dequant bug doesn't apply before assuming a smaller file is safe.
<!-- /WIKI:GENERATED -->

---
