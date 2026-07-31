# Known Limitations

<!-- WIKI:GENERATED unit=unit-known-limitations-known-limitations -->
Canonical limitation register. Each entry carries its own current status:
unresolved entries define active constraints, while resolved, retired, or
shelved entries preserve the decision and evidence that prevent the same issue
from being rediscovered or reintroduced. The status inside an entry is
authoritative; presence in this register alone does not mean the issue is open.

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
- **Status**: RESOLVED 2026-07-31 for catalog coverage and SPL content.
- **Reconciliation**: The original limitation described seven scenarios and
  target `10.10.11.10`. The current spine identifies vmid 113 at
  `10.10.11.13`, and the repository had already expanded to 21 `meta3_*`
  scenarios plus Windows-aware SPL variants for `T1059`, `T1548.001`,
  `T1068`, `T1210`, `T1021.002`, and IIS-aware `T1190`. Those landed changes
  made most of the old open list stale.
- **Scenario completion**: Cross-checking the current 21-scenario catalog
  against Rapid7's Metasploitable3 vulnerability wiki left three documented
  Windows surfaces. `meta3_phpmyadmin_rce` now covers CVE-2013-3238 on 8585
  with Metasploit's canonical `exploit/multi/http/phpmyadmin_preg_replace`
  module and blank root credential;
  `meta3_rails_console_rce` covers CVE-2015-3224 on 3000 with the exact
  `exploit/multi/http/rails_web_console_v2_code_exec` module after a bounded
  exposed-console preflight; and
  `meta3_rdp_standard_auth` covers RDP on 3389 with a non-interactive standard
  credential check. The catalog now has 24 scenarios.
- **Legacy correction**: Four historical entries had been copied from a Linux
  target even though `_LAB_META3` is Windows. FTP no longer attempts the
  vsftpd port-6200 backdoor, MySQL no longer loads `udf.so`,
  `meta3_linux_privesc` performs bounded Windows token inspection while
  retaining its ID for result compatibility, and `meta3_full_chain` no longer
  reads `/etc`, searches SUID files, or uses a Unix shell technique. Regression
  coverage rejects those Linux-only payload markers anywhere in the meta3
  catalog.
- **SPL completion**: The existing OS-aware variants are retained, and
  `T1021.001` now adds the missing Windows RDP signature
  (`EventCode=4624`, `LogonType=10`). `T1557` was also hardened separately:
  generic 4624 volume is no longer enough; its rule requires correlated NTLM
  network logons and privileged-share access across multiple targets.
- **Validation**: The focused scenario, SPL-variant, and corpus suites pass.
  The attack image now installs `metasploit-framework`, fails its build if
  `msfconsole` or either required module is absent, and records all three
  capabilities in its image manifest. A fresh image build and load into the
  lab's DinD runtime reported Framework 6.4.146-dev, true manifest entries,
  and successfully loaded both modules with their expected option sets.
  The sandbox now also injects the Meta3 target and credential contract into
  each lab-exec container; the FTP and RDP scenarios consume those variables
  instead of embedding credentials in commands.
  The follow-up image audit expanded this from three Meta3 checks to an
  authoritative lab-exercise contract. WebDAV, GraphQL, Nuclei, relay proxy,
  SNMP, and SSH helpers are now hard image requirements; smuggler and ysoserial
  support files are pinned. The Windows FTP, MySQL, and full-compromise
  `EXEC_SEQUENCES` were reconciled with their scenario contracts, and stale
  target-local Windows commands were moved behind remote-capable clients.
  `nxc rdp` remains installed for the non-interactive RDP check. Metasploit is
  available to these explicit, bounded scenario steps; it remains deliberately
  excluded from the emergent objective loop's read-only binary allowlist.
  New exploit scenarios are catalog/test verified but have not been fired
  against vmid 113 in this change set; the VM's documented instability still
  requires bounded live runs and recovery planning before such execution.
<!-- /WIKI:GENERATED -->

---

### RBP Benign-Corpus Breadth and Alert Fatigue

<!-- WIKI:GENERATED unit=unit-known-limitations-rbp-benign-corpus-alert-fatigue -->
- **ID**: P5-SEC-BENIGN-CORPUS-001
- **Status**: RESOLVED 2026-07-30 for the representative corpus.
- **Former issue**: The 2026-07-26 six-cell closeout stayed silent on only 2/6
  benign cases and emitted four `ANOMALOUS_UNCLASSIFIED` notifications:
  notification precision 33.3% and false-flag rate 66.7%.
- **Expansion**: The live negative corpus now contains twelve cells, balanced
  at four each for `windows:security`, `web:access`, and `linux:auditd`.
  Added cases cover approved scheduled-task maintenance, SCCM/WMI inventory,
  QA link checking, mTLS deployment automation, change-ticketed service
  restart, and Kubernetes CSI `nsenter`/mount reconciliation. They use the same
  HEC/index/sourcetype/provenance shape as attack corpus records, while the
  benign answer key remains outside model-visible telemetry.
- **Root cause**: Before grounding, the expanded run scored 8/12 correct
  silences, two honest anomaly false flags, and two confident wrong confirms.
  All four misses treated the mere occurrence of a dual-use ATT&CK-shaped
  primitive as malicious while ignoring explicit operational context in the
  cited record.
- **Resolution**: Shared Hunter, Expert, merged-role, and barrier-tool verdict
  contracts now require evidence of adversarial or unauthorized use in
  addition to a dual-use primitive. Change tickets, known automation/service
  identities, vendor paths, mTLS, purpose-specific agents, and coherent
  completion sequences are material counter-evidence. They are not automatic
  allow rules: an unexplained deviation or contradiction still escalates.
- **Measured proof**: The final live checkpoint produced 12/12
  `RULED_OUT`, notification precision 100%, false-flag rate 0%, zero anomaly
  flags, and zero confident wrong confirms. The full pre-grounding checkpoint
  is retained byte-for-byte for comparison.
- **Attack regression**: A fresh strong-arm replay notified on 4/5 previously
  model-visible attack cells. The non-notify was T1557 evidence containing only
  EventCode 4624 counts; its old notification depended on an invented
  EventCode 4738 and an incorrect technique description. This exposes the
  threshold-only T1557 SPL as weak evidence for the later Windows-aware SPL
  item rather than justifying a hallucinated alert.
- **T1557 follow-through (2026-07-31)**: The threshold-only rule is retired.
  The Windows rule now requires correlated NTLM network logons and privileged
  ADMIN$/C$ share access from the same source/account across more than one
  target. The old 4624-only cell is removed from the curated attack corpus,
  and the blue evidence mapper no longer treats one generic 4624 marker as
  sufficient T1557 coverage.
- **Boundary**: Twelve plausibly confusable cells remain a representative
  subset, not an exhaustive estimate of normal enterprise behavior. Broader
  hosts, identities, time windows, applications, and routine workflows remain
  unmeasured; any future NOTIFY on benign activity remains a false flag.
<!-- /WIKI:GENERATED -->

### ComfyUI Runs Outside Docker

<!-- WIKI:GENERATED unit=unit-known-limitations-comfyui-runs-outside-docker -->
- **Description**: ComfyUI runs on the host (not in Docker) to access MPS/CUDA directly. This is required for supported image-generation performance; video operation is shelved.
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

### Legacy ComfyUI Model Download Command Is Retired

<!-- WIKI:GENERATED unit=unit-known-limitations-comfyui-model-download-commands-are-broken -->
- **Description**: The legacy `./launch.sh download-comfyui-models` command no longer downloads models because its monolithic script was deleted in commit `ea864cf`; the handler now exits with a clear pointer to the family-specific commands.
- **Resolution (2026-07-29)**: `pull-qwen-image` and `pull-wan22` both have real handlers. `pull-qwen-image` now downloads the exact image checkpoints verified on Apple Silicon MPS: Qwen-Image-2512 plain FP8, Qwen-Image-Edit-2509 plain FP8, the shared text encoder/VAE, and the Lightning LoRA. Video generation remains shelved even though its archival pull command exists.
- **Remaining impact**: Operators must use the explicit family command instead of the retired alias. Separately, `flux-uncensored` still has no known working checkpoint source.
- **Operator action**: Run `./launch.sh pull-qwen-image` for the supported image set. Do not treat `pull-wan22` as enabling video operation; see `unit-known-limitations-wan22-fp8-scaled-checkpoints-crash-on-apple-silicon-mps`.
<!-- /WIKI:GENERATED -->

---

### ComfyUI Cross-Model-Family Memory Exhaustion (Apple Silicon)

<!-- WIKI:GENERATED unit=unit-known-limitations-comfyui-cross-model-family-memory-exhaustion-apple-silicon -->
- **Description**: ComfyUI on MPS does not reliably evict a previously-loaded model's weights when a new workflow loads a different model family in the same long-running process. Observed live during Slice P: Flux (~22GB) followed by a Wan2.1-NSFW 14B video job (~39GB) in the same process, without a restart between them, drove swap to 66.7GB/67.6GB used and locked up the system (not just RAM pressure — genuine swap-thrashing). Recurred a second time during Slice 7's own live verification: a *tiny* wan21-nsfw job (9 frames, 5 steps) still crashed free RAM from ~45GB to ~60MB — the 14B backend's real peak usage (diffusion activation/buffer overhead) runs well above its static on-disk weight size (~39GB) regardless of frame count, close to the entire 64GB pool.
- **Impact**: Chaining image generation and large video generation (or switching between very different video model families) without restarting ComfyUI in between risks a full system lockup on 64GB unified-memory Apple Silicon hardware. The wan21-nsfw backend specifically should be treated as needing the *whole* machine, not just its weight size.
- **Mitigation**: Tier 0 (`unit-fact-media-memory-budget`) and Tier 1 (`portal/modules/media/tools/_admission.py`, `admit()`) pre-flight admission control landed in `TASK_VRAM_ADMISSION_V1` (Slice 7) — wan21-nsfw's estimate is set to 55GB (not the 39GB weight size) to reflect the observed real peak. Restart ComfyUI between large model-family switches regardless: `launchctl kickstart -k gui/$(id -u)/com.portal5.comfyui`. Tier 2 (shared cross-engine broker with Ollama) is explicitly not built — see the task's `[GATE: SCOPE]`.
<!-- /WIKI:GENERATED -->

---

### `pytest portal` Write-Through Test Artifacts (Resolved)

<!-- WIKI:GENERATED unit=unit-known-limitations-pytest-portal-leaves-real-write-through-test-artifacts -->
- **Status**: RESOLVED 2026-07-29.
- **Former issue**: Security module tests could write journals and checkpoints
  into the real runtime tree.
- **Resolution**: An autouse fixture redirects `JOURNAL_DIR`, `RESULTS_DIR`, and
  `CHECKPOINT_DIR` into each test's `tmp_path`. The production modules also
  stopped creating those directories merely by being imported; write
  functions create their destination lazily.
- **Regression coverage**: `test_write_isolation.py` writes both artifact types
  and asserts that their parents are the fixture sandbox.
<!-- /WIKI:GENERATED -->

---

### Emergent Objective Loop — Curated Capability Tool Names vs Live-Dispatch Whitelist

<!-- WIKI:GENERATED unit=unit-known-limitations-emergent-objective-loop-curated-capability-tool-names-vs-live-dispatch-whitelist -->
- **ID**: P5-EMERGENT-001
- **Status**: RESOLVED 2026-07-31 for the live emergent dispatch boundary. Verified read-only binaries can dispatch; unbound and stateful/destructive capabilities cannot enter a live trajectory.
- **Description**: `capability/index.py`'s curated Capability library (used by `capability.query()` and now the emergent objective loop, `TASK_EMERGENT_SLICE1_PERCEPTION_ENTRY_V1`) has two kinds of `tools` values for many entries — real Kali binary names (`nmap`, `impacket-secretsdump`, `bloodhound-ce-python`, ...) for domain-probe capabilities (`smb_probe`, `ldap_probe`, ...), or an **empty list** for several named-technique capabilities (`ad-certificate-abuse`, `kerberos-delegation`, `oauth-oidc-chain`, `file-upload-bypass`, `smb-enumeration`, and others). `lab.py::_lab_dispatch_inner`'s real live-dispatch path only recognizes a small fixed whitelist of ~15 literal tool names — neither the Kali binary names nor the empty-tools capability IDs originally matched that whitelist, so `SecurityExecutor` (Slice 1.2) dispatched them through the synthetic fallback even when the lab was fully live and reachable. A second, compounding cause was found the same day: `capability.query()`'s `applies_when` predicates (e.g. `smb_probe` requires `open_ports` to contain 445) are gated on a flat `observations["open_ports"]` list that predates `LabPerception` — `PerceptionDelta.to_observation()` didn't populate it, and `run_emergent_engagement` started with `observations={}` (no upfront perception call), so on a cold start every real-tooled AD-probe capability was starved out and only the empty-`tools` capabilities (which have no `applies_when` gate) ever matched.
- **Fixes landed** (all live-verified against the real Proxmox lab, portal-lab-dc01/srv01/vulhub, sandbox MCP `lab_exec_active:true`):
  1. `--domain-hint` threaded into `run_emergent_engagement`/CLI (was hardcoded `None`).
  2. `lab.py::_lab_dispatch_inner` now aliases the two real Kali binary names verified correct: `"nmap"` → same path as `run_nmap_scan` (confirmed real: 22/80/8080 open on `10.10.11.50`), `"impacket-GetUserSPNs"` → same path as `exploit_service`/Kerberoast (confirmed real: 3 live TGS hashes captured from `lab-srv01.portal.lab`, then a real offline `john`+rockyou.txt crack attempt inside the sandbox — 0/3 cracked, correctly scored `FAILED` not `PROVEN`, since the passwords aren't in the common wordlist).
  3. `PerceptionDelta.to_observation()` now also derives a flat `open_ports` list (`perception._extract_open_ports`, additive) from either shape the real prober can return, and `run_emergent_engagement` gained a `perception` param that seeds real initial observations before the loop starts (`goal_cli._cmd_emergent` wires this by default via the new shared `perception.default_lab_prober`, replacing a near-duplicate that used to live only in `security_mcp.py`). Confirmed live: after this fix the ranker's first pick against the AD domain moved from an empty-`tools` capability (`ad-certificate-abuse`) to a real-tooled one (`smb_probe`/`ldap_probe`'s `bloodhound-ce-python`) — proving the seed closes the starvation and motivating the audited allowlist in item 5.
  4. The platform deterministic fallback now chooses a capability before ranking that capability's tools, consumes both supported history shapes, avoids already-attempted actions while alternatives remain, starts with a recon capability, and progresses to an unattempted oracle-bound action after recon. This fixes the structural dead-end where an empty-`tools` oracle capability could never be selected whenever any other candidate declared a tool.
  5. `SecurityExecutor` now honors the ranker's selected binary only through one explicit read-only allowlist: `nmap`, `impacket-GetUserSPNs`, `bloodhound-ce-python`, `enum4linux-ng`, `nxc`, and `impacket-GetNPUsers`. The four new aliases use the previously live-audited command shapes: BloodHound `DCOnly` collection, `enum4linux-ng -A`, anonymous NetExec SMB share enumeration, and a GetNPUsers check bounded to the two known lab accounts. Every non-allowlisted selection retains the semantic capability probe. Regression coverage proves `curl`, Certipy, secretsdump, psexec, wmiexec, Responder, and Metasploit cannot override that fallback.
  6. The live `_SecurityCapabilityProvider` now queries with `live_dispatchable_only=True`. That retains semantic service probes (including probes whose catalog `tools` list is empty but whose action has a concrete `lab.py` route) and retires every unbound challenge-class/lab-target entry from live selection. Catalog queries and dry-run planning remain unchanged. The five named empty-tool examples can no longer produce synthetic live steps.
- **Intentional exclusions**: Stateful/destructive or otherwise unaudited binaries (`impacket-secretsdump`, `impacket-psexec`, `impacket-wmiexec`, `responder`, `impacket-dacledit`, `certipy-ad`, `ldap3`, `metasploit`) remain deliberately unaliased. Unbound challenge-class and lab-target capabilities remain visible in the catalog and dry-run planner but are not live-dispatchable.
- **Residual boundary**: The live emergent loop can now perform honest reconnaissance but will not advance into an exploit capability until that capability receives a separately audited executor binding. It may therefore halt blocked after exhausting applicable probes. That is the intended truthful behavior: no synthetic exploit is represented as live progress, and future capability expansion must land with its dispatch and rollback contract.
- **Resolution**: The selected-binary path is explicit and allowlisted, unsafe selections retain safe action-level fallback, and capabilities with no concrete live binding are retired from the live provider. Synthetic steps remain excluded from `emergent_gaps.gaps_from_trajectory`, and synthetic-derived trajectories can never be PROVEN (AX ratchet).
- **Live completion checkpoint (2026-07-31)**: A bounded one-action AD
  emergent verification seeded fresh perception against `10.10.11.21`,
  observed ports 53/80/88/135/389/445/464/636/3268, and deterministically
  selected `smb_probe` with `bloodhound-ce-python`. `SecurityExecutor`
  dispatched the selected allowlisted binary. The `DCOnly` collection
  completed successfully and returned 13 users, 53 groups, 3 computers, 2
  GPOs, 5 OUs, and 0 trusts before compressing the sandbox-local output.
- **Safety finding**: `certipy-ad find` is not read-only in this lab; it
  started/used the Windows Remote Registry dependency while retrieving CA
  configuration. DFS and Remote Registry were returned to their observed
  running state after the probe. Keep Certipy out of the safe allowlist.
  `impacket-secretsdump`, `impacket-psexec`, `impacket-wmiexec`,
  `impacket-dacledit`, `responder`, and `metasploit` also remain deferred
  because they dump credentials, execute remotely, modify ACLs, poison
  traffic, or select arbitrary exploit modules.
- **Future extension rule**: A retired capability may return to live emergent
  selection only with a separately audited semantic executor binding. Keep
  the stateful/destructive tool set out of the allowlist unless a future task
  explicitly defines containment, rollback, and live-verification
  requirements for that tool.
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

### Security Bench Import Mutated Host Environment (Resolved)

<!-- WIKI:GENERATED unit=unit-known-limitations-importing-the-security-bench-module-sets-a-linux-only-prometheus-multiproc-dir-host-side -->
- **ID**: P5-ENV-MULTIPROC-HOSTLEAK-001
- **Status**: RESOLVED 2026-07-29.
- **Former issue**: importing the security data module transitively loaded
  `.env` into process-global `os.environ`, including the container-only
  `PROMETHEUS_MULTIPROC_DIR=/dev/shm/portal_metrics` value.
- **Resolution**: the security data module, lab-exec benchmark, and shared
  benchmark config now parse dotenv into private mappings. Explicit process
  environment still wins, but imports do not add or alter environment keys.
- **Regression coverage**: a clean subprocess deliberately removes
  `UNIT_TEST_MODE` and `PROMETHEUS_MULTIPROC_DIR`, imports the security data
  module, and verifies that no environment key was added or changed.
<!-- /WIKI:GENERATED -->

---

### POST /v1/messages Null Success Body (Resolved)

<!-- WIKI:GENERATED unit=unit-known-limitations-post-v1-messages-anthropic-compat-endpoint-returns-http-200-with-a-null-body -->
- **ID**: P5-ANTHROPIC-COMPAT-001
- **Status**: RESOLVED 2026-07-29.
- **Former issue**: The non-streaming success path completed after checking the
  loopback response status but never returned the translated response, so
  FastAPI serialized Python `None` as `null`.
- **Resolution**: The handler now returns
  `openai_response_to_anthropic(resp.json(), model_id)` on HTTP 200. Error
  propagation and the streaming translation path are unchanged.
- **Regression coverage**: The endpoint test exercises the ASGI loopback and
  asserts the complete Anthropic Messages response shape, content, stop reason,
  model, and token usage.
- **Discovered**: 2026-07-13, live-verifying `DESIGN_OPENCODE_ADDRESSING_V1.md`'s
  Step 3e CLI-contract migration (`cc-local.sh`'s default model rename).
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

### Request-Size Cap Relied on Content-Length Only (Resolved)

<!-- WIKI:GENERATED unit=unit-known-limitations-request-size-cap-relies-on-content-length-only -->
- **ID**: P5-REQ-SIZE-001
- **Status**: RESOLVED 2026-07-29.
- **Former issue**: The pipeline enforced its 4 MB cap only through
  `Content-Length`, so chunked transfer encoding bypassed the limit.
- **Resolution**: `RequestBodyLimitMiddleware` buffers and bounds the two JSON
  inference endpoints before route handling, enforcing the same limit against
  declared and streamed/chunked bodies. Oversize requests return 413 before
  the handler runs.
- **Regression coverage**: `tests/unit/test_request_limits.py` sends a chunked
  async body with no usable `Content-Length` and verifies rejection.
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
- **2026-07-30 mitigation proof**: A benign-corpus replay demonstrated the
  operational consequence on current Ollama: raw `granite4.1:30b` loaded at
  131,072 tokens and about 91 GB, while raw `granite4.1:8b` loaded at 131,072
  tokens and about 51 GB. The security evaluation workspaces now use baked
  `granite4.1:30b-ctx16k` and `granite4.1:8b-ctx8k` tags and explicit workspace
  IDs. Live pipeline route-identity probes returned those exact tags; Ollama
  reported contexts 16,384 and 8,192 respectively. This mitigates these
  operated workspaces but does not resolve the general `/v1` limitation.

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

### P5-EMERGENT-002 — Deterministic capability progression (Resolved)

<!-- WIKI:GENERATED unit=unit-known-limitations-p5-emergent-002-deterministic-capability-ranker-can-t-reach-oracle-bearing-capabilities-once-any-tool-declaring-recon-capability-is-a-candidate -->
**Status:** RESOLVED 2026-07-29.

Found live during `TASK_SECURITY_ARM_CLOSE_LOOP_V1` Phase 8 (`goal emergent`
against `10.10.11.50`, `objective_class=host_foothold`, 2026-07-16). The
deterministic fallback selected a tool before selecting a capability, so any
tool-declaring reconnaissance candidate made `tools=[]` exploit capabilities
with real oracles structurally unreachable. It also ignored action history,
reselected the same reconnaissance action, and eventually hit the I4
no-progress gate.

Two real, separate fixes are already applied in this task's run (both
correctness fixes, not workarounds): (1) `SecurityExecutor.execute` now
dispatches on `decision["action"]` (the semantic capability id) instead of
`decision["tool"]` (the raw binary name) — `lab.lab_dispatch`'s fn_name
routing is action-keyed, so dispatching on `tool` silently fell through to
the synthetic catch-all the moment any capability had a declared tool; (2)
`lab.py`'s `run_nmap_scan`/`nmap` fixed port list only covered AD-lab ports
and missed the WEB target's own vulhub ports (6379/8081/8983) — perception
never discovered those services even though they're live.

The platform-level cause is now fixed in
`portal/platform/agent/decide.py`. The fallback:

1. reads both platform-loop and direct-decision history shapes;
2. selects a grounded capability before ranking tools within it;
3. starts with reconnaissance when appropriate;
4. avoids repeating attempted capabilities while alternatives remain;
5. progresses after reconnaissance to an oracle-bearing or other non-recon
   capability; and
6. can select a grounded `tools=[]` capability directly.

Regression coverage in
`portal/platform/agent/tests/test_agent_core.py` proves initial
reconnaissance, progression to an oracle-bearing action, and direct-history
compatibility. The full local CI mirror and system validator pass. This
resolves the deterministic reachability defect; live target availability and
the separately documented unverified tool-alias gap remain independent
operational constraints.
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

### Qwen-Image Apple Silicon Working Routes and Constraints

<!-- WIKI:GENERATED unit=unit-known-limitations-qwen-image-bf16-crashes-on-apple-silicon-mps -->
- **Memory constraint**: The original Qwen-Image-2512 bf16 diffusion and text-encoder pair needs about 57.4GB of static weights. On this 64GB unified-memory host, Docker and loaded Ollama models can leave far less free memory than the nominal capacity. The first unguarded load exhausted host memory and rebooted the machine.
- **Memory-safe configuration**: `qwen-image-2512` uses `qwen_image_fp8_e4m3fn.safetensors` plus `qwen_2.5_vl_7b_fp8_scaled.safetensors`. Admission estimates are 38GB for the base model and 39GB for Lightning. The duplicate estimates in `_admission.py` and the media-memory wiki fact are protected by a unit test.
- **Black-output root cause and fix**: ComfyUI was launched globally with `--force-fp16`. QwenImage declares only bf16 and float32 as supported inference dtypes, but the global override bypassed that selection. A diagnostic `SaveLatent` showed 16,384/16,384 NaNs before VAE decode, proving that the VAE was not the source of the black image. Removing `--force-fp16` from the generated launcher, launchd plist, and current host launcher restored bf16 compute; the same diagnostic then contained no NaNs.
- **Verification**: A 256×256 base diagnostic produced finite latents and a non-degenerate image. A 512×512 Lightning generation produced a detailed fox-astronaut poster with correctly rendered `PORTAL FIVE` text and full-range RGB output. The required 1024×1024, 20-step base-model proof also completed with a prompt-matching non-degenerate image.
- **Why the isolated VAE test failed**: `EmptySD3LatentImage` alone supplies a four-dimensional latent, while Qwen's WanVAE decode path expects the five-dimensional latent produced by the complete Qwen sampling graph. That shape error does not implicate VAE decode in the black-output failure.
- **Working local edit route**: `qwen-image-edit-2509` uses the official `qwen_image_edit_2509_fp8_e4m3fn.safetensors` checkpoint. A 512×512, 20-step live probe completed in 697.8 seconds and produced a non-degenerate prompt-matching edit. Starting free memory was 44.46GB and the lowest observed value was 10.55GB; the admission estimate is therefore 38GB plus 4GB headroom. Plain FP8 storage expands to bf16 compute but avoids the scaled/mixed dequantization path that fails on MPS.
- **Edit fidelity**: The 2509 probe correctly changed a white astronaut suit to vivid emerald green and preserved the recognizable fox and setting, but reframed the composition and cropped most source text. Treat it as generative instruction editing, not pixel-preserving retouching.
- **Remaining limitation — Qwen-Image-Edit-2511**: The bf16 edit checkpoint is estimated at 60GB, and admission control correctly refuses it even with all ComfyUI models unloaded (53.5GB was the best observed free memory, versus 64GB required with headroom). The two official 20.5GB alternatives remain unusable on this MPS stack: `fp8mixed` fails comfy-kitchen dequantization with `Undefined type Float8_e4m3fn`; `int8_convrot` requires CPU fallback for unsupported MPS `aten::_int_mm` and is operationally too slow. They were removed after 2509 passed and can be re-downloaded if MPS support changes. Use a larger or remote CUDA host for 2511.
- **Serving invariant**: The public 2509 and 2511 names map to their actual checkpoint generations; 2509 is not silently served as 2511. The tool manifest and HTTP dispatch endpoints must retain `image_url` or edit calls cannot reach the workflow.
- **Launcher invariant**: Do not use a global ComfyUI inference-dtype override. Model families declare different supported compute dtypes, and a global fp16 flag can turn an otherwise safe quantized checkpoint into numerically invalid compute.
<!-- /WIKI:GENERATED -->

---

### Spine Code-Surface Coverage Is Partial (Ratchet, Not a Cliff)

<!-- WIKI:GENERATED unit=unit-known-limitations-spine-code-coverage-ratchet -->
- **ID**: P5-SPINE-COVERAGE-001
- **Status**: OPEN — an active problem to pay down, not an accepted steady state. The ratchet
  is a floor that stops it from growing, not a reason to stop working on it.
- **Description**: `validate_system.py` check **BR** (spine code coverage ratchet) measures the
  fraction of eligible Python code surfaces cited by at least one non-aggregate wiki unit.
  At the time this gate landed (v8.0.0), coverage was **7.7%** (47 of 607 eligible files).
  Aggregate `unit-code-*` units (auto-seeded by `seed_code.py`, which cites only the first
  five files of a subsystem while titling itself with the full count) are deliberately
  excluded from the numerator — counting them would grade the generator against its own
  output, the same circularity the doc-generation arc paid for elsewhere.
- **Impact**: The vast majority of the codebase has no unit describing it. The spine's
  single-write-point discipline guarantees the *forward* direction (a unit change
  regenerates its docs); it does not by itself guarantee that new code arrives documented.
- **Mitigation shipped**: The gate is a ratchet, not a cliff. `config/spine_coverage_baseline.yaml`
  pins the current uncovered set; CI (check BR) fails only when that set *grows* — new code
  cannot land with zero coverage unnoticed. This prevents the debt from getting worse; it does
  not pay it down.
- **Current measurement (2026-07-31)**: **14.9%** (91 of 609 eligible files), with 518
  uncovered. The latest continuation added twenty-one exact citations in two
  bounded audits. The security-bench structure and sub-component units now
  cite the ten package, CLI, capability-rendering, goal-evaluation, and
  perception modules their bodies describe. The platform-agent unit now maps
  its seven core modules plus its hermetic regression suite, while the emergent
  resolution unit cites the gap and trajectory-honesty implementations it
  relies on. Meta3's sandbox-environment regression also joined its owning
  limitation unit. The baseline was re-pinned downward after each audit.
- **Next action**: Backfill coverage for the 518 currently-uncovered surfaces (write covering
  units, re-pin the baseline down as each batch lands). Not completed in v8.0.0's release
  window — tracked as ongoing work, not closed out or deprioritized indefinitely.
<!-- /WIKI:GENERATED -->

---

### LLM Router Model Evicted by Single Inference Request (Resolved)

<!-- WIKI:GENERATED unit=unit-known-limitations-router-model-eviction-single-request -->
- **ID**: P5-ROUTER-EVICTION-001
- **Status**: RESOLVED 2026-07-30 — fixed upstream in the supported Ollama line and
  regression-probed on this host.
- **Description**: The LLM intent-router model (`LLM_ROUTER_MODEL`), loaded with
  `keep_alive: -1` specifically to stay pinned in memory (see
  `_warmup_llm_router` in `lifespan.py`), gets evicted by Ollama after exactly
  **one** subsequent completion request to a different inference model —
  reproduced twice in a clean, minimal test: fresh pipeline restart → router
  model confirmed loaded and pinned "Forever" via `ollama ps` → one single
  `/v1/chat/completions` request → `ollama ps` shows only the inference model,
  router gone. Both models were ~5-6GB (≈11GB combined), nowhere near this
  host's 64GB unified memory or a 5-model `OLLAMA_MAX_LOADED_MODELS` cap.
- **Ruled out**: `OLLAMA_MAX_LOADED_MODELS` was found completely absent from
  the actual host-native Ollama service's launchd plist
  (`/Library/LaunchDaemons/com.portal5.ollama.plist`) — the `.env` value only
  ever applied to the unused, optional Dockerized Ollama profile. This was a
  real, separate config gap and has been fixed (plist now sets
  `OLLAMA_MAX_LOADED_MODELS=5` and `OLLAMA_NUM_PARALLEL=4`, matching `.env`).
  **Fixing it did not resolve the eviction** — reproduced again afterward with
  only 2 of 5 slots in use. Not a testing-methodology artifact either: the
  reproduction is a single clean two-step transition (restart, one request),
  not an accumulation of the session's earlier heavy multi-model churn.
- **Impact**: Every real "auto"-routed request pays the LLM router's full
  cold-load latency (2.7-4s observed) rather than the documented ~840ms warm
  figure, because the router is never actually warm when a real request
  arrives — the previous request's inference model always evicted it. This
  is a real, live tax on router accuracy/latency tradeoffs project-wide, and
  a plausible contributing factor (not sole cause) in some of the extreme
  multi-thousand-second "backend instability" retry patterns observed during
  the v8.0.0 UAT sweep on `auto`-prefixed workspaces.
- **Root cause and upstream fix**: Ollama commit
  `9eef4a7195dc8ad246e697a5251a8df344a56880` ("mlx: keep loaded model memory
  resident"), released in `v0.32.4`, configures Metal residency after the MLX
  runner materializes model weights. This directly addresses the missing
  residency behavior suspected in the original finding. A version bisect was
  not performed, but the upstream change and the post-upgrade reproduction
  agree on the failure mechanism.
- **Regression proof**: On the current `v0.32.5` server, a clean
  router-load → `/v1/chat/completions` inference transition left both the
  5.3GB router model and a 5.6GB inference model present in `/api/ps`, each
  fully resident in Metal memory. Repeating through the OpenAI-compatible
  endpoint no longer evicts the router.
- **Repository fix**: Portal's Apple-Silicon launch preflight now treats
  Ollama `v0.32.4` as the supported minimum and warns before launch on older
  servers. The previous `0.30.7+` requirement allowed the known-bad residency
  behavior back into supported deployments.
- **No latency workaround added**: `LLM_ROUTER_TIMEOUT_MS` remains at the
  bench-validated warm-router value. The pipeline does not re-warm after every
  request or silently disable semantic routing; those mitigations would evict
  useful inference models or reduce routing accuracy.
- **2026-07-30 follow-up — the Ollama upgrade was necessary but not
  sufficient**: a live reproduction on this same `v0.32.5` host still evicted
  the router under real `auto`-routed traffic. Root cause was a second,
  distinct bug living in the same file: `_warmup_llm_router` and
  `_warmup_auto_model` (`lifespan.py`) both pin their model with
  `keep_alive: -1` but omitted `options.num_ctx`. Ollama then defaults the
  warmed runner's reserved context to the model's full context window
  multiplied by `OLLAMA_NUM_PARALLEL` slots (`4`) — for the router
  (`gemma-4-E4B`, 131072 max context) that is `131072 x 4 = 524288` tokens of
  reserved KV-cache, tens of GiB, for a 3B-class model. `_warmup_auto_model`
  had the identical gap warming `baronllm:q6_k` (also 131072 max context, no
  Modelfile cap), pinned forever with no cap at all. Either reservation alone
  is large enough to force the scheduler to evict everything else on the next
  model load — this is what reproduced live even after the version fix.
- **Fix**: both warmup calls now set `options.num_ctx` — `2048` for the
  router (matching the real classification call in `_route_with_llm`,
  `routing.py`) and `8192` for the auto-model warmup (matching the `auto`
  workspace's `context_limit`). Regression tests:
  `TestRouterWarmupContext::test_warmup_sets_same_num_ctx_as_routing_call` and
  `::test_auto_model_warmup_caps_num_ctx` in `tests/unit/test_pipeline.py`.
- **Live re-verification**: after rebuilding and restarting
  `portal5-pipeline`, `/api/ps` showed the router (2048 ctx), `baronllm`
  (8192 ctx), and the inference model (8192 ctx) all resident simultaneously
  across three consecutive live `auto`-routed `/v1/chat/completions`
  requests — no eviction.
- **Not isolated — two more sites fixed the same way**:
  `tool_preselect/preselector.py` and `tool_preselect/cli_probe.py` had the
  same missing-`num_ctx` shape (lower severity — `keep_alive: "5m"`
  self-expiring rather than `-1` permanent pin, and `preselector.py` has no
  call sites in the live request path as of this check, per
  `handlers.py`/`non_streaming.py`/`validation.py`). Both now set
  `options.num_ctx` (`4096`) on their `/api/generate` payloads. Regression
  tests: `TestOllamaOutcomes::test_payload_caps_num_ctx` in
  `portal/platform/inference/tool_preselect/tests/test_preselector.py`.
  `cli_probe.py` is operator-invoked only, no automated coverage needed.
<!-- /WIKI:GENERATED -->

---

### Model Narrates a Fake Tool Call Instead of Invoking the Real One (Resolved)

<!-- WIKI:GENERATED unit=unit-known-limitations-narrated-tool-call-instead-of-real-dispatch -->
- **ID**: P5-TOOL-NARRATION-001
- **Status**: RESOLVED 2026-07-30.
- **Description**: Under a multi-tool payload, a tool-capable model sometimes narrates a
  plausible-looking pseudo tool-call in plain text — e.g.
  `<function=execute_python>...</function></tool_call>` (note the mismatched/absent opening
  `<tool_call>` tag) — instead of emitting Ollama's real structured `tool_calls` field. The
  pipeline's `_dispatch_tool_call` (`portal/platform/inference/router/tools.py`) only ever
  reads the model's native `tool_calls` array, so this narrated text passes straight through
  to the user as if it were a normal, successful answer.
- **Reproduced directly** (bypassing the harness/pipeline entirely, isolating the model): the
  same model + prompt + a single-tool payload against Ollama's `/api/chat` succeeds every
  time with a clean `tool_calls` response. The exact same request with the workspace's full
  multi-tool payload (4+ tools) fails intermittently — 4 repeated identical calls: 3 succeeded
  with real `tool_calls`, 1 narrated fake text. This is genuine sampling-driven unreliability
  that worsens with more tools in context, not a wiring or schema bug.
- **Affected UAT cases at v8.0.0**: `T-01`/`T-02`/`T-03` (Code Sandbox exact-execution,
  `auto-coding`, `qwen3-coder`) and the Document Generation family (`T-04`/`T-05`/`T-06`/`WS-10`,
  `auto-documents`, `granite4.1`) both show this pattern — the latter confirmed NOT a document-
  tooling regression (the real `create_word_document` tool works perfectly when dispatched
  directly; see the MCP v2 migration audit) but the same narration-instead-of-dispatch failure
  under retry/backend-instability conditions.
- **Resolution**: The pipeline now recognizes explicit side-effect requests before model
  dispatch. `_select_explicit_required_tool()` maps conservative execution and artifact-creation
  intents to one tool only (Python/Bash/Node execution or Word/Excel/PowerPoint creation), but
  only when that tool is already in the resolved workspace/persona whitelist. Both streaming
  and non-streaming paths then expose only that schema and set `tool_choice=required`.
- **Why this fix**: The direct reproduction proved the same model was reliable with one tool
  and intermittent with the full multi-tool payload. Deterministic narrowing removes the
  ambiguity at its source without buffering the streaming hot path and without forcing tools
  for ordinary code-writing, prose-documentation, or document-reading prompts.
- **Safety boundary**: Client `tool_choice=none`, `portal_no_tools`, and non-matching prompts
  retain their prior behavior. A selected tool must be allow-listed; the selector never grants
  a capability. Unit coverage includes the affected UAT prompt shapes and negative cases.
<!-- /WIKI:GENERATED -->

---
