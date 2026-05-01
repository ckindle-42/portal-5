# Compliance Fallback Policy

**Status**: Initial baseline pending. Updated by operator after first
matrix sweep run (TASK_GRANITE_COMPLIANCE_VALIDATE_005).

**Last reviewed**: <YYYY-MM-DD by operator>

This document captures the operator's policy for which models are
acceptable as fallbacks behind the `auto-compliance` workspace, the
threshold each fallback must meet, and the action taken when a fallback
falls below threshold.

## What "compliance fallback" means

The `auto-compliance` workspace routes through `[mlx, reasoning, general]`
groups in that priority order. The MLX primary (currently
`Jackrong/MLX-Qwen3.5-35B-A3B-Claude-...-8bit`) handles the request when
MLX is healthy and has free memory. When it does not — MLX evicted, MLX
loading another model, MLX in big_model mode, or memory pressure — the
pipeline falls through to Ollama models in the listed groups.

Every Ollama model in `ollama-reasoning` and `ollama-general` is
therefore a potential primary handler for a compliance request. This
policy specifies the bar each must meet to remain in those groups.

## Threshold policy

The persona matrix driver
(`tests/portal5_persona_matrix.py`) produces a per-(persona, model) result
matrix using the assertion library in `tests/lib/compliance_assertions.py`
against scenarios in `tests/fixtures/compliance_scenarios.yaml`.

For each model, summed across all 7 compliance personas:

| Outcome | Per-cell rule | Routing action |
|---|---|---|
| **Acceptable fallback** | &ge;80% of MUST assertions PASS, no scenario shows fabricated verbatim text | Keep current routing position |
| **Borderline** | 60&ndash;80% MUST PASS, no fabrications | Move to back of group; flag for re-evaluation in 90 days |
| **Reject** | <60% MUST PASS, OR any fabrication-pattern failure | Remove from compliance routing groups; remains available via direct workspace targeting |

Special-case rule: **fabrication failures override percentage**. A model
that confabulates verbatim requirement text on any scenario is rejected
regardless of overall PASS rate. Fabrication is the highest-stakes
behavior in compliance work.

## Canonical baseline

Operator stores the accepted baseline at:
```
tests/benchmarks/results/persona_matrix_baseline.json
```

Re-baselining cadence: quarterly, or after any of the following changes:

- New model added to `ollama-reasoning` / `ollama-general` / MLX text models
- Existing model upgraded (Ollama re-pull moves the digest)
- Persona system prompt edited (TASK_COMPLIANCE_REFRAME class changes)
- Fixture scenario added or modified
- Assertion library threshold or regex changed

## Granite 4.1 — initial expectation

Per IBM Research's stated design (Granite 4.1: dense, no-thinking,
tool-calling-first, BFCL V3 leader at 73.7 for the 30B, GRC-aware
training, ISO certification), Granite is expected to:

- **PASS clearly** on dense-structured-tool-output (scenario I) — no
  reasoning chain to leak into the structured output.
- **PASS** on classification-token-discipline — strong instruction
  following per IFEval 87.1 (8B) / 89.7 (30B).
- **PASS** on citation discipline across the 7 frameworks rotated by
  the multi-framework scenarios.
- **PASS** on anti-fabrication scenarios — Apache 2.0 + ISO discipline +
  the "no chain of thought" design favor explicit refusal over confident
  invention.
- **WARN-acceptable or PASS** on insufficient-context — the persona
  prompt enforces the exact phrase regardless of model.

If Granite 8B fails to clear the 60% MUST threshold on the first run,
the realistic interpretations are: (a) the persona system prompt isn't
guiding it well — tune the prompt; (b) the assertion bar is overly
strict — tune the assertion regex; (c) Granite 8B genuinely doesn't
suit compliance fallback at this size — demote it within
`ollama-general`.

If Granite 30B fails to clear the 80% MUST threshold, the operator
explicitly evaluates whether to keep it in `ollama-reasoning` or
demote it. The dense architecture's slower TPS at 30B is a separate
trade-off captured in `bench_tps` runs, not in this policy.

## Re-running the matrix

```bash
# Full sweep
python3 tests/portal5_persona_matrix.py \
    --output tests/benchmarks/results/persona_matrix_$(date -u +%Y%m%dT%H%M%SZ).json

# Granite-required sweep (fails if Granite has been removed from chain)
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

## Out of scope

This policy covers only `auto-compliance`. Other workspaces with
multi-model fallback chains (`auto-coding`, `auto-research`, `auto-data`,
`auto-security`, etc.) are valid future targets for the same per-backend
matrix approach but require their own scenario fixtures and threshold
documents. The matrix driver is workspace-parameterizable; only the
fixture and threshold doc are workspace-specific.
