# Known Limitations

<!-- WIKI:GENERATED unit=unit-known-limitations-known-limitations -->
Canonical limitation register. Each entry carries its own current status: unresolved entries define active constraints, while resolved, retired, or shelved entries preserve the decision and evidence that prevent the same issue from being rediscovered or reintroduced. The status inside an entry is authoritative; presence in this register alone does not mean the issue is open.

`KNOWN_LIMITATIONS.md` is a Tier-1 doc whose blocks are rendered by `portal/platform/wiki/render.py` (`render_all_generated_blocks`): this unit provides the intro paragraph, and each `unit-known-limitations-*` unit provides one section, so the doc stays current as the individual units change without manual editing.

## Why

The register is a rendered view, not an independent ledger, which is the whole point: an operator reads one doc, but every section traces to a unit that can be individually verified and re-grounded against code. Making the status field authoritative per entry keeps resolved issues visible as history while preventing stale entries from being mistaken for open constraints, so a regression cannot quietly reopen a closed problem.
<!-- /WIKI:GENERATED -->

---

### CadQuery and build123d Unusable on linux/arm64

<!-- WIKI:GENERATED unit=unit-known-limitations-cadquery-and-build123d-unusable-on-linux-arm64 -->
- **ID**: P5-CAD-ARM64-001
- **Description**: CadQuery and build123d both require OCP (OpenCASCADE Python bindings), which has no pre-built wheels for `linux/arm64`. `Dockerfile.mcp` documents this: the code-CAD dependency comment states CadQuery/build123d cannot be installed on `linux/arm64` without a source build, so only `trimesh[easy]`, `pyrender`, and `numpy-stl` are installed.
- **Impact**: Python-native parametric CAD (`.box()`, `.extrude()` style) is unavailable inside the MCP containers. The `auto-cad` workspace in `config/portal.yaml` uses OpenSCAD instead, which runs headlessly with no platform restriction, and notes the OCP arm64 limitation in its own description.
- **Mitigation**: Use OpenSCAD via the `render_openscad` tool (exposed by `portal/modules/cad/tools/cad_render_mcp.py`) for parametric geometry. Use `trimesh` for procedural mesh manipulation.
- **Do not re-add** `cadquery` or `build123d` to `Dockerfile.mcp` without first verifying an arm64 wheel exists — the build would silently succeed on x86 CI and fail on this hardware.

## Why

The MCP CAD container must stay buildable on Apple Silicon hosts, and OCP's missing `linux/arm64` wheel makes both libraries a hard build failure there. Choosing OpenSCAD as the primary path keeps parametric geometry available without a multi-hour source compile, and the comment in `Dockerfile.mcp` records the constraint at the exact place a future dependency edit would otherwise ignore it.
<!-- /WIKI:GENERATED -->

---

### Code Sandbox Requires Privileged Container

<!-- WIKI:GENERATED unit=unit-known-limitations-code-sandbox-requires-privileged-container -->
- **ID**: P5-ROAD-SEC-001
- **Description**: The `dind` (Docker-in-Docker) service in `deploy/portal-5/docker-compose.yml` runs with `privileged: true`. Docker-in-Docker cannot function without host kernel capabilities; the compose comment documents that `docker:dind-rootless` needs kernel user-namespace support unavailable in Docker Desktop's LinuxKit VM, so privileged DinD is accepted there. `mcp-sandbox` (port 8914) dispatches code execution through this DinD engine.
- **Impact**: In hardened environments, a compromised sandbox container could potentially escape to the host.
- **Mitigation**: Disable the code sandbox by removing `mcp-sandbox` and `dind` from the compose file, or apply host-level controls (AppArmor/seccomp on the Docker daemon). On bare-metal Linux hosts, the compose comments describe the rootless alternative.

## Why

The isolation boundary on macOS lives in Docker Desktop's LinuxKit VM, so privileged DinD does not add a second escape surface there; on bare-metal Linux the same flag does. Recording the tradeoff inline at the `privileged: true` site keeps the security decision visible to anyone editing the compose file and names the rootless configuration as the Linux escape hatch.
<!-- /WIKI:GENERATED -->

---

### No Built-in Multi-User Rate Limiting

<!-- WIKI:GENERATED unit=unit-known-limitations-no-built-in-multi-user-rate-limiting -->
- **ID**: P5-ROAD-031
- **Description**: There is no per-user rate limiting in the stack. The pipeline's only throttle is request-concurrency limiting in `portal/platform/inference/router/concurrency.py` (`RequestSlot`, `_request_semaphore`, `_workspace_semaphores`), which bounds in-flight conversations per workspace but does not distinguish users; `streaming.py` documents that a slot is held for the entire multi-hop conversation, not per HTTP request. Open WebUI, the multi-user front end, adds no per-user quota of its own. A single user in a multi-user deployment can therefore exhaust server resources.
- **Mitigation**: Deploy behind a reverse proxy (nginx, Traefik) with rate limiting, or use Open WebUI's admin controls for per-user quotas.

## Why

Concurrency slots protect the backend from oversubscription but were never designed to arbitrate between users — they treat every request as equally entitled to a slot. Per-user fairness is a product-level policy that the pipeline deliberately does not guess at, so the boundary is documented: the operator who needs multi-tenant isolation must enforce it at the proxy layer where user identity is actually visible.
<!-- /WIKI:GENERATED -->

---

### Devstral 2509 Upgrade Blocked — Model Not Published

<!-- WIKI:GENERATED unit=unit-known-limitations-devstral-2509-upgrade-blocked-model-not-published -->
- **ID**: P5-BENCH-DEVSTRAL-2509
- **Description**: A Devstral 2509 upgrade is blocked because no such model is registered in the catalog. The bench persona `config/personas/bench_devstral.yaml` is named for the 2507 (July 2025) variant, and both `bench-devstral` and `bench-devstral-small-2` in `config/portal.yaml` pin to `devstral:24b` and `devstral-small-2:latest` respectively — neither `config/backends.yaml` nor the workspaces reference any 2509 tag.
- **Operator action**: Re-run the persona-intent verification when a 2509 model card appears and is registered as a catalog candidate; the MLX-tagged variant named in the original finding is no longer relevant because the MLX inference tier is retired.

## Why

The bench workspaces must not silently promote to a model that was never verified, so the catalog is the gate: a 2509 tag cannot be routed until it exists as a backend model entry and the bench persona is updated to name it. Recording the blocked upgrade preserves the intent while making the blocker mechanical — a missing catalog registration — rather than a stale prose promise.
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
  credential check. The catalog now covers the full documented Windows surface of the target.
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
  `impacket-rdp_check` is runtime-verified for the non-interactive RDP check. Metasploit is
  available to these explicit, bounded scenario steps; it remains deliberately
  excluded from the emergent objective loop's read-only binary allowlist.
  All three added Meta3 scenarios were fired in bounded live runs against vmid
  113 on 2026-07-31 and produced 100%-valid scenario-specific captures. Target
  readiness now discovers DHCP drift by MAC and persistently repairs the Rails
  and vulnerable phpMyAdmin services after clean boots.

## Why

Metasploitable3 is a Windows target, so Linux-shaped scenario payloads and SPL written for Unix hosts were silently wrong against it — the original limitation's open list recorded exactly that drift. Re-grounding the catalog to `config/lab_targets.yaml`'s MAC-verified vmid 113 address and to the actual scenario set in `exec_chain.py` makes the coverage claim checkable, while the hardened SPL in `spl_detections.yaml` documents what evidence each technique now requires so a weak rule cannot masquerade as detection.
<!-- /WIKI:GENERATED -->

---

### RBP Benign-Corpus Breadth and Alert Fatigue

<!-- WIKI:GENERATED unit=unit-known-limitations-rbp-benign-corpus-alert-fatigue -->
- **ID**: P5-SEC-BENIGN-CORPUS-001
- **Status**: RESOLVED 2026-07-30 for the representative corpus.
- **Former issue**: An early benign-corpus closeout stayed silent on only part of the benign cases and emitted `ANOMALOUS_UNCLASSIFIED` notifications for the rest, producing a notification-precision and false-flag problem. The evaluation scaffolding lives in `portal/modules/security/core/benign_corpus_bench.py`, which generates live benign negatives and scores alert fatigue against a retained attack corpus.
- **Expansion**: The live negative corpus now contains twelve cells, balanced across `windows:security`, `web:access`, and `linux:auditd`. Added cases cover approved scheduled-task maintenance, SCCM/WMI inventory, QA link checking, mTLS deployment automation, change-ticketed service restart, and Kubernetes CSI `nsenter`/mount reconciliation (all visible in `benign_corpus_bench.py`'s record patterns). They use the same HEC/index/sourcetype/provenance shape as attack corpus records, while the benign answer key stays outside model-visible telemetry.
- **Root cause**: Misses treated the mere occurrence of a dual-use ATT&CK-shaped primitive as malicious while ignoring explicit operational context in the cited record.
- **Resolution**: The shared verdict contracts in `portal/modules/security/core/blue_orchestrate.py` now require evidence of adversarial or unauthorized use in addition to a dual-use primitive. Change tickets, known automation/service identities, vendor paths, mTLS, purpose-specific agents, and coherent completion sequences are material counter-evidence — not automatic allow rules: an unexplained deviation still escalates.
- **Measured proof**: The final live checkpoint produced `RULED_OUT` for every benign cell with zero anomaly flags. The pre-grounding checkpoint is retained byte-for-byte for comparison.
- **T1557 follow-through**: The threshold-only T1557 rule is retired in `portal/modules/security/core/siem/spl_detections.yaml`; the Windows rule now requires correlated NTLM network logons and privileged ADMIN$/C$ share access from the same source/account across more than one target.
- **Boundary**: Twelve plausibly confusable cells remain a representative subset, not an exhaustive estimate of normal enterprise behavior. Broader hosts, identities, time windows, applications, and routine workflows remain unmeasured; any future NOTIFY on benign activity remains a false flag.

## Why

Alert-fatigue evaluation must use plausibly confusable benign telemetry, not obviously-safe records, or it overstates precision. The corpus generator reuses the attack record's transport shape so the only difference from an attack is the operational context the verdict contract must weigh; the resolution hardening — requiring adversarial evidence, not just a dual-use primitive — is what makes a benign case a true negative instead of an anomaly.
<!-- /WIKI:GENERATED -->

### ComfyUI Runs Outside Docker

<!-- WIKI:GENERATED unit=unit-known-limitations-comfyui-runs-outside-docker -->
- **Description**: ComfyUI runs on the host (not in Docker) to access MPS directly. `_launch_install_comfyui` in `scripts/lib/services.sh` installs it natively on Apple Silicon via git+pip; on non-Apple-Silicon it exits with pointers to Docker (via the compose `docker-comfyui` profile) or a manual install. Native host execution is required for supported image-generation performance; video operation is shelved.
- **Impact**: Manual setup is required outside `./launch.sh up`. On a fresh machine, ComfyUI must be installed separately with `./launch.sh install-comfyui`; the media MCPs reach it over HTTP rather than through the compose stack.
- **Mitigation**: `./launch.sh install-comfyui` handles setup on supported platforms. See `docs/COMFYUI_SETUP.md`.

## Why

ComfyUI on Apple Silicon needs direct access to the Metal/MPS device, which a container boundary would blunt or break, so the supported path runs it on the host with its own launchd agent. That keeps inference performance but moves ComfyUI out of the one-command compose lifecycle — hence the dedicated install command and setup doc that document the divergence.
<!-- /WIKI:GENERATED -->

---

### Voice Cloning (fish-speech) Requires Separate Installation

<!-- WIKI:GENERATED unit=unit-known-limitations-voice-cloning-fish-speech-requires-separate-installation -->
- **Description**: Voice cloning via `fish-speech` is not in the Docker stack — it requires host-side installation. The Docker `tts_mcp`'s `clone_voice` tool requires it: `_check_fish_speech` in `portal/modules/media/tools/tts_mcp.py` imports `fish_speech` and reports "fish-speech not installed (voice cloning unavailable)" on `ImportError`, and the `fish_speech` backend is selected only when that check passes.
- **Impact**: The docker-side `clone_voice` tool is unavailable without fish-speech installed.
- **Mitigation**: Voice cloning still works without fish-speech via the native `mlx-speech` service on port 8918: `scripts/mlx-speech.py` accepts `voice="clone:/path/to/reference.wav"` (Qwen3-TTS Base voice cloning from reference audio). `kokoro-onnx` covers non-cloned TTS out of the box either way, as `tts_mcp.py`'s backend fallback shows. See `docs/FISH_SPEECH_SETUP.md` for fish-speech.

## Why

fish-speech is a heavy optional dependency, so the container keeps it out and the MCP fails with a precise diagnostic rather than a vague error. The native `mlx-speech` service provides the same capability through a different mechanism, which keeps voice cloning available on the default stack while letting operators who want the higher-quality fish-speech path install it separately — two routes, one documented prerequisite each.
<!-- /WIKI:GENERATED -->

---

### Legacy ComfyUI Model Download Command Is Retired

<!-- WIKI:GENERATED unit=unit-known-limitations-comfyui-model-download-commands-are-broken -->
- **Description**: The legacy `./launch.sh download-comfyui-models` command no longer downloads models. `_launch_download_comfyui_models` in `scripts/lib/services.sh` exits with an error explaining that the standalone download script it once called was removed (2026-05-23) and pointing to the family-specific commands `pull-wan22` and `pull-qwen-image`. The command still appears in the `launch.sh` usage string for compatibility.
- **Resolution**: `_launch_pull_qwen_image` in `scripts/lib/services.sh` downloads the Qwen-Image checkpoint set verified on Apple Silicon MPS (T2I FP8, Edit-2509 FP8, shared text encoder/VAE, Lightning LoRA) into ComfyUI's flat `models/{diffusion_models,text_encoders,vae,loras}/` layout. `_launch_pull_wan22` downloads the Wan 2.2 TI2V-5B/S2V-14B/T2V-A14B set; video operation remains shelved even though the archival pull command exists.
- **Remaining impact**: Operators must use the explicit family command instead of the retired alias. Separately, `flux-uncensored` still has no verified working checkpoint source; the media MCP references a `Flux_v8-NSFW.safetensors` filename in `portal/modules/media/tools/comfyui_mcp.py`.
- **Operator action**: Run `./launch.sh pull-qwen-image` for the supported image set. Do not treat `pull-wan22` as enabling video operation; see the Wan 2.2 fp8 scaled-checkpoint limitation.

## Why

The monolithic download script was removed in favor of per-family handlers because the checkpoint sources and verification differ per model family, and a single script could not stay current across all of them. Keeping the dead alias registered but failing loudly with a pointer preserves CLI compatibility while forcing the operator to the command that actually works for their target family.
<!-- /WIKI:GENERATED -->

---

### ComfyUI Cross-Model-Family Memory Exhaustion (Apple Silicon)

<!-- WIKI:GENERATED unit=unit-known-limitations-comfyui-cross-model-family-memory-exhaustion-apple-silicon -->
- **Description**: ComfyUI on MPS does not reliably evict a previously-loaded model's weights when a new workflow loads a different model family in the same long-running process. Observed live: a Wan2.1-NSFW 14B video job following a Flux image job in the same process drove swap into a full system lockup, and a tiny 9-frame/5-step wan21-nsfw job still exhausted nearly the whole 64GB unified pool. The 14B backend's real peak (diffusion activation and buffer overhead) runs well above its static on-disk weight size, regardless of frame count.
- **Impact**: Chaining image generation and large video generation, or switching between very different model families, without restarting ComfyUI in between risks a full system lockup on 64GB unified-memory Apple Silicon. The wan21-nsfw backend should be treated as needing the whole machine, not just its weight size.
- **Mitigation**: Tier 1 pre-flight admission control is implemented in `portal/modules/media/tools/_admission.py` (`admit()`); its `MEDIA_MODEL_MEMORY_GB` map sets `video:wan21-nsfw` to 55.0 GB (not the ~39GB weight size) to reflect the observed real peak, and the comment there documents the tiny-job lockup incident. Restart ComfyUI between large model-family switches regardless; the service runs as a launchd agent named `com.portal5.comfyui` (see `tests/uat/lifecycle.py`). A shared cross-engine broker with Ollama is explicitly not built.

## Why

ComfyUI's single long-running MPS process is where model-family switching accumulates memory, and the measured peak of the 14B video backend far exceeds its weight file size, so static size is a dangerously misleading admission input. The admission map hard-codes the observed 55GB figure with the incident comment attached, making the operational truth visible to any future edit that might lower the estimate.
<!-- /WIKI:GENERATED -->

---

### `pytest portal` Write-Through Test Artifacts (Resolved)

<!-- WIKI:GENERATED unit=unit-known-limitations-pytest-portal-leaves-real-write-through-test-artifacts -->
- **Status**: RESOLVED 2026-07-29.
- **Former issue**: Security module tests could write journals and checkpoints into the real runtime tree, leaving dated entries in the committed `field_journal/` history and stray checkpoint files.
- **Resolution**: The autouse fixture `isolated_security_writes` in `portal/modules/security/tests/conftest.py` monkeypatches `field_journal.JOURNAL_DIR`, `loop.RESULTS_DIR`, and `loop.CHECKPOINT_DIR` into each test's `tmp_path`. The production modules also stopped creating those directories merely by being imported; the write functions (`field_journal.write_entry`, `loop._write_checkpoint`) create their destination lazily at write time.
- **Regression coverage**: `portal/modules/security/tests/test_write_isolation.py` writes both artifact types and asserts that their parents are the fixture sandbox.

## Why

Write-through test artifacts are dangerous because they look like real committed history and can ride along with an unrelated commit — the field journal is tracked, so a test-side entry becomes an untraceable line in the repo. Routing the write destinations through a fixture-injected `tmp_path` makes the sandbox the only possible target, and asserting the parent path in the regression test proves the isolation mechanically rather than by inspection.
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

## Why

The curated capability library and the live dispatch boundary are two different trust levels, and conflating them produced synthetic exploits being reported as real progress. The allowlist is the seam: only a small set of read-only binaries verified against the live lab may dispatch through `_lab_dispatch_inner`, and `live_dispatchable_only` retires everything unbound from the live trajectory while keeping it visible for planning. That asymmetry is deliberate — an unbound capability must never be represented as a live step.
<!-- /WIKI:GENERATED -->

---

### auto-math Workspace — Reasoning Block Support

<!-- WIKI:GENERATED unit=unit-known-limitations-auto-math-workspace-reasoning-block-support -->
- **ID**: P5-MATH-001
- **Status**: RESOLVED (V8 model refresh — 2026-06-10)
- **History**: The `auto-math` workspace once ran a math-tuned model whose responses carried no separate reasoning channel, so step-by-step thought was not surfaced as a collapsible block. The V8 refresh replaced that primary with `phi4-mini-reasoning:latest-ctx24k`, and `config/portal.yaml` now records `emits_reasoning: true` for the workspace (`model_hint`, `context_limit: 24576`, `tools: []`).
- **Alternative**: For heavier reasoning, `auto-reasoning` (`DeepSeek-R1-0528-Qwen3-8B`, `emits_reasoning: true`) also separates reasoning content.

## Why

The workspace's `emits_reasoning` flag is the routing contract that tells the pipeline and Open WebUI how to render the model's thinking: when true, reasoning is delivered as a distinct block the chat UI can collapse. Recording it per-workspace in `config/portal.yaml` rather than inferring from the model name keeps the presentation contract explicit and auditable against the live config.
<!-- /WIKI:GENERATED -->

---

### baronllm text_only tool output — auto-security MCP tools non-functional

<!-- WIKI:GENERATED unit=unit-known-limitations-baronllm-text-only-tool-output-auto-security-mcp-tools-non-functional -->
- **ID**: P5-TOOL-001
- **Description**: `huihui_ai/baronllm-abliterated` (in the security pool; `auto-security`'s `model_hint` primary is now `VulnLLM-R-7B` per `config/portal.yaml`) once output tool-call JSON embedded in the `content` field of Ollama's `/v1/chat/completions` response rather than in the structured `tool_calls` field. The pipeline's `_dispatch_tool_call` in `portal/platform/inference/router/tools.py` reads only the native `tool_calls` array, so tool intent in prose never triggered dispatch. UAT `g_auto_security.py` documents the `text_only` outcome from the 2026-06-18 `--audit-tools` probe.
- **Impact**: MCP tool use (e.g. `execute_python`, `classify_vulnerability`) was not dispatched for such requests; prose security analysis was unaffected.
- **Status**: RESOLVED 2026-06-20 (TASK_TOOLCALL_FIX_LOCKIN_V1). A corrected tool-calling chat template made baronllm emit structured `tool_calls`; the `--audit-tools` probe then returned `tool_call`. `supports_tools: true` is recorded in `config/backends.yaml` for both `huihui_ai/baronllm-abliterated` entries, backed by the live probe. `baronllm:q6_k` remains `supports_tools: false`.
- **Do not re-enable** `supports_tools: true` for a baronllm tag without running `python3 tests/portal5_persona_matrix.py --audit-tools --workspace auto-security` and confirming outcome=`tool_call`. `_model_supports_tools` in `portal/platform/inference/router/validation.py` is what gates dispatch on the declared flag.

## Why

A model's `supports_tools` declaration must be backed by a live response probe, not by inspecting its Ollama template header. The pipeline treats the flag as authoritative — `_model_supports_tools` gates whether tool schemas are exposed and dispatch is attempted — so a false positive silently degrades every request into a narrated tool-call with no dispatch. The audit command exists to make that verification mechanical and repeatable before any flag is set.
<!-- /WIKI:GENERATED -->

---

### Asteroids Bench Score Variance Is the Benchmark's Purpose

<!-- WIKI:GENERATED unit=unit-known-limitations-asteroids-bench-score-variance-is-the-benchmark-s-purpose -->
- **ID**: P5-BENCH-001
- **Description**: The CC-01 Asteroids challenge is the creative-coding benchmark wired across the `bench-` workspaces in `config/portal.yaml`, one identical task per model (ship rotation, thrust, bullet fire, asteroid split, level advance). The bench persona catalog (`config/personas/`) shares a single `prompt_template: creative_coder`, and `tests/benchmarks/bench/prompts.py` documents that CC-01 deliberately uses the coding category so cross-bench numbers stay comparable even though creative coding is not every model's strength. Score variance on the fixed task is therefore the benchmark's purpose: it reflects model capability, not a test harness defect.
- **Operator action**: Use bench scores as model-selection signal. A low CC-01 score against a reasoning-heavy model is expected, not a defect; a model that cannot clear a basic creative-coding bar should not be promoted into HTML-generation routing.

## Why

Benchmark workspaces exist to isolate model capability from routing and harness noise, so the corpus and prompt must be held fixed across every candidate. If each bench persona carried its own system prompt, score deltas would be unreadable as model signal. Keeping one `creative_coder` template and one task makes the output comparable, and the documented category assignment prevents a low score from being misread as a regression.
<!-- /WIKI:GENERATED -->

---

### Tool Preselection — Candidate 1B Models Cannot Rank Tools

<!-- WIKI:GENERATED unit=unit-known-limitations-tool-preselection-candidate-1b-models-cannot-rank-tools -->
- **ID**: P5-TOOLPRESELECT-001
- **Status**: BUILT NOT DEPLOYED — exhausted, closed.
- **Description**: `portal/platform/inference/tool_preselect/` implements query-level tool-schema preselection — a small fast model ranks a workspace's tools by relevance to the user's turn so only the top-K schemas are sent to the primary model. The module, config surface, parser, and metrics are built and unit-tested, shipped feature-flagged off (`PORTAL5_TOOL_PRESELECT=0`, default, per `config.py`; `PORTAL5_TOOL_PRESELECT_MODEL` defaults to `hf.co/openbmb/MiniCPM5-1B-GGUF:Q4_K_M`).
- **Evidence**: The candidate 1B-scale models could not rank tools reliably. Natural-language ranking prompts produced endless unrequested reasoning with no ranking; grammar-constrained JSON produced syntactically valid but semantically nonsensical rankings. Additional elicitation attempts (system-prompt framing, `think: false`, single-choice simplification, few-shot examples, and a different model lineage) all converged on the same failure — positional defaults or unreliable picks, not genuine ranking.
- **Conclusion**: No model tested at ~1-2B scale can perform this specific ranking task reliably, regardless of prompt framing, output-format constraint, or reasoning-mode control — a genuine capability gap at this scale, not a fixable prompting artifact.
- **Impact**: None on production — the feature has never been enabled on any workspace, and `preselector.py`'s fallback invariant (`subset == effective_tools` on any failure, "never raises") means even an accidental enable would degrade to a no-op, not a broken tool call.
- **Resolution path**: Revisit only with a materially larger (3B+) or purpose-built tool-ranking model. The built code is reusable as-is — only `PORTAL5_TOOL_PRESELECT_MODEL` needs to point at a model that passes the ranking task.
- **Do not** re-attempt promotion without first re-running `portal/platform/inference/tool_preselect/cli_probe.py` against the new candidate and confirming a plausible top-K ranking on multiple varied scenarios, not a single spot-check.

## Why

The whole point of preselection is a cheap model deciding which schemas the expensive model sees, so the capability gap is disqualifying at the source: a ranker that cannot rank buys nothing and risks hiding tools the primary model needs. The fallback-to-full-set invariant is what lets the feature ship disabled safely — failure degrades to the pre-feature behavior, so the module can stay built and tested until a capable candidate exists.
<!-- /WIKI:GENERATED -->

---

## MLX Inference Proxy — RETIRED (commit 3a0c58e)

<!-- WIKI:GENERATED unit=unit-known-limitations-mlx-inference-proxy-retired-commit-3a0c58e -->
The MLX inference proxy (formerly ports 8081/18081/18082) was retired in commit `3a0c58e`, and all its limitations (single-model eviction, cold-boot 503 windows, admission control, deploy staleness) no longer apply. All chat inference runs through Ollama on port 11434, which reaches parity with standalone `mlx_lm` on this hardware without the dual-stack overhead. MLX is retained only outside chat inference: speech (`scripts/mlx-speech.py`, :8918), diarized transcription (`scripts/mlx-transcribe.py`, :8924), embeddings (:8917), and the RAG reranker (:8925). Do not remove those when "cleaning up MLX".

## Why

Retiring the proxy deleted an entire failure surface at once, so the residual limitations are intentionally only the audio and retrieval runtimes that legitimately use MLX today. Recording the retirement with the surviving MLX surfaces prevents a future cleanup pass from mistaking those four services for the retired inference tier and deleting them along with the dead stack.
<!-- /WIKI:GENERATED -->

---

## Model Parity — Specialist models lost in the MLX→Ollama migration

<!-- WIKI:GENERATED unit=unit-known-limitations-model-parity-specialist-models-lost-in-the-mlx-ollama-migration -->
Two production specialist models were MLX-only safetensor builds with no
verified GGUF equivalent at migration time. The migration (3a0c58e) remapped
their workspaces to GGUF substitutes:

| Workspace(s) | Original (MLX) | Now served (Ollama GGUF) | Gap |
|---|---|---|---|
| `auto-security` (blueteam variant), `bench-foundation-sec` | Foundation-Sec-8B-Reasoning (Cisco, purpose-trained defender cybersec: CVE→CWE, MITRE ATT&CK, SOC triage) | First-party GGUF `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0` (in `config/backends.yaml`) | RESTORED via first-party GGUF (P5-FUT-PARITY-001) |
| `tools-specialist`, `bench-toolace25` | ToolACE-2.5-Llama-3.1-8B (Team-ACE, BFCL-topping tool-caller) | granite4.1:8b (general tool-tagged, BFCL V3 68.27, first-party IBM) | ACCEPTED — granite4.1:8b adopted; ToolACE-2.5 dropped (P5-FUT-PARITY-001 closed) |

**Status — Foundation-Sec:** The first-party GGUF is registered in `config/backends.yaml` under the security group. In `config/portal.yaml` it is wired as the `expert_model` of the `blueteam-orchestrated` and `blueteam-council` variants and as the `bench-foundation-sec-8b-reasoning` workspace `model_hint`. The `blueteam` variant's production `model_hint` is `granite4.1:8b-ctx8k`; Foundation-Sec serves the orchestrated/council blue lanes rather than the default blue single-model path.

**Status — ToolACE:** RESOLVED (accepted). granite4.1:8b adopted as the
`tools-specialist` model by operator decision; ToolACE-2.5 evaluated and dropped
(no verified ToolACE-2.5 GGUF confirmed; self-quant + Ollama tool-template risk
not justified). P5-FUT-PARITY-001 is CLOSED/DONE — both specialists dispositioned
(Foundation-Sec restored, ToolACE substitute accepted).

## Why

The MLX-to-Ollama migration could not keep every specialist model because some existed only as MLX safetensors. Re-grounding the two dispositions to the current config shows where each landed: Foundation-Sec returned through a first-party GGUF but now occupies the expert/orchestrated role, not the default blue primary, while ToolACE's slot is deliberately served by a different, tool-tagged model. That mapping is what an operator needs to avoid re-proposing the dropped model.
<!-- /WIKI:GENERATED -->

---

## Ollama Native MLX Engine — Evaluation Findings (2026-07-01)

<!-- WIKI:GENERATED unit=unit-known-limitations-ollama-native-mlx-engine-evaluation-findings-2026-07-01 -->
Ollama 0.31.1 added a built-in MLX engine (distinct from the retired standalone `mlx_lm` proxy) that claims a large MTP-driven speedup for Gemma 4. A same-day evaluation of that engine, plus a broader catalog sweep for MLX equivalents of the fleet, is documented in `coding_task/TASK_EVAL_GEMMA4_MLX_TAGS_V1.md`. The sweep tooling is `tests/benchmarks/bench_mlx_hf.py`, which pulls any HF `mlx-community` repo and benches it directly via `mlx_lm` — a throwaway measurement tool, not a serving mechanism, and its module docstring explicitly forbids wiring it into launch hooks or the pipeline. **No production config was changed**: `config/backends.yaml` was reverted, the pulled MLX models were deleted, and disk usage was restored to its pre-evaluation baseline.

## Why

Ollama's claimed MLX speedups are real enough to measure but unusable in production because the pipeline only talks to Ollama's GGUF-serving endpoint, so the evaluation had to be recorded without leaving artifacts behind. Keeping the throwaway bench tool separate from the serving stack, and reverting config after measuring, prevents an experiment from silently becoming an undocumented production dependency.
<!-- /WIKI:GENERATED -->

---

### P5-MLX-EVAL-001 — GGUF fleet regressed slightly on 0.31.1; MTP is MLX-engine-only

<!-- WIKI:GENERATED unit=unit-known-limitations-p5-mlx-eval-001-gguf-fleet-regressed-slightly-on-0-31-1-mtp-is-mlx-engine-only -->
- **Description**: Ollama 0.31.1's claimed MTP speedup applies only when Ollama selects its own MLX engine subprocess (triggered by official `-mlx`-tagged models), so the GGUF fleet routed through `llama-server` regardless of version. Separately, the GGUF fleet measured slower after the 0.31.1 upgrade, and the 5-11% regression is recorded in `coding_task/TASK_SEC_DRIFT_GATE_V1.md` as the motivating example for the delta gate it adds — a version-induced performance shift that absolute gates would not flag. The MTP claim and its MLX-engine-only scope are documented in `coding_task/TASK_EVAL_GEMMA4_MLX_TAGS_V1.md`.
- **Impact**: None today (no config changed). Documented so a future Ollama upgrade isn't mistaken for a routing/pipeline regression.

## Why

An Ollama point release silently shifting GGUF throughput is exactly the failure a routing regression gate cannot see, because routing behavior is unchanged while latency moves. Recording the measured regression and the scope of the MTP claim keeps the two facts distinct — the speedup is an MLX-engine property, the slowdown is a llama.cpp-version property — so a future upgrade is evaluated against the right baseline.
<!-- /WIKI:GENERATED -->

---

### P5-MLX-EVAL-002 — Ollama's official gemma4 `-mlx` tags are not drop-in swaps

<!-- WIKI:GENERATED unit=unit-known-limitations-p5-mlx-eval-002-ollama-s-official-gemma4-mlx-tags-are-not-drop-in-swaps -->
- **Description**: Ollama's official `gemma4:{e2b,e4b,12b}-mlx` library tags are not drop-in replacements for the production `gemma4:{e2b,e4b,12b}-it-qat` GGUF models. The evaluation in `coding_task/TASK_EVAL_GEMMA4_MLX_TAGS_V1.md` documents the swap-blocking differences: parameter counts differ per tier, the quantization schemes differ (QAT versus nvfp4), and the 12b tag reports a different architecture name (`gemma4_unified` vs `gemma4`). At the time of the original evaluation the `-mlx` tags lacked the vision/audio capability that the QAT variants' multimodal projection provides.
- **Impact**: Cannot be swapped in as a pure speed upgrade. A workspace routing image/audio input to the QAT tags would silently lose that capability if swapped to `-mlx`. Output quality is also unverified — QAT training targets low-precision quality retention, which nvfp4 post-training quant does not guarantee.
- **Future work needed**: (1) Audit which workspaces using these models rely on vision/audio input vs text-only. (2) Run a live tool-call probe on any candidate before promotion — never infer `supports_tools` from the model card. (3) Run a quality eval, not just TPS, before promoting. **Do not add `gemma4:*-mlx` tags to `config/backends.yaml` until all three are done.**

## Why

A model tag that is faster but semantically different — different weights, different quant scheme, different architecture, and originally missing a modality — is a regression wearing a speedup costume. The eval task doc records the exact deltas so a swap is never justified on TPS alone, and the three-step future-work gate keeps the decision mechanical: capability audit, live tool probe, quality eval.
<!-- /WIKI:GENERATED -->

---

### P5-MLX-EVAL-003 — HF-hosted MLX models are currently unreachable by the Pipeline

<!-- WIKI:GENERATED unit=unit-known-limitations-p5-mlx-eval-003-hf-hosted-mlx-models-are-currently-unreachable-by-the-pipeline -->
- **Description**: Ollama's `hf.co/` puller only accepts GGUF repos; pulling any `mlx-community` safetensors repo fails with the "Repository is not GGUF or is not compatible with llama.cpp" error, as `tests/benchmarks/bench_mlx_hf.py` documents. Only Ollama's curated `-mlx` library tags can be served through its MLX engine. None of the HF-hosted MLX conversions is usable in production because `BackendRegistry` in `portal/platform/inference/cluster_backends.py` talks only to Ollama's OpenAI-compatible endpoint (`chat_url` appends `/v1/chat/completions`), so a raw `mlx_lm`-served model is unreachable without new serving infrastructure.
- **Impact**: Real, measured speed gains exist for part of the catalog but are inaccessible through the pipeline as built.
- **Tooling**: `tests/benchmarks/bench_mlx_hf.py` (committed) pulls and benches any HF MLX repo directly via `mlx_lm`. It is not a serving mechanism; its docstring forbids adding launch hooks or pipeline integration without a deliberate decision to revive MLX serving.
- **Not universal**: MLX gains are not guaranteed — at least one model's MLX equivalent measured slower than its GGUF, and one large apparent gain reflects a pre-existing GGUF incompatibility for that specific model, not a general MLX advantage. Verify per-model.
- **Future work needed**: A deliberate decision on whether to stand up a lightweight MLX serving layer (Ollama would remain the primary scheduler; this would not revive the retired proxy/watchdog/admission-control stack) or wait for Ollama to expand its official `-mlx` library coverage. No infrastructure work has started; this is an evaluation finding only.

## Why

The pipeline's backend contract is one endpoint family, and its URL construction proves it — every model must speak Ollama's OpenAI-compatible API. HF MLX models break that contract, so measuring their speed with a throwaway bench tool records the opportunity without pretending it exists in production; the explicit no-hooks warning on the tool preserves the retired-proxy boundary.
<!-- /WIKI:GENERATED -->

---

### P5-MLX-EVAL-004 — Large single-blob MLX downloads hang intermittently

<!-- WIKI:GENERATED unit=unit-known-limitations-p5-mlx-eval-004-large-single-blob-mlx-downloads-hang-intermittently -->
- **Description**: During the MLX evaluation, several separate large downloads (each in the 18-26GB range) silently stalled mid-transfer for 30+ minutes with no error — the blob stopped growing with stale TCP close-wait sockets. It happened on both the official registry (`ollama pull`, via `./launch.sh pull-models`) and HuggingFace (`hf download`, the mechanism `scripts/lib/services.sh` uses for ComfyUI pulls), so it is a network/CDN reliability issue for large single-file transfers on this connection, not a tool-specific bug. No stalls appeared on smaller pulls.
- **Mitigation**: A stall-detection wrapper (poll the blob size every 10s, kill and retry after 90s with no growth) recovered every case on retry. It is **not** a committed script — the codebase has no such wrapper today. If large-model pulls become a recurring pain point, promote this pattern into `scripts/`.

## Why

The platform's model-download path is plain `ollama pull` / `hf download` with no progress guard, so an intermittent CDN stall is invisible until the operator notices the transfer stopped. Recording the observed behavior and the throwaway wrapper that fixed it keeps the failure mode known — and documents explicitly that the mitigation is not yet part of the tooling, so nobody assumes the protection exists.
<!-- /WIKI:GENERATED -->

---

### P5-MLX-EVAL-005 — Two security-tier fine-tunes have no working MLX conversion

<!-- WIKI:GENERATED unit=unit-known-limitations-p5-mlx-eval-005-two-security-tier-fine-tunes-have-no-working-mlx-conversion -->
- **Description**: `supergemma4-26b-uncensored` (the `redteam-deep` and `purpleteam-exec` variant `model_hint` in `config/portal.yaml`, and registered in `config/backends.yaml`) and `huihui_ai/gemma-4-abliterated:E2b-qat` were searched across multiple HF uploaders for a text-only MLX conversion. Every MLX conversion found for these specific fine-tunes is a multimodal/vision-language checkpoint whose weights crash on plain text-only `mlx_lm` load with a parameter-count mismatch. The GGUF paths remain the only working forms.
- **Impact**: These models stay GGUF-only for the foreseeable future; the pipeline serves them through Ollama's GGUF path regardless.
- **Do not** spend further time searching for a working MLX conversion for either unless a new text-only-compatible upload appears.

## Why

A fine-tune's MLX port can quietly change modality — producing a vision-language checkpoint that a text-only loader rejects — so the search for a working conversion is a bounded cost that should not be re-litigated on every model refresh. Recording the two known failures with their exact symptom prevents repeated dead-end hunting, while the note that they are GGUF-only matches the fact that the serving tier is Ollama.
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

## Why

A library module must not mutate process-global state on import, because the security data module is imported by nearly every security test and any env leak would silently change behavior for the whole session. Parsing the dotenv into a private mapping keeps the config readable while making imports side-effect-free, and the subprocess regression test proves the invariant mechanically rather than trusting a comment.
<!-- /WIKI:GENERATED -->

---

### POST /v1/messages Null Success Body (Resolved)

<!-- WIKI:GENERATED unit=unit-known-limitations-post-v1-messages-anthropic-compat-endpoint-returns-http-200-with-a-null-body -->
- **ID**: P5-ANTHROPIC-COMPAT-001
- **Status**: RESOLVED 2026-07-29.
- **Former issue**: The non-streaming `/v1/messages` (Anthropic Messages API) success path completed after checking the loopback response status but did not return the translated response, so FastAPI serialized Python `None` as `null` — HTTP 200 with an empty body.
- **Resolution**: `anthropic_messages` in `portal/platform/inference/router/handlers.py` now returns `openai_response_to_anthropic(resp.json(), model_id)` on HTTP 200 (line ~1328). The translation lives in `portal/platform/inference/router/anthropic_compat.py`. Error propagation and the streaming translation path are unchanged.
- **Regression coverage**: `test_anthropic_non_streaming_success_returns_message` in `tests/unit/test_pipeline.py` exercises the ASGI loopback and asserts the complete Anthropic Messages response shape, content, stop reason, model, and token usage.
- **Discovered**: 2026-07-13, live-verifying the opencode CLI-contract migration.

## Why

An Anthropic-compatible endpoint returning HTTP 200 with a null body is the worst possible failure mode for a CLI client: the request looks successful so the client waits for a response that never arrives. The fix keeps the loopback pattern for routing but makes the return value explicit, and the test asserts the full wire shape rather than just the status code, so a regression reintroducing the silent null is caught at the contract level.
<!-- /WIKI:GENERATED -->

---

### devstral:24b Runtime VRAM Footprint (25.7 GB)

<!-- WIKI:GENERATED unit=unit-known-limitations-devstral-24b-runtime-vram-footprint-25-7-gb -->
- **ID**: P5-VRAM-DEVSTRAL-001
- **Description**: `devstral:24b` is registered in `config/backends.yaml` under both the general and coding groups. `config/portal.yaml` lists its file size at ~14 GB, but runtime Ollama resident size runs roughly double that because a large default context window drives KV-cache allocation. This can cause memory-pressure eviction of other loaded models; on M4 Pro 64 GB it is non-critical (graceful CPU offload), but relevant on tighter budgets.
- **Impact**: When devstral is active, it may evict the LLM router model. The first post-eviction routing request falls back to Layer 2 keyword scoring (correct behavior), then the router cold-loads and stays warm; subsequent requests route normally.
- **This is graceful, not a crash**: Ollama offloads CPU layers under memory pressure rather than failing. Unlike the former MLX Metal OOM, no kernel panic occurs.
- **Mitigation**: `.env.example` sets `OLLAMA_MAX_LOADED_MODELS=5` (LLM router + 4 inference models), and `OLLAMA_MEMORY_LIMIT=0` (unlimited, native Ollama unaffected). If devstral:24b loads as an inference peer, its runtime footprint is the limiting factor — not the slot count. Worst-case slot composition stays within the 64 GB budget.

## Why

The catalog advertises devstral by its 14.3 GB file size, but the scheduler competes on resident footprint, so the ~25.7 GB runtime figure is the number that actually drives eviction decisions. Documenting the two numbers separately and describing the graceful CPU-offload behavior prevents a future operator from treating an eviction as a crash and "fixing" it with destructive measures.
<!-- /WIKI:GENERATED -->

---

### Request-Size Cap Relied on Content-Length Only (Resolved)

<!-- WIKI:GENERATED unit=unit-known-limitations-request-size-cap-relies-on-content-length-only -->
- **ID**: P5-REQ-SIZE-001
- **Status**: RESOLVED 2026-07-29.
- **Former issue**: The pipeline enforced its request-size cap only through `Content-Length`, so HTTP chunked transfer encoding bypassed the limit — a client could stream an oversized inference body past the check.
- **Resolution**: `RequestBodyLimitMiddleware` in `portal/platform/inference/router/request_limits.py` buffers and bounds the two JSON inference endpoints before route handling, enforcing the same limit against declared and streamed/chunked bodies. Its module docstring documents that a `Content-Length`-only check is bypassed by chunked transfer. Oversize requests return 413 before the handler runs.
- **Regression coverage**: `test_chunked_body_over_limit_is_rejected_before_handler` in `tests/unit/test_request_limits.py` sends a chunked async body with no usable `Content-Length` and verifies rejection with status 413.

## Why

`Content-Length` is a header the client controls, and chunked transfer omits it entirely, so trusting it for a size cap leaves the endpoint unbounded for any client that speaks HTTP/1.1 chunking. Middleware that reads the actual ASGI body stream and enforces the same ceiling on what it consumes closes the gap at the transport layer, and the chunked regression test proves the exact bypass that motivated it.
<!-- /WIKI:GENERATED -->

---

### Speculative Decoding / MTP — RETIRED with the MLX proxy (commit 3a0c58e)

<!-- WIKI:GENERATED unit=unit-known-limitations-speculative-decoding-mtp-retired-with-the-mlx-proxy-commit-3a0c58e -->
- **IDs**: P5-SPEC-001, P5-MTP-001, P5-MTP-PATH (all moot)
- **Status**: The MLX inference proxy that hosted `--draft-model` speculative decoding and the `speculative_decoding.draft_models` map was retired (commit `3a0c58e`); chat inference is Ollama-only. These limitations no longer apply because the infrastructure they described no longer exists — `coding_task/TASK_DOC_STEADY_STATE_V1.md` records the collapse of the three live MLX-proxy limitation sections into this single retirement note.
- **If revisited**: any future speculative-decoding / MTP work targets Ollama's native path (llama.cpp b9180+), not MLX. Bench-only MTP GGUF candidates remain as bench entries in `config/portal.yaml` (e.g. `bench-qwen36-27b-mtp`, created via `./launch.sh apply-mtp-drafts`); there is no production MLX serving path to enable.
- **P5-FUT**: evaluate `/api/chat` as the chat URL — it would allow full `options` passthrough but requires changing payload/response shapes.

## Why

When the proxy died, three sections describing its speculative-decoding limitations became instructions for infrastructure that no longer exists, which is worse than a stale doc — it actively misleads anyone reading them as current constraints. Collapsing them into one retirement note preserves the decision record (the draft-model wiring and why it was removed) while making the current truth unambiguous: MTP work, if any, belongs on Ollama's native speculative path.
<!-- /WIKI:GENERATED -->

---

### phi4-reasoning:plus crashes Ollama's llama-server on this host — CONFIRMED NOT a corrupted download

<!-- WIKI:GENERATED unit=unit-known-limitations-phi4-reasoning-plus-crashes-ollama-s-llama-server-on-this-host-confirmed-not-a-corrupted-download -->
- **ID**: P5-MODEL-PHI4REASONING-001
- **Description**: `phi4-reasoning:plus` crashes Ollama's llama-server on this host — the runtime reports `llama-server process has terminated: signal: abort trap` on direct generation. `config/backends.yaml` records the confirmed exclusion: the `reasoning` group deliberately omits `phi4-reasoning:plus-ctx32k` with a comment saying the model crashes Ollama's llama-server on load and must not be made reachable from any production workspace until resolved upstream. This is a local Ollama/model-file incompatibility (llama.cpp device-memory-fitting at load on the Apple Silicon Metal backend), not a routing or pipeline bug.
- **Root cause confirmed**: a full `ollama rm` plus re-pull of the base model and rebuild of the ctx-tagged variants reproduced the identical abort — not a corrupted download.
- **Impact**: The `phi4stemanalyst` persona was re-identified generically: `config/personas/phi4stemanalyst.yaml` has no `model_pin` and documents the crash, serving `auto-reasoning`'s pool default (`DeepSeek-R1-0528-Qwen3-8B`) instead of Phi-4-reasoning-plus.
- **Do not add** `phi4-reasoning:plus` or `phi4-reasoning:plus-ctx32k` to a reachable backend group without first resolving this crash. Re-pulling alone will NOT fix it — already tried and reproduced.
- **Mitigation options not yet tried**: upgrade/downgrade Ollama to a different llama.cpp vendor commit and retest; try a different quantization/source GGUF; file upstream against Ollama/llama.cpp with the log excerpt.

## Why

A model that aborts during load is indistinguishable from a corrupted download without the reproduction, so the re-pull experiment was necessary to prove it is a real incompatibility between this GGUF and the installed llama-server build. Recording the confirmed crash and the persona's generic re-identification keeps the persona honest about what it serves and prevents anyone from "fixing" the model by re-adding it to the reachable catalog.
<!-- /WIKI:GENERATED -->

---

### 70B Dense Models Unusable for Daily Routing on M4 Pro 64GB

<!-- WIKI:GENERATED unit=unit-known-limitations-70b-dense-models-unusable-for-daily-routing-on-m4-pro-64gb -->
- **ID**: P5-SPEED-001
- **Description**: Dense 70B-class models are unusable for daily routing on this M4 Pro 64GB host. The catalog removal record in `tests/unit/test_pipeline.py` documents measured 3.8 TPS for `llama3.3:70b-q4_k_m`, below the project's 20 TPS interactive floor, with `supports_tools: false`, bench-only. Both `llama3.3:70b-q4_k_m` and `dolphin-llama3:70b-q4_k_m` survive only as `retired: true` entries in the `config/portal.yaml` pull registry, excluded from default pulls. An MLX 3-bit ~28GB variant was theorized but never validated, and the MLX inference tier itself is retired.
- **Mitigation**: No 70B dense model is registered in any `config/backends.yaml` backend group for daily routing. Daily-routed workspaces use the compact catalog; 70B variants exist only as retired registry history.

## Why

The 64GB unified-memory budget and a 20 TPS interactive-latency floor combine to exclude dense 70B models from the routing catalog: their measured throughput sits at roughly a fifth of the floor at any quality-preserving quantization, and their weight footprints would crowd out the co-resident router and inference peers scheduling depends on. Keeping them as retired registry entries preserves the measured evidence so a cluster-scale node, not a catalog edit, is the only route back in.
<!-- /WIKI:GENERATED -->

---

### Ollama /v1 ignores options.num_ctx and options.num_batch

<!-- WIKI:GENERATED unit=unit-known-limitations-ollama-v1-ignores-options-num-ctx-and-options-num-batch -->
- **ID**: P5-OLLAMA-OPTIONS-001
- **Description**: Ollama's OpenAI-compatible `/v1/chat/completions` endpoint ignores the `options` sub-object (VERIFY-1 probes, 2026-06). The pipeline still injects `options.num_ctx` (from each workspace's `context_limit`) and `options.num_batch` (fixed 2048) because a future Ollama version may honor them; `predict_limit` is mapped to top-level `max_tokens`, which IS honored. `_apply_workspace_settings` in `portal/platform/inference/router/validation.py` implements all three injections.
- **Consequence**: `context_limit` per workspace (e.g. `auto-coding: 16384`) is not enforced through `/v1` — it must be baked into the model's Modelfile or set via `OLLAMA_CONTEXT_LENGTH`. `num_batch` injection is likewise inert.
- **Mitigation proof**: Raw `granite4.1:30b` loaded at 131,072 tokens while `granite4.1:8b` loaded at the same default, so the security evaluation workspaces now use baked `granite4.1:30b-ctx16k` and `granite4.1:8b-ctx8k` tags (registered in `config/backends.yaml`; used by `portal/modules/security/core/blue_orchestrate.py`, `agentic_blue_eval.py`, and `_sweep_driver.py`). Ollama then reports contexts 16,384 and 8,192 respectively. This mitigates the operated workspaces but does not resolve the general `/v1` limitation.
- **Roadmap note**: evaluate `/api/chat` as the chat URL — it honors the Ollama-native parameter set but requires changing all payload/response shapes.
- **Recurrence (2026-08-10)**: TASK-BATCH-BENCH-002's `bench-deepwen-cad` workspace was created with a bare `context_limit: 8192` (not a pre-baked tag), reproducing this exact limitation — the resulting corrupted tool-call JSON was initially misdiagnosed as a broken GGUF quant conversion before being root-caused back to this entry. Fixed via `./launch.sh apply-model-params` (note: requires `PORTAL_ENABLE_EVAL=1` to see eval-module workspaces). See `unit-model-catalog-portal5-deepwen-3-6-q4-5-moq` for the full misdiagnosis-and-correction narrative.

## Why

The `/v1` compatibility surface is convenient but drops the `options` object, so context and prefill tuning must travel through a channel the endpoint actually honors. Baking a context-limited tag per workspace is the pragmatic fix because it moves the constraint into the Modelfile where Ollama cannot ignore it, while the pipeline keeps injecting `options` for future compatibility rather than deleting a currently-inert but standards-shaped field.
<!-- /WIKI:GENERATED -->

---

## Shared Workspace + Auto-STT Disabled (TASK-WORKSPACE-001)

<!-- WIKI:GENERATED unit=unit-known-limitations-shared-workspace-auto-stt-disabled-task-workspace-001 -->
- **Voice-input via microphone is disabled.** `OWUI_AUDIO_STT_ENGINE` is empty in `.env.example`, and `deploy/portal-5/docker-compose.yml` passes it through as `AUDIO_STT_ENGINE` to Open WebUI, disabling auto-transcription of both file uploads and microphone recordings. Re-enabling it re-enables auto-transcribe-on-upload. The global toggle is OWUI's only knob.
- **Existing MCPs not migrated to /workspace.** `mcp-documents` and `mcp-tts` in `deploy/portal-5/docker-compose.yml` write to `${AI_OUTPUT_DIR}` via `OUTPUT_DIR=/app/data/generated` (mounted flat), while newer MCPs (e.g. `mcp-whisper`) use `WORKSPACE_DIR=/workspace` with `/workspace/generated/<category>/` subpaths. Both layouts coexist; migration is opportunistic.
- **Permissions assume single-host deployment.** `launch.sh` and `scripts/lib/services.sh` apply `chmod -R 0775` to the workspace tree, which assumes operator-owned files and compatible Docker UIDs. Multi-tenant or hardened hosts need explicit UID mapping.
- **No retention policy.** `${AI_OUTPUT_DIR}` grows unbounded; `./launch.sh workspace-clean --age=Nd` is a planned but not yet implemented command.

## Why

The shared-workspace contract is the single path for user files, but the migration from flat `${AI_OUTPUT_DIR}` writes to the `/workspace/generated/<category>/` layout is still incomplete, so both layouts coexist and any code must handle both. Auto-STT is intentionally off to keep audio uploads accessible to personas, and permissive permissions are accepted because the deployment is single-host — each constraint is a deliberate, documented trade-off rather than an accident.
<!-- /WIKI:GENERATED -->

---

## Diarized Transcription (TASK-TRANSCRIBE-001)

<!-- WIKI:GENERATED unit=unit-known-limitations-diarized-transcription-task-transcribe-001 -->
- **Pyannote model gating.** `scripts/mlx-transcribe.py` gates diarization on `HF_TOKEN` (env `DIARIZATION_MODEL` defaults to `pyannote/speaker-diarization-3.1`); without it the pipeline returns an error telling the operator to accept the HF agreements and set `HF_TOKEN` in `.env`. The Docker fallback `portal/modules/media/tools/whisper_mcp.py` gates on the same token.
- **Overlapping speech.** Pyannote underperforms when multiple speakers talk simultaneously; segments are assigned to a single speaker by maximum overlap.
- **Speaker count drift on long recordings.** For long recordings pyannote may split one speaker into two IDs after long silence gaps. Pass `num_speakers=N` when known; both `scripts/mlx-transcribe.py` and `whisper_mcp.py` forward it to the diarization pipeline.
- **OWUI tool-call timeout for long files.** OWUI's MCP tool-call ceiling can fire before a long file finishes. Raise `AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA` (set to 1800 in `.env.example`) or use the direct endpoint on port `8924`.
- **MLX path is Apple-Silicon-specific.** `scripts/mlx-transcribe.py` is the host-native MPS path (mlx-whisper + pyannote on MPS, ~5x faster). The Docker `whisper_mcp.py` fallback (faster-whisper + pyannote on CPU, or CUDA on Linux nodes) is the cross-platform alternative.

## Why

Diarization lives behind HuggingFace gated model agreements, so the code fails fast with a token hint instead of a mysterious 500; that keeps the failure mode self-diagnosing. Keeping the fast MPS path and the portable Docker path side by side, with the token gate shared between them, means one operational prerequisite (`HF_TOKEN`) governs both routes and the platform choice is left to the host.
<!-- /WIKI:GENERATED -->

---

## OWUI Audio Drop UX (TASK-OWUI-AUDIO-DROP-001)

<!-- WIKI:GENERATED unit=unit-known-limitations-owui-audio-drop-ux-task-owui-audio-drop-001 -->
- **OWUI internal tool-call ceiling.** Some OWUI builds enforce a hard internal timeout on tool execution that `AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA` does not affect; `.env.example` sets that variable to 1800 but the OWUI-side ceiling can still fire. When it does, the tool completes server-side but the persona never sees the result. Use `scripts/transcribe_and_complete.sh` for files whose wall time exceeds the ceiling.
- **WEBUI_SECRET_KEY rotation invalidates OAuth tokens.** If `.env` is regenerated and the secret key changes, all MCP OAuth tools need re-authentication. The variable is set in `.env.example` with a placeholder.
- **Microphone voice input remains disabled.** `.env.example` leaves `OWUI_AUDIO_STT_ENGINE` empty, disabling auto-transcription of audio uploads and microphone recordings; this trade-off keeps audio accessible to the personas.

## Why

The tool server timeout is only one knob in a two-sided timeout path: `.env.example` raises Portal's client timeout, but an OWUI-side hard ceiling can still drop a completed result, so the surviving workaround is a script that completes transcription out of band. Recording the three audio-UX constraints together keeps the known failure modes and their environment variables in one place for an operator diagnosing a dropped file.
<!-- /WIKI:GENERATED -->

---

## Models Out of M4 Pro 64 GB Budget

<!-- WIKI:GENERATED unit=unit-known-limitations-models-out-of-m4-pro-64-gb-budget -->
The following models were evaluated and explicitly **refused** from the Portal 5 catalog. They exceed the M4 Pro 64 GB unified memory ceiling at the lowest quality-preserving quantization. Do not re-propose without a cluster scaling plan (P5_ROADMAP Stage 3 vLLM node). The refuse list is preserved in `coding_task/TASK_MODEL_REFRESH_V7.md`, and the newer April-2026 exclusions are recorded in `coding_task/TASK_MODEL_REFRESH_V8.md`.

**Guardrail**: before recommending any MoE model with total params over 100B on a 64 GB M4 Pro budget, compute the 4-bit weight footprint; if it exceeds 50 GB, refuse and reference this section. Mac Studio 128 GB+ is the path for these models.

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

## Why

Large-MoE marketing focuses on the small active-parameter count, which predicts decode speed but not residency, so the refusal record is written to short-circuit future re-proposals: the footprint figures are captured at decision time, and the 100B/50 GB guardrail turns the reasoning into a mechanical pre-check. Because these models are MLX-tier artifacts and never entered `config/backends.yaml`, the audit trail lives in the refresh task docs rather than the serving config.
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

## Why

The deterministic ranker must pick a capability before ranking its tools, because dispatch is capability-keyed and a tool-first choice structurally starves every `tools=[]` oracle-bearing option. Progressing from recon to an unattempted oracle-bound action is what makes the loop truthful — it can reach the capability that actually proves the objective — and the regression tests in `test_agent_core.py` pin that ordering so a future refactor cannot silently reintroduce the dead-end.
<!-- /WIKI:GENERATED -->

---

### V8 Catalog Deferred (insufficient hardware)

<!-- WIKI:GENERATED unit=unit-known-limitations-v8-catalog-deferred-insufficient-hardware -->
The following models were evaluated for the V8 catalog and deferred on hardware grounds. None of them is registered in `config/backends.yaml` or appears as a workspace in `config/portal.yaml`, so they are not routable today:

| Model | Est Size | Reason Deferred |
|-------|----------|-----------------|
| `sjakek/Nex-N2-Pro` | ~230GB | 397B total, 17B active — far exceeds 64 GB even at Q1. |
| `DeepSeek-R1-0528` (full) | ~400GB | 671B full model. The 8B distill variant `DeepSeek-R1-0528-Qwen3-8B` is in the catalog instead (the `auto-reasoning` workspace `model_hint`). |
| `Harness-1` (full capability) | n/a | Requires Chroma vector DB + external search state harness. |

`bench-nex-n2-mini` (the smaller N2 line) is present as a bench workspace, so the Nex family is partially covered by the mini variant. Any re-proposal of the deferred entries requires hardware beyond the 64 GB host or a cluster scaling plan.

## Why

Deferral here is a hardware ceiling, not a quality judgment — all three models were considered and excluded because the full-size weights cannot fit the M4 Pro 64 GB budget at any usable quantization. Recording them as deferred (rather than simply absent) tells a future operator they were already evaluated and why, preventing re-litigation, while the note on the N2-mini and R1-0528-8B variants points at what was actually adopted in their place.
<!-- /WIKI:GENERATED -->

---

### Wan 2.2 fp8_scaled Checkpoints Crash on Apple Silicon MPS (Video Generation Shelved)

<!-- WIKI:GENERATED unit=unit-known-limitations-wan22-fp8-scaled-checkpoints-crash-on-apple-silicon-mps -->
- **Description**: Every Wan 2.2 ComfyUI checkpoint published as `*_fp8_scaled.safetensors` (Comfy-Org/Wan_2.2_ComfyUI_Repackaged) crashes at inference time on this host's Apple Silicon MPS stack with an undefined fp8 dtype error during the dequantization of the fp8 diffusion weights. Confirmed live against the T2V-A14B high/low-noise pair and the S2V-14B checkpoint, each with all three `UNETLoader` `weight_dtype` options, failing the same way every time during model load. `wan2.2_ti2v_5B_fp16.safetensors` (TI2V-5B) is unaffected because it is full fp16, not fp8-quantized — it generated successfully end to end.
- **Impact**: T2V-A14B and S2V-14B are unusable on this hardware via their `_fp8_scaled` checkpoints. The only working alternative is full fp16/bf16, roughly 90GB combined and against the project's usual quantized-only model policy — a genuine hardware blocker rather than a quality tradeoff. `video_mcp.py`'s `_WAN22_T2V_A14B_WORKFLOW` was also independently corrected to the real two-expert MoE graph (two `UNETLoader` + two chained `KSamplerAdvanced`), matching ComfyUI's official reference workflow, in the same session and independent of the fp8 finding.
- **Decision (2026-07-29)**: Video generation is shelved for this project — Portal 5 operates ComfyUI **image** generation (via `mcp-comfyui`), not video. The `mcp-video` container is profile-gated and not part of the default `./launch.sh up` set; `deploy/portal-5/docker-compose.yml` documents that image and video were split into separate profiles so gating video does not take images down. The video workflow code is left in place — designed, not deleted — in case MPS fp8 support improves later, but nothing video-related should be treated as in operation.
- **Mitigation**: None pursued. If video generation is revisited, first check whether a newer PyTorch/comfy_kitchen release fixes MPS fp8 support, then fall back to the fp16/bf16 downloads.

## Why

The fp8_scaled checkpoint family is the standard published form of Wan 2.2, and it fails on MPS at the dequantization step — a PyTorch/comfy_kitchen platform gap, not a workflow bug. Shelving video rather than carrying a broken, unquantized 90GB path keeps the fleet policy consistent, while splitting the compose profiles preserves image generation, which was never the problem. The corrected workflow and the decision are recorded so the shelving is reversible when MPS support lands.
<!-- /WIKI:GENERATED -->

---

### Qwen-Image Apple Silicon Working Routes and Constraints

<!-- WIKI:GENERATED unit=unit-known-limitations-qwen-image-bf16-crashes-on-apple-silicon-mps -->
- **Memory constraint**: The original Qwen-Image-2512 bf16 diffusion and text-encoder pair needs ~57.4GB of static weights. On this 64GB unified-memory host, Docker and loaded Ollama models leave far less free memory than nominal capacity; an unguarded load exhausted host memory and rebooted the machine.
- **Memory-safe configuration**: `qwen-image-2512` uses `qwen_image_fp8_e4m3fn.safetensors` plus `qwen_2.5_vl_7b_fp8_scaled.safetensors` (filenames configured in `portal/modules/media/tools/comfyui_mcp.py` and pulled by `scripts/lib/services.sh`). Admission estimates live in `portal/modules/media/tools/_admission.py`: 38.0 GB for the base model, 39.0 GB for Lightning, 38.0 GB for edit-2509, and 60.0 GB for edit-2511, each annotated with the incident rationale.
- **Black-output root cause and fix**: A global `--force-fp16` launch override bypassed QwenImage's declared bf16/float32 compute, producing all-NaN latents before VAE decode. Removing the override from the launcher restored bf16 compute; the current launchd plist generated by `scripts/lib/services.sh` (`com.portal5.comfyui`) carries no such override.
- **Remaining limitation — Qwen-Image-Edit-2511**: The bf16 edit checkpoint is estimated at 60.0 GB in `_admission.py`, so admission control refuses it on this host. The smaller official variants remain unusable on this MPS stack (fp8 dequantization failure and unsupported MPS ops requiring slow CPU fallback). Use a larger or remote CUDA host for 2511.
- **Serving invariant**: The public 2509 and 2511 names map to their actual checkpoint generations; 2509 is not silently served as 2511. The tool manifest and HTTP dispatch endpoints retain `image_url` so edit calls reach the workflow.
- **Launcher invariant**: Do not use a global ComfyUI inference-dtype override. Model families declare different supported compute dtypes, and a global fp16 flag can turn an otherwise safe quantized checkpoint into numerically invalid compute.

## Why

Qwen-Image is memory- and dtype-sensitive in ways that generic image tooling masks: a global fp16 override silently corrupts its compute, and its real working peak is set by activation overhead, not weight size. The admission map encodes the measured figures so a job cannot be admitted on a host that will OOM, and the launcher invariant documents the specific flag that caused the black-image incident so it is not reintroduced.
<!-- /WIKI:GENERATED -->

---

### Spine Code-Surface Coverage Is Partial (Ratchet, Not a Cliff)

<!-- WIKI:GENERATED unit=unit-known-limitations-spine-code-coverage-ratchet -->
- **ID**: P5-SPINE-COVERAGE-001
- **Status**: RESOLVED — TASK_WIKI_ZERO_DEBT_V1 drove the uncovered set to empty and deleted the baseline; BR is now an absolute 100% gate with nothing to tolerate.
- **Description**: `validate_system.py` check **BR** (spine code coverage), backed by `portal/platform/wiki/coverage.py`, measures the fraction of eligible Python code surfaces cited by at least one non-aggregate, gate-passing wiki unit. At the time the gate landed (v8.0.0), coverage was about 7.6% (46 of 605 eligible files, per `coverage.py`'s module docstring). Aggregate `unit-code-*` units (auto-seeded by `seed_code.py`, which cites only the first five files of a subsystem while titling itself with the full count) are deliberately excluded from the numerator — counting them would grade the generator against its own output.
- **Mechanism**: The gate started as a ratchet — a pinned uncovered-set baseline file and CI failed only when that set *grew*. TASK_WIKI_ZERO_DEBT_V1 paid the debt down to zero: covering units were authored for every remaining surface, and once 100% was reached the baseline file was deleted. BR became absolute: any uncovered eligible Python surface was an unconditional FAIL, with no baseline to absorb it. TASK_PORTAL_SIMPLIFY_V1 Phase R3 then ended the per-file era: coverage became manifest-driven (`config/spine_surfaces.yaml` names each surface, its globs, and its covering unit), collapsing ~570 per-file mirror units into ~30 subsystem surfaces. BR now asserts every declared surface has a gate-passing unit citing its globs, and every eligible `.py` file falls under a declared surface.
- **Current state**: Manifest coverage is 100% — every declared surface is documented by a gate-passing unit and every eligible `.py` file is matched by a declared surface glob. The wiki engine stays per-file as the extraction-guarantee boundary (check AJ); a new file there fails BR until deliberately registered in the manifest.
- **Next action**: Keep the discipline. New code inside a documented surface costs nothing; new code outside one must force a deliberate manifest entry — BR fails outright until it does.

## Why

The ratchet exists to fix an authority inversion: docs generated from units were certified current by comparing them with the very units they came from, so nothing proved new code arrived documented. Measuring code citations from non-aggregate units only, and failing when the uncovered set grows, forces the forward direction — every new surface must earn its coverage. Re-pinning to 100% does not retire the gate; it changes its job from paying down debt to holding the line.
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

## Why

The router warmup pins the model with `keep_alive: -1`, which is load-bearing: without it the router re-cold-loads on every heavy inference request. But the same pin becomes a memory bug when `options.num_ctx` is omitted, because Ollama then reserves the model's full context window times the parallel slots — tens of GiB for a small model — which forces the scheduler to evict the router it was trying to keep warm. Matching the warmup context to the real routing call and the workspace limit is what makes the pin actually safe.
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

## Why

The direct reproduction proved the same model was reliable with one tool and intermittent with the full multi-tool payload, so the failure is sampling-driven ambiguity under schema load, not wiring. Narrowing the exposed schema to one required tool for explicit side-effect intents removes the ambiguity at its source without buffering the streaming hot path, and the allow-list plus retained `tool_choice=none` behavior keeps the selector from ever granting a capability it did not already have.
<!-- /WIKI:GENERATED -->

---

### Fara1.5-27B CUA Preflight — Correct Perception, Unreliable XML Tag Closure (Open, Follow-On Scoped)

<!-- WIKI:GENERATED unit=unit-known-limitations-fara-cua-tag-closure -->
- **ID**: P5-FARA-CUA-001
- **Status**: Open — TASK-BATCH-BENCH-001 Part C intake finding. Not blocking; scoped to a
  named follow-on below.
- **Description**: `portal5/fara1.5-27b:q4_k_m` (`microsoft/Fara1.5-27B`, imported via
  `hf_hub_download` + `ollama create` with a second `FROM` line for the
  `mmproj-Fara1.5-27B-f16.gguf` vision projector — `ollama show` confirms the projector loaded:
  `clip`, 460.73M params) correctly perceives a synthetic 1440x900 login-page screenshot fixture
  and correctly reasons about the CUA task (identified the username/password fields, correctly
  triggered a Case-1 "missing user information" critical point per its own trained pause logic)
  in every sample tested. But the tool call itself lands in the `thinking` field rather than
  `content` or Ollama's structured `tool_calls`, in the model's native
  `<tool_call><function=computer_use><parameter=KEY>value</parameter>...</function></tool_call>`
  XML dialect — because this is a from-GGUF custom import with no `TEMPLATE` override, so the
  GGUF's own embedded chat template drives generation and Ollama's built-in tool-call parser
  does not recognize this dialect as structured `tool_calls`. Across 4 raw `temperature=0.0`
  samples: 1 was a complete, well-formed block (action `pause` — not in the model card's
  documented 17-action vocabulary, a possible near-synonym for `pause_and_memorize_fact` or
  `ask_user_question`); 3 omitted the closing `</parameter>` tag on the `action` field, causing
  the value to run on into the next `<parameter=` tag (`bench_fara_cua_probe.py`'s parser
  isolates this correctly as a malformed/unsupported action rather than silently absorbing the
  bleed-through text).
- **Reproduced directly** (bypassing any harness, isolating the model via raw `/api/chat`
  calls): confirmed across both a bare system-prompt-only request (which degenerated into a
  `</think>`-tag repetition loop without the `tools` field present) and a request with the
  `computer_use` tool declared via Ollama's standard OpenAI-style `tools` array (which produced
  the coherent, correctly-reasoned XML-dialect responses described above). The `tools` field is
  necessary for coherent output; it does not by itself make tag closure reliable.
- **Verdict**: Real capability confirmed (screenshot perception, correct CUA reasoning, correct
  critical-point handling), format brittleness noted as the open caveat. This clears the bar the
  task set for scheduling the bounded MagenticLite follow-on (`TASK_FARA_MAGENTIC_BENCH_V1`,
  not built in this task) — MagenticLite ships Fara's actual trained chat template and grammar
  constraints, which this ad-hoc Ollama import deliberately does not attempt to replicate.
- **Not attempted here**: writing a custom Ollama `TEMPLATE` to force well-formed native
  `tool_calls` extraction for this XML dialect. That is exactly the class of harness investment
  MagenticLite already provides and TASK-BATCH-BENCH-001 scoped as intake-only.

## Why

The direct raw-`/api/chat` reproduction (bypassing any pipeline or probe-script logic) is what proves this is a chat-template/extraction gap rather than a Fara capability gap or a probe bug: the same model, same fixture, same question produces coherent, correctly-reasoned CUA output every time, but the *closure* of that output's XML tags is unreliable under the generic GGUF template. Recording the exact XML dialect and the 1-well-formed/3-malformed sample split here — rather than leaving it only in the gitignored `tests/benchmarks/results/fara_cua_probe_*.txt` artifacts — is what lets a future session (or the MagenticLite follow-on) start from "known to work, known brittleness point" instead of re-deriving both facts from scratch.
<!-- /WIKI:GENERATED -->

---

### Antares-1b Role Probe — Gated on Cisco HF Approval (Open, Deferred)

<!-- WIKI:GENERATED unit=unit-known-limitations-antares-gate-e1-gated-download -->
- **ID**: P5-ANTARES-GATE-E1
- **Status**: Open, honest-BLOCKED — root cause required two corrections before landing on the
  real one. TASK-BATCH-BENCH-001 Part E finding.
- **Correction history** (kept because each wrong turn is a real lesson): pass 1 concluded
  "gated, unavailable" from `ollama list` alone, without attempting a pull — wrong, ungated
  community GGUF conversions exist. Pass 2, after actually pulling and probing two independent
  quants and seeing garbage chat output (`@@@@@@@@@@@@@@@@`) on both, concluded "arch mismatch"
  (`granitemoehybrid` mapped down to plain `granite`) — also wrong, caught by a direct question
  prompting a proper isolation test.
- **Actual root cause (verified)**: `ollama generate --raw` (bypasses the chat template
  entirely, sends plain text) produces **perfectly coherent output** — "The capital of France
  is" → "Paris. 2. The largest city in the world by population is Tokyo..." — proving the
  underlying weights, quantization, and `granite`-mapped forward pass are all fine. The garbage
  appears *only* when the model's own embedded chat template is applied. Isolated further:
  feeding the exact literal special-token markup the template emits
  (`<|start_of_role|>user<|end_of_role|>The capital of France is<|end_of_text|>\n<|start_of_role|>assistant<|end_of_role|>`)
  through `--raw` reproduces the identical garbage — so the bug is specifically in how
  Granite-4's `<|start_of_role|>`/`<|end_of_role|>`/`<|end_of_text|>` special tokens are
  registered/embedded in these GGUF conversions, not in the base model weights or in llama.cpp's
  architecture support for `granite`/`granitemoehybrid`. Reproduced identically across two
  independently-uploaded quants (`hf.co/HolkViking/antares-1b-Q4_K_M-GGUF`,
  `hf.co/DevQuasar/fdtn-ai.antares-1b-GGUF`), which points at either a shared upstream
  conversion-tool bug for this token family, or a subtly broken special-token embedding row in
  the base model that every converter faithfully reproduces.
- **Why still blocked**: `TASK_ANTARES_ROLE_PROBE_V1.md`'s Phase 0.4 tool-call smoke test goes
  through `/api/chat` (the template path), so it fails the same way regardless of the corrected
  diagnosis — Experiments A and B both need coherent chat-formatted tool-calling to run.
  Hand-authoring a working custom Ollama `TEMPLATE` (bypassing the broken embedded one) would
  fix this, but is real reverse-engineering work — deferred as a follow-on, the same call made
  for Fara1.5-27B's XML tool-call dialect in this same batch-bench task, not attempted here.
- **Unblocking**: either a GGUF conversion with correctly-registered special tokens, or a
  hand-authored Ollama `TEMPLATE` override proven against the `--raw` isolation test above
  (garbage → coherent) before trusting any chat-mode result.

## Why

Two wrong conclusions in a row on the same finding is exactly the failure mode this note exists to prevent recurring: the first (assumed gate) skipped verification entirely, the second (assumed arch) stopped at the first plausible-looking `ollama show` signal instead of isolating chat-template vs. raw-completion behavior. The `--raw` isolation test that finally pinned this down is cheap and repeatable — recording it here means a future session (or the deferred custom-TEMPLATE follow-on) starts from a verified root cause instead of either stale wrong answer.
<!-- /WIKI:GENERATED -->

---

### Serena MCP Air-Gap LSP Staging (Not Applicable On This Box, Deferred For Air-Gapped Deploys)

<!-- WIKI:GENERATED unit=unit-known-limitations-serena-gate-d1-airgap-staging -->
- **ID**: P5-SERENA-GATE-D1
- **Status**: Not applicable on this box; deferred as a note for a genuinely air-gapped
  deployment. TASK-BATCH-BENCH-001 Part D finding.
- **Description**: The `serena` `mcp_fleet` entry (`config/portal.yaml`) launches via
  `uvx --from git+https://github.com/oraios/serena serena start-mcp-server`, which fetches the
  Serena package from GitHub and its LSP backend (`pyright`, via a further `uvx pyright==1.1.403`
  invocation) from PyPI on first activation. TASK-BATCH-BENCH-001's GATE-D1 flagged this as a
  potential blocker on an air-gapped box, where these must be pre-staged rather than fetched live.
  This box has live internet access throughout the whole batch-bench session (confirmed by ~60GB
  of HuggingFace model pulls across Parts A-C) — `uvx` fetched and built `serena-agent` plus
  `pyright-langserver` cleanly on first `activate_project` call (see
  `results/serena_refactor_bench_20260809.md`), so GATE-D1 did not block anything here.
- **For an actual air-gapped deployment**: pre-stage the `oraios/serena` package (e.g. a vendored
  wheel or mirrored pip index) and a `pyright` binary matching the pinned `1.1.403` version (or
  configure Serena's `--language-backend` for an alternative already-installed language server),
  then confirm `uvx --from git+https://github.com/oraios/serena serena start-mcp-server --help`
  succeeds with network access disabled before relying on the fleet entry in production.

## Why

Recording that GATE-D1 was checked and found not-applicable — rather than silently skipping the check because it happened to not matter — is what keeps this a real gate for any future deployment of this fleet entry onto hardware that isn't already known to have live internet, instead of an assumption nobody re-verifies.
<!-- /WIKI:GENERATED -->

---

### Ollama GPU Overhead Reservation (Resolved)

<!-- WIKI:GENERATED unit=unit-known-limitations-ollama-gpu-overhead-ceiling -->
- **ID**: P5-OLLAMA-GPU-OVERHEAD-001
- **Status**: Resolved 2026-08-10 (TASK-BATCH-BENCH-002 Part A). Not a bug in Ollama or the fleet — a misconfigured safety margin, corrected in place.
- **Description**: `com.portal5.ollama.plist`'s `OLLAMA_GPU_OVERHEAD` was set to `42949672960` (40GiB), intended as coexistence headroom so Ollama and oMLX never collide and crash the box on this 64GB M4 Pro. In practice this overhead is subtracted from a largely fixed Metal working-set ceiling (~56GiB on this hardware), not from live free memory — freeing oMLX's loaded models and even a full daemon restart left Ollama's reported "available" figure completely unchanged (`model requires 19.7 GiB but only 15.5 GiB are available (after 40.5 GiB overhead)`). At 40GiB, the reservation capped **any single Ollama model at ~15.5GiB regardless of oMLX's actual state** — a real problem, since the fleet already runs 20-30GB-class models (Muse-Glimmer-30B, Deepwen-3.6, Qwen3-Coder-30B-A3B) routinely.
- **Fix**: lowered to `21474836480` (20GiB) in the plist, reloaded via `sudo launchctl bootout system/com.portal5.ollama && sudo launchctl bootstrap system /Library/LaunchDaemons/com.portal5.ollama.plist` (note: `launchctl kickstart -k` restarts the process but does **not** re-read the plist's `EnvironmentVariables` — a full bootout/bootstrap is required to pick up an env change). 20GiB still reserves real coexistence headroom (sized off oMLX's own observed footprint, ~22-29GB for its largest single models) without starving Ollama's own budget down to a sliver. Verified: Muse-Glimmer-30B (19.7GiB) loads cleanly post-fix.
- **If this recurs**: check `ps eww -p <ollama-serve-pid> | grep OLLAMA_GPU_OVERHEAD` against the current plist value first — a mismatch means the daemon needs a full bootout/bootstrap, not just a kickstart.

## Why

This is a permanent, box-level constraint that silently caps every future large-model bench on this host, not something scoped to the Muse-Glimmer bench that surfaced it. The kickstart-vs-bootstrap distinction is the actual gotcha (identical-looking "restart" commands, only one re-reads env vars) — a future session hitting the same static "N GiB available" error after changing an Ollama plist env var should find this before re-diagnosing it as a stale-cache or live-memory problem again.
<!-- /WIKI:GENERATED -->

---

### Ling-3.0-flash TurboQuant Build + Memory Gates

<!-- WIKI:GENERATED unit=unit-known-limitations-ling-3-0-flash-turboquant-memory-gates -->
- **ID**: P5-LING30-GATE-C
- **Status**: Deferred; not benched. TASK-BATCH-BENCH-002 Part C finding.
- **Description**: `AtomicChat/Ling-3.0-flash-GGUF` (`bailingmoe3` MoE, 124B/5.1B-active, hand-placed Atomic Dynamic quants) was gated behind two checks before any bench attempt, both of which failed on this box (2026-08-10):
  - **GATE-C1 (memory headroom)**: the smallest viable rung is ~`AD-IQ2_M` at 49GB. This 64GB box's realistic single-model ceiling, even after the `OLLAMA_GPU_OVERHEAD` fix (see `P5-OLLAMA-GPU-OVERHEAD-001`), leaves only ~36-44GB — a 49GB load would need the entire MCP fleet + Docker VM evicted, an operator call this task correctly declined to make unilaterally.
  - **GATE-C2 (custom build)**: these GGUFs require AtomicChat's TurboQuant llama.cpp build (`bailingmoe3` upstream + their bugfixes), not stock Ollama. Only stock `llama-server` (`/opt/homebrew/bin/llama-server`) is present; no TurboQuant build is staged, and building one is explicitly out of scope for this task.
- **Value if unblocked**: the Atomic Dynamic quant-methodology datapoint (hand-placed bits, card claims 31-41% closer to BF16 than stock quants) is the actual interest here, more than a fleet slot — a future attempt should capture a KL/quality read, not just t/s.

## Why

Recording both gate failures with their specific numbers (49GB rung, no TurboQuant build present) means a future session doesn't have to re-derive whether this candidate is worth attempting — it can check whether either constraint has changed (more RAM, a TurboQuant build becomes available) before re-evaluating, rather than re-running the same failed preflight.
<!-- /WIKI:GENERATED -->

---
