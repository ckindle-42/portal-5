---
id: unit-portal5-bench-execute-v4-served-model-sanity-new-in-v4
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 Served-model sanity (new in V4)"
sources:
- type: doc
  path: tests/PORTAL5_BENCH_EXECUTE_V4.md
  commit: 05e42ec2
  section: Served-model sanity (new in V4)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.70277
updated_at: 1784946220.70277
---

Because persona served-model correctness was a recent bug class, add one check
to the run: for each `model_pin` persona (preflight lists them), confirm the
bench recorded it being served its pinned model, not the workspace pool default.
`bench_tps.py` records the resolved model per test; grep the results JSON:

```bash
python3 - <<'PY'
import json, glob, yaml, os
latest = max(glob.glob("tests/benchmarks/results/*.json"), key=os.path.getmtime)
res = json.load(open(latest))
pins = {yaml.safe_load(open(f))["slug"]: yaml.safe_load(open(f))["model_pin"]
        for f in glob.glob("config/personas/*.yaml") if yaml.safe_load(open(f)).get("model_pin")}
for r in res.get("results", res):
    persona = r.get("persona") or r.get("model")
    if persona in pins and r.get("mode") == "persona":
        served = r.get("resolved_model") or r.get("served_model")
        ok = served and pins[persona].split(":")[0] in served
        print(f"{'OK ' if ok else 'MISMATCH'} {persona}: pin={pins[persona]} served={served}")
PY
```

Any MISMATCH is a served-model regression — report it; it means the `model_pin`
handler hook regressed.

---
