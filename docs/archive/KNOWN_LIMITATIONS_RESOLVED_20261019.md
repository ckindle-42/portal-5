# Known Limitations — resolved register

Resolved entries moved out of the current-only `KNOWN_LIMITATIONS.md` on
2026-10-19. They are kept verbatim (minus wiki render markers) so the decision,
evidence and "do not reinstate" notes survive. Each also has a one-line entry in
`CHANGELOG.md` under `[Unreleased]`.

### CadQuery and build123d on linux/arm64 (RESOLVED)

- **ID**: P5-CAD-ARM64-001
- **Status**: RESOLVED (TASK_CAD_MODULE_OVERHAUL_V1 Phase 0, 2026-08-27). See
  `portal/modules/cad/PLATFORM.md` for the full empirical record.
- **Original claim (now known wrong)**: "CadQuery and build123d both require OCP (OpenCASCADE Python bindings), which has no pre-built wheels for `linux/arm64` — cannot install on arm64, use OpenSCAD only." This was a **pip-wheel artifact**, not a platform ceiling: true for *pip* wheels of OCP as of early 2024, but conda-forge's `ocp`/`occt` packages ship for `linux-aarch64` and `osx-arm64` (also linux-64/osx-64/win-64).
- **Resolution**: pip-installed arm64 wheels in the dedicated `Dockerfile.cad` image: `build123d==0.11.1` (pulls `cadquery-ocp-novtk`, which ships `manylinux_2_28_aarch64` and `macosx_11_0_arm64`) and `build123d-mcp==0.3.90`. The earlier conda-forge/micromamba layer in `Dockerfile.mcp` is **gone** — it was only needed while pip had no arm64 OCP wheels. CadQuery is intentionally not installed (its OCP variant conflicts with build123d's). `capabilities.py` probes `build123d`/`ocp`/`step_read` (and the live engine) at runtime instead of hardcoding platform assumptions.
- **Do not reinstate** the "no arm64 wheels, OpenSCAD only" wording — it is factually wrong regardless of pip's continued arm64 gap. If a future session hits a *different* install failure, record the specific new failure as its own entry rather than reviving this one.
- **In-container verification (2026-10-06)**: image `Architecture` = `arm64`, container `uname -m` = `aarch64`; `build123d 0.11.1`, `vtk 9.7.1`, OCP `OCP.cpython-311-aarch64-linux-gnu.so`, `build123d-mcp 0.3.90`; the eight gauntlet oracle parts all grade PASS in the container (`machine=aarch64`); `/capabilities` reports `build123d: true`, `ocp: true`, `engine: true`, `arch: aarch64`. The host (macOS arm64) passes the same oracles. This closes the residual-verification item the original entry carried.

## Why

The original register entry existed to stop CadQuery/build123d from being silently re-added in a way that would build on x86 CI and fail on Apple Silicon. That risk is now inverted: OCP genuinely works on arm64 via conda-forge, and the residual risk is a future reader trusting the old "impossible" framing and never trying. Keeping this entry (marked resolved, with the original wrong claim preserved) rather than deleting it prevents that regression in belief, while the still-open residual-verification item keeps the record honest about what was proven where.
---
### `pytest portal` Write-Through Test Artifacts (Resolved)

- **Status**: RESOLVED 2026-07-29.
- **Former issue**: Security module tests could write journals and checkpoints into the real runtime tree, leaving dated entries in the committed `field_journal/` history and stray checkpoint files.
- **Resolution**: The autouse fixture `isolated_security_writes` in `portal/modules/security/tests/conftest.py` monkeypatches `field_journal.JOURNAL_DIR`, `loop.RESULTS_DIR`, and `loop.CHECKPOINT_DIR` into each test's `tmp_path`. The production modules also stopped creating those directories merely by being imported; the write functions (`field_journal.write_entry`, `loop._write_checkpoint`) create their destination lazily at write time.
- **Regression coverage**: `portal/modules/security/tests/test_write_isolation.py` writes both artifact types and asserts that their parents are the fixture sandbox.

## Why

Write-through test artifacts are dangerous because they look like real committed history and can ride along with an unrelated commit — the field journal is tracked, so a test-side entry becomes an untraceable line in the repo. Routing the write destinations through a fixture-injected `tmp_path` makes the sandbox the only possible target, and asserting the parent path in the regression test proves the isolation mechanically rather than by inspection.
---
### Security Bench Import Mutated Host Environment (Resolved)

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
---
### POST /v1/messages Null Success Body (Resolved)

- **ID**: P5-ANTHROPIC-COMPAT-001
- **Status**: RESOLVED 2026-07-29.
- **Former issue**: The non-streaming `/v1/messages` (Anthropic Messages API) success path completed after checking the loopback response status but did not return the translated response, so FastAPI serialized Python `None` as `null` — HTTP 200 with an empty body.
- **Resolution**: `anthropic_messages` in `portal/platform/inference/router/handlers.py` now returns `openai_response_to_anthropic(resp.json(), model_id)` on HTTP 200 (line ~1328). The translation lives in `portal/platform/inference/router/anthropic_compat.py`. Error propagation and the streaming translation path are unchanged.
- **Regression coverage**: `test_anthropic_non_streaming_success_returns_message` in `tests/unit/test_pipeline.py` exercises the in-process dispatch (the ASGI loopback was replaced 2026-09-25 — it buffered streamed replies; see P5-PIPELINE-HARDEN-001) and asserts the complete Anthropic Messages response shape, content, stop reason, model, and token usage.
- **Discovered**: 2026-07-13, live-verifying the opencode CLI-contract migration.

## Why

An Anthropic-compatible endpoint returning HTTP 200 with a null body is the worst possible failure mode for a CLI client: the request looks successful so the client waits for a response that never arrives. The fix keeps routing through `chat_completions` but makes the return value explicit, and the test asserts the full wire shape rather than just the status code, so a regression reintroducing the silent null is caught at the contract level.
---
### Request-Size Cap Relied on Content-Length Only (Resolved)

- **ID**: P5-REQ-SIZE-001
- **Status**: RESOLVED 2026-07-29.
- **Former issue**: The pipeline enforced its request-size cap only through `Content-Length`, so HTTP chunked transfer encoding bypassed the limit — a client could stream an oversized inference body past the check.
- **Resolution**: `RequestBodyLimitMiddleware` in `portal/platform/inference/router/request_limits.py` buffers and bounds the two JSON inference endpoints before route handling, enforcing the same limit against declared and streamed/chunked bodies. Its module docstring documents that a `Content-Length`-only check is bypassed by chunked transfer. Oversize requests return 413 before the handler runs.
- **Regression coverage**: `test_chunked_body_over_limit_is_rejected_before_handler` in `tests/unit/test_request_limits.py` sends a chunked async body with no usable `Content-Length` and verifies rejection with status 413.

## Why

`Content-Length` is a header the client controls, and chunked transfer omits it entirely, so trusting it for a size cap leaves the endpoint unbounded for any client that speaks HTTP/1.1 chunking. Middleware that reads the actual ASGI body stream and enforces the same ceiling on what it consumes closes the gap at the transport layer, and the chunked regression test proves the exact bypass that motivated it.
---
### P5-EMERGENT-002 — Deterministic capability progression (Resolved)

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
---
### LLM Router Model Evicted by Single Inference Request (Resolved)

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
- **2026-09-25 follow-up — fleet-wide KV churn, and no recovery after eviction**:
  mining `ollama.log` showed 1,053 of 1,187 Ollama load decisions since
  2026-09-01 had to evict. Each seat's footprint was then measured live at its
  baked context: most are weight-dominated, but dense-attention seats scale
  with `OLLAMA_NUM_PARALLEL` — DeepSeek-R1 8B ctx64k 10.0 / 15.2 / 25.7 GiB and
  granite4.1:30b at compliance's 98,304 window 29.7 / 44.5 / ~73 GiB at 1 / 2
  / 4 slots. At 1 slot the concurrent auto-council reviewers fit (50.3 vs
  60.2 GiB at 2) and so does the compliance granite seat, so the daemon now
  runs `OLLAMA_NUM_PARALLEL=1` (same-model requests queue instead of running
  side by side — a known cost for security/compliance fan-out, to revisit).
  `keep_alive: -1` only stops the idle timer; the scheduler still evicts a
  pinned model to fit a load.
  Three router defects, all fixed: (1) the routing call's deadline cancelled
  its own cold load (Ollama: "client connection closed before llama-server
  finished loading, aborting load"), so an evicted router never came back
  until a pipeline restart — a timeout now schedules one background reload;
  (2) warmup and reload sent a trivial prompt, which loaded the weights but
  never cached the ~1,500-token routing prefix: a cold call measured 1.32 s
  (0.82 s prefill) against the deadline and, cancelled, never populated the
  cache — both now send the routing call itself (`warm_router_model`,
  `routing.py`); (3) `LLM_ROUTER_TIMEOUT_MS` 1000 sat inside the normal warm
  spread (0.5-1.0 s, mean 0.8 s) and docker-compose defaulted it to 500; all
  three places are now 2000. Verified live from a restart: 8/8 auto requests
  routed by the classifier, 0 timeouts, mean 0.70 s.
  oMLX had no idle unload (`idle_timeout_seconds = None`): idle models held
  ~41 GiB of unified memory Ollama could not reclaim (`system_limited=true`).
  `~/.omlx/settings.json` now sets `idle_timeout.idle_timeout_seconds: 300`
  (Ollama's default), verified firing (idle 305 s > ttl 300 s). oMLX's
  `memory_guard_tier` stays `balanced` pending data.

## Why

The router warmup pins the model with `keep_alive: -1`, which is load-bearing: without it the router re-cold-loads on every heavy inference request. But the same pin becomes a memory bug when `options.num_ctx` is omitted, because Ollama then reserves the model's full context window times the parallel slots — tens of GiB for a small model — which forces the scheduler to evict the router it was trying to keep warm. Matching the warmup context to the real routing call and the workspace limit is what makes the pin actually safe.
---
### Model Narrates a Fake Tool Call Instead of Invoking the Real One (Resolved)

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
---
### Ollama GPU Overhead Reservation (Resolved)

- **ID**: P5-OLLAMA-GPU-OVERHEAD-001
- **Status**: Resolved 2026-08-10 (TASK-BATCH-BENCH-002 Part A). Not a bug in Ollama or the fleet — a misconfigured safety margin, corrected in place.
- **Description**: `com.portal5.ollama.plist`'s `OLLAMA_GPU_OVERHEAD` was set to `42949672960` (40GiB), intended as coexistence headroom so Ollama and oMLX never collide and crash the box on this 64GB M4 Pro. In practice this overhead is subtracted from a largely fixed Metal working-set ceiling (~56GiB on this hardware), not from live free memory — freeing oMLX's loaded models and even a full daemon restart left Ollama's reported "available" figure completely unchanged (`model requires 19.7 GiB but only 15.5 GiB are available (after 40.5 GiB overhead)`). At 40GiB, the reservation capped **any single Ollama model at ~15.5GiB regardless of oMLX's actual state** — a real problem, since the fleet already runs 20-30GB-class models (Muse-Glimmer-30B, Deepwen-3.6, Qwen3-Coder-30B-A3B) routinely.
- **Fix**: lowered to `21474836480` (20GiB) in the plist, reloaded via `sudo launchctl bootout system/com.portal5.ollama && sudo launchctl bootstrap system /Library/LaunchDaemons/com.portal5.ollama.plist` (note: `launchctl kickstart -k` restarts the process but does **not** re-read the plist's `EnvironmentVariables` — a full bootout/bootstrap is required to pick up an env change). 20GiB still reserves real coexistence headroom (sized off oMLX's own observed footprint, ~22-29GB for its largest single models) without starving Ollama's own budget down to a sliver. Verified: Muse-Glimmer-30B (19.7GiB) loads cleanly post-fix.
- **If this recurs**: check `ps eww -p <ollama-serve-pid> | grep OLLAMA_GPU_OVERHEAD` against the current plist value first — a mismatch means the daemon needs a full bootout/bootstrap, not just a kickstart.

## Why

This is a permanent, box-level constraint that silently caps every future large-model bench on this host, not something scoped to the Muse-Glimmer bench that surfaced it. The kickstart-vs-bootstrap distinction is the actual gotcha (identical-looking "restart" commands, only one re-reads env vars) — a future session hitting the same static "N GiB available" error after changing an Ollama plist env var should find this before re-diagnosing it as a stale-cache or live-memory problem again.
---
##### An engine with no route is an engine that does not exist (RESOLVED)

- **ID**: T5-COMPLIANCE-LANDING-001
- **Status**: RESOLVED `TASK_COMPLIANCE_ENGINE_LANDING_V1`. Six prior tasks
  (T1–T4 plus the completeness correction) improved `coverage.py`,
  `mapping_store.py`, `applicability.py`, `tiers.py`, and `engine.py` while
  none of them had a route or a tool. `engine.route()` had never dispatched at
  HEAD, and the `⚖ Portal Compliance Analyst` workspace's `tools:` list
  contained none of the compliance-specific tools — not `compliance_ingest`,
  not `compliance_search`, not even the pre-existing `nerc_cip_currency`.
- **Description**: Every green number up to this task came from tests calling
  the library directly (`Register.load()`, `coverage_matrix()`,
  `make_proposer()` over the planted corpus). No test exercised the MCP
  surface a model actually sees, so no test caught the gap — the module was
  correct and completely unreachable at the same time. `compliance_mcp.py`
  now carries 8 new `@mcp.tool()` functions (`compliance_gaps`,
  `compliance_orphans`, `compliance_change_impact`, `compliance_mappings`,
  `compliance_scope`, `compliance_route`, `compliance_review_list`,
  `compliance_review_decide`), plus `compliance_ingest`/`compliance_search`
  (pre-existing custom routes, previously absent from the discovery manifest
  entirely — reachable by direct POST but invisible to the tool-registry's
  `GET /tools` discovery, so no model could ever have called them). All are
  in `config/inference/tools_manifest_compliance_mcp.json`, `_DISPATCH`, AND
  the workspace's `tools:` list — being reachable at the REST surface is
  necessary but not sufficient; the workspace's `tools:` list is what the
  model sees.
- **V3 update (2026-09-05)**: `compliance_requirement`,
  `compliance_analyze`, `compliance_compare`, and `compliance_impact` are now
  registered through the same three layers. The earlier V2 limitations that
  forced determinate questions to `UNRESOLVED` and kept redline generation
  behind a `NotImplementedError` gate are closed by the source-backed
  assessment and draft-as-proposal paths. Remaining SME review is limited to
  the closed decision-kind enum; it is not a prerequisite for computation.
- **Guard**: `compliance.workspace_tools` (`portal/platform/wiki/claims.py`)
  cross-checks all three — the workspace list, the discovery manifest, and
  `_DISPATCH` — for every `compliance_*`/`nerc_cip*` tool name, and reports
  `unreachable:<name>` the moment any one of the three drops it. The current
  inventory is 36 reachable compliance/register tools. Verified to actually fail:
  removing one dispatch entry flips the probe from
  `all_reachable:12` to `unreachable:compliance_scope`.

#### Why

A probe that only checks a tool exists somewhere in the codebase would have
passed for six tasks straight while the workspace's model never saw it — that
is the exact failure this task exists to fix, so the guard has to bind all
three layers (manifest, dispatch, workspace list) at once, not just one of
them. Recording it here — with the negative-test evidence that the probe
actually flips red — is what keeps a future refactor from quietly re-severing
one of the three links and having every existing test stay green.
---
##### Do not gate on a question the data answers (RESOLVED)

- **ID**: T5-COMPLIANCE-LANDING-002
- **Status**: RESOLVED `TASK_COMPLIANCE_ENGINE_LANDING_V1` Phase 4.
  `applicability.py`'s own docstring asserted: *"Asset scope is operator
  input. Which BES Cyber Systems exist and at what impact rating is not
  derivable from any document in the corpus."* That claim held across four
  prior tasks (`[GATE]` in T3, carried forward through T4 and the
  completeness correction) and was false the moment the operator's own CIP
  policies entered the corpus: CIP-002 R1 *requires* the entity to identify
  and categorize its BES Cyber Systems, and every CIP policy states its
  applicability in exactly the language `parse_applicable_systems` was
  already written to read. `AssetScope.declared_by` existed in the dataclass
  from T3 onward — nobody had populated it.
- **Description**: `scope_derive.derive_scope()` now unions impact ratings
  and associated-system types across every ingested span containing an
  explicit impact-rating statement, populates `declared_by="derived:corpus"`,
  and files an `applicability_scope` review-queue item with the citing
  evidence (25 spans max, confidence weighted by evidence count). Verified
  live against the operator's real CIP-007 + CIP-003 corpus: 143 citing spans
  produced `impact_present={high, medium, low}` with full evidence, no
  operator prompt required.
- **What stayed a genuine judgement call, not a gate**: `has_erc` and
  `has_control_center` default to the inclusive `True` (matching
  `AssetScope()`'s own default) rather than being derived from a negative
  search — deriving a *false* (excluding a scope dimension) from the mere
  absence of a corroborating span would reproduce the exact false-exclusion
  risk this phase was written to prevent, just moved one level down. The
  queue item names this explicitly so an operator can correct it.

#### Why

The applicability gate was carried forward unexamined across three follow-on
tasks because "operator input" reads as a reasonable, conservative default —
it is the same shape as a genuine gate, so nothing forced a re-check. The
lesson generalizes past this one field: **before declaring something operator
input, check whether the operator's own documents already answer it.** A gate
that never gets re-examined is functionally a permanent block, and this one
sat behind four tasks despite the parser to close it having existed the whole
time.
