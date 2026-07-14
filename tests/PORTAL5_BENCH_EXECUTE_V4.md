# PORTAL5_BENCH_EXECUTE_V4 — opencode Bench Execution Prompt

> **Supersedes** `PORTAL5_BENCH_EXECUTE_V3.md` (archive it to
> `docs/_archive_execdocs/`). V4 updates for the post-collapse / post-alias-
> retirement codebase (HEAD `87b19bf`): corrected scale, `PORTAL_ENABLE_EVAL`
> gating, preflight-driven counts (no baked numbers), and served-model
> verification tie-in.

Run the Portal 5 comprehensive TPS benchmark suite (Ollama-only). The live
stack is expected running when you begin. At the end, update the Grafana
benchmarks dashboard and commit results.

**Scale is config-driven and drifts — never trust a number in this doc. Run the
preflight first:**

```bash
python3 scripts/execute_preflight.py
```

As of HEAD `87b19bf` it reports **21 production workspaces, 60 eval/bench
workspaces, 138 personas, 114 Ollama models**. `bench_tps.py --dry-run`
translates that to **~273 tests (mode=all)**. These will change; the preflight
and `--dry-run` are the source of truth, not this paragraph.

`bench_tps.py` is the sole TPS instrument. The acceptance and UAT suites assert
no performance numbers.

---

## Your Role

You are the **benchmark execution agent**, not the implementation agent. You
execute the suite, diagnose failures, adjust the run, retry intelligently, and
produce a Grafana dashboard update. Results go to
`tests/benchmarks/results/` as a timestamped JSON; the dashboard at
`config/grafana/dashboards/portal5_benchmarks.json` updates from that file.

**No shortcuts. No prior-run bias.** Do not assume models from a previous run
are still loaded or producing similar TPS. Every run is fresh.

**Do NOT modify product code.** `portal/**` is protected. If a bench failure
traces to a product bug, report it — don't patch it here.

---

## Phase 0 — Preflight (required before any run)

```bash
# 1. Ground truth — counts + no retired-alias leak
python3 scripts/execute_preflight.py                 # must end "OK to run"; nonzero = STOP

# 2. Bench plan — the real test count for THIS run
PORTAL_ENABLE_EVAL=1 python3 tests/benchmarks/bench_tps.py --dry-run

# 3. Backends up?
curl -s localhost:11434/api/tags  >/dev/null && echo "ollama ok"
curl -s localhost:9099/health     >/dev/null && echo "pipeline ok"
```

**`PORTAL_ENABLE_EVAL=1` is required** — without it the eval/bench workspaces
don't load and the plan is incomplete. The bench harness sets this itself in
its entry point, but set it explicitly for the dry-run so your plan matches the
real run.

If the preflight reports a retired-alias leak, STOP — the surface has regressed
(a retired id like `auto-redteam`/`auto-phi4` reappeared); do not bench a broken
surface.

---

## Autonomous Monitoring Loop — required default

Full bench runs take 3–6 hours (~273 tests across 3 modes). **Immediately after
launching, establish a `ScheduleWakeup` loop.** Not optional.

### On launch
1. Start the run detached, logging to a timestamped file under
   `tests/benchmarks/results/`.
2. Record the PID and the expected test count (from `--dry-run`).
3. Set the first wakeup ~20 min out.

### On each wakeup
1. Is the process alive? (`ps`), how far along? (tail the log, count completed
   tests vs planned).
2. If progressing: reschedule ~20–30 min out.
3. If stalled (no new completed test in ~2 cooldown intervals): diagnose — a
   model that won't load, an OOM, a hung backend. Note it, and either skip the
   offending model (`--skip-model <id>`) and continue, or halt with evidence.
4. If finished: proceed to results + dashboard.

---

## Modes

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

## Served-model sanity (new in V4)

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

## Results + dashboard

1. Confirm the run completed the planned test count (allow documented skips).
2. Update `config/grafana/dashboards/portal5_benchmarks.json` from the results
   JSON via the existing updater (confirm its name):
   ```bash
   python3 scripts/update_grafana_benchmarks.py --input tests/benchmarks/results/<file>.json
   ```
3. Commit:
   ```bash
   git add tests/benchmarks/results/<file>.json config/grafana/dashboards/portal5_benchmarks.json
   git commit -m "bench(tps): run <date> — <N> tests, <notable findings>"
   ```

---

## Failure playbook

- **A model won't load / OOMs** — the M4 Pro has 64GB; a 70B q4 + context can
  exceed it. Skip and note; don't force.
- **Persona benches at pool-default TPS not its pin** — served-model regression;
  report, don't patch.
- **Pipeline mode much slower than direct for the same model** — expected
  (routing overhead), but a large gap on a simple prompt may indicate a
  mis-route; cross-check with `routing_regression.py --assert-baseline`.
- **Preflight retired-alias leak** — surface regression; halt.

## Non-negotiables
- Preflight + `--dry-run` before every run; counts come from there, not this doc.
- `PORTAL_ENABLE_EVAL=1` for full coverage.
- Product code is read-only; bench failures that are product bugs get reported.
- Every run fresh; no prior-run assumptions.
