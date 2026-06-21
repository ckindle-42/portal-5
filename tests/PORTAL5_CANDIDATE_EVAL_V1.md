# PORTAL5_CANDIDATE_EVAL_V1 — Pending Candidate Bench Execution

Continuation task for evaluating all remaining bench candidates that lack TPS,
quality, or security chain data. Do not start this until the qwable-35b security
chain has completed and been committed. Everything here runs sequentially — never
two bench processes at once.

**Context:** As of 2026-06-20, the following changes were made:
- auto-coding-agentic → Laguna-XS.2 (promoted, 68.2% SWE-bench)
- gpt-oss:20b → coding pool / auto-agentic fallback (promoted)
- bench-vulnllm-r7b → already production auto-security primary (VulnLLM-R-7B)
- 3 Qwable 27B dense models removed (too slow, same quality as faster alternatives)
- bench-qwable-35b → security chain eval (result written in step 0 below)

---

## Step 0 — Record Qwable-35B Security Chain Result

The security chain for `bench-qwable-35b` was running when this doc was written.
Check the result before proceeding:

```bash
# Find the result file
ls -lt /tmp/sec_bench_qwable35b*.json | head -1

# Read the chain outcomes
python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
for r in d.get('chain_results', []):
    model = r.get('model','')
    scenario = r.get('scenario','')
    outcome = r.get('outcome','')
    steps = r.get('steps_completed',0)
    total = r.get('steps_total',0)
    chain_t = r.get('chain_time_s',0)
    refusals = r.get('refusal_rate',0)
    print(f'{scenario}: {outcome} {steps}/{total} steps  {chain_t:.0f}s  refusals={refusals}')
" \$(ls -t /tmp/sec_bench_qwable35b*.json | head -1)
```

**Promotion threshold:** 2/2 scenarios WIN, refusal_rate=0.0, chain_time_s < 300s.

- If PASS → add model_hint to a security workspace (create new bench-to-production
  mapping or promote to existing slot). Update workspace description. Commit.
- If FAIL → remove bench-qwable-35b from workspaces.py, backends.yaml,
  dispatcher.py. Run `ollama rm hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf`.
  Update unit test workspace count. Commit and push.

---

## Step 1 — TPS Bench: All Unbenched Candidates

Run a targeted direct-mode TPS bench covering every candidate that has no speed
data yet. Uses `--model` substring filter to avoid re-running the full fleet.

**Models covered by this run:**

| Model substring | Workspace | Est. size |
|---|---|---|
| qwopus | bench-qwopus-coder-mtp | ~19GB |
| nex-n2 | bench-nex-n2-mini | ~22GB |
| devstral | bench-devstral + bench-devstral-small-2 | ~14GB each |
| lfm2 | bench-lfm25-8b + bench-lfm25-8b-uncensored | ~5GB each |
| gemma4 | bench-gemma4-12b/26b-qat/31b-qat/e2b/e4b-qat | 8–19GB |
| huihui.*qwen36 | bench-huihui-qwen36-27b | ~17GB |
| qwen3-coder-next | bench-qwen3-coder-next + abliterated | ~46GB each |

```bash
# Pre-flight: confirm nothing is resident
curl -s http://localhost:11434/api/ps | python3 -m json.tool

# Run — order size (smallest first) so LFM/small models warm the eviction pool
# before the 46GB Coder-Next loads. ~2-3 hours total.
python3 -u tests/benchmarks/bench_tps.py \
    --mode direct \
    --order size \
    --runs 5 \
    --cooldown 10 \
    --model "qwopus\|nex-n2\|devstral\|lfm2\|gemma4\|huihui.*qwen36\|qwen3-coder-next" \
    > /tmp/candidate_tps.log 2>&1 &

echo "PID: $!  Log: /tmp/candidate_tps.log"
```

**Monitor:**
```bash
tail -f /tmp/candidate_tps.log
# or check progress:
RESULTS=$(ls -t tests/benchmarks/results/bench_tps_*.json | head -1)
python3 -c "import json; d=json.load(open('$RESULTS')); [print(r['model'][-40:], r.get('avg_tps','?'), 't/s', r.get('runs_success',0), 'ok') for r in d.get('results',[])]"
```

**20 t/s floor** — any model below this is disqualified from production workspaces
that serve interactive sessions. Flag but do not discard yet — slow models may
still qualify for batch/deep workspaces (auto-purpleteam-deep, auto-reasoning).

---

## Step 2 — Security Chain: Huihui-Qwen36-27B

This is the only remaining non-Gemma candidate with a dual coding + security eval
mandate. Run after TPS — we need to know if it clears 20 t/s before spending time
on a chain test (if it's slow, chain results are academic).

**Gate:** only run this if bench_tps shows avg_tps ≥ 15 t/s for `huihui.*qwen36`.
Below 15 t/s, the chain will time out on multiple steps — skip and discard.

```bash
# Check TPS result first:
python3 -c "
import json
d = json.load(open('$(ls -t tests/benchmarks/results/bench_tps_*.json | head -1)'))
for r in d['results']:
    if 'huihui' in r['model'].lower() and 'qwen36' in r['model'].lower():
        print(r['model'], r.get('avg_tps'), 't/s', r.get('runs_success'), '/5')
"

# If TPS ≥ 15, run security chain:
python3 tests/benchmarks/bench_security.py \
    --chain-models hf.co/bartowski/huihui-ai_Qwen3.6-27B-abliterated-GGUF:Q4_K_M \
    --output tests/benchmarks/results/sec_bench_huihui_qwen36_$(date -u +%Y%m%dT%H%M%SZ).json
```

**Promotion threshold:** same as qwable-35b — 2/2 WIN, refusal_rate=0.0, < 300s.
If it passes, it's a candidate for auto-redteam or auto-pentest upgrade.

---

## Step 3 — Evaluate TPS Results and Make Promotion Decisions

After Step 1 completes, read results and apply this decision table:

```bash
RESULTS=$(ls -t tests/benchmarks/results/bench_tps_*.json | head -1)
python3 -c "
import json
d = json.load(open('$RESULTS'))
print(f'{'Model':<50} {'TPS':>8} {'Runs':>6} {'Floor':>6}')
print('-'*75)
for r in sorted(d['results'], key=lambda x: x.get('avg_tps') or 0, reverse=True):
    tps = r.get('avg_tps') or 0
    ok = r.get('runs_success', 0)
    flag = '✓' if tps >= 20 else ('~' if tps >= 15 else '✗')
    print(f'{flag} {r[\"model\"][-48:]:<48} {tps:>8.1f} {ok:>4}/5  {\"PASS\" if tps>=20 else \"SLOW\" if tps>=15 else \"FAIL\"}')
"
```

### Decision table per candidate:

**bench-qwopus-coder-mtp** (27B dense, coding)
- ≥ 20 t/s + 4/5 runs → candidate for auto-coding or auto-agentic fallback slot.
  Run `bench_security.py --chain-models <id>` to verify tool-call chain.
- < 20 t/s → same reasoning-trace blowout as Qwable 27Bs. Remove + `ollama rm`.

**bench-nex-n2-mini** (35B/3B MoE, multimodal)
- ≥ 20 t/s → vision + coding candidate. Run promptfoo coding_quality eval.
- < 20 t/s → flag for deep/batch only (not interactive).

**bench-devstral vs bench-devstral-small-2**
- Compare TPS head-to-head. devstral-small-2 is already in the coding pool as a
  fallback. If full devstral matches or beats small-2 at ≥ 20 t/s, it becomes
  the primary for a workspace slot. If small-2 is faster with comparable quality,
  keep it where it is and discard full devstral bench workspace.

**bench-lfm25-8b / bench-lfm25-8b-uncensored** (5GB, speed candidates)
- ≥ 30 t/s → fast-lane candidate (auto-daily, router replacement, lightweight tasks).
- 20–30 t/s → marginal; only promote if quality distinctly beats granite4.1:8b.
- < 20 t/s → remove both.

**bench-gemma4-e2b** (fastest TPS candidate in fleet)
- Should be the fastest model in the fleet by design (~2B active). Expect 60–100+ t/s.
- If quality_score ≥ 0.6 → candidate for high-throughput lanes (router, auto-daily).

**bench-gemma4-12b, bench-gemma4-26b-qat, bench-gemma4-31b-qat, bench-gemma4-e4b-qat**
- QAT question: does quantization-aware training close the quality gap vs standard quants?
- Compare quality_score across the QAT variants vs their non-QAT siblings already benched.
- 31b-qat: only promote if it fits in memory without evicting other loaded models
  (64GB system; ~19GB model means ~45GB headroom — check `vm_stat` after load).

**bench-qwen3-coder-next** (already production primary in auto-agentic)
- This bench exists to validate the production model. If TPS ≥ 20 and 5/5 runs
  clean, update workspace description with confirmed bench data and mark as
  formally validated. No workspace change needed.

**bench-qwen3-coder-next-abliterated** (auto-coding-uncensored-agentic upgrade candidate)
- Compare TPS vs current auto-coding-uncensored-agentic primary.
- If faster or equal quality → swap the hint in auto-coding-uncensored-agentic.

---

## Step 4 — Promptfoo Quality Eval (Optional, for top TPS performers)

For any model clearing 20 t/s with 4+/5 runs that is a coding candidate,
run promptfoo to validate instruction-following quality:

```bash
# Requires promptfoo installed and stack running
npx promptfoo eval --config config/promptfoo/coding_quality.yaml
# For security candidates:
npx promptfoo eval --config config/promptfoo/security_quality.yaml
```

---

## Step 5 — Commit All Decisions

After each promotion or discard:

```bash
# After any workspace/backends/dispatcher changes:
pytest tests/unit/ -q --tb=short  # must pass before commit

git add portal_pipeline/router/workspaces.py \
        config/backends.yaml \
        portal_channels/dispatcher.py \
        tests/unit/test_pipeline.py \
        tests/benchmarks/results/
git commit -m "chore(fleet): candidate eval results $(date -u +%Y-%m-%d) — <summary>"
git push origin main
```

---

## Workspace Count Tracking

Current as of 2026-06-20 after today's cleanup: **75 workspaces (35 production + 40 bench-)**.
Update `test_workspace_count_is_14` and `test_workspace_count_is_16` in
`tests/unit/test_pipeline.py` whenever workspaces are added or removed.

---

## Models NOT to Discard Without Explicit Decision

The following bench workspaces have no TPS/quality data yet but are NOT stale —
they are active candidates waiting for this eval run:
`bench-qwopus-coder-mtp`, `bench-nex-n2-mini`, `bench-devstral`,
`bench-devstral-small-2`, `bench-huihui-qwen36-27b`, `bench-lfm25-8b`,
`bench-lfm25-8b-uncensored`, `bench-gemma4-12b`, `bench-gemma4-26b-qat`,
`bench-gemma4-31b-qat`, `bench-gemma4-e2b`, `bench-gemma4-e4b-qat`,
`bench-qwen3-coder-next`, `bench-qwen3-coder-next-abliterated`.

Do not remove these in a cleanup pass — they need eval data first.

## Models That Are Stranded (no eval plan, safe to prune in a separate pass)

These bench workspaces have no active eval plan and predate current fleet strategy.
Review and prune separately — do not mix with this eval run:
`bench-glm`, `bench-granite41-8b`, `bench-granite41-30b`, `bench-llama33-70b`,
`bench-omnicoder2`, `bench-qwen3-coder-30b`, `bench-qwen35-abliterated`,
`bench-qwen36-27b`, `bench-qwen36-27b-mtp`, `bench-qwen36-27b-optiq`,
`bench-qwen36-27b-ud`, `bench-qwen36-35b-a3b`, `bench-qwen36-35b-a3b-ud`,
`bench-qwen36-hauhaucs`, `bench-gemma4-e4b`, `bench-gemma4-26b-optiq`,
`bench-sylink`.
