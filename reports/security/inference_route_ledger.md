# Security inference route ledger — TASK_AUTO_COUNCIL_PIPELINE_REVISIT_V1 P0/P1

Generated 2026-09-26 at HEAD `1179539a` (compliance work landed just before this
task started; unrelated). Re-verified against live code, not copied blind from
the task doc — the task's own tables are the starting inventory (P0.2), each
row below is grepped/read against current source. P1 fixes applied in this
pass are marked `FIXED (this pass)`; everything else is `OPEN` (task's
original finding still holds) or `NOT_APPLICABLE` with the reason inline.

**Status as of the second pass (same day, HEAD still `1179539a`, no new
commits from the concurrent compliance agent): P0 and P1 are closed** except
for the one deliberate, stated scope limitation (`portal_strict_seat` is
opt-in, not a pipeline-wide default — see "Scope limitation" in the second
pass's P1.2/P1.3 section below). P2/P3/P4 remain explicitly out of scope.
Nothing in either pass has been committed.

## Live environment at time of writing
- `:9099/health` → `backends_healthy=12/12`, `workspaces=52`, oMLX + Ollama 0.34.4 both healthy.
- `portal5-pipeline` Docker image was rebuilt (`docker compose build portal-pipeline` +
  `up -d --no-deps portal-pipeline`) mid-pass to pick up the `config/portal.yaml`
  changes below — **`config/portal.yaml` is baked into the pipeline image, only
  `config/backends.yaml` is bind-mounted** (`docker inspect portal5-pipeline
  --format '{{range .Mounts}}...'`). Any future portal.yaml-only config change
  needs at minimum `docker compose build portal-pipeline && docker compose up -d
  --no-deps portal-pipeline` to take effect on the running container — `./launch.sh
  sync-config` alone (regenerates `backends.yaml`/`.mcp.json`/OWUI JSON) does not.
- Receipts (raw request/response bodies) for every probe below are private,
  under `/tmp/p1-route-verify/` and `/tmp/council-*-probe.*` — not committed.

## Root cause confirmed (both live wrong-seat cases)

`portal.platform.inference.model_addressing._load()` (pre-fix) indexed **only
top-level** `workspaces:` entries. Security's RBP/HEART roles are declared as
`variants:` nested under `auto-security` (e.g. `auto-security.variants.
blueteam-council`) — those nested model_hints were never added to `_BY_HINT`,
and the variant ids themselves were never added to `_BY_WORKSPACE`. So:
- `resolve_pipeline_model("qwen3.6:27b-q4_K_M")` → `workspace_id_for_model` →
  `_BY_HINT` miss → returned the raw tag **unchanged**.
- That raw tag was sent as `model` to `POST /v1/chat/completions`, where the
  pipeline's own workspace lookup also failed to match it to any workspace —
  and an unmatched `model` is **not an error**, it silently falls back to the
  routing group's first model.
- Same mechanism for the literal `"bully-handoff-drafter"` string
  (`bully/handoff.py`), which was never a real Ollama tag or workspace id at all.

Confirmed live, before any fix, reproducing the task's original probes:
`qwen3.6:27b-q4_K_M` and `bully-handoff-drafter` both served
`gemma-4-26b-a4b-it-QAT-4bit` via `omlx-general`, HTTP 200, no error.
(`/tmp/p1-route-verify/qwen36_27b_after.json`, `hnd_literal_after.json` — these
filenames are misleadingly "after" only in probe order, not in fix order;
they were captured **before** the config+code fix below took effect, since the
pipeline container needed a rebuild.)

## P1 fixes applied this pass

| Fix | File(s) | What changed |
| --- | --- | --- |
| Variant indexing | `portal/platform/inference/model_addressing.py` | `_load()` now does a second pass over every top-level workspace's `variants:` map, registering `f"{base}::{variant_id}"` in `_BY_WORKSPACE` and its `model_hint` in `_BY_HINT` (`setdefault`, so a top-level hint still wins ties — verified against `tests/unit/test_transport_pipeline_dialect.py`'s existing `tools-specialist` vs `auto-security::blueteam` precedence assertion, which still passes). |
| Council seat binding | `config/portal.yaml` (`auto-security.variants.security-council-qwen36-27b`) | New workspace, `model_hint: qwen3.6:27b-q4_K_M` (the exact untagged-context variant the council roster and HEART roster both name — deliberately NOT the `-ctx16k` public-council tag). Closes the qwen3.6 wrong-seat case. |
| HND drafter binding | `config/portal.yaml` (`auto-security.variants.bully-handoff-drafter`) | New workspace, `model_hint: granite4.1:30b-ctx16k`. `bully/handoff.py` now calls `_HND_DRAFTER_ROUTE = "auto-security::bully-handoff-drafter"` instead of the bare literal. Closes the HND wrong-seat case. |
| Fail-closed dispatch | `portal/modules/security/core/agentic_blue_eval.py::_call_model` | Pipeline-mode branch now calls `is_addressable(resolved_model)` before building the request body and raises `UnaddressableSecurityModelError` if it's False, instead of letting an unmapped tag reach the pipeline and get silently substituted. Verified: known-good tag still dispatches; a made-up tag now raises instead of returning 200. |

**Live re-verification after the fix** (pipeline image rebuilt, container
recreated): calling the real production `_call_model()` in-process —
- `_call_model("qwen3.6:27b-q4_K_M", ...)` → `served_model == "qwen3.6:27b-q4_K_M"` (was Gemma).
- `_call_model("auto-security::bully-handoff-drafter", ...)` → `served_model == "granite-4.1-30b-4bit"` (was Gemma).
- Regression check: `_call_model("granite4.1:8b-ctx8k", ...)` (tools-specialist's tag, pre-existing correct routing) still → `served_model == "granite-4.1-8b-mxfp8"`, unaffected.

## Second pass (same day): granite/mistral seats, P1.4, P1.5, P1.2/P1.3

All four gaps below (except the intentionally-deferred P2/P3/P4 row) are now
**closed**, live-verified against the rebuilt/restarted pipeline container.

### Dedicated security-role workspaces (was: shadowed by bench-*/tools-specialist)

`resolve_role_model()`/`resolve_council_models()` (`bully/config.py`) return
`config/portal.yaml`'s `tool_model`/`reasoning_model`/`expert_model`/
`council_models[i]` field values **verbatim** to `_call_model`. A raw Ollama
tag there is looked up in `model_addressing`'s GLOBAL hint map, first-match-
wins — so `granite4.1:30b-ctx16k`, `mistral-small3.2:24b`, `granite4.1:8b-
ctx8k`, and the Foundation-Sec tag all lost to earlier-registered top-level
workspaces (`bench-granite41-30b`, `bench-mistral-small-3-2`, `tools-
specialist`, `bench-foundation-sec-8b-reasoning`) even though addressing
itself "worked" — the security role got that OTHER workspace's general eval/
tool-composer sampling and tool policy, not a dedicated security-role policy.

Fix: four new `auto-security::security-*` variant workspaces (`security-
tool-granite41-8b`, `security-council-granite41-30b`, `security-council-
mistral-small32-24b`, `security-expert-foundation-sec-8b`), and
`blueteam-orchestrated`/`blueteam-council`'s `tool_model`/`reasoning_model`/
`expert_model`/`council_models` fields now hold those workspaces' **ids**
(`auto-security::security-*`) instead of the raw tags — `resolve_pipeline_
model()` passes an already-workspace-id-shaped string through unchanged (the
same mechanism `bully-handoff-drafter` already used), so this changes ONLY
what these two bully-config trios resolve to. The global hint map is
untouched — no new collision, and every other caller of these raw tags
(compliance, bench harness, tools-specialist itself) is unaffected. `qwen3.6:
27b-q4_K_M` (no collision, already fixed in pass one) was switched to its
workspace id too, for consistency — every council seat now addressed the
same way.

Live-verified (`_call_model` in-process, pipeline rebuilt+restarted):
`auto-security::security-tool-granite41-8b` → `granite-4.1-8b-mxfp8`,
`auto-security::security-council-granite41-30b` → `granite-4.1-30b-4bit`,
`auto-security::security-council-mistral-small32-24b` →
`mlx-community--Mistral-Small-3.2-24B-Instruct-2506-4bit`,
`auto-security::security-expert-foundation-sec-8b` →
`hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0`. Regression-
checked all seven addressable seats (including the two from pass one) in one
sweep — all still correct.

### P1.4 — client tool schema isolation: CLOSED

`portal_client_tools_only` already existed as a working, tested mechanism
(`router/non_streaming.py:491`, `router/streaming.py:1714` both already
honored it — used by compliance's `transport_dialects.py` and the WFE
runner). Security just wasn't setting it. Fix: `agentic_blue_eval._call_model`
now sets `body["portal_client_tools_only"] = True` whenever `tools` is
non-empty (covers RBP's retriever call in `run_tool_model` AND the tools/
harness eval arms' `report_detection`+grounding call) — every security tool-
bearing call now dispatches EXACTLY its own scoped schema; the pipeline
never merges in the resolved workspace's tool whitelist (`tools-specialist`'s
`execute_python`/`remember`/`recall` or otherwise). Regression tests:
`tests/unit/test_security_call_model_route.py`.

### P1.5 — direct-generation switches: CLOSED for the accidental-bypass class

New shared gate `portal/modules/security/core/_direct_engine_diagnostic.py`:
`direct_engine_diagnostic_enabled(switch_env_var)` requires BOTH the
module's own switch (`CHAIN_DIRECT_OLLAMA`, `BLUE_DIRECT_OLLAMA`,
`REFUSAL_DIRECT_OLLAMA`, `DRIFT_DIRECT_OLLAMA`) AND a new shared
`PORTAL_SECURITY_DIRECT_ENGINE_DIAGNOSTIC` gate to be explicitly `"true"`.
Wired into all four call sites (`agentic_blue_eval.py`, `exec_chain.py`'s
`_is_pipeline_model`, `blue.py`'s `_use_pipeline` check, `drift_gate.py`'s
`_run_single_probe`, `refusal.py`'s `_refusal_chat`) — none removed, all
still work as diagnostics, but a lone stray env var (a stale `.env` line, a
copy-pasted CI config) can no longer silently take a product/qualification
run off the pipeline by itself. Regression tests: `tests/unit/
test_direct_engine_diagnostic_gate.py` (parametrized over all four switches:
switch-alone, gate-alone, both, neither, and cross-switch isolation).

**Reviewed and left as-is** (already correctly isolated, not a bypass-switch
risk): `council_review_bench.py`'s `_call_solo`/`run_live_bench` is a
standalone, self-documenting bench module (unconditionally direct-to-Ollama
by design, to produce the solo-vs-council comparison) never invoked from the
product hunt/council path. `intake.py`'s raw `/api/generate` TPS probe,
`refusal._audit_tools_probe`, and `commands/run.py`'s `call_theory_direct`
are consumed only by TRAIN/candidate-benchmarking flows (`bully/
training.py`, `candidate_eval.py`) and explicit CLI diagnostic commands —
never the normal hunt/council product path (grepped: zero product-path
callers). Per the task's own words ("Raw engine benchmark may remain a
labeled diagnostic, never the sole serve gate"), these already satisfy that
bar structurally; wiring TRAIN's actual pipeline-canary serve-gate (so a raw
TPS number can never BECOME the serve decision) is P2 scope (`bully.
training`, already tracked OPEN below), not touched here.

### P1.2/P1.3 — pipeline-side strict-seat enforcement: CLOSED (scoped, opt-in)

Root cause, traced through `router/handlers.py::_resolve_request_route`:
`workspace_id = body.get("model") or "auto"` is used almost verbatim as the
routing key. For a `model` value that matches NO known workspace/persona/
variant (e.g. a raw tag `_call_model` sent pre-fix), every resolution phase
(`_resolve_persona_workspace`, `_resolve_auto_routing`, `_unpack_synthetic_
workspace`, `_resolve_workspace_variant`) passes it through unchanged, and
`registry.get_backend_candidates(workspace_id)` (`cluster_backends.py:464`)
silently clamps an unknown id to `self._fallback_group` ("general")'s
healthy backends. Then `_try_non_streaming`/streaming see `WORKSPACES.get
(workspace_id, {})` → `{}` → no `model_hint` → `target_model = backend.
resolve_model(workspace_id) or backend.models[0]` — that `backend.models[0]`
is exactly how Gemma got served in both live probes. This is the SAME
"degrade-don't-fail" fallback ladder that legitimately serves ordinary
general-chat traffic when a known workspace's preferred backend is
unhealthy — the task doc explicitly requires that behavior be preserved, so
this could not be turned into a global "reject on any unknown model" change
without risking exactly that.

Fix (opt-in, conservative — the "narrower version" this task's own fallback
guidance allowed for): `body.get("portal_strict_seat")`. When present and
truthy, `_resolve_request_route` checks `workspace_id not in WORKSPACES`
AFTER all resolution phases complete (persona/auto-routing/synthetic-unpack/
variant-merge/override) and BEFORE `get_backend_candidates` is ever called —
if unresolved, returns `404` with a named reason instead of proceeding into
the candidate-selection fallback ladder. Because this sits before candidate
selection, it protects all three dispatch paths (non-streaming, streaming,
council) from a single check point — `chat_completions` calls
`_resolve_request_route` once, then branches to `_dispatch_council`/
`_dispatch_non_streaming`/`_select_streaming_backend` using the SAME already-
validated `workspace_id`. `agentic_blue_eval._call_model` now sets
`portal_strict_seat: True` on every pipeline-mode request — defense in
depth alongside its existing client-side `is_addressable()` pre-check (P1
pass one), not a replacement for it. The flag is popped from `body` before
any further processing so it never reaches a backend as a stray field.

**Scope limitation, stated honestly**: this is opt-in, not the global
"strict-seat contract for security" the task describes at its most complete
— a caller that does NOT set `portal_strict_seat` still gets the pre-
existing silent-fallback behavior for an unknown `model` value (verified
live below). Every security call now sets it, so security itself is fully
covered; a hypothetical OTHER unmapped-tag caller (compliance, a bench
script, a future integration) is not automatically protected unless it also
opts in. Making this the pipeline's unconditional default behavior was
assessed and deliberately not done in this pass — it's a broader blast-
radius change (affects every workspace, every caller, not just security) and
deserves its own review/live-traffic verification, not a same-pass bundling
with security-specific fixes.

Live-verified against the rebuilt/restarted pipeline:
```
POST /v1/chat/completions {"model":"totally-bogus-tag-xyz", ..., "portal_strict_seat":true}
  -> 404 {"detail":"Unaddressable workspace/seat 'totally-bogus-tag-xyz' for a
          strict-seat request -- no matching workspace/variant binding in
          config/portal.yaml. Refusing to fall back to the routing group's
          first model."}
POST /v1/chat/completions {"model":"totally-bogus-tag-xyz", ...}   (no flag)
  -> 200  (unchanged legacy fallback behavior, confirmed still intact)
```
All seven addressable security seats re-verified end-to-end with the flag
now wired live (see table above) — no regression.

Regression tests: `tests/unit/test_pipeline.py::TestStrictSeatEnforcement`
(3 cases: unknown+flag→404, unknown+no-flag→not-404, known+flag→200 via
`TestClient`), plus `test_security_call_model_route.py` asserting
`_call_model` actually sets the flag.

### Still open (P2/P3/P4 — explicitly out of scope, unchanged from pass one)

| Gap | Disposition |
| --- | --- |
| `bully.training` (`bully-<hash>` tags), `bully.promotion`, `bully.soc.deliver`, `siem.blue_triage.poll_alerts`, autonomous candidate/detection/playbook promotion, DB migrations removing operator-gates | P2 scope — not touched. |
| Crogl `Organ._embed`, `rerank_url` false-success receipt | P3 scope — not touched. |
| Public `auto-council` (`router.council`, `_backend_for_model` literal-membership check) | P4 scope — not touched. |
| `portal_strict_seat` is opt-in, not the pipeline's unconditional default | See "Scope limitation" above — a deliberate, stated choice for this pass, not an oversight. |

## Call-site inventory (from task's own call-graph table, spot-verified)

| Entry/consumer | Verified against | Status |
| --- | --- | --- |
| `agentic_blue_eval._call_model` | Read in full this pass (lines 258–340ish after edit). `_DIRECT_OLLAMA = os.environ.get("CHAIN_DIRECT_OLLAMA", "").lower() == "true"` still exists, still bypasses pipeline entirely to `:11434/api/chat` when set. | OPEN (diagnostic switch not yet isolated) |
| `blue_orchestrate.run_tool_model/run_reasoning_model/run_expert_model/run_mentor_model` (corrected count: 5 `_call_model` call sites in `blue_orchestrate.py`, not the ~15 estimated in pass one) | All pass their role parameter (`tool_model`/`reasoning_model`/`expert_model`/`mentor_model`/council member) straight into `_call_model`, unmodified. | FIXED (second pass) — `config/portal.yaml`'s `tool_model`/`reasoning_model`/`expert_model`/`council_models` fields now hold dedicated workspace ids instead of raw tags (see "Dedicated security-role workspaces" above), so every one of these call sites now resolves to a security-scoped seat without any Python change. |
| `bully.adversary.resolve_roster` → `bully_config.resolve_council_models` | Confirmed: same `council_models` list as `blueteam-council`, so HEART roster gets the qwen3.6 fix "for free" (same config source). | FIXED (this pass, via council binding) |
| `bully.handoff.draft_generalization` | Fixed this pass — see above. | FIXED (this pass) |
| `bully.training` (`bully-<hash>` tags), `bully.promotion`, `bully.soc.deliver`, `siem.blue_triage.poll_alerts` | Not touched this pass — P2 scope. | OPEN (P2) |
| Crogl `Organ._embed`, `rerank_url` false-success receipt | Not touched this pass — P3 scope. | OPEN (P3) |
| Public `auto-council` (`router.council`, `_backend_for_model` literal-membership check) | Not touched this pass — P4 scope. | OPEN (P4) |

## Reproduction

```
# route-check probes (bounded, max_tokens=8, no lab/attack actions):
python3 -c "
import sys; sys.path.insert(0,'.')
from portal.modules.security.core.agentic_blue_eval import _call_model
print(_call_model('qwen3.6:27b-q4_K_M', [{'role':'user','content':'ok'}], max_tokens=8).get('served_model'))
print(_call_model('auto-security::bully-handoff-drafter', [{'role':'user','content':'ok'}], max_tokens=8).get('served_model'))
"
# expected: qwen3.6:27b-q4_K_M / granite-4.1-30b-4bit (not gemma-4-26b-a4b-it-QAT-4bit)
```
