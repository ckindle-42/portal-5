# P5_ROADMAP.md — Portal 5 v7 Future Enhancements

The roadmap document at the repo root is the tracking file for open Portal 5
work. Its header states the current release as 8.0.0, which matches the `version`
field in `pyproject.toml`. Completed work is not kept in the open queue:
`CHANGELOG.md` records shipped milestones, and the roadmap marks all v5.0 through
v6.1.0 items as DONE there. The live set of open items, each with its
implementation or absence in code, is tracked in the roadmap's open-work section
rather than being repeated in a doc copy here.

## Why

This unit exists because the roadmap header was once extracted as if it were a
fact about the system. The only code-determined facts it contains are the release
version in `pyproject.toml` and the location of the completed-work record in
`CHANGELOG.md`; the roadmap itself is a planning artifact, not a fact source, so
the unit now asserts only those two anchors and does not restate the roadmap
body.

---

## Future Considerations (Not Yet Implemented)

This queue lists open roadmap items. Two of them are grounded in current code:
`P5-FUT-WS-FROM-MODULE` and `P5-FUT-MODEL-CHAINWALK` both hinge on
`workspace_model` in `config/personas/*.yaml` being the canonical served-model
selector that `portal/platform/inference/config.py` reads in the serving path,
while `preferred_models` is advisory metadata that is NOT consumed —
`scripts/persona_intent_audit.py` documents it as dead metadata — so a live
chain-walk over `preferred_models` does not exist.

The security rows have code anchors for their current state but no implementing
feature. `P5-FUT-RBP-LLM-SECURITY-EXPAND` would extend the OWASP LLM Top 10 probe
set in `portal/modules/security/core/llm_redteam.py`. `P5-FUT-RBP-MCP-SECURITY`
would add an MCP-compromise challenge class; `config/challenge_classes.yaml`
still marks classes `status: aspirational`. `P5-FUT-ABLATION-CAPTURE-PERSIST`
touches the corpus driver `portal/modules/security/core/corpus_replay_bench.py`,
which records verdicts but not Expert/Hunter handoffs. `P5-FUT-PROMPT-GUARD-INLINE`
has no code footprint: no input-side prompt-injection filter exists in
`portal/platform/inference/router/`.

Completed, canceled, and retired items are kept out of this queue; they live in
the referenced code and in git history.

## Why

A roadmap queue is only useful when each entry points at the code that either
absorbs it or currently stands in for it. `config.py` and `persona_intent_audit.py`
decide that `workspace_model` is canonical and `preferred_models` is dead, so
those two items are grounded; the security and prompt-guard rows have no
implementing code, so their bodies only assert the existing surface that planned
work would extend, leaving the aspirational status explicit.

---

### Speculative Decoding / MTP — RETIRED (commit 3a0c58e)

Speculative decoding and MTP support lived in the retired MLX proxy and are not
part of the current serving stack. The archived
`scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py` reads the draft-model map
(`speculative_decoding.draft_models` in `config/backends.yaml`) into
`DRAFT_MODEL_MAP` and passes `--draft-model` when the draft for a target model is
present locally; that surface was deleted with the proxy at commit 3a0c58e. The
archive README confirms the scripts are not runnable at HEAD and that any future
speculation work targets Ollama's native path rather than MLX — the archive exists
as reference for the admission-control pattern and the draft-model mapping.

## Why

The MLX-proxy speculative-decoding and MTP unblock paths were removed with the
proxy because Ollama's native MLX Metal backend reached throughput parity without
the dual-stack admission and thread-patch complexity. The archived implementation
is intentionally retained as reference but is not runnable at HEAD, so this unit
records the removal and the surviving reference rather than describing a live
feature.

---

### workspace-clean Utility (LOW priority)

A `workspace-clean` command is planned but does not exist: `launch.sh` has no such
subcommand. What the code does determine is the layout the utility would operate
on. `portal/platform/mcp_host/workspace.py` resolves the shared workspace root
from `WORKSPACE_DIR` or `AI_OUTPUT_DIR` (default `~/AI_Output` on the host) and
creates per-category `generated/` subdirectories on demand, so the generated tree
grows without any age-based purge. The only time-based cleanup in the repo is the
speech janitor `_cleanup_stale_audio` in `scripts/mlx-speech.py`, which deletes
stale audio older than a bounded max age. A general workspace cleaner therefore
remains open roadmap work with no code footprint yet.

## Why

The shared output directory grows unbounded because nothing prunes old generated
artifacts, and the unit records both the gap and why it stays low priority. The
only expiry-driven janitor that exists is scoped to one category (`mlx-speech.py`),
generalizing it to the full workspace is planned but unimplemented, so the body
asserts the layout the planned command would target and the absence of the command
in `launch.sh`.

---

### P5-FUT-004: Webhook-Based Event Notifications

P5-FUT-004 is implemented. `WebhookChannel`
(`portal/platform/inference/notifications/channels/webhook.py`) is a
`NotificationChannel` registered in
`portal/platform/inference/notifications/channels/__init__.py` and POSTs a JSON
body to `WEBHOOK_URL` for both alert and daily-summary events. `send_alert`
carries the event type, message, backend id, workspace and timestamp;
`send_summary` carries request totals, per-workspace counts, backend health,
uptime, token metrics and average latency. `WEBHOOK_HEADERS`, a JSON object,
adds extra request headers and is ignored with a warning when unparsable. The
channel only activates when `WEBHOOK_URL` is set to a value other than "false".
Both env vars are documented in `.env.example`. The dispatcher
(`portal/platform/inference/notifications/dispatcher.py`) fans each event out to
every registered channel asynchronously, so webhook delivery is fire-and-forget
alongside the Slack, Pushover, Telegram, and Email channels.

## Why

`WebhookChannel` exists because alert delivery needs a generic operator-defined
sink that needs no external account: a JSON POST to an arbitrary HTTP endpoint
is the lowest-friction route for custom notification consumers. Keeping the two
event shapes (`send_alert` / `send_summary`) separate lets a receiver distinguish
a per-backend failure from the periodic digest without parsing the payload, and
the header override covers authenticated endpoints without storing credentials
in the repo.

---

### P5-FUT-006: LLM-Based Intent Routing

P5-FUT-006 is implemented as Layer 1 of auto-routing. `_route_with_llm()`
(`portal/platform/inference/router/routing.py`) calls the Ollama `/api/generate`
endpoint with `format: _ROUTER_JSON_SCHEMA`, grammar-enforced JSON that can only
emit a valid workspace id plus a confidence score. The request uses
`temperature: 0`, `num_predict: 40`, `num_ctx: 2048`, and `keep_alive: -1` so
the classifier is deterministic and stays resident. It returns `None` on low
confidence (below `_LLM_ROUTER_CONFIDENCE_THRESHOLD`, default 0.5), on timeout
(`_LLM_ROUTER_TIMEOUT_MS`, default 1000), on `LLM_ROUTER_ENABLED=false`, and on
any parse or HTTP error — the caller then falls back to `_detect_workspace()`,
the weighted keyword scorer. `bench-*` workspaces are excluded from
`_VALID_WORKSPACE_IDS`. The model is chosen by `LLM_ROUTER_MODEL` (default
`hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M`); all five env vars
are in `.env.example`. Operator-editable inputs are
`config/routing_descriptions.json` (workspace capability descriptions) and
`config/routing_examples.json` (44 few-shot examples under its `examples` key).
The router behavior is covered by 32 test functions in
`tests/unit/test_routing.py`.

## Why

Layer 1 exists because keyword scoring alone cannot reliably separate the more
similar workspaces in the fleet; grammar-enforced JSON guarantees the model
answer is structurally valid, and the hard 1000ms timeout plus `keep_alive: -1`
turn the classifier into a cheap, always-warm first opinion. Routing is
non-fatal by design — every failure mode degrades to the deterministic keyword
scorer rather than erroring the request.

---

### P5-FUT-009: Model-Size-Aware Admission Control (MLX Proxy)

P5-FUT-009 shipped in the retired MLX proxy and is now historical. The archived
`scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py` holds the implementation:
`MODEL_MEMORY` maps model ids to estimated GB (loaded from the `mlx_models`
`memory_gb` metadata in `config/backends.yaml`), and `_check_memory_for_model()`
runs before any model switch, rejecting a load with an HTTP 503 and an
operator-actionable message when required GB plus `MEMORY_HEADROOM_GB` exceeds
free memory. The override env vars were `MLX_MEMORY_HEADROOM_GB` (default 10.0)
and `MLX_MEMORY_UNKNOWN_DEFAULT_GB` (default 20.0). The proxy and its unit tests
were deleted at commit 3a0c58e, which retired
the whole MLX inference tier; the archive README at
`scripts/_archive/mlx-retired-3a0c58e/` documents recovering the tests
via git. Memory pressure is now managed by Ollama itself through
`OLLAMA_MAX_LOADED_MODELS` and `OLLAMA_MEMORY_LIMIT` in `.env.example` and
`deploy/portal-5/docker-compose.yml`.

## Why

The admission-control code survives only as reference, but the reason it existed
has not gone away: on a fixed-memory Mac, a model-switch pre-flight check was the
difference between a clean swap and an OOM crash. Retiring the proxy moved that
niche to Ollama's native `OLLAMA_MAX_LOADED_MODELS` cap, while the archived
implementation remains the documented pattern if a successor engine ever needs a
memory gate again.

---

### P5-FUT-013: OMLX Evaluation — CANCELED

P5-FUT-013 evaluated oMLX as a candidate inference engine and is superseded by
Phase 1 integration. `OMLX_DECISION.md` records the decision chain: the
2026-04-25 bake-off RETIRED oMLX because KV-cache persistence was not functional
(warm TTFT slower than cold); the 2026-05-28 re-evaluation (v0.3.12) kept it
retired but cleared MTP speedup past the 1.5x gate; and the 2026-08-02 six-gate
re-evaluation (v0.5.4) passed every gate — KV-cache warm TTFT speedup on
agentic-length prefixes, decode 1.32-1.46x over production GGUF (2.2-2.5x with
Lightning MTP), Qwen/Gemma tool calling, grammar with one reproducible gemma
livelock edge, and batching 1.6-3.1x with zero failures — producing the decision
PROCEED to Phase 1 dual-backend. Full results are in
`tests/benchmarks/results/omlx_v3_reeval_20260802T221435Z.md`. Phase 1 is visible
in `config/backends.yaml`, which registers the `omlx` backend type and two
backends: `omlx-local` (holding group, no routing reference) and `omlx-coding`
(the live `group: coding` candidate with `priority: 10` and aliases). Per the
decision doc, Ollama remains the sole production engine until Phase 1 lands.

## Why

The oMLX path flipped from RETIRE to PROCEED because part of the original verdict
was a methodology artifact: the paged KV cache works in 256-token blocks, so
short prefixes never show a warm-cache win. Re-measuring on agentic-length
prefixes cleared the cancel trigger, and the dual-backend decision registers
oMLX in `config/backends.yaml` without disturbing production routing —
evidence before promotion, the same rule the bench fleet follows.

---

### P5-FUT-014-V7: Model Refresh Waterline

TASK_MODEL_REFRESH_V7 (2026-05-27, recorded in `CHANGELOG.md`) added six bench
workspaces to the fleet. Two survive in current config:
`bench-qwen36-27b-ud` (in `config/portal.yaml`, `model_hint` qwen3.6:27b-q4_K_M,
described as a proxy for the not-yet-pulled Unsloth UD quant) and
`bench-qwen36-35b-a3b-ud` (`model_hint`
`hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`, agentic-lane candidate C1) —
both under `module: eval` and gated for promotion (`PROMOTE_POLICY=confirm` in
`config/backends.yaml`). The three speech candidates from the same intake —
bench-voxtral-realtime, bench-voxtral-tts, bench-granite-speech — are not
registered in `config/portal.yaml` and survive only as CHANGELOG records. The
promotion gates the roadmap lists have code anchors: the CC-01 Asteroids coding
challenge shootout lives in `tests/uat_catalog/g_benchmark.py` and the
coding-shootout-v2 analyzer in `tests/benchmarks/coding_shootout_analyze.py`.

## Why

This unit records which V7 bench candidates actually shipped as config versus
which were aspirational or already removed. `config/portal.yaml` is the single
source of truth for what the fleet serves, so the two surviving UD workspaces
and the absence of the speech bench entries are the facts this unit asserts; the
promotion gates are future intent, anchored only to the benchmark harnesses that
would measure them.

---

### P5-FUT-EMBED-001: EmbeddingGemma Migration Seed

P5-FUT-EMBED-001 is an open migration. Current production embedding is
`scripts/embedding-server.py`, which serves a sentence-transformers model —
`microsoft/harrier-oss-v1-0.6b` by default — on CPU on port 8917; the same
default is set in `scripts/lib/services.sh` and the launchd wrapper. The RAG MCP
(`portal/modules/research/tools/rag_mcp.py`) consumes the endpoint via
`EMBEDDING_URL` (default http://localhost:8917/v1/embeddings) and stores the
LanceDB index at `LANCE_DIR` (default `/Volumes/data01/portal5_lance`) built from
sources under `KB_SOURCES_DIR` (default `/Volumes/data01/portal5_kb_sources`),
which binds the index to the current embedding dimensionality.
`config/backends.yaml` carries an `embedding_candidates` block listing
`google/embeddinggemma-300M` and `Qwen/Qwen3-Embedding-0.6B`; the note for the
Qwen3-Embedding entry says its 4-bit variant is pre-positioned for a future
swap, so which candidate wins is still open scope. Migration requires
re-ingesting every RAG source under `KB_SOURCES_DIR`, a shadow-index A/B test,
and a rollback path with a feature flag in the RAG MCP.

## Why

Embedding swap is expensive because the LanceDB index encodes the embedding
dimensionality: switching models without re-indexing silently breaks retrieval,
and re-indexing every source is a full-corpus job. The migration therefore needs
a shadow-index A/B and a rollback window before the Harrier index is retired.
The code makes the dimension-binding the load-bearing constraint, and the
`embedding_candidates` block keeps the swap decision in config rather than
hardcoded.

---

### P5-FUT-SPEECH-002: Speech-Model Shootout

P5-FUT-SPEECH-002 is planned work. The current production speech stack is
`scripts/mlx-transcribe.py` — Parakeet-TDT-v3 for the transcript plus Sortformer
(`mlx-community/diar_sortformer_4spk-v1-fp32`) speaker diarization merged at the
word level, American English only, serving on port 8924 — and
`scripts/mlx-speech.py` (`mlx-community/Kokoro-82M-bf16` plus three Qwen3-TTS
12Hz-1.7B variants for custom-voice, voice-design, and base/cloning, and Qwen3-ASR
for plain STT, serving on port 8918). The three bench-only speech candidates from
TASK_MODEL_REFRESH_V7 — Voxtral-Mini-4B-Realtime-2602, Voxtral-4B-TTS-2603, and
Granite-Speech-4.1-2B — are recorded in `CHANGELOG.md` but are not registered in
`config/portal.yaml`. The planned shootout would score WER, keyword F1, TTFT, and
subjective Likert ratings and emit a Pareto frontier for the speech lane.
`tests/benchmarks/bench_tps.py` is a text TPS harness and would not exercise
streaming ASR or TTS rendering.

## Why

Speech evaluation cannot reuse the text benchmark because the artifacts are
audio: WER and keyword F1 need a shared audio corpus, TTFT measures first audio
chunk rather than first token, and TTS has no transcript to score. The bench
candidates are kept out of the serving fleet until the shootout runs, so
`config/portal.yaml`, which defines the fleet, registers only the production
speech servers and the roadmap keeps the candidates out of routing.

---

## Score History

The roadmap score-history records which P5-FUT items shipped, and each shipped
item is verifiable in current code. P5-FUT-004 (webhook notifications) is
implemented in `portal/platform/inference/notifications/channels/webhook.py`.
P5-FUT-005 (weighted keyword routing) is Layer 2 auto-routing — the
`_detect_workspace()` function in `portal/platform/inference/router/routing.py`.
P5-FUT-006 (LLM-based intent routing) is Layer 1 — `_route_with_llm()` in the
same module. P5-FUT-009 (model-size-aware admission control) shipped in the
now-retired MLX proxy and survives only in
`scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py`. The completion scores
themselves are dated snapshots recorded in `CHANGELOG.md` at each milestone;
current code is the live status, not the historical score.

## Why

A percentage from a past date cannot be re-derived from current code and would go
stale the moment anything changes, so the unit drops the historical figures. What
stays true is the mapping of each shipped roadmap item to its implementation, and
that mapping is asserted here with file paths so the unit remains verifiable
against the live tree rather than against a snapshot.

---
