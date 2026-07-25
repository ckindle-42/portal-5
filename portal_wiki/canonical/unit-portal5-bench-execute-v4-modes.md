---
id: unit-portal5-bench-execute-v4-modes
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 Modes"
sources:
- type: doc
  path: tests/PORTAL5_BENCH_EXECUTE_V4.md
  commit: 05e42ec2
  section: Modes
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.702423
updated_at: 1784946220.702423
---

`bench_tps.py` runs three modes (`--mode all` default):
- **direct** — model hit directly on Ollama (raw model TPS).
- **pipeline** — through the pipeline at `:9099` (routing + serving overhead).
- **persona** — a persona slug as the model (exercises persona → workspace →
  served-model resolution, including `model_pin`).

The **persona mode is now especially important**: the recent served-model fixes
(`model_pin` on 7 personas) mean persona-mode TPS reflects the *pinned* model.
If a `model_pin` persona benches at a wildly different TPS than its pinned
model's direct-mode number, that's a signal the pin isn't being served — flag
it (it should match the pinned model's direct TPS within overhead).

---
