---
id: unit-COMPLIANCE_FALLBACK_POLICY-granite-required-sweep-fails-if-granite-has-been-r
kind: why
title: "COMPLIANCE_FALLBACK_POLICY \u2014 Granite-required sweep (fails if Granite\
  \ has been removed from chain)"
sources:
- type: design
  path: docs/COMPLIANCE_FALLBACK_POLICY.md
  section: Granite-required sweep (fails if Granite has been removed from chain)
last_generated_commit: ''
confidence: high
tags:
- docs
- COMPLIANCE_FALLBACK_POLICY
created_at: 1783195000.833865
updated_at: 1783195000.833865
---

python3 tests/portal5_persona_matrix.py \
    --backend ollama \
    --require granite4.1:8b,granite4.1:30b \
    --output tests/benchmarks/results/persona_matrix_granite_$(date -u +%Y%m%dT%H%M%SZ).json
```

Comparison against baseline:

```bash
python3 -c "
import json
base = json.load(open('tests/benchmarks/results/persona_matrix_baseline.json'))
new = json.load(open('tests/benchmarks/results/persona_matrix_<NEW>.json'))

def per_model_pass(report):
    out = {}
    for c in report['cells']:
        s = c['summary']
        total = s.get('PASS', 0) + s.get('WARN', 0) + s.get('FAIL', 0)
        if not total:
            continue
        out.setdefault(c['model'], [0, 0])
        out[c['model']][0] += s.get('PASS', 0)
        out[c['model']][1] += total
    return {m: (p / t * 100) if t else 0 for m, (p, t) in out.items()}

base_p = per_model_pass(base)
new_p = per_model_pass(new)
all_models = sorted(set(base_p) | set(new_p))
for m in all_models:
    b = base_p.get(m, float('nan'))
    n = new_p.get(m, float('nan'))
    delta = n - b if (b == b and n == n) else float('nan')
    flag = '\u26a0' if abs(delta) >= 5 else ''
    print(f'  {m:60} baseline={b:5.1f}%  new={n:5.1f}%  \u0394={delta:+5.1f}  {flag}')
"
```
