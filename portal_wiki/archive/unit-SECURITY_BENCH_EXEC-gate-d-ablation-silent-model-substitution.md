---
id: unit-SECURITY_BENCH_EXEC-gate-d-ablation-silent-model-substitution
kind: why
title: "GATE-D ablation — silent model substitution, sampling tuning, section/role replay"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: GATE-D full-corpus ablation + failure attribution (TASK-SEC-GATED-ABLATION-TO-COUNCIL-V1)
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
- gate-d-ablation
- silent-model-substitution
- resolve_pipeline_model
- sampling-tuning
- capture-replay
created_at: 1784601014.0
updated_at: 1784601014.0
---

**Document type**: Incident write-up + reusable-infrastructure summary
**Scope**: `TASK-SEC-GATED-ABLATION-TO-COUNCIL-V1` — Part I (attribution instrument, corpus ablation, model comparison)
**Status**: Root cause found, fixed, and live-verified as of 2026-07-21; validation corpus rerun pending

---

## The headline finding

Every Expert-role call in the GATE-D ablation — the original 30-hour full corpus run, the
"flawed instrument" run, the 19-scenario validation run, and this task's own earlier diagnostic
probes — was silently served by `huihui_ai/Qwen3.6-abliterated:27b` instead of the intended
`hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0`. `resolve_pipeline_model()` maps a raw
Ollama model tag to its workspace via `model_hint` in `config/portal.yaml`, specifically to
prevent the pipeline's own unknown-workspace fallback (silently serving the routing group's first
model) from mis-attributing a result to the wrong model — a failure mode its own docstring already
documented from a prior 2026-07-05 incident. The Expert model simply had no workspace entry, so it
fell straight through that gap. Verified via the router's own `x-portal-route` response header.

**Everything measured about "the Expert model won't conclude" before this fix was actually
measuring `Qwen3.6-abliterated`'s behavior, not the intended model's.** Post-fix, live-verified
5/5 reps across 3 scenarios: concise, no truncation, no non-convergence.

## Fix

- Added a `bench-foundation-sec-8b-reasoning` workspace with the correct `model_hint`, routed to
  the `reasoning` backend group (where the model is actually registered — the default `general`
  group doesn't carry it, which trips the pipeline's own `STRICT_HINT_VALIDATION` startup check).
- **Structural guard, not just the one-off fix**: `exec_chain._stream_chain_turn` (the single
  chokepoint every security-harness pipeline call goes through) now verifies the actually-served
  model against the requested workspace's registered `model_hint` via the `x-portal-route` header,
  raising loudly on any future mismatch instead of silently continuing.
- Project-wide audit (scoped): only this ablation harness was exposed. `bench_tps.py`/
  `bench_router*.py` call Ollama directly; `bench_candidates_v10.py`/`capability_probe.py` already
  only address pre-registered `bench-*` workspace slugs, with `bench_candidates_v10.py` carrying
  its own explicit guard for a missing `model_hint`.

## Sampling tuning — researched, applied, controlled-tested; effect: negligible

Every Expert candidate model except `sylink:8b` had zero Modelfile-level sampling overrides
(`/api/show` → `parameters: None`), running on Ollama's raw defaults rather than each model
creator's own GGUF-embedded recommendation (auto-application of that metadata is a recent,
not-guaranteed llama.cpp feature). Applied creator-recommended values via `config/portal.yaml`'s
per-workspace sampling fields, then ran a **controlled** before/after comparison (one captured
hand-off, old vs. new `options` forced explicitly, evidence context held fixed): 5/6 and 6/6
agreement at the Expert role, 6/6 at the Hunter role. Sampling tuning made almost no observable
difference at either role. The real source of run-to-run variance is upstream of both roles'
sampling config — the inherent stochasticity of free-form generation itself (which evidence the
Hunter gathers, how it phrases a hypothesis) — not something a temperature/top_p tweak controls at
the ranges tested.

## Section/role replay infrastructure — built so this never needs a fresh 30-hour run again

`blue_orchestrate.py` now supports capturing and replaying either hand-off point in the 3-section
arm independently, without re-paying for the rounds that produced that state:

- `capture_expert_handoff()` / `resume_from_handoff()` — capture arms 1+2 once, swap in any Expert
  model against that fixed evidence packet.
- `capture_hunter_handoff()` / `resume_hunter_from_handoff()` — capture the tool rounds (+ any
  earlier Hunter rounds) once, swap in a different reasoning model or sampling config.
- Both dataclasses (`ExpertHandoff`, `HunterHandoff`) are JSON-round-trippable (`to_dict`/
  `from_dict`) — a capture is durable across separate script invocations.
- Both accept `extra_options` for controlled sampling A/B tests without touching
  `config/portal.yaml`.
- Shares the exact same call/retry logic the live loop uses (a `_capture_only`/
  `_capture_hunter_only` interception point in `_run_three_section`, not a parallel
  reimplementation) — no risk of the live and replay paths drifting apart.
- Live-verified: one capture (100–115s) + N resumes (12–45s each) vs. N full independent runs
  (85–220s each) — roughly 2.4× faster at N=5 candidates, gap growing with N.
- **Scope limit**: only the round that actually led to hand-off is captured; a resumed candidate's
  own follow-up `request_more` (beyond its one retry) isn't independently replayable — covers the
  dominant observed case, not every branch.

## What's still open

- The full 1-vs-2-vs-3-section ablation comparison needs to be rerun with the routing fix in
  place — the data that made 3-section look worse than 2-section was contaminated by this exact
  bug and hasn't been re-measured since.
- Expert-candidate comparison data (5 candidates, 3 scenarios, 1–3 reps each) is too thin for a
  real ranking; `decide_route()`'s output should not be trusted until both of the above are
  addressed.

See `docs/SECURITY_BENCH_EXEC.md` § "GATE-D full-corpus ablation + failure attribution" for the
full numbered incident history (findings #1–11) and exact code references.
