# Test trim phase 2 — live exerciser plan

Snapshot: `b75c16d8419e0f324585eabb709bb0f900124806` (`lane/trim-p2-plan`). This is a plan-only read of the current HEAD. The four phase-1 lanes are separate worktrees and their edits are not included here; recalculate the inventory after those lanes merge and before assigning phase-2 deletion lists.

The operator direction is to keep a small offline merge gate for contracts, parsers, and pure logic, while moving product behavior checks to live exercisers. A passing offline check remains a merge gate, not product evidence. No live command, service, UAT, benchmark, or acceptance driver was run while preparing this plan.

## 1. Inventory and measurement

### Measurement rules

- Count tracked Python files named `test_*.py` under `tests/unit/`, `tests/wfe/tests/`, `tests/security/`, and `tests/benchmarks/`. These are the offline test modules in this inventory. `tests/wfe/graded/**/test_*.py` are separate WFE workload payloads, not harness unit tests. The other Python files under `tests/benchmarks/` are executable harness code, not pytest modules.
- Physical lines are `len(path.read_text().splitlines())`, including blank and comment lines.
- For each file, an indicator line contains one or more of these case-insensitive tokens: `mock`, `patch`, `monkeypatch`, `MagicMock`, `AsyncMock`, `Mock`, `mocker`, or `fake`. Density is indicator lines divided by physical lines. A file is called mock-heavy at **5% or more**. The share is mock-heavy files divided by files in that primary area. This is a source-text proxy, not an AST, test-execution, or coverage measurement.
- Assign every offline test file once to a primary area by path and filename. This keeps the summary totals disjoint. The MCP roster table below is a crosswalk and can refer to the same file from more than one module; its counts are not additive to the primary-area totals.

The scoped offline inventory is **648 files / 166,217 lines**. **184/648 (28.4%)** meet the mock-heavy threshold; those whole files contain **56,093 lines**. This is only a candidate ceiling for deletion. Pure assertions in a mock-heavy file may still belong in the offline gate.

| Primary product area | Test files | Lines | Mock-heavy files | Lines in heavy files |
|---|---:|---:|---:|---:|
| Pipeline/router and tool orchestration | 70 | 34,258 | 35/70 (50.0%) | 17,758 |
| Inference engines and serving | 37 | 12,791 | 20/37 (54.1%) | 5,398 |
| Security/hunt/Bully | 175 | 33,971 | 25/175 (14.3%) | 5,566 |
| Compliance | 102 | 26,339 | 17/102 (16.7%) | 3,700 |
| WFE harness (offline tests plus selected unit tests) | 84 | 25,385 | 32/84 (38.1%) | 12,297 |
| Bench harness (offline tests plus selected unit tests) | 14 | 2,801 | 6/14 (42.9%) | 1,325 |
| Documents MCP | 5 | 2,038 | 4/5 (80.0%) | 1,579 |
| Execution/sandbox MCP | 2 | 233 | 1/2 (50.0%) | 192 |
| CAD and rendering | 15 | 1,961 | 5/15 (33.3%) | 482 |
| Proxmox MCP | 1 | 126 | 1/1 (100%) | 126 |
| Memory MCP | 4 | 536 | 3/4 (75.0%) | 401 |
| RAG MCP | 3 | 688 | 3/3 (100%) | 688 |
| Research/search adjacent tests | 2 | 296 | 1/2 (50.0%) | 158 |
| Wiki MCP | 6 | 1,391 | 2/6 (33.3%) | 264 |
| Audio/transcription adjacent tests | 1 | 283 | 0/1 (0%) | 0 |
| Media admission | 1 | 202 | 1/1 (100%) | 202 |
| CLI/config/validation | 29 | 5,824 | 6/29 (20.7%) | 1,308 |
| Security review service | 18 | 3,383 | 0/18 (0%) | 0 |
| Security review evaluation | 16 | 2,375 | 1/16 (6.2%) | 53 |
| Other shared platform/support | 63 | 11,336 | 21/63 (33.3%) | 4,596 |

The primary-area assignment includes 429 `tests/unit/test_*.py`, 61 `tests/wfe/tests/test_*.py`, 157 `tests/security/**/test_*.py`, and the single `tests/benchmarks/test_empty_retry.py`. The WFE pytest tree alone is 61 files / 20,250 lines; the 33 files under `tests/wfe/graded/` add 927 lines of real task payloads and are retained workload inputs, not mocks to replace. The benchmark Python tree is 88 files / 26,128 lines, but only `test_empty_retry.py` is named as a pytest test. The other 87 files / 26,061 lines are benchmark runners, probes, scorers, and reporting code. Their line-by-line inventory is in Appendix C; do not treat that harness LOC as deletable offline test LOC.

Appendix A lists every counted offline test file with physical lines and measured indicator density. Appendix B lists the WFE workload payloads. Appendix C lists the benchmark Python tree. MCP-specific file references in the next table are deliberately qualified where a test only covers a shared parser, score function, or admission gate rather than the service's live path.

### MCP module crosswalk

The current `config/portal.yaml` roster has 33 `mcp_fleet` entries. `pipeline=False` means the module is not exposed to the OWUI/Pipeline route in this snapshot; do not claim an OWUI test for it or change the roster as part of a trim lane. `default_enabled=False` means a lane must not silently enable that module to manufacture a live result. The module-specific inventory numbers below are direct or adjacent filename matches; the full disjoint file inventory remains in Appendix A.

| `mcp_fleet` ID | Current path | Offline files found at HEAD | Current live coverage and phase-2 owner |
|---|---|---|---|
| `filesystem` | IDE only (`pipeline=False`) | None by module name; shared MCP/client contracts only | NEW `scripts/proofs/ide_mcp_matrix.py --case filesystem`; exercise the configured IDE MCP client against a scoped file and read back path/content/hash. |
| `fetch` | IDE only | None by module name | NEW IDE MCP matrix case; fetch an allowlisted real URL and read back the source URL plus returned content signature. |
| `git` | IDE only | None by module name | NEW IDE MCP matrix case; read a real repository status/diff and verify the returned repo/path. Do not mutate the shared checkout. |
| `serena` | IDE only | None by module name | NEW IDE MCP matrix case; resolve a real symbol and read back repository path plus symbol span. |
| `docker` | IDE only | None by module name | NEW IDE MCP matrix case; perform a read-only inspect/list and read back container/image identity. |
| `music-minimax` | Pipeline exposed; `default_enabled=False` | None direct | Existing S07 is a direct component acceptance; UAT has historical audio output rows. NEW OWUI matrix case only when already enabled; read back the generated audio artifact and metadata. |
| `mflux` | Pipeline exposed; `default_enabled=False` | `test_media_admission.py` (202 lines), shared admission gate only | Existing S30 is component acceptance. NEW OWUI matrix case when already enabled; read back the generated image artifact and dimensions. |
| `video_mlx` | Pipeline exposed; `default_enabled=False` | `test_media_admission.py` (202 lines), shared admission gate only | Existing S31 is component acceptance. NEW OWUI matrix case when already enabled; read back the completed video job/artifact and metadata. |
| `documents` | Pipeline exposed | 5 files / 2,038 lines; 4/5 mock-heavy. `test_document_mcp.py`, `test_attachment_paths.py`, `test_documents_read_refusal.py`, `test_download_link_safety.py`, `test_followup_artifact_tool.py` | Existing S04 exercises the service; UAT A-01 is an OWUI document/RAG path. NEW OWUI matrix case must show the actual document tool in the trace and read back extracted fixture text/artifact. |
| `execution` | Pipeline exposed | 2 files / 233 lines; 1/2 mock-heavy. `test_code_sandbox_sessions.py`, `test_sandbox_network_flag.py` | Existing S18 is lab acceptance; OWUI UAT TV-01/TV-05/TV-06 checks returned calculations. NEW matrix case reads the exact sandbox output and verifies a scoped effect; keep network isolation as a negative live case. |
| `whisper` | Pipeline exposed | `test_mlx_speech_asr_gate.py` (77), `test_mlx_transcribe_openai_stt.py` (150), `test_transcribe_diarize.py` (283); these are adjacent speech/transcription tests, not proof of the Whisper MCP route | Existing S09 is direct STT acceptance. NEW OWUI matrix case reads back transcript text and timestamps from a known audio input, and trace proves which tool/server ran. |
| `tts` | Pipeline exposed | None direct by module name | Existing S08 is component acceptance; UAT has historical TTS artifact rows. NEW OWUI matrix case reads back a non-empty audio artifact and duration/format metadata. |
| `security` | Pipeline exposed | Security route/autoupdate tests are in the Security/hunt primary group; `test_security_autoupdate.py` (249), `test_security_call_model_route.py` (97), `test_security_corpus_contract.py` (21) | Existing S16 is direct service acceptance; security/hunt OWUI path is owned by `scripts/proofs/owui_hunt_chat.py`. Use a separate safe classification case for the security MCP and read back its tool call/result. |
| `memory` | Pipeline exposed | 4 files / 536 lines; 3/4 mock-heavy. `test_graph_memory_eg2.py`, `test_graph_memory_extract.py`, `test_memory_gate_headroom.py`, `test_memrag_native_rest_parity.py` | Existing S70 performs a real tagged remember/recall/forget round-trip; UAT A-08 is an OWUI cross-chat recall case. NEW assertion reads the specific tool trace and returned record ID, then verifies cleanup. |
| `rag` | Pipeline exposed | 3 files / 688 lines; 3/3 mock-heavy. `test_rag.py`, `test_rag_kb_list.py`, `test_rag_multimodal.py` | Existing S13/S70 cover component health; UAT A-01/A-02 cover OWUI retrieval behavior. NEW assertion reads actual retrieved source/collection identity from the trace/store. |
| `research` | Pipeline exposed | `test_research_probe_scoring.py` (138) is scorer-only; `test_web_search_fallback.py` (158) is router fallback, not MCP execution | Existing S12 and S70 check component paths. NEW OWUI matrix case reads a real returned URL/source and proves the research tool call in trace. |
| `browser` | IDE only (`pipeline=False`) | `test_uat_browser.py` (176) tests the UAT browser frontend, not Browser MCP | Existing S42 is component acceptance. NEW IDE MCP matrix case reads the target URL/title and one observable page action; no OWUI claim while the module is IDE-only. |
| `mlx_transcribe` | Pipeline exposed | The same 3 adjacent transcription tests above (510 lines total; 2/3 mock-heavy) | Existing S09. NEW OWUI matrix case reads transcript text/segments and the actual `mlx_transcribe` tool span. |
| `cad_render` | Pipeline exposed | 15 files / 1,961 lines; 5/15 mock-heavy. `test_cad_*`, `test_scad_*`, `test_b123d_*`, `test_cam_lds_extract.py`, `test_mesh_printability.py` | Existing S17 is component acceptance. NEW OWUI matrix case reads the real PNG/STL/OBJ artifact, dimensions, and mesh validation result. |
| `proxmox` | IDE only (`pipeline=False`) | `test_proxmox_mcp.py` (126 lines; mock-heavy) | S18 is lab-exec acceptance, not proof of this module. NEW IDE MCP case uses a read-only inventory call and reads back the real VM/node identifier. |
| `pipeline` | Pipeline exposed | Pipeline/router primary group plus shared transport tests (`test_mcp_http_client.py` 635, `test_mcp_endpoints.py` 268) | Existing `portal trace --section workspaces` checks the Pipeline route directly; S60 checks tool-loop behavior. NEW OWUI route-trace proof reads actual served route and tool spans. |
| `mitre` | Pipeline exposed | `test_portal_mitre_mcp.py` (199 lines; no mock-heavy indicator) | No module-specific acceptance section found. NEW OWUI matrix case reads a real technique/entity result and citation/source identifier. |
| `detections` | Pipeline exposed | Adjacent normalizer tests: `test_detector_precision.py` (183), `test_hec_ship_dns_error.py` (71), `test_siem_collect_normalize.py` (323); 3 files / 577 lines, 1/3 heavy | `portal trace --section lab` checks Splunk auth/query/labeled event; it does not prove this MCP tool path. NEW OWUI case reads the actual query ID and labeled result rows from the real lab. |
| `wiki` | Pipeline exposed | 6 files / 1,391 lines; 2/6 mock-heavy. `test_seed_facts.py`, `test_wiki_archive.py`, `test_wiki_core.py`, `test_wiki_quality.py`, `test_wiki_search_ranking.py`, `test_wiki_writeback.py` | Existing information-access probes are partial. NEW OWUI matrix case reads the cited unit ID and returned source text. |
| `binresearch` | IDE only (`pipeline=False`) | None direct by module name | No live section found. NEW IDE MCP case analyzes a safe checked-in binary/sample and reads back file identity plus extracted findings. |
| `vulnintel` | Pipeline exposed | No module-specific offline test found | No module-specific live acceptance found. NEW OWUI matrix case reads a real CVE/source/timestamp tuple and proves the tool span. |
| `icsot` | Pipeline exposed | No module-specific offline test found | S18 is generic lab-exec, not ICS/OT MCP coverage. NEW OWUI matrix case reads a real lab asset/protocol observation and its provenance. |
| `compliance` | Pipeline exposed | 102 files / 26,339 lines; 17/102 mock-heavy. See compliance primary group | Existing S10c and compliance UAT cases drive live models, but S10c sends directly to Pipeline. NEW `scripts/proofs/owui_compliance_grounding.py --case cip-003-r1-2-6` drives Open WebUI and reads the actual cited source/version and compliance receipt. |
| `detection` | Pipeline exposed | No module-specific file found; adjacent detector/HEC/SIEM tests above | No separate live case found. NEW OWUI matrix case reads an actual detection result/event identifier and source provenance. |
| `context7` | IDE only (`pipeline=False`) | None direct by module name | NEW IDE MCP case only; read back the exact library/version/documentation URL. No OWUI route exists in this snapshot. |
| `data` | Pipeline exposed | `test_realuse_fixture_paths.py` (245) and `test_eval_scope.py` (445) exercise `data_mcp` with temp/scoped state; not live-store evidence | WFE live rig probes the data MCP directly. NEW OWUI matrix case writes one scoped test row, reads it back through the product path, then deletes and verifies it is gone. |
| `netforensics` | Pipeline exposed | No module-specific offline file found | No live acceptance section found. NEW OWUI matrix case reads a real lab PCAP/session identifier, extracted fields, and source offsets. |
| `review` | Pipeline exposed | 18 review + 16 review-eval files / 5,758 lines; 1/34 mock-heavy | Existing `scripts/proofs/owui_hunt_chat.py` proves one real security-reviewer → review MCP hunt lifecycle. Keep it as owner for the hunt path; additional review lanes must read their own durable receipt/state. |

The shared MCP/config contract tests are not module behavior proof: `test_mcp_http_client.py` (635 lines), `test_mcp_endpoints.py` (268), `test_mcp_fleet_single_source.py` (377), `test_mcp_vendor_smoke.py` (66), and `test_native_mcp_service.py` (218) pin transport, endpoint, roster, or process contracts. Keep those deterministic assertions in the offline merge gate.

## 2. Exerciser ownership

| Area | Existing exerciser and what it proves | Phase-2 live owner and proof to read back | Offline merge-gate tests to retain |
|---|---|---|---|
| Pipeline/router | `uv run portal trace --json --section workspaces` sends workspace calls to Pipeline and reads Pipeline traces; S03/S21 acceptance also calls Pipeline directly. | NEW `scripts/proofs/owui_route_trace.py --workspace auto --case route-smoke`: submit through OWUI `/api/chat/completions`, find that turn in `/v1/trace`, and assert the served workspace/model/backend, terminal usage, and any tool spans. The exact trace must match the OWUI turn timestamp/workspace. | Routing selection, request schemas, retries, streaming/SSE parsing, tool-loop limits, and trace serialization. |
| Inference engines | `portal trace --section engines` checks engine endpoints; `--section workspaces` also executes a Pipeline workspace. Neither starts through OWUI. | Same new `owui_route_trace.py`, with one case per currently seated Ollama and oMLX route. Read the trace's actual served engine/model and usage; require the configured seat identity and a completed engine call. Do not promote engine-health output to inference proof. | Engine request builders, response parsers, model-card/config loaders, capacity/failover rules, and deterministic transport contracts. |
| MCP modules | Acceptance S04/S07-S09/S12-S18/S30-S31/S42/S60/S70 has service-level or direct-Pipeline probes. `tests/uat/runner.py` uses the OWUI browser route but `pipeline_tool_called` is an aggregate counter, not a per-tool receipt. | NEW `scripts/proofs/owui_mcp_matrix.py --case <mcp_fleet-id>` for Pipeline-exposed IDs; one case/lane per module. Submit via OWUI, read the matching `/v1/trace` or `exec_audit` event, then read the module-specific artifact, row, job, or source ID. Use `scripts/proofs/ide_mcp_matrix.py --case <id>` for IDE-only IDs (`filesystem`, `fetch`, `git`, `serena`, `docker`, `browser`, `proxmox`, `binresearch`, `context7`); read back the actual tool result and a scoped effect. Never enable a disabled service just to make the case run. | Request/response schemas, parser/serializer behavior, capability filtering, safety guards, and stable pure logic for each MCP. |
| Security/hunt/Bully | `portal trace --section lab` checks live Splunk auth/query/labeled-event hops. `scripts/proofs/owui_hunt_chat.py` is the existing full OWUI → Pipeline → `security-reviewer` → review MCP proof, with a real job ID, terminal status, leads, case, and answer citations. | Keep the hunt proof for its covered path. Add one `owui_mcp_matrix.py --case security` safe classification case and one read-only real-lab case per security lane. Read tool outputs, query/job IDs, evidence provenance, and final verdict; `PARTIAL`/missing output stays a failure or inconclusive result. | Truth walls, parsers, evidence attribution, calibrated scoring, schema and state-machine contracts. |
| Compliance | S10c uses Pipeline chat; `tests/portal5_uat_driver.py` is OWUI-mediated. `tests/benchmarks/compliance_stream_p0_live_capture.py` and P3c capture scripts exercise live compliance paths but are not OWUI proofs. | NEW `scripts/proofs/owui_compliance_grounding.py --case cip-003-r1-2-6`: real OWUI chat on `auto-compliance`, read Pipeline trace and the returned source/version/citation from the live compliance corpus/store. Receipt must identify the source actually read; no generated fixture may stand in for the corpus. | Regulation/corpus parsers, citation and quote fidelity, applicability, truth instruments, policy graph, and receipt schemas. |
| WFE harness | `uv run python -m tests.wfe.e2e.rig --live` checks deployed Pipeline/MCP identity and production trace/store paths. It is a live direct-Pipeline rig, not OWUI ingress. | NEW `tests/wfe/e2e/owui_live.py --case <stable-realuse-case>` runs one existing real-use case through OWUI and reads the same served identity, tool trace, and real store/artifact evidence before grading. | Plans, schemas, graders, checkers, identity maps, provenance, stop rules, and report parsing. Keep `tests/wfe/graded/**` as workload inputs. |
| Bench harness | `tests/benchmarks/bench_tps.py --mode pipeline --runs 1` measures Pipeline calls; several other probes call engines or services directly. | NEW `tests/benchmarks/bench_owui_route.py --case <stable-case> --runs 1`: bounded OWUI → Pipeline → engine requests, each paired with a trace and rendered response. Report latency/throughput only for calls with a matching live trace. Do not delete the benchmark runner library. | Result readers, sample accounting, confidence/statistics helpers, benchmark plan/config parsers, and zero-row/error contracts. |
| CLI/config | `uv run portal config validate` is a local config contract; `uv run portal trace --json --section pins --section workspaces` checks configured pins against live Pipeline routes. | Keep both. For CLI work, read exact command exit/output and `portal trace` pins/workspace hop results. Do not invent a chat test for local parsing. | YAML parsing, config validation, CLI argument/error contracts, generated artifact checks, and roster consistency. |
| Shared platform/storage/orchestration | WFE live rig checks some real data/memory/RAG operations; S70 contains a real memory write/recall/forget round-trip. Most other tests are deterministic local repository or state helpers. | NEW `scripts/proofs/owui_platform_matrix.py --case <stable-case>` for remaining user-reachable operations. Each case must record the actual store/object ID and verify cleanup or final persisted state. Split the matrix into one-area lanes before deleting tests. | Storage schemas, lock/transaction behavior, parsers, service registration, local state-machine and dispatch contracts. |

### Current driver boundaries

- `tests/portal5_uat_adaptive.py` is the offline authoring/review CLI. Its own docstring directs execution to `tests/portal5_uat_driver.py`, whose Playwright path logs into OWUI, sends the chat, reads the rendered/API response, and records `tests/UAT_RESULTS.md`.
- `tests/portal5_acceptance_v6.py` is a thin entry point for `tests/acceptance/`. `tests/acceptance/_common.py::_chat_with_model` posts directly to `http://localhost:9099/v1/chat/completions`; it is a Pipeline live driver, not OWUI ingress.
- `tests/acceptance/s70_information_access.py` performs direct health checks and a real memory MCP write/recall/forget transaction. It explicitly says the store transaction does not exercise model tool-calling.
- `tests/wfe/e2e/live.py` runs against production Pipeline/MCP addresses, reads production trace/store evidence, and cleans scoped test state. Its header command is `uv run python -m tests.wfe.e2e.rig --live`.
- `tests/benchmarks/bench_tps.py --mode pipeline` is a Pipeline benchmark. Its documented `direct` mode bypasses Pipeline. Neither is an OWUI route proof.
- `scripts/proofs/` currently contains one proof, `owui_hunt_chat.py`. It uses OWUI `exec_audit` with `/v1/trace` fallback and native review-MCP status/read calls. This is a real path, but it covers one hunt workflow rather than the whole security suite.

## 3. Live coverage gaps ranked by risk

| Rank | Gap | Why it matters and repository evidence |
|---:|---|---|
| 1 — critical | Served route and engine identity are not proved for every OWUI user path. | `c04dbf044` reverted a reachability change after a live-confirmed Ollama host crash during model load. `19cea3c38` repaired sampling delivery and WFE seat routing after the real Ollama path dropped configured options. `2144cb5c2` records a live trace where missing usage concealed reasoning-only output and a host-memory load refusal. A health hop or mocked route does not detect these failures. |
| 2 — high | Tool response text and actual tool execution can diverge. | Checked-in UAT rows `tests/UAT_RESULTS.md:40-43` show three code-sandbox UAT failures (T-01/T-02/T-03) alongside a separate TV-01 result whose computed output demonstrated execution. `f4929ed79` then fixed a sandbox command mismatch, acceptance signature crash, and missing workspace entries. The new owner must pair the user-facing answer with a per-turn tool span and real output. |
| 3 — high | Compliance content and store identity need the OWUI path and a real source readback. | Historical UAT rows `tests/UAT_RESULTS.md:57` and `:209-211` include a CIP-003 citation failure and later different outcomes; they are dated receipts, not current status. `c3a9caee9` records a live compliance acceptance fan-out that exhausted swap and reset the host, which is why the suite became opt-in. Compliance lanes must run serially under the orchestrator's host-safety gate and must cite the source/version actually read. |
| 4 — high | Hunt/review proof is narrow; the wider Bully/review evaluator tests are mostly local contracts. | `5caaf400d` added the first OWUI hunt chat proof; `376614f11` corrected its result grading to require what the prompt actually asks for. Keep this strong proof, but do not generalize one security-reviewer job to all Bully, intake, truth, and review-eval behavior. |
| 5 — medium/high | Several MCP services have no module-specific live receipt; some are not even exposed to Pipeline. | The current roster in `config/portal.yaml` marks `filesystem`, `fetch`, `git`, `serena`, `docker`, `browser`, `proxmox`, `binresearch`, and `context7` as `expose_to_pipeline: false`. OWUI cannot exercise those routes in this snapshot. `music-minimax`, `mflux`, and `video_mlx` have `default_enabled: false`. Preserve those effective states; use an IDE-path proof where the roster exposes only IDE, and mark a disabled path not run until it is already enabled by the operator. |
| 6 — medium | WFE and benchmark harnesses mostly hit Pipeline, engines, or MCPs directly. | `tests/wfe/e2e/live.py` explicitly talks to production Pipeline and MCP endpoints; `bench_tps.py` documents direct and Pipeline modes. They can prove their own layer and real store receipts, but not the Open WebUI ingress/rendered response. Add an OWUI case before deleting a corresponding offline behavior check. |

## 4. Sequenced phase-2 lanes

The expected reductions below are planning estimates, not live-verified outcomes. For each exclusive primary area, the measured candidate is the total LOC of files over the 5% mock-density threshold. Estimate a 10–40% deletion of those file LOC after retaining pure contracts/parsers; the point estimate is 25%. That fraction is an explicit planning heuristic, not measured coverage. Recalculate each lane's actual deletion list from current HEAD and its live receipt. New proof-script LOC is not subtracted from these test-deletion estimates.

Run live lanes serially against the shared host. The real host reset recorded by `c3a9caee9` shows why parallel large-model acceptance is not a safe default. A lane is done only when its live exerciser passes against the stack and reads the expected trace/store/artifact evidence, the specifically replaced offline behavior tests are deleted, and `bash scripts/ci_local.sh` is green. Contracts, parsers, pure logic, and unproven cases remain in the offline merge gate.

| Wave | One-area lanes in execution order | Measured heavy-file LOC | Expected offline test line reduction (estimate) |
|---:|---|---:|---:|
| 1 | `P2-01 CLI/config` (pins/config prerequisites) | 1,308 | 131–523; midpoint about 327 |
| 2 | `P2-02 Pipeline/router`; `P2-03 inference engines` | 23,156 | 2,316–9,262; midpoint about 5,789 |
| 3 | `P2-04 security/hunt`; `P2-05 compliance` | 9,319 | 932–3,728; midpoint about 2,330 |
| 4 | One lane per stateful MCP: `documents`, `execution`, `memory`, `rag`, `wiki`, `data`, `review` | 3,124 | 312–1,250; midpoint about 781 |
| 5 | One lane per remaining MCP in the roster: use OWUI cases for pipeline-exposed IDs and IDE MCP cases for IDE-only IDs; keep disabled-by-default IDs gated | 968 | 97–387; midpoint about 242. IDs with no offline module file contribute zero until a replaceable test exists. |
| 6 | `P2-06 WFE harness`; `P2-07 bench harness` | 13,622 | 1,362–5,449; midpoint about 3,406 |
| 7 | `P2-08 shared platform/storage/orchestration` | 4,596 | 460–1,838; midpoint about 1,149 |
| **Total** | **One area per lane; no lane removes another area's tests** | **56,093** | **About 5,610–22,437; midpoint about 14,024 lines** |

### Per-lane acceptance contract

1. Preflight the deployed build and target service with `portal trace`; inspect current `config/portal.yaml` exposure/enablement and the real case's available source/store. A missing source, disabled service, absent repeat, or non-current deployment is `BLOCKED`, not a passing substitute.
2. Build one live proof for the lane's actual user path. For OWUI routes, capture the request's rendered response, identify its real Pipeline trace, and read the relevant tool output/store/artifact. For IDE-only MCPs, exercise the configured IDE MCP client and record the actual tool result. Do not change `mcp_fleet` exposure or enablement as a trim shortcut.
3. Keep an offline test when it specifies a parser/schema, safety boundary, state transition, deterministic score, grading rule, or pure calculation. Delete only a behavior test whose concrete live case has passed and whose covered behavior is now asserted by that live receipt.
4. Record the exact live command, build SHA, case ID, trace/job/source/artifact IDs, result and cleanup verification. Then run the focused offline gates and `bash scripts/ci_local.sh`. A green CI run does not replace the live receipt.

## Appendix A — file-level offline test inventory

Each row gives physical LOC, indicator lines, density, and whether density reaches the 5% mock-heavy threshold. These rows are the per-file measurement behind the primary-area table.

### compliance (102 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/unit/test_cip_register.py` | 179 | 1 | 0.6% | no |
| `tests/unit/test_compliance_acceptance_currency.py` | 361 | 72 | 19.9% | yes |
| `tests/unit/test_compliance_analyze_live.py` | 104 | 2 | 1.9% | no |
| `tests/unit/test_compliance_answer_contract.py` | 95 | 0 | 0.0% | no |
| `tests/unit/test_compliance_applicability.py` | 145 | 0 | 0.0% | no |
| `tests/unit/test_compliance_assertions.py` | 205 | 0 | 0.0% | no |
| `tests/unit/test_compliance_assessment_report.py` | 265 | 1 | 0.4% | no |
| `tests/unit/test_compliance_assessment_runs.py` | 231 | 17 | 7.4% | yes |
| `tests/unit/test_compliance_assessment_source.py` | 634 | 12 | 1.9% | no |
| `tests/unit/test_compliance_auth.py` | 63 | 2 | 3.2% | no |
| `tests/unit/test_compliance_authority_surfaces.py` | 436 | 18 | 4.1% | no |
| `tests/unit/test_compliance_candidate_closure.py` | 222 | 4 | 1.8% | no |
| `tests/unit/test_compliance_capture.py` | 257 | 3 | 1.2% | no |
| `tests/unit/test_compliance_change_pipeline.py` | 600 | 17 | 2.8% | no |
| `tests/unit/test_compliance_citation_by_quote.py` | 323 | 0 | 0.0% | no |
| `tests/unit/test_compliance_citation_integrity.py` | 243 | 8 | 3.3% | no |
| `tests/unit/test_compliance_comparison.py` | 105 | 0 | 0.0% | no |
| `tests/unit/test_compliance_constraints.py` | 86 | 0 | 0.0% | no |
| `tests/unit/test_compliance_council.py` | 284 | 5 | 1.8% | no |
| `tests/unit/test_compliance_currency.py` | 121 | 8 | 6.6% | yes |
| `tests/unit/test_compliance_data_truth_instruments.py` | 946 | 24 | 2.5% | no |
| `tests/unit/test_compliance_docling_chunking.py` | 66 | 0 | 0.0% | no |
| `tests/unit/test_compliance_draft_revisions.py` | 77 | 9 | 11.7% | yes |
| `tests/unit/test_compliance_dual_document.py` | 350 | 4 | 1.1% | no |
| `tests/unit/test_compliance_duty_decomposition.py` | 180 | 3 | 1.7% | no |
| `tests/unit/test_compliance_duty_lineage.py` | 137 | 0 | 0.0% | no |
| `tests/unit/test_compliance_duty_verification.py` | 348 | 2 | 0.6% | no |
| `tests/unit/test_compliance_engine.py` | 247 | 1 | 0.4% | no |
| `tests/unit/test_compliance_eval_instance.py` | 208 | 10 | 4.8% | no |
| `tests/unit/test_compliance_evaluation.py` | 296 | 0 | 0.0% | no |
| `tests/unit/test_compliance_fixtures.py` | 77 | 1 | 1.3% | no |
| `tests/unit/test_compliance_gaps_live.py` | 136 | 7 | 5.1% | yes |
| `tests/unit/test_compliance_gate.py` | 93 | 0 | 0.0% | no |
| `tests/unit/test_compliance_gate_aligned.py` | 229 | 0 | 0.0% | no |
| `tests/unit/test_compliance_glossary.py` | 243 | 1 | 0.4% | no |
| `tests/unit/test_compliance_governing_packet.py` | 150 | 3 | 2.0% | no |
| `tests/unit/test_compliance_ingest.py` | 58 | 0 | 0.0% | no |
| `tests/unit/test_compliance_ingest_roots.py` | 114 | 14 | 12.3% | yes |
| `tests/unit/test_compliance_intentionality.py` | 72 | 0 | 0.0% | no |
| `tests/unit/test_compliance_internal_corpus.py` | 632 | 8 | 1.3% | no |
| `tests/unit/test_compliance_judgment_contract_v2.py` | 149 | 0 | 0.0% | no |
| `tests/unit/test_compliance_judgment_r1_experiment.py` | 67 | 3 | 4.5% | no |
| `tests/unit/test_compliance_machine_seat_isolation.py` | 47 | 0 | 0.0% | no |
| `tests/unit/test_compliance_mapping_store_consolidation.py` | 93 | 0 | 0.0% | no |
| `tests/unit/test_compliance_mcp.py` | 292 | 26 | 8.9% | yes |
| `tests/unit/test_compliance_migrate_legacy.py` | 159 | 1 | 0.6% | no |
| `tests/unit/test_compliance_nerc_source_sync.py` | 283 | 22 | 7.8% | yes |
| `tests/unit/test_compliance_obligation_alignment.py` | 395 | 13 | 3.3% | no |
| `tests/unit/test_compliance_operations.py` | 399 | 2 | 0.5% | no |
| `tests/unit/test_compliance_operator_text_audit.py` | 314 | 1 | 0.3% | no |
| `tests/unit/test_compliance_operator_traceability.py` | 513 | 0 | 0.0% | no |
| `tests/unit/test_compliance_org_graph.py` | 105 | 3 | 2.9% | no |
| `tests/unit/test_compliance_p6r_amendment1.py` | 122 | 4 | 3.3% | no |
| `tests/unit/test_compliance_p6r_measurement.py` | 337 | 14 | 4.2% | no |
| `tests/unit/test_compliance_payload_tools.py` | 238 | 6 | 2.5% | no |
| `tests/unit/test_compliance_planner.py` | 125 | 0 | 0.0% | no |
| `tests/unit/test_compliance_planted.py` | 158 | 0 | 0.0% | no |
| `tests/unit/test_compliance_policy_graph.py` | 258 | 0 | 0.0% | no |
| `tests/unit/test_compliance_propose.py` | 377 | 28 | 7.4% | yes |
| `tests/unit/test_compliance_prospective.py` | 76 | 6 | 7.9% | yes |
| `tests/unit/test_compliance_prove_then_scale.py` | 418 | 1 | 0.2% | no |
| `tests/unit/test_compliance_public_text.py` | 101 | 0 | 0.0% | no |
| `tests/unit/test_compliance_public_text_changed_only.py` | 105 | 2 | 1.9% | no |
| `tests/unit/test_compliance_quote_fidelity_and_snapshot.py` | 109 | 0 | 0.0% | no |
| `tests/unit/test_compliance_reader.py` | 910 | 40 | 4.4% | no |
| `tests/unit/test_compliance_reading_acceptance.py` | 1273 | 3 | 0.2% | no |
| `tests/unit/test_compliance_reading_assembly.py` | 293 | 4 | 1.4% | no |
| `tests/unit/test_compliance_reading_boundaries.py` | 265 | 6 | 2.3% | no |
| `tests/unit/test_compliance_reading_judgment.py` | 427 | 6 | 1.4% | no |
| `tests/unit/test_compliance_reading_live_runner.py` | 102 | 5 | 4.9% | no |
| `tests/unit/test_compliance_reading_transport.py` | 505 | 44 | 8.7% | yes |
| `tests/unit/test_compliance_reading_truth_tools.py` | 493 | 0 | 0.0% | no |
| `tests/unit/test_compliance_reasoning_v2_regressions.py` | 216 | 0 | 0.0% | no |
| `tests/unit/test_compliance_recapture_guard.py` | 45 | 0 | 0.0% | no |
| `tests/unit/test_compliance_regulatory_bundle.py` | 234 | 0 | 0.0% | no |
| `tests/unit/test_compliance_regulatory_corpus.py` | 215 | 0 | 0.0% | no |
| `tests/unit/test_compliance_relevance_arbiter.py` | 190 | 14 | 7.4% | yes |
| `tests/unit/test_compliance_repository.py` | 442 | 4 | 0.9% | no |
| `tests/unit/test_compliance_requirement_anchor.py` | 506 | 7 | 1.4% | no |
| `tests/unit/test_compliance_requirement_scope.py` | 430 | 15 | 3.5% | no |
| `tests/unit/test_compliance_requirement_scoping.py` | 492 | 21 | 4.3% | no |
| `tests/unit/test_compliance_result_contract.py` | 379 | 3 | 0.8% | no |
| `tests/unit/test_compliance_retrieval_seam.py` | 167 | 20 | 12.0% | yes |
| `tests/unit/test_compliance_review_decide_auth.py` | 94 | 8 | 8.5% | yes |
| `tests/unit/test_compliance_review_queue.py` | 87 | 3 | 3.4% | no |
| `tests/unit/test_compliance_rewrite_integrity.py` | 177 | 0 | 0.0% | no |
| `tests/unit/test_compliance_scenarios.py` | 289 | 4 | 1.4% | no |
| `tests/unit/test_compliance_search_pushdown.py` | 465 | 34 | 7.3% | yes |
| `tests/unit/test_compliance_section_index.py` | 409 | 8 | 2.0% | no |
| `tests/unit/test_compliance_sme_packet_kinds.py` | 101 | 0 | 0.0% | no |
| `tests/unit/test_compliance_sources.py` | 172 | 24 | 14.0% | yes |
| `tests/unit/test_compliance_technical_basis.py` | 319 | 0 | 0.0% | no |
| `tests/unit/test_compliance_temporal_projections.py` | 361 | 0 | 0.0% | no |
| `tests/unit/test_compliance_tiers.py` | 103 | 1 | 1.0% | no |
| `tests/unit/test_compliance_tool_manifest_parity.py` | 79 | 0 | 0.0% | no |
| `tests/unit/test_compliance_v3_contract.py` | 52 | 0 | 0.0% | no |
| `tests/unit/test_compliance_v3_matrices.py` | 683 | 4 | 0.6% | no |
| `tests/unit/test_compliance_vertical_slice.py` | 161 | 4 | 2.5% | no |
| `tests/unit/test_compliance_vocabulary_bridge.py` | 66 | 0 | 0.0% | no |
| `tests/unit/test_compliance_y21_error_classes.py` | 135 | 0 | 0.0% | no |
| `tests/unit/test_compliance_y23_variants.py` | 105 | 3 | 2.9% | no |
| `tests/unit/test_validation_compliance_currency_gate.py` | 39 | 11 | 28.2% | yes |

### security hunt (175 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/unit/test_attack_data_identity.py` | 69 | 0 | 0.0% | no |
| `tests/unit/test_bully_field_roles_time_parse.py` | 82 | 0 | 0.0% | no |
| `tests/unit/test_corpus_truth_key.py` | 244 | 0 | 0.0% | no |
| `tests/unit/test_detector_precision.py` | 183 | 0 | 0.0% | no |
| `tests/unit/test_hec_ship_dns_error.py` | 71 | 16 | 22.5% | yes |
| `tests/unit/test_hunt_baselines.py` | 349 | 4 | 1.1% | no |
| `tests/unit/test_hunt_bounded.py` | 782 | 6 | 0.8% | no |
| `tests/unit/test_hunt_case_focus.py` | 904 | 2 | 0.2% | no |
| `tests/unit/test_hunt_discovery.py` | 402 | 8 | 2.0% | no |
| `tests/unit/test_hunt_driver.py` | 117 | 15 | 12.8% | yes |
| `tests/unit/test_hunt_env_resolve.py` | 344 | 20 | 5.8% | yes |
| `tests/unit/test_hunt_evidence.py` | 468 | 0 | 0.0% | no |
| `tests/unit/test_hunt_executor.py` | 384 | 6 | 1.6% | no |
| `tests/unit/test_hunt_graph.py` | 343 | 0 | 0.0% | no |
| `tests/unit/test_hunt_graph_runner.py` | 404 | 28 | 6.9% | yes |
| `tests/unit/test_hunt_history.py` | 57 | 0 | 0.0% | no |
| `tests/unit/test_hunt_judge.py` | 210 | 0 | 0.0% | no |
| `tests/unit/test_hunt_judged_runner.py` | 677 | 16 | 2.4% | no |
| `tests/unit/test_hunt_knowledge.py` | 267 | 0 | 0.0% | no |
| `tests/unit/test_hunt_manifest.py` | 430 | 5 | 1.2% | no |
| `tests/unit/test_hunt_notables.py` | 676 | 2 | 0.3% | no |
| `tests/unit/test_hunt_notables_backpressure.py` | 278 | 2 | 0.7% | no |
| `tests/unit/test_hunt_notables_behaviours.py` | 481 | 2 | 0.4% | no |
| `tests/unit/test_hunt_notables_generators.py` | 351 | 0 | 0.0% | no |
| `tests/unit/test_hunt_notables_judge.py` | 240 | 2 | 0.8% | no |
| `tests/unit/test_hunt_notables_merge.py` | 330 | 0 | 0.0% | no |
| `tests/unit/test_hunt_notables_misfit.py` | 279 | 1 | 0.4% | no |
| `tests/unit/test_hunt_notables_similarity.py` | 465 | 3 | 0.6% | no |
| `tests/unit/test_hunt_observations.py` | 782 | 6 | 0.8% | no |
| `tests/unit/test_hunt_order.py` | 345 | 8 | 2.3% | no |
| `tests/unit/test_hunt_product_path.py` | 877 | 58 | 6.6% | yes |
| `tests/unit/test_hunt_relate.py` | 888 | 0 | 0.0% | no |
| `tests/unit/test_hunt_rerank.py` | 399 | 0 | 0.0% | no |
| `tests/unit/test_hunt_run_injection.py` | 254 | 10 | 3.9% | no |
| `tests/unit/test_hunt_scoreboard.py` | 731 | 0 | 0.0% | no |
| `tests/unit/test_hunt_stage2.py` | 298 | 2 | 0.7% | no |
| `tests/unit/test_hunt_tool_result_size.py` | 123 | 4 | 3.3% | no |
| `tests/unit/test_hunt_wire.py` | 387 | 14 | 3.6% | no |
| `tests/unit/test_image_security_update.py` | 331 | 51 | 15.4% | yes |
| `tests/unit/test_lab_exec_posture.py` | 73 | 13 | 17.8% | yes |
| `tests/unit/test_lab_guard_shell_injection.py` | 98 | 9 | 9.2% | yes |
| `tests/unit/test_lab_setup.py` | 301 | 27 | 9.0% | yes |
| `tests/unit/test_owui_hunt_chat_proof.py` | 436 | 26 | 6.0% | yes |
| `tests/unit/test_pending_verdicts_alignment.py` | 82 | 16 | 19.5% | yes |
| `tests/unit/test_pending_verdicts_evidence.py` | 40 | 0 | 0.0% | no |
| `tests/unit/test_portal_mitre_mcp.py` | 199 | 0 | 0.0% | no |
| `tests/unit/test_security_autoupdate.py` | 249 | 39 | 15.7% | yes |
| `tests/unit/test_security_call_model_route.py` | 97 | 15 | 15.5% | yes |
| `tests/unit/test_security_corpus_contract.py` | 21 | 0 | 0.0% | no |
| `tests/unit/test_siem_collect_normalize.py` | 323 | 3 | 0.9% | no |
| `tests/unit/test_uat_security.py` | 366 | 38 | 10.4% | yes |
| `tests/unit/test_wiki_seed_security.py` | 92 | 0 | 0.0% | no |
| `tests/security/bully/test_adaptive_scope_a1.py` | 201 | 0 | 0.0% | no |
| `tests/security/bully/test_analyst_x2_store.py` | 79 | 0 | 0.0% | no |
| `tests/security/bully/test_analyst_x4_concern_event.py` | 73 | 2 | 2.7% | no |
| `tests/security/bully/test_analyst_x5_generator_classes.py` | 79 | 0 | 0.0% | no |
| `tests/security/bully/test_anchor_spine_content.py` | 266 | 0 | 0.0% | no |
| `tests/security/bully/test_behavior_inference_i1b.py` | 147 | 0 | 0.0% | no |
| `tests/security/bully/test_behavior_values.py` | 104 | 0 | 0.0% | no |
| `tests/security/bully/test_boundaries.py` | 239 | 0 | 0.0% | no |
| `tests/security/bully/test_conformance_w1.py` | 193 | 0 | 0.0% | no |
| `tests/security/bully/test_conformance_w2.py` | 221 | 0 | 0.0% | no |
| `tests/security/bully/test_conformance_w3.py` | 71 | 0 | 0.0% | no |
| `tests/security/bully/test_conformance_w4.py` | 82 | 0 | 0.0% | no |
| `tests/security/bully/test_conformance_w5.py` | 95 | 2 | 2.1% | no |
| `tests/security/bully/test_corpus_bed_a4_distance_planting.py` | 133 | 0 | 0.0% | no |
| `tests/security/bully/test_corpus_bed_a5_bed_guard.py` | 71 | 0 | 0.0% | no |
| `tests/security/bully/test_corpus_bed_c1.py` | 160 | 0 | 0.0% | no |
| `tests/security/bully/test_corpus_bed_c3_capture.py` | 83 | 6 | 7.2% | yes |
| `tests/security/bully/test_corpus_bed_c4_fit_wide.py` | 84 | 0 | 0.0% | no |
| `tests/security/bully/test_corpus_bed_c5_cousin_inject.py` | 149 | 6 | 4.0% | no |
| `tests/security/bully/test_corpus_bed_c6_blocked_conformance.py` | 92 | 0 | 0.0% | no |
| `tests/security/bully/test_corpus_bed_i4_cousin_time_range.py` | 150 | 2 | 1.3% | no |
| `tests/security/bully/test_corpus_bed_t2_guard_holes.py` | 162 | 0 | 0.0% | no |
| `tests/security/bully/test_corpus_ingest_index.py` | 61 | 6 | 9.8% | yes |
| `tests/security/bully/test_cousin_c1_relation.py` | 212 | 0 | 0.0% | no |
| `tests/security/bully/test_cousin_c3_measurement_guards.py` | 148 | 0 | 0.0% | no |
| `tests/security/bully/test_discovery_bench_adoption.py` | 75 | 0 | 0.0% | no |
| `tests/security/bully/test_discovery_bench_identity_diagnostic.py` | 93 | 0 | 0.0% | no |
| `tests/security/bully/test_discovery_d1.py` | 210 | 0 | 0.0% | no |
| `tests/security/bully/test_discovery_first_d2.py` | 80 | 0 | 0.0% | no |
| `tests/security/bully/test_discovery_first_d3.py` | 70 | 0 | 0.0% | no |
| `tests/security/bully/test_embedding_spaces_thresholds.py` | 125 | 0 | 0.0% | no |
| `tests/security/bully/test_full_assembly_f1.py` | 189 | 0 | 0.0% | no |
| `tests/security/bully/test_full_assembly_f2.py` | 56 | 0 | 0.0% | no |
| `tests/security/bully/test_full_assembly_f3.py` | 54 | 0 | 0.0% | no |
| `tests/security/bully/test_hec_ship_timestamps.py` | 119 | 9 | 7.6% | yes |
| `tests/security/bully/test_hunt_sweep_h1.py` | 213 | 0 | 0.0% | no |
| `tests/security/bully/test_hunt_sweep_h2.py` | 327 | 28 | 8.6% | yes |
| `tests/security/bully/test_hunt_sweep_h2_anchor_time.py` | 135 | 11 | 8.1% | yes |
| `tests/security/bully/test_hunt_sweep_h3.py` | 302 | 26 | 8.6% | yes |
| `tests/security/bully/test_hunt_sweep_h4.py` | 117 | 0 | 0.0% | no |
| `tests/security/bully/test_hunt_sweep_h6_ci_invariants.py` | 57 | 0 | 0.0% | no |
| `tests/security/bully/test_i6_live_fidelity_fixes.py` | 100 | 4 | 4.0% | no |
| `tests/security/bully/test_inject_plane_i3_capture_investigation.py` | 139 | 6 | 4.3% | no |
| `tests/security/bully/test_investigation_a2_adaptive_pivot.py` | 91 | 0 | 0.0% | no |
| `tests/security/bully/test_investigation_a3_reach_chain.py` | 67 | 0 | 0.0% | no |
| `tests/security/bully/test_investigation_a7_ci_invariants.py` | 30 | 0 | 0.0% | no |
| `tests/security/bully/test_investigation_i1.py` | 220 | 0 | 0.0% | no |
| `tests/security/bully/test_investigation_i7_ci_invariants.py` | 73 | 0 | 0.0% | no |
| `tests/security/bully/test_live_connect_i2_bounded_spl.py` | 95 | 0 | 0.0% | no |
| `tests/security/bully/test_p1_0_config.py` | 42 | 0 | 0.0% | no |
| `tests/security/bully/test_p1_1_contracts.py` | 164 | 0 | 0.0% | no |
| `tests/security/bully/test_p1_2_store.py` | 323 | 0 | 0.0% | no |
| `tests/security/bully/test_p1_3_evidence.py` | 178 | 0 | 0.0% | no |
| `tests/security/bully/test_p1_4_organ.py` | 264 | 0 | 0.0% | no |
| `tests/security/bully/test_p1_5_cousin_engine.py` | 316 | 0 | 0.0% | no |
| `tests/security/bully/test_p1_6_investigation.py` | 102 | 6 | 5.9% | yes |
| `tests/security/bully/test_p2_1_bin_tables.py` | 409 | 0 | 0.0% | no |
| `tests/security/bully/test_p3_1_mutation.py` | 268 | 0 | 0.0% | no |
| `tests/security/bully/test_p5_1_store.py` | 347 | 0 | 0.0% | no |
| `tests/security/bully/test_p5_2_handoff.py` | 370 | 1 | 0.3% | no |
| `tests/security/bully/test_p6_1_store.py` | 380 | 0 | 0.0% | no |
| `tests/security/bully/test_p6_8_cousin_calibration.py` | 141 | 0 | 0.0% | no |
| `tests/security/bully/test_p7_4_retrieval_validity.py` | 167 | 0 | 0.0% | no |
| `tests/security/bully/test_raw_kv_multipair.py` | 72 | 0 | 0.0% | no |
| `tests/security/bully/test_real_telemetry_t1.py` | 175 | 0 | 0.0% | no |
| `tests/security/bully/test_reintegration_r1_pyramid.py` | 71 | 0 | 0.0% | no |
| `tests/security/bully/test_reintegration_r2_loop_grader.py` | 81 | 0 | 0.0% | no |
| `tests/security/bully/test_reintegration_r3_behavioral_signatures.py` | 63 | 0 | 0.0% | no |
| `tests/security/bully/test_reintegration_r3b_correlation.py` | 186 | 0 | 0.0% | no |
| `tests/security/bully/test_reintegration_r3c_series.py` | 180 | 0 | 0.0% | no |
| `tests/security/bully/test_reintegration_r5_universe.py` | 122 | 0 | 0.0% | no |
| `tests/security/bully/test_reintegration_r5a_live_chains.py` | 107 | 8 | 7.5% | yes |
| `tests/security/bully/test_reintegration_r5c_behavior_classifier.py` | 122 | 0 | 0.0% | no |
| `tests/security/bully/test_relate_a1_anchors.py` | 93 | 0 | 0.0% | no |
| `tests/security/bully/test_relate_b1_ungated_intake.py` | 66 | 0 | 0.0% | no |
| `tests/security/bully/test_relate_g1_confidence_calibration.py` | 61 | 0 | 0.0% | no |
| `tests/security/bully/test_relate_g2_provenance_tiers.py` | 108 | 0 | 0.0% | no |
| `tests/security/bully/test_relate_g3_contamination_canary.py` | 79 | 0 | 0.0% | no |
| `tests/security/bully/test_relate_m2_ci_invariants.py` | 94 | 0 | 0.0% | no |
| `tests/security/bully/test_sa2_1_real_pairs.py` | 97 | 2 | 2.1% | no |
| `tests/security/bully/test_sa2_2_taxonomy.py` | 52 | 0 | 0.0% | no |
| `tests/security/bully/test_sa2_3_circularity.py` | 57 | 0 | 0.0% | no |
| `tests/security/bully/test_sa2_4_cross_class.py` | 38 | 0 | 0.0% | no |
| `tests/security/bully/test_sa2_5_forge_demotion.py` | 62 | 0 | 0.0% | no |
| `tests/security/bully/test_sa3_4_discovery_seed.py` | 200 | 1 | 0.5% | no |
| `tests/security/bully/test_sa3_5_discovery_bakeoff.py` | 164 | 6 | 3.7% | no |
| `tests/security/bully/test_sa7_l1_live_connect.py` | 101 | 6 | 5.9% | yes |
| `tests/security/bully/test_score_sample_k1.py` | 137 | 0 | 0.0% | no |
| `tests/security/bully/test_scorer_feed_k2.py` | 116 | 8 | 6.9% | yes |
| `tests/security/bully/test_scorer_feed_k5_ci_invariants.py` | 56 | 0 | 0.0% | no |
| `tests/security/bully/test_soc_mld_instance_split.py` | 64 | 0 | 0.0% | no |
| `tests/security/bully/test_spl_detections_cloud.py` | 123 | 0 | 0.0% | no |
| `tests/security/bully/test_starvation_k3.py` | 97 | 0 | 0.0% | no |
| `tests/security/bully/test_telemetry_behavior_i5_concentration.py` | 86 | 0 | 0.0% | no |
| `tests/security/bully/test_truth_y1_acceptance.py` | 106 | 0 | 0.0% | no |
| `tests/security/bully/test_truth_y2_observed_coverage.py` | 98 | 0 | 0.0% | no |
| `tests/security/bully/test_truth_y3_priority_selection.py` | 90 | 0 | 0.0% | no |
| `tests/security/bully/test_truth_y4_quarantine_and_guard.py` | 166 | 0 | 0.0% | no |
| `tests/security/bully/test_truth_y5_output_distribution.py` | 77 | 0 | 0.0% | no |
| `tests/security/bully/test_truth_y6_json_raw_parsing.py` | 62 | 0 | 0.0% | no |
| `tests/security/bully/test_truth_y7_ci_invariants.py` | 36 | 0 | 0.0% | no |
| `tests/security/bully/test_universal_e1_field_roles.py` | 237 | 0 | 0.0% | no |
| `tests/security/bully/test_universal_e3_blend.py` | 87 | 0 | 0.0% | no |
| `tests/security/bully/test_universal_e4_baseline.py` | 72 | 0 | 0.0% | no |
| `tests/security/bully/test_universal_e5_inject_plane.py` | 267 | 26 | 9.7% | yes |
| `tests/security/bully/test_universal_m4_honest_metrics.py` | 190 | 0 | 0.0% | no |
| `tests/security/bully/test_universal_m5_ci_invariants.py` | 78 | 0 | 0.0% | no |
| `tests/security/bully/test_universal_u3_cross_vocabulary_ladder.py` | 81 | 0 | 0.0% | no |
| `tests/security/bully/test_unknown_l1_writeback_suppression.py` | 92 | 0 | 0.0% | no |
| `tests/security/bully/test_unknown_m1_falsification_ladder.py` | 126 | 0 | 0.0% | no |
| `tests/security/bully/test_unknown_m2_ci_invariants.py` | 99 | 0 | 0.0% | no |
| `tests/security/bully/test_unknown_n1_benign_types.py` | 69 | 0 | 0.0% | no |
| `tests/security/bully/test_unknown_n2_baseline.py` | 94 | 0 | 0.0% | no |
| `tests/security/bully/test_unknown_n3_likelihood_ratio.py` | 57 | 0 | 0.0% | no |
| `tests/security/bully/test_unknown_t1_grading_plane_legend.py` | 73 | 0 | 0.0% | no |
| `tests/security/bully/test_unknown_t2_held_out_split.py` | 83 | 0 | 0.0% | no |
| `tests/security/bully/test_unknown_t3_precision_recall.py` | 81 | 0 | 0.0% | no |
| `tests/security/bully/test_unknown_t4_leave_one_family_out.py` | 160 | 0 | 0.0% | no |
| `tests/security/bully/test_unknown_u1_artifact_graph.py` | 215 | 0 | 0.0% | no |
| `tests/security/bully/test_unknown_u2_unit_signature.py` | 51 | 0 | 0.0% | no |
| `tests/security/bully/test_unknown_u3_action_classifier.py` | 75 | 0 | 0.0% | no |
| `tests/security/bully/test_unknown_v1_unit_relation.py` | 181 | 0 | 0.0% | no |
| `tests/security/bully/test_unknown_v2_unit_outcome.py` | 196 | 0 | 0.0% | no |

### wfe (84 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/unit/test_eval_scope.py` | 445 | 14 | 3.1% | no |
| `tests/unit/test_eval_workspace_hygiene.py` | 115 | 12 | 10.4% | yes |
| `tests/unit/test_memory_eval_scope.py` | 131 | 8 | 6.1% | yes |
| `tests/unit/test_rag_eval_scope.py` | 140 | 9 | 6.4% | yes |
| `tests/unit/test_realuse_fixture_builder.py` | 23 | 0 | 0.0% | no |
| `tests/unit/test_realuse_fixture_paths.py` | 245 | 17 | 6.9% | yes |
| `tests/unit/test_seat_fit.py` | 130 | 2 | 1.5% | no |
| `tests/unit/test_seat_preflight.py` | 219 | 19 | 8.7% | yes |
| `tests/unit/test_seat_primary_matches_production.py` | 57 | 2 | 3.5% | no |
| `tests/unit/test_seat_screen.py` | 191 | 25 | 13.1% | yes |
| `tests/unit/test_seat_screen_grader.py` | 116 | 4 | 3.4% | no |
| `tests/unit/test_seat_screen_intake_s8.py` | 364 | 2 | 0.5% | no |
| `tests/unit/test_seat_screen_kit_apply.py` | 104 | 4 | 3.8% | no |
| `tests/unit/test_settings_audit_backend_reachability.py` | 187 | 15 | 8.0% | yes |
| `tests/unit/test_settings_audit_card_preflight.py` | 245 | 5 | 2.0% | no |
| `tests/unit/test_variant_module_gate.py` | 226 | 12 | 5.3% | yes |
| `tests/unit/test_wfe_campaign_finish.py` | 331 | 31 | 9.4% | yes |
| `tests/unit/test_wfe_campaign_script.py` | 1288 | 33 | 2.6% | no |
| `tests/unit/test_wfe_exec_audit.py` | 125 | 10 | 8.0% | yes |
| `tests/unit/test_wfe_garble_probe.py` | 56 | 0 | 0.0% | no |
| `tests/unit/test_wfe_production_smoke_cleanup.py` | 137 | 29 | 21.2% | yes |
| `tests/unit/test_wfe_production_smoke_kb.py` | 87 | 11 | 12.6% | yes |
| `tests/unit/test_wfe_surface_audit.py` | 173 | 7 | 4.0% | no |
| `tests/wfe/tests/test_longread_agg_diag.py` | 509 | 15 | 2.9% | no |
| `tests/wfe/tests/test_variant_module_audit.py` | 50 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_audio_slice.py` | 197 | 9 | 4.6% | no |
| `tests/wfe/tests/test_wfe_backfill.py` | 285 | 12 | 4.2% | no |
| `tests/wfe/tests/test_wfe_baseline.py` | 55 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_cad_slice.py` | 248 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_canary.py` | 996 | 79 | 7.9% | yes |
| `tests/wfe/tests/test_wfe_cells.py` | 93 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_checkers.py` | 1715 | 11 | 0.6% | no |
| `tests/wfe/tests/test_wfe_coding_slice.py` | 215 | 4 | 1.9% | no |
| `tests/wfe/tests/test_wfe_compliance_attainability.py` | 89 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_compliance_classify.py` | 89 | 6 | 6.7% | yes |
| `tests/wfe/tests/test_wfe_compliance_slice.py` | 111 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_component.py` | 265 | 16 | 6.0% | yes |
| `tests/wfe/tests/test_wfe_contracts.py` | 4177 | 277 | 6.6% | yes |
| `tests/wfe/tests/test_wfe_controls.py` | 220 | 16 | 7.3% | yes |
| `tests/wfe/tests/test_wfe_data_slice.py` | 64 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_decision.py` | 298 | 1 | 0.3% | no |
| `tests/wfe/tests/test_wfe_documents_slice.py` | 115 | 2 | 1.7% | no |
| `tests/wfe/tests/test_wfe_eval_mode.py` | 480 | 29 | 6.0% | yes |
| `tests/wfe/tests/test_wfe_extract_slice.py` | 171 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_fitness_report.py` | 423 | 53 | 12.5% | yes |
| `tests/wfe/tests/test_wfe_general_slice.py` | 257 | 2 | 0.8% | no |
| `tests/wfe/tests/test_wfe_gold_isolation.py` | 35 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_incumbent_reuse.py` | 888 | 85 | 9.6% | yes |
| `tests/wfe/tests/test_wfe_judge.py` | 295 | 31 | 10.5% | yes |
| `tests/wfe/tests/test_wfe_judge_cloud.py` | 111 | 17 | 15.3% | yes |
| `tests/wfe/tests/test_wfe_judge_compare.py` | 304 | 17 | 5.6% | yes |
| `tests/wfe/tests/test_wfe_judge_council.py` | 304 | 13 | 4.3% | no |
| `tests/wfe/tests/test_wfe_ledger_check.py` | 155 | 25 | 16.1% | yes |
| `tests/wfe/tests/test_wfe_multiturn.py` | 338 | 27 | 8.0% | yes |
| `tests/wfe/tests/test_wfe_next_screens_slice.py` | 94 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_office_contains.py` | 448 | 9 | 2.0% | no |
| `tests/wfe/tests/test_wfe_plan_suites.py` | 130 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_preflight_scope.py` | 35 | 10 | 28.6% | yes |
| `tests/wfe/tests/test_wfe_production_path.py` | 98 | 9 | 9.2% | yes |
| `tests/wfe/tests/test_wfe_production_surface.py` | 282 | 14 | 5.0% | no |
| `tests/wfe/tests/test_wfe_prompt_surface.py` | 158 | 4 | 2.5% | no |
| `tests/wfe/tests/test_wfe_provenance.py` | 308 | 49 | 15.9% | yes |
| `tests/wfe/tests/test_wfe_publish.py` | 60 | 4 | 6.7% | yes |
| `tests/wfe/tests/test_wfe_reading_long_slice.py` | 234 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_reading_slice.py` | 204 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_realuse_tier.py` | 306 | 30 | 9.8% | yes |
| `tests/wfe/tests/test_wfe_reasoning_hard_slice.py` | 768 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_reasoning_math_slice.py` | 293 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_research_slice.py` | 185 | 2 | 1.1% | no |
| `tests/wfe/tests/test_wfe_routing_slice.py` | 208 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_run_arm.py` | 466 | 67 | 14.4% | yes |
| `tests/wfe/tests/test_wfe_runner_timing_guard.py` | 18 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_security_analysis_production_slice.py` | 199 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_stop_rules.py` | 33 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_supervise.py` | 370 | 7 | 1.9% | no |
| `tests/wfe/tests/test_wfe_sweep_plan.py` | 210 | 2 | 1.0% | no |
| `tests/wfe/tests/test_wfe_tiers.py` | 163 | 2 | 1.2% | no |
| `tests/wfe/tests/test_wfe_timing.py` | 284 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_tool_modes.py` | 37 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_tool_surface_proxy.py` | 165 | 8 | 4.8% | no |
| `tests/wfe/tests/test_wfe_tools_specialist_slice.py` | 277 | 0 | 0.0% | no |
| `tests/wfe/tests/test_wfe_upload_fidelity.py` | 379 | 5 | 1.3% | no |
| `tests/wfe/tests/test_wfe_vision_preflight.py` | 149 | 13 | 8.7% | yes |
| `tests/wfe/tests/test_wfe_vision_slice.py` | 137 | 0 | 0.0% | no |

### bench (14 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/unit/test_bench_cad_probe_think.py` | 83 | 5 | 6.0% | yes |
| `tests/unit/test_bench_capability_cli.py` | 54 | 0 | 0.0% | no |
| `tests/unit/test_bench_config_coverage.py` | 123 | 15 | 12.2% | yes |
| `tests/unit/test_bench_repair.py` | 326 | 35 | 10.7% | yes |
| `tests/unit/test_bench_skip.py` | 84 | 4 | 4.8% | no |
| `tests/unit/test_bench_supervisor.py` | 368 | 20 | 5.4% | yes |
| `tests/unit/test_candidate_eval.py` | 57 | 4 | 7.0% | yes |
| `tests/unit/test_council_bench.py` | 336 | 0 | 0.0% | no |
| `tests/unit/test_council_review_bench.py` | 109 | 0 | 0.0% | no |
| `tests/unit/test_embedding_consumers_harness.py` | 130 | 5 | 3.8% | no |
| `tests/unit/test_router_bench.py` | 52 | 2 | 3.8% | no |
| `tests/unit/test_speed_bench.py` | 368 | 25 | 6.8% | yes |
| `tests/unit/test_tps_metrics.py` | 644 | 0 | 0.0% | no |
| `tests/benchmarks/test_empty_retry.py` | 67 | 0 | 0.0% | no |

### engines (37 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/unit/test_backend_registry_health.py` | 461 | 4 | 0.9% | no |
| `tests/unit/test_capacity_fallback.py` | 220 | 19 | 8.6% | yes |
| `tests/unit/test_check_model_bindings.py` | 123 | 0 | 0.0% | no |
| `tests/unit/test_config_ollama_url.py` | 123 | 15 | 12.2% | yes |
| `tests/unit/test_direct_engine_diagnostic_gate.py` | 64 | 14 | 21.9% | yes |
| `tests/unit/test_eg2_embedding_server.py` | 217 | 15 | 6.9% | yes |
| `tests/unit/test_engine_autoupdate.py` | 409 | 98 | 24.0% | yes |
| `tests/unit/test_engine_call_metrics.py` | 397 | 22 | 5.5% | yes |
| `tests/unit/test_engine_contract_check.py` | 109 | 20 | 18.3% | yes |
| `tests/unit/test_fetch_mlx_asr_models.py` | 141 | 22 | 15.6% | yes |
| `tests/unit/test_host_quiet.py` | 354 | 39 | 11.0% | yes |
| `tests/unit/test_load_guard.py` | 3068 | 126 | 4.1% | no |
| `tests/unit/test_memory_safety_watch.py` | 515 | 40 | 7.8% | yes |
| `tests/unit/test_mlx_audio_idle_unload.py` | 350 | 23 | 6.6% | yes |
| `tests/unit/test_mlx_cache_probe.py` | 339 | 43 | 12.7% | yes |
| `tests/unit/test_mlx_cache_release.py` | 458 | 54 | 11.8% | yes |
| `tests/unit/test_mlx_speech_asr_gate.py` | 77 | 13 | 16.9% | yes |
| `tests/unit/test_mlx_transcribe_openai_stt.py` | 150 | 23 | 15.3% | yes |
| `tests/unit/test_model_catalog_parity.py` | 202 | 0 | 0.0% | no |
| `tests/unit/test_model_cleanup_audit.py` | 72 | 0 | 0.0% | no |
| `tests/unit/test_model_management_dashboard.py` | 68 | 0 | 0.0% | no |
| `tests/unit/test_model_refresh.py` | 635 | 9 | 1.4% | no |
| `tests/unit/test_model_upstream.py` | 761 | 13 | 1.7% | no |
| `tests/unit/test_ollama_direct_allowlist.py` | 59 | 0 | 0.0% | no |
| `tests/unit/test_ollama_native.py` | 632 | 0 | 0.0% | no |
| `tests/unit/test_ollama_passthrough.py` | 376 | 13 | 3.5% | no |
| `tests/unit/test_omlx_auth.py` | 55 | 15 | 27.3% | yes |
| `tests/unit/test_omlx_backend.py` | 411 | 22 | 5.4% | yes |
| `tests/unit/test_omlx_capacity_retry.py` | 524 | 56 | 10.7% | yes |
| `tests/unit/test_omlx_chat_template_patch.py` | 76 | 1 | 1.3% | no |
| `tests/unit/test_omlx_memory_tier.py` | 38 | 0 | 0.0% | no |
| `tests/unit/test_owui_eg2_prefixes.py` | 32 | 0 | 0.0% | no |
| `tests/unit/test_platform_embedding.py` | 223 | 3 | 1.3% | no |
| `tests/unit/test_powermetrics_daemon.py` | 173 | 2 | 1.2% | no |
| `tests/unit/test_prismml_mlx_server.py` | 114 | 12 | 10.5% | yes |
| `tests/unit/test_uat_engines.py` | 394 | 9 | 2.3% | no |
| `tests/unit/test_vl_retrieval_server.py` | 371 | 25 | 6.7% | yes |

### pipeline router (70 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/unit/router/test_context_inject.py` | 152 | 18 | 11.8% | yes |
| `tests/unit/router/test_correlation.py` | 32 | 0 | 0.0% | no |
| `tests/unit/router/test_image_reroute.py` | 150 | 19 | 12.7% | yes |
| `tests/unit/test_acceptance_common.py` | 50 | 2 | 4.0% | no |
| `tests/unit/test_arm_digests_refresh.py` | 199 | 8 | 4.0% | no |
| `tests/unit/test_arm_escalation.py` | 1624 | 71 | 4.4% | no |
| `tests/unit/test_arm_job_specs.py` | 469 | 0 | 0.0% | no |
| `tests/unit/test_arm_shadow_batch.py` | 187 | 18 | 9.6% | yes |
| `tests/unit/test_channels.py` | 797 | 99 | 12.4% | yes |
| `tests/unit/test_context_overflow_guard.py` | 692 | 57 | 8.2% | yes |
| `tests/unit/test_council_review.py` | 911 | 43 | 4.7% | no |
| `tests/unit/test_council_speed.py` | 880 | 33 | 3.8% | no |
| `tests/unit/test_failover_protection_and_empty_hop.py` | 102 | 13 | 12.7% | yes |
| `tests/unit/test_failover_window_floor.py` | 50 | 0 | 0.0% | no |
| `tests/unit/test_no_answer.py` | 613 | 58 | 9.5% | yes |
| `tests/unit/test_notifications.py` | 934 | 71 | 7.6% | yes |
| `tests/unit/test_orchestration_acceptance.py` | 441 | 41 | 9.3% | yes |
| `tests/unit/test_orchestration_arm.py` | 2270 | 68 | 3.0% | no |
| `tests/unit/test_orchestration_bite_suite.py` | 490 | 13 | 2.7% | no |
| `tests/unit/test_orchestration_detection_discipline.py` | 202 | 0 | 0.0% | no |
| `tests/unit/test_orchestration_jobs.py` | 2809 | 52 | 1.9% | no |
| `tests/unit/test_orchestration_owui_entry.py` | 356 | 36 | 10.1% | yes |
| `tests/unit/test_orchestration_phase2.py` | 531 | 4 | 0.8% | no |
| `tests/unit/test_orchestration_rbp_injection.py` | 116 | 0 | 0.0% | no |
| `tests/unit/test_orchestration_repair_quote.py` | 55 | 0 | 0.0% | no |
| `tests/unit/test_orchestration_router_fixes.py` | 941 | 101 | 10.7% | yes |
| `tests/unit/test_pipeline.py` | 2661 | 151 | 5.7% | yes |
| `tests/unit/test_pipeline_hardening.py` | 2482 | 204 | 8.2% | yes |
| `tests/unit/test_pipeline_image_personas.py` | 124 | 0 | 0.0% | no |
| `tests/unit/test_pipeline_tool_carry.py` | 450 | 0 | 0.0% | no |
| `tests/unit/test_quality_signals.py` | 156 | 3 | 1.9% | no |
| `tests/unit/test_rag_tool_contract.py` | 219 | 17 | 7.8% | yes |
| `tests/unit/test_reasoning_effort.py` | 185 | 25 | 13.5% | yes |
| `tests/unit/test_request_limits.py` | 60 | 0 | 0.0% | no |
| `tests/unit/test_request_no_tools.py` | 101 | 7 | 6.9% | yes |
| `tests/unit/test_request_slot.py` | 187 | 4 | 2.1% | no |
| `tests/unit/test_require_tool_before_answer.py` | 328 | 40 | 12.2% | yes |
| `tests/unit/test_required_tool_choice_retry.py` | 478 | 50 | 10.5% | yes |
| `tests/unit/test_router_placement.py` | 348 | 8 | 2.3% | no |
| `tests/unit/test_routing.py` | 511 | 45 | 8.8% | yes |
| `tests/unit/test_smoke_stream_script.py` | 91 | 0 | 0.0% | no |
| `tests/unit/test_stream_fallback.py` | 680 | 31 | 4.6% | no |
| `tests/unit/test_stream_inband_error.py` | 332 | 21 | 6.3% | yes |
| `tests/unit/test_stream_parity.py` | 329 | 34 | 10.3% | yes |
| `tests/unit/test_stream_pipeline_errors.py` | 887 | 91 | 10.3% | yes |
| `tests/unit/test_streaming_client.py` | 56 | 0 | 0.0% | no |
| `tests/unit/test_telegram_jarvis_control.py` | 584 | 83 | 14.2% | yes |
| `tests/unit/test_text_tool_call_salvage.py` | 367 | 29 | 7.9% | yes |
| `tests/unit/test_thinking_channels.py` | 456 | 18 | 3.9% | no |
| `tests/unit/test_tool_backoff.py` | 443 | 13 | 2.9% | no |
| `tests/unit/test_tool_dispatch_order.py` | 41 | 2 | 4.9% | no |
| `tests/unit/test_tool_loop_byte_budget.py` | 475 | 44 | 9.3% | yes |
| `tests/unit/test_tool_registry_duplicate_precedence.py` | 105 | 4 | 3.8% | no |
| `tests/unit/test_tool_registry_refresh.py` | 492 | 38 | 7.7% | yes |
| `tests/unit/test_tool_registry_retry.py` | 68 | 7 | 10.3% | yes |
| `tests/unit/test_tool_repeat_guard.py` | 390 | 22 | 5.6% | yes |
| `tests/unit/test_trace_report.py` | 73 | 0 | 0.0% | no |
| `tests/unit/test_trace_sections.py` | 1009 | 31 | 3.1% | no |
| `tests/unit/test_transport_pipeline_dialect.py` | 499 | 29 | 5.8% | yes |
| `tests/unit/test_triage_layer2.py` | 585 | 29 | 5.0% | no |
| `tests/unit/test_turn_trace.py` | 228 | 28 | 12.3% | yes |
| `tests/unit/test_uat_adaptive.py` | 311 | 5 | 1.6% | no |
| `tests/unit/test_uat_browser.py` | 176 | 6 | 3.4% | no |
| `tests/unit/test_uat_dispatch_route_params.py` | 83 | 13 | 15.7% | yes |
| `tests/unit/test_uat_dispatch_url.py` | 87 | 4 | 4.6% | no |
| `tests/unit/test_uat_grading.py` | 275 | 15 | 5.5% | yes |
| `tests/unit/test_uat_metrics_url.py` | 76 | 8 | 10.5% | yes |
| `tests/unit/test_uat_settings_gate.py` | 53 | 10 | 18.9% | yes |
| `tests/unit/test_uat_swap.py` | 374 | 15 | 4.0% | no |
| `tests/unit/test_validation_orchestration_arm.py` | 290 | 27 | 9.3% | yes |

### documents (5 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/unit/test_attachment_paths.py` | 459 | 15 | 3.3% | no |
| `tests/unit/test_document_mcp.py` | 627 | 34 | 5.4% | yes |
| `tests/unit/test_documents_read_refusal.py` | 45 | 3 | 6.7% | yes |
| `tests/unit/test_download_link_safety.py` | 181 | 12 | 6.6% | yes |
| `tests/unit/test_followup_artifact_tool.py` | 726 | 39 | 5.4% | yes |

### sandbox execution (2 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/unit/test_code_sandbox_sessions.py` | 192 | 34 | 17.7% | yes |
| `tests/unit/test_sandbox_network_flag.py` | 41 | 0 | 0.0% | no |

### cad (15 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/unit/test_b123d_emitter.py` | 144 | 0 | 0.0% | no |
| `tests/unit/test_cad_b123d_bridge.py` | 206 | 14 | 6.8% | yes |
| `tests/unit/test_cad_capabilities.py` | 23 | 2 | 8.7% | yes |
| `tests/unit/test_cad_coverage_corpus.py` | 201 | 0 | 0.0% | no |
| `tests/unit/test_cad_gauntlet_scoring.py` | 26 | 0 | 0.0% | no |
| `tests/unit/test_cad_generate_part.py` | 75 | 11 | 14.7% | yes |
| `tests/unit/test_cad_grader.py` | 73 | 3 | 4.1% | no |
| `tests/unit/test_cad_ir_bases.py` | 159 | 0 | 0.0% | no |
| `tests/unit/test_cad_loop.py` | 121 | 14 | 11.6% | yes |
| `tests/unit/test_cad_render_fallback.py` | 57 | 4 | 7.0% | yes |
| `tests/unit/test_cad_schema_parity.py` | 84 | 0 | 0.0% | no |
| `tests/unit/test_cam_lds_extract.py` | 375 | 0 | 0.0% | no |
| `tests/unit/test_mesh_printability.py` | 64 | 0 | 0.0% | no |
| `tests/unit/test_scad_emitter.py` | 328 | 0 | 0.0% | no |
| `tests/unit/test_scad_golden.py` | 25 | 0 | 0.0% | no |

### proxmox (1 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/unit/test_proxmox_mcp.py` | 126 | 33 | 26.2% | yes |

### memory (4 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/unit/test_graph_memory_eg2.py` | 135 | 5 | 3.7% | no |
| `tests/unit/test_graph_memory_extract.py` | 32 | 4 | 12.5% | yes |
| `tests/unit/test_memory_gate_headroom.py` | 186 | 26 | 14.0% | yes |
| `tests/unit/test_memrag_native_rest_parity.py` | 183 | 18 | 9.8% | yes |

### rag (3 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/unit/test_rag.py` | 162 | 21 | 13.0% | yes |
| `tests/unit/test_rag_kb_list.py` | 70 | 10 | 14.3% | yes |
| `tests/unit/test_rag_multimodal.py` | 456 | 37 | 8.1% | yes |

### web research (2 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/unit/test_research_probe_scoring.py` | 138 | 3 | 2.2% | no |
| `tests/unit/test_web_search_fallback.py` | 158 | 28 | 17.7% | yes |

### wiki (6 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/unit/test_seed_facts.py` | 51 | 0 | 0.0% | no |
| `tests/unit/test_wiki_archive.py` | 192 | 1 | 0.5% | no |
| `tests/unit/test_wiki_core.py` | 595 | 14 | 2.4% | no |
| `tests/unit/test_wiki_quality.py` | 191 | 11 | 5.8% | yes |
| `tests/unit/test_wiki_search_ranking.py` | 73 | 7 | 9.6% | yes |
| `tests/unit/test_wiki_writeback.py` | 289 | 0 | 0.0% | no |

### audio (1 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/unit/test_transcribe_diarize.py` | 283 | 10 | 3.5% | no |

### media (1 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/unit/test_media_admission.py` | 202 | 14 | 6.9% | yes |

### cli config (29 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/unit/test_catalog_schema.py` | 217 | 3 | 1.4% | no |
| `tests/unit/test_complexity_budget.py` | 116 | 8 | 6.9% | yes |
| `tests/unit/test_config_schema.py` | 482 | 4 | 0.8% | no |
| `tests/unit/test_config_validate.py` | 66 | 0 | 0.0% | no |
| `tests/unit/test_dependency_drift.py` | 83 | 0 | 0.0% | no |
| `tests/unit/test_exposed_workspace_variants.py` | 173 | 16 | 9.2% | yes |
| `tests/unit/test_fleet_consolidate.py` | 716 | 2 | 0.3% | no |
| `tests/unit/test_generated_artifacts_fresh.py` | 275 | 13 | 4.7% | no |
| `tests/unit/test_import_environment.py` | 36 | 0 | 0.0% | no |
| `tests/unit/test_mcp_endpoints.py` | 268 | 0 | 0.0% | no |
| `tests/unit/test_mcp_fleet_single_source.py` | 377 | 5 | 1.3% | no |
| `tests/unit/test_module_services.py` | 624 | 37 | 5.9% | yes |
| `tests/unit/test_module_toggle.py` | 161 | 16 | 9.9% | yes |
| `tests/unit/test_netguard.py` | 69 | 0 | 0.0% | no |
| `tests/unit/test_platform_module_boundary.py` | 33 | 0 | 0.0% | no |
| `tests/unit/test_portal_cli.py` | 144 | 0 | 0.0% | no |
| `tests/unit/test_portal_yaml_consistency.py` | 53 | 0 | 0.0% | no |
| `tests/unit/test_promptfoo_configs.py` | 101 | 0 | 0.0% | no |
| `tests/unit/test_spine_coverage.py` | 387 | 0 | 0.0% | no |
| `tests/unit/test_spine_drift.py` | 346 | 4 | 1.2% | no |
| `tests/unit/test_spine_gates.py` | 41 | 0 | 0.0% | no |
| `tests/unit/test_update_workspace_tools_dead.py` | 28 | 0 | 0.0% | no |
| `tests/unit/test_validation_ae_launcher.py` | 65 | 0 | 0.0% | no |
| `tests/unit/test_validation_fleet_fallback.py` | 316 | 0 | 0.0% | no |
| `tests/unit/test_validation_mtp_intake.py` | 143 | 0 | 0.0% | no |
| `tests/unit/test_validation_serving_conformance.py` | 63 | 13 | 20.6% | yes |
| `tests/unit/test_validation_test_hygiene.py` | 149 | 0 | 0.0% | no |
| `tests/unit/test_validation_unit_tests_skip.py` | 121 | 4 | 3.3% | no |
| `tests/unit/test_workspace.py` | 171 | 14 | 8.2% | yes |

### security review (18 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/security/review/test_adapters.py` | 109 | 0 | 0.0% | no |
| `tests/security/review/test_defense.py` | 392 | 2 | 0.5% | no |
| `tests/security/review/test_funnel_pipeline.py` | 250 | 1 | 0.4% | no |
| `tests/security/review/test_intake_knowledge.py` | 137 | 3 | 2.2% | no |
| `tests/security/review/test_invariants.py` | 93 | 0 | 0.0% | no |
| `tests/security/review/test_io_adapters.py` | 321 | 1 | 0.3% | no |
| `tests/security/review/test_judge.py` | 372 | 0 | 0.0% | no |
| `tests/security/review/test_loader_contamination.py` | 49 | 0 | 0.0% | no |
| `tests/security/review/test_prune_ledger.py` | 146 | 0 | 0.0% | no |
| `tests/security/review/test_reader_guards.py` | 70 | 0 | 0.0% | no |
| `tests/security/review/test_reader_tools.py` | 152 | 0 | 0.0% | no |
| `tests/security/review/test_runs.py` | 97 | 0 | 0.0% | no |
| `tests/security/review/test_runtime.py` | 366 | 5 | 1.4% | no |
| `tests/security/review/test_service_knowledge.py` | 175 | 2 | 1.1% | no |
| `tests/security/review/test_state_renderer.py` | 128 | 0 | 0.0% | no |
| `tests/security/review/test_store_verdicts.py` | 285 | 0 | 0.0% | no |
| `tests/security/review/test_surfaces.py` | 107 | 3 | 2.8% | no |
| `tests/security/review/test_wall_calibration_content.py` | 134 | 0 | 0.0% | no |

### security review eval (16 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/security/review_eval/test_arms.py` | 53 | 6 | 11.3% | yes |
| `tests/security/review_eval/test_attribution_decisions.py` | 170 | 0 | 0.0% | no |
| `tests/security/review_eval/test_bots_truth_key.py` | 52 | 0 | 0.0% | no |
| `tests/security/review_eval/test_captures.py` | 86 | 0 | 0.0% | no |
| `tests/security/review_eval/test_claims.py` | 246 | 0 | 0.0% | no |
| `tests/security/review_eval/test_folds.py` | 62 | 0 | 0.0% | no |
| `tests/security/review_eval/test_mixed_harness.py` | 251 | 0 | 0.0% | no |
| `tests/security/review_eval/test_proof.py` | 103 | 0 | 0.0% | no |
| `tests/security/review_eval/test_runner_evidence_twins.py` | 95 | 0 | 0.0% | no |
| `tests/security/review_eval/test_runner_one_path.py` | 30 | 0 | 0.0% | no |
| `tests/security/review_eval/test_selftest_report_wall.py` | 244 | 0 | 0.0% | no |
| `tests/security/review_eval/test_stamp_metrics.py` | 139 | 0 | 0.0% | no |
| `tests/security/review_eval/test_traces.py` | 78 | 0 | 0.0% | no |
| `tests/security/review_eval/test_truth.py` | 282 | 0 | 0.0% | no |
| `tests/security/review_eval/test_truth_audit.py` | 192 | 0 | 0.0% | no |
| `tests/security/review_eval/test_truth_runner.py` | 292 | 0 | 0.0% | no |

### other platform (63 files)

| Test file | LOC | Indicator lines | Density | Heavy |
|---|---:|---:|---:|:---:|
| `tests/unit/test_adhoc_probe.py` | 139 | 20 | 14.4% | yes |
| `tests/unit/test_all_writebacks.py` | 96 | 0 | 0.0% | no |
| `tests/unit/test_anchor_semantic_card.py` | 158 | 0 | 0.0% | no |
| `tests/unit/test_apply_params_write_back.py` | 53 | 6 | 11.3% | yes |
| `tests/unit/test_apply_renderers.py` | 169 | 35 | 20.7% | yes |
| `tests/unit/test_build_specimen_corpus_v3.py` | 42 | 0 | 0.0% | no |
| `tests/unit/test_calibrate_builder.py` | 272 | 24 | 8.8% | yes |
| `tests/unit/test_calibration_slice.py` | 62 | 0 | 0.0% | no |
| `tests/unit/test_cancellation_w3.py` | 285 | 9 | 3.2% | no |
| `tests/unit/test_candidates_probe_max_tokens.py` | 51 | 3 | 5.9% | yes |
| `tests/unit/test_capability_lib.py` | 261 | 0 | 0.0% | no |
| `tests/unit/test_capability_probe.py` | 34 | 0 | 0.0% | no |
| `tests/unit/test_check_updates.py` | 763 | 59 | 7.7% | yes |
| `tests/unit/test_chunking_5tuple.py` | 45 | 5 | 11.1% | yes |
| `tests/unit/test_coding_fixtures.py` | 76 | 0 | 0.0% | no |
| `tests/unit/test_corpus_reingest.py` | 1545 | 107 | 6.9% | yes |
| `tests/unit/test_egress_aliyuncs.py` | 77 | 4 | 5.2% | yes |
| `tests/unit/test_embeddings_route.py` | 301 | 35 | 11.6% | yes |
| `tests/unit/test_expected_models.py` | 50 | 0 | 0.0% | no |
| `tests/unit/test_fallback_sampling.py` | 113 | 6 | 5.3% | yes |
| `tests/unit/test_fara_probe_scoring.py` | 48 | 3 | 6.2% | yes |
| `tests/unit/test_gate_c_calculator.py` | 458 | 0 | 0.0% | no |
| `tests/unit/test_growth_guard.py` | 70 | 0 | 0.0% | no |
| `tests/unit/test_health_checked.py` | 31 | 0 | 0.0% | no |
| `tests/unit/test_hint_validator.py` | 136 | 4 | 2.9% | no |
| `tests/unit/test_intent_eval.py` | 36 | 2 | 5.6% | yes |
| `tests/unit/test_judgment_probe_instrument.py` | 44 | 4 | 9.1% | yes |
| `tests/unit/test_judgment_probe_scope.py` | 12 | 0 | 0.0% | no |
| `tests/unit/test_lance_guard.py` | 87 | 11 | 12.6% | yes |
| `tests/unit/test_lancedb_table_listing.py` | 61 | 0 | 0.0% | no |
| `tests/unit/test_launchd_plist_install.py` | 155 | 0 | 0.0% | no |
| `tests/unit/test_launchd_process_type.py` | 32 | 0 | 0.0% | no |
| `tests/unit/test_launchd_reload.py` | 295 | 0 | 0.0% | no |
| `tests/unit/test_mawa_join.py` | 103 | 0 | 0.0% | no |
| `tests/unit/test_mawa_join_guard.py` | 69 | 0 | 0.0% | no |
| `tests/unit/test_mawa_join_reader.py` | 82 | 0 | 0.0% | no |
| `tests/unit/test_mawa_join_scorer.py` | 297 | 0 | 0.0% | no |
| `tests/unit/test_mcp_http_client.py` | 635 | 8 | 1.3% | no |
| `tests/unit/test_mcp_vendor_smoke.py` | 66 | 0 | 0.0% | no |
| `tests/unit/test_native_mcp_service.py` | 218 | 0 | 0.0% | no |
| `tests/unit/test_overview_accuracy.py` | 331 | 11 | 3.3% | no |
| `tests/unit/test_owui_preset_drift.py` | 83 | 0 | 0.0% | no |
| `tests/unit/test_owui_seeding_payloads.py` | 182 | 0 | 0.0% | no |
| `tests/unit/test_parallel_seat.py` | 164 | 8 | 4.9% | no |
| `tests/unit/test_part4_production_defects.py` | 173 | 14 | 8.1% | yes |
| `tests/unit/test_persona_matrix_diff.py` | 92 | 0 | 0.0% | no |
| `tests/unit/test_persona_system_prompt.py` | 395 | 38 | 9.6% | yes |
| `tests/unit/test_prompt_signal_overlap.py` | 57 | 0 | 0.0% | no |
| `tests/unit/test_prompt_truncation_detect.py` | 45 | 0 | 0.0% | no |
| `tests/unit/test_provenance_ledger.py` | 131 | 0 | 0.0% | no |
| `tests/unit/test_recall_scorer.py` | 125 | 0 | 0.0% | no |
| `tests/unit/test_retrieval_catalog_pagination.py` | 34 | 2 | 5.9% | yes |
| `tests/unit/test_retrieval_contextualize_gate.py` | 67 | 8 | 11.9% | yes |
| `tests/unit/test_retrieval_payload.py` | 81 | 1 | 1.2% | no |
| `tests/unit/test_retrieval_predicates.py` | 405 | 17 | 4.2% | no |
| `tests/unit/test_review_event_time.py` | 162 | 0 | 0.0% | no |
| `tests/unit/test_root_dispatcher.py` | 72 | 0 | 0.0% | no |
| `tests/unit/test_rotate_logs.py` | 138 | 6 | 4.3% | no |
| `tests/unit/test_self_index_validator_spawn.py` | 67 | 4 | 6.0% | yes |
| `tests/unit/test_semaphore.py` | 83 | 4 | 4.8% | no |
| `tests/unit/test_state_persistence.py` | 142 | 1 | 0.7% | no |
| `tests/unit/test_timing_instrument.py` | 663 | 22 | 3.3% | no |
| `tests/unit/test_weekly_rebuild.py` | 117 | 31 | 26.5% | yes |

## Appendix B — WFE workload payloads

These 33 files are real task code run by the WFE harness, not pytest harness unit tests. They total 927 physical lines. Retain as workload inputs unless a separate workload migration explicitly replaces them.

| Workload file | LOC | Indicator lines | Density |
|---|---:|---:|---:|
| `tests/wfe/graded/arm_testfix_clamp/test_clamp.py` | 21 | 0 | 0.0% |
| `tests/wfe/graded/arm_testfix_percent/test_percent.py` | 23 | 0 | 0.0% |
| `tests/wfe/graded/code_fizz/test_fizz.py` | 23 | 0 | 0.0% |
| `tests/wfe/graded/code_kv/test_parse_kv.py` | 35 | 0 | 0.0% |
| `tests/wfe/graded/code_summarize/test_summarize.py` | 44 | 0 | 0.0% |
| `tests/wfe/graded/cp_fix_00/test_stats.py` | 27 | 0 | 0.0% |
| `tests/wfe/graded/cp_fix_01/test_calendar_util.py` | 28 | 0 | 0.0% |
| `tests/wfe/graded/cp_fix_02/test_tagbag.py` | 27 | 0 | 0.0% |
| `tests/wfe/graded/cp_fix_03/test_pager.py` | 27 | 0 | 0.0% |
| `tests/wfe/graded/cp_fix_04/test_growth.py` | 27 | 0 | 0.0% |
| `tests/wfe/graded/cp_fix_05/test_prefix.py` | 28 | 0 | 0.0% |
| `tests/wfe/graded/cp_fix_06/test_slugs.py` | 28 | 0 | 0.0% |
| `tests/wfe/graded/cp_fix_07/test_wc.py` | 27 | 0 | 0.0% |
| `tests/wfe/graded/cp_fix_08/test_due.py` | 26 | 0 | 0.0% |
| `tests/wfe/graded/cp_fix_09/test_flatten_util.py` | 27 | 0 | 0.0% |
| `tests/wfe/graded/cp_implement_00/test_runs.py` | 26 | 0 | 0.0% |
| `tests/wfe/graded/cp_implement_01/test_spans.py` | 26 | 0 | 0.0% |
| `tests/wfe/graded/cp_implement_02/test_clock.py` | 30 | 0 | 0.0% |
| `tests/wfe/graded/cp_implement_03/test_grid.py` | 26 | 0 | 0.0% |
| `tests/wfe/graded/cp_implement_04/test_fold.py` | 30 | 0 | 0.0% |
| `tests/wfe/graded/cp_implement_05/test_common.py` | 30 | 0 | 0.0% |
| `tests/wfe/graded/cp_implement_06/test_numeral.py` | 31 | 0 | 0.0% |
| `tests/wfe/graded/cp_implement_07/test_nest.py` | 28 | 0 | 0.0% |
| `tests/wfe/graded/cp_implement_08/test_budget.py` | 27 | 0 | 0.0% |
| `tests/wfe/graded/cp_implement_09/test_latest.py` | 28 | 0 | 0.0% |
| `tests/wfe/graded/cp_implement_10/test_rebase.py` | 30 | 0 | 0.0% |
| `tests/wfe/graded/cp_implement_11/test_paths.py` | 30 | 0 | 0.0% |
| `tests/wfe/graded/cp_refactor_00/test_invoice.py` | 28 | 0 | 0.0% |
| `tests/wfe/graded/cp_refactor_01/test_money.py` | 28 | 0 | 0.0% |
| `tests/wfe/graded/cp_refactor_02/test_orders.py` | 28 | 0 | 0.0% |
| `tests/wfe/graded/cp_refactor_03/test_ids.py` | 27 | 0 | 0.0% |
| `tests/wfe/graded/cp_refactor_04/test_rows.py` | 27 | 0 | 0.0% |
| `tests/wfe/graded/cp_refactor_05/test_calc.py` | 29 | 0 | 0.0% |

## Appendix C — benchmark Python harness inventory

This tree contains 88 Python files / 26128 lines. One file is the pytest module `tests/benchmarks/test_empty_retry.py` (also listed in Appendix A); the other 87 files are benchmark harnesses, live probes, scorers, or reporting code. Across all 88 files, 1 file meets the textual marker threshold; that hit is benchmark source code and is not a claim that the runner is mock-driven.

| Benchmark Python file | LOC | Indicator lines | Density |
|---|---:|---:|---:|
| `tests/benchmarks/bench/__init__.py` | 19 | 0 | 0.0% |
| `tests/benchmarks/bench/adhoc_probe.py` | 179 | 0 | 0.0% |
| `tests/benchmarks/bench/cli.py` | 358 | 0 | 0.0% |
| `tests/benchmarks/bench/config.py` | 329 | 0 | 0.0% |
| `tests/benchmarks/bench/discovery.py` | 203 | 0 | 0.0% |
| `tests/benchmarks/bench/lifecycle.py` | 155 | 0 | 0.0% |
| `tests/benchmarks/bench/measure.py` | 439 | 0 | 0.0% |
| `tests/benchmarks/bench/notify.py` | 105 | 0 | 0.0% |
| `tests/benchmarks/bench/prompts.py` | 88 | 0 | 0.0% |
| `tests/benchmarks/bench/report.py` | 141 | 0 | 0.0% |
| `tests/benchmarks/bench/results_io.py` | 77 | 0 | 0.0% |
| `tests/benchmarks/bench/runners.py` | 471 | 0 | 0.0% |
| `tests/benchmarks/bench_cad_gauntlet.py` | 511 | 1 | 0.2% |
| `tests/benchmarks/bench_cad_gauntlet_v2.py` | 459 | 0 | 0.0% |
| `tests/benchmarks/bench_cad_probe.DEEPWEN_FOLLOWUP_001.py` | 333 | 0 | 0.0% |
| `tests/benchmarks/bench_cad_probe.py` | 274 | 1 | 0.4% |
| `tests/benchmarks/bench_candidates_v10.py` | 665 | 0 | 0.0% |
| `tests/benchmarks/bench_capability.py` | 1021 | 4 | 0.4% |
| `tests/benchmarks/bench_compliance_probe.py` | 218 | 0 | 0.0% |
| `tests/benchmarks/bench_daily_soak.py` | 429 | 0 | 0.0% |
| `tests/benchmarks/bench_data_probe.py` | 265 | 0 | 0.0% |
| `tests/benchmarks/bench_fara_cua_probe.py` | 206 | 0 | 0.0% |
| `tests/benchmarks/bench_judgment_probe_v6.py` | 1079 | 0 | 0.0% |
| `tests/benchmarks/bench_lab_exec.py` | 1401 | 0 | 0.0% |
| `tests/benchmarks/bench_long_context_probe.py` | 216 | 0 | 0.0% |
| `tests/benchmarks/bench_mbptl.py` | 823 | 0 | 0.0% |
| `tests/benchmarks/bench_mlx_hf.py` | 129 | 0 | 0.0% |
| `tests/benchmarks/bench_mtp_probe.py` | 163 | 0 | 0.0% |
| `tests/benchmarks/bench_omlx_soak.py` | 303 | 0 | 0.0% |
| `tests/benchmarks/bench_omlx_stress_extras.py` | 358 | 0 | 0.0% |
| `tests/benchmarks/bench_omlx_v3.py` | 1123 | 0 | 0.0% |
| `tests/benchmarks/bench_reasoning_probe.py` | 336 | 0 | 0.0% |
| `tests/benchmarks/bench_refusal_preservation_probe.py` | 258 | 0 | 0.0% |
| `tests/benchmarks/bench_repair/__init__.py` | 54 | 0 | 0.0% |
| `tests/benchmarks/bench_repair/checkpoint.py` | 51 | 0 | 0.0% |
| `tests/benchmarks/bench_repair/cli.py` | 302 | 0 | 0.0% |
| `tests/benchmarks/bench_repair/config.py` | 53 | 0 | 0.0% |
| `tests/benchmarks/bench_repair/corpus.py` | 43 | 0 | 0.0% |
| `tests/benchmarks/bench_repair/report.py` | 137 | 0 | 0.0% |
| `tests/benchmarks/bench_repair/runner.py` | 219 | 0 | 0.0% |
| `tests/benchmarks/bench_repair/scoring.py` | 17 | 1 | 5.9% |
| `tests/benchmarks/bench_repair.py` | 39 | 0 | 0.0% |
| `tests/benchmarks/bench_research_probe.py` | 423 | 0 | 0.0% |
| `tests/benchmarks/bench_router.py` | 585 | 0 | 0.0% |
| `tests/benchmarks/bench_router_conditions.py` | 900 | 0 | 0.0% |
| `tests/benchmarks/bench_security.py` | 33 | 0 | 0.0% |
| `tests/benchmarks/bench_security_exec_probe.py` | 343 | 0 | 0.0% |
| `tests/benchmarks/bench_spl_probe.py` | 226 | 0 | 0.0% |
| `tests/benchmarks/bench_tool_use_probe.py` | 331 | 0 | 0.0% |
| `tests/benchmarks/bench_tps.py` | 97 | 1 | 1.0% |
| `tests/benchmarks/bench_vision_probe.py` | 307 | 0 | 0.0% |
| `tests/benchmarks/bench_window_seat_sweep.py` | 210 | 0 | 0.0% |
| `tests/benchmarks/cad_gauntlet_v2_oracles.py` | 132 | 0 | 0.0% |
| `tests/benchmarks/cad_grader.py` | 105 | 0 | 0.0% |
| `tests/benchmarks/capability_lib.py` | 205 | 0 | 0.0% |
| `tests/benchmarks/coding_shootout_analyze.py` | 339 | 0 | 0.0% |
| `tests/benchmarks/compare_cad_gauntlet.py` | 124 | 0 | 0.0% |
| `tests/benchmarks/compliance_judgment_contract_v2.py` | 237 | 0 | 0.0% |
| `tests/benchmarks/compliance_judgment_r1_experiment.py` | 547 | 0 | 0.0% |
| `tests/benchmarks/compliance_judgment_r1_experiment_v2.py` | 651 | 0 | 0.0% |
| `tests/benchmarks/compliance_stream_p0_live_capture.py` | 221 | 0 | 0.0% |
| `tests/benchmarks/compliance_stream_p3c_assess_part_live.py` | 309 | 7 | 2.3% |
| `tests/benchmarks/eg2_runtime_measure.py` | 133 | 1 | 0.8% |
| `tests/benchmarks/eg2_runtime_parity.py` | 143 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/__init__.py` | 7 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/__main__.py` | 3 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/cli.py` | 45 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/framework.py` | 518 | 1 | 0.2% |
| `tests/benchmarks/embedding_consumers/gen_media.py` | 188 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/probes/__init__.py` | 28 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/probes/_common.py` | 217 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/probes/attack_mapping.py` | 114 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/probes/bully.py` | 356 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/probes/compliance.py` | 271 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/probes/harmful_intent.py` | 140 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/probes/hygiene.py` | 589 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/probes/media.py` | 488 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/probes/memory.py` | 355 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/probes/rag.py` | 542 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/probes/refusal_classifier.py` | 171 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/probes/router.py` | 200 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/probes/seccode.py` | 425 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/probes/security_text.py` | 184 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/probes/tool_preselect.py` | 105 | 0 | 0.0% |
| `tests/benchmarks/embedding_consumers/probes/wiki_search.py` | 111 | 0 | 0.0% |
| `tests/benchmarks/notify_soak_complete.py` | 65 | 0 | 0.0% |
| `tests/benchmarks/prismml_mlx_server.py` | 289 | 0 | 0.0% |
| `tests/benchmarks/test_empty_retry.py` | 67 | 0 | 0.0% |

## RESULT

Plan authored from repository snapshot `b75c16d`; no live claim is made.

## WHAT CHANGED

- `docs/test_trim/PHASE2_PLAN.md`: inventory, per-module live owner map, risk-ranked gaps, and sequenced lane plan with measured baselines and labeled deletion estimates.

## EVIDENCE

- `git rev-parse HEAD` → `b75c16d8419e0f324585eabb709bb0f900124806`.
- `tests/unit`: 429 files / 123,850 lines; `tests/wfe/tests`: 61 / 20,250; `tests/security`: 157 / 22,050; `tests/benchmarks/test_empty_retry.py`: 1 / 67. Combined → 648 files / 166,217 lines.
- Marker-density scan across those 648 files → 184/648 (28.4%) at or above 5%; heavy-file LOC 56,093. Per-file measurements and the primary-area assignment are in Appendix A.
- `tests/wfe/graded/**/test_*.py` → 33 workload files / 927 lines. `tests/benchmarks/**/*.py` → 88 Python files / 26,128 lines; one is the 67-line pytest module.
- `config/portal.yaml` `mcp_fleet` → 33 module IDs; exposure and default-enable attributes were read to classify the route in the MCP table.
- `uv run portal trace --help` → command help only; no trace/service call. Its available sections are `host`, `containers`, `workspaces`, `pins`, `engines`, and `lab`.
- `git show` of `c04dbf044`, `19cea3c38`, `2144cb5c2`, `f4929ed79`, `5caaf400d`, `376614f11`, and `c3a9caee9`, plus the cited historical rows in `tests/UAT_RESULTS.md`, supplied the incident examples.

## ORCHESTRATOR RUNS

These are proposed live commands only; this worker did not run them. A passing `portal trace` JSON report must show PASS for the selected live hops and a matching actual trace. A UAT pass must append a real OWUI chat URL, response assertions, and routed model to `tests/UAT_RESULTS.md`. The hunt proof must print PASS with observed `hunt_start`, terminal `hunt_status`, `hunt_leads`, `hunt_case`, returned IDs cited by the final answer, and its tool evidence source.

```bash
uv run portal trace --json --section workspaces --section engines --section lab
uv run python tests/portal5_uat_driver.py --test WS-01 --append
uv run python scripts/proofs/owui_hunt_chat.py --index hb_kyoushi_s1 --require-sources
uv run python -m tests.wfe.e2e.rig --live
```

For phase-2 owners, the planned executable commands after those proof files/cases exist are `uv run python scripts/proofs/owui_route_trace.py --workspace auto --case route-smoke`, `uv run python scripts/proofs/owui_mcp_matrix.py --case <mcp_fleet-id>`, `uv run python scripts/proofs/ide_mcp_matrix.py --case <ide-only-id>`, `uv run python scripts/proofs/owui_compliance_grounding.py --case cip-003-r1-2-6`, `uv run python tests/wfe/e2e/owui_live.py --case <stable-realuse-case>`, and `uv run python tests/benchmarks/bench_owui_route.py --case <stable-case> --runs 1`. Pass means the case's actual per-turn trace/tool/result and readback match; an answer-only response, health-only response, missing trace, or absent durable readback fails the proof.

## OPEN

- The phase-1 worktree changes are not present at this HEAD; all LOC and percentages must be refreshed once they merge.
- Mock density is a keyword heuristic. It does not tell whether a whole file is replaceable, which is why line-reduction values are estimates and tests must be mapped one by one before deletion.
- Some MCPs are IDE-only or disabled by default in config. Their route owners must respect the current exposure and enablement; a lane cannot be declared live-green on a path that is unavailable.
- The names of new proof scripts are planning targets. Their implementation and exact schema/receipt fields must be reviewed in their own one-area lanes before running them.

## UNPROVEN

- No service state, deployed build identity, current model/engine availability, OWUI response, real lab query, compliance source read, MCP tool result, real store record, WFE row, or benchmark result was checked during this plan-only lane.
- Historical UAT rows and commit incident notes describe earlier runs; they do not establish current behavior.
