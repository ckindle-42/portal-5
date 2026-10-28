---
id: unit-ollama-native-passthrough
kind: mixed
title: "Native Ollama passthrough — authenticated, load-guarded inference"
sources:
- type: code
  path: portal/platform/inference/router/ollama_passthrough.py
- type: code
  path: portal/platform/inference/router/app.py
- type: code
  path: portal/platform/inference/router/lifespan.py
- type: code
  path: portal/platform/inference/load_guard.py
- type: code
  path: portal/platform/inference/router/routing.py
- type: code
  path: portal/platform/inference/tool_preselect/preselector.py
- type: code
  path: portal/platform/inference/ollama_native.py
- type: code
  path: portal/platform/memory/graph_memory.py
- type: code
  path: portal/modules/research/tools/rag_multimodal.py
- type: code
  path: portal/modules/compliance/core/transport_dialects.py
- type: code
  path: portal/modules/compliance/core/reading_transport.py
- type: code
  path: portal/platform/wiki/adapters/portal_inference.py
- type: code
  path: config/ollama_direct_allowlist.yaml
- type: code
  path: scripts/validation/ollama_direct.py
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: .env.example
- type: code
  path: tests/unit/test_ollama_passthrough.py
- type: code
  path: tests/unit/test_ollama_direct_allowlist.py
- type: code
  path: scripts/memory_safety_watch.py
- type: code
  path: deploy/launchd/com.portal5.host-ml-watch.plist
- type: code
  path: tests/unit/test_memory_safety_watch.py
claims: []
confidence: high
tags:
- capability
- inference
- memory-safety
---

# Native Ollama passthrough — authenticated, load-guarded inference

The pipeline exposes `POST /ollama/api/chat`, `/generate`, and `/embed`, plus
read-only `/ollama/api/ps`, `/tags`, and `/show`. Every route requires the
pipeline bearer key. The proxy selects the first healthy Ollama backend from
`BackendRegistry`, forwards native request bytes unchanged with a dedicated
HTTPX client, and streams the upstream status, headers, and body back without
the OpenAI translation in `OllamaNativeTransport`.

Inference routes call `LoadGuard.admit` before sending, track the model as busy
while the response is being read, and release both tracking and any cold-load
lock on completion or stream close. A guard refusal is returned as HTTP 507 in
Ollama's `{"error": "..."}` shape. This preserves `think`, `format`, `images`,
`options`, `keep_alive`, and `message.thinking` for native-protocol clients.

The memory extractor, RAG page transcription, compliance `ollama-native`
rollback, and wiki seeding adapter default to this route and send
`PIPELINE_API_KEY`. Tool preselection and startup warmup stay inside the
pipeline process and call `LoadGuard.admit` directly. The pinned intent-router
call is only tracked as busy (`LoadGuard.begin`), never admitted: it is resident,
and an admission check would put an `/api/ps` round-trip inside every routing
deadline. The AST-based
`validate_system` check scans runtime `portal/**` code and requires a reasoned
entry in `config/ollama_direct_allowlist.yaml` for operator probes, gated
engine diagnostics, or guarded pipeline internals that still construct native
requests. Multi-model live checks run under `scripts/memory_safety_watch.py`,
which samples host swap, memory pressure, and oMLX headroom every two seconds.
It trips on critical kernel memory pressure, or on low free swap only while free
memory is also low (macOS grows swap in 1 GiB files on demand, so low free swap
alone is routine). On a trip it stops test clients, unloads non-router Ollama
and idle oMLX models, and writes an evidence log.

The same loop watches the host-native launchd ML services, which the Ollama and
oMLX guards cannot see. The service list is derived from `config/portal.yaml` —
`mcp_fleet` entries with `host_native: true` plus every `host_jobs` entry, keyed
by `native_service` (or `id`, or the label without its `com.portal5.` prefix) and
carrying its `launchd_label` — so no label is hardcoded. Each sample resolves the
job's pid with `launchctl print gui/$UID/<label>`, walks `ps` for a python child
when the job is a shell wrapper, and reads that pid's `phys_footprint` from
`footprint -p` rather than `ps` RSS. A service held above its ceiling for three
consecutive samples is reported once with service, footprint and ceiling, and
only a **measured** ceiling is restart-eligible: the offending service alone is
restarted with `launchctl kickstart -k gui/$UID/<label>`, at most once per
30-minute per-service cooldown, so a leak in one server no longer needs a
whole-host trip. A **provisional** ceiling produces a log-only
`HOST SERVICE CEILING BREACH (log-only)` line with `ceiling_status=provisional`
and never a kickstart, because guessing a ceiling in the live watchdog would
restart a serving process on a guess (mlx-transcribe peaked 5.5 GB on
2026-10-07 against a 6 GiB placeholder). A service that cannot be measured (not
loaded, no python child, unparseable `footprint` output) is logged once per run
and never restarted. The table is `DEFAULT_HOST_CEILINGS` in the script, one
`ServiceCeiling(gib, measured)` per service: today only `eg2-embedding` is
measured — 2.09 GiB idle on 2026-10-28 and a ~5 GB peak at the 2026-10-07 13:29
leak, ceilinged at 6 GiB. `vl-retrieval` and `mlx-speech` 8 GiB,
`mlx-transcribe` 6 GiB, `mflux` 16 GiB, `video_mlx` 24 GiB and 4 GiB for any
other host service are provisional until an operator records measured idle/peak
and sets `measured=True`. `--service-ceilings` / `WATCH_HOST_CEILINGS_GIB`
(`eg2-embedding=0.5`) overrides the Gib value but keeps the service's
measured/provisional status, so an override alone cannot arm a restart.

The script has two modes. The default is the on-demand emergency watchdog for a
live test: swap/pressure trip, test-client kills and model unloads, 2 s samples.
`--services-only` runs the service ceilings alone — no `_snapshot` read, no
`_trip`, no PID-file kills, no Ollama/oMLX unloads — on a 30 s interval, with the
same three-sample debounce counted in samples. That mode is the always-on
launchd job `com.portal5.host-ml-watch`
(`deploy/launchd/com.portal5.host-ml-watch.plist`, `KeepAlive`, logs under
`~/.portal5/logs`), installed idempotently by `_ensure_native_services` next to
the oMLX watchdog and shown in `./launch.sh status`; it runs on the repo venv
interpreter (`__PORTAL_ROOT__/.venv/bin/python`) like `com.portal5.log-rotate`.
The 2026-10-07 embedder leak happened in normal use, not under a live test,
which is why the ceilings cannot depend on a test being in flight.

## Why

On 2026-10-07 oMLX and Ollama loaded 27B-class models at once into one unified
memory pool and the Mac was watchdog-reset. Callers that reached Ollama directly
never met the host-wide load guard. Routing native callers through the pipeline
over HTTP puts every inference load behind one admission point, while MCP
modules keep zero imports from `portal.platform.inference` (Rule 3). The
rejected alternative was sending these callers through the OpenAI `/v1`
surface: it would drop native fields (`think`, `format`, `message.thinking`,
request-time `num_ctx`) that compliance readings and memory extraction rely on.
