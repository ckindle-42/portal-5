# HUNT_CORE Phase 1 A/B plan — `hunt-reasoning` on Inkling vs gemma-4-26B QAT (2026-11-26)

Phase 1 of `docs/design/CORE_SET_MEMORY_ARCHITECTURE_20261126.md` §8, run under
`docs/MODEL_SEAT_PROCESS.md`. Written for the orchestrator: **this lane ran no live arm**; every
command below is for it to run. The seat decision, the switch, the instruments and the decision
rule are fixed here before the first run.

## 1. The seat decision (seat process rule 1)

| field | value |
|---|---|
| Seat | `hunt-reasoning` (the hunt's own reasoning: source cards, notable judgement, lead ranking) |
| Helper in scope | `auto-council` — the hunt's council second pass (`notables/stage2.py`, `rerank.py`) |
| Incumbent | gemma-4-26b-a4b-it-QAT-4bit on oMLX, via the hint `gemma4:26b-a4b-it-qat-ctx8k-hunt` (Ollama fallback: the derived ctx8k tag of the same name) |
| Candidate | `Inkling-2-Mini-oQ4e-mtp` — the checkpoint `security-reviewer` (`config/portal.yaml:2889`) and base `auto-security` (`:1923`) already run; Ollama fallback `inkling-2-mini:ctx256k` through the `Inkling-2-Mini-oQ4e-mtp` alias in `ollama-general` (`config/backends.yaml:511`) |
| Action on a win | keep the patch, 2–3 day real-use trial, then keep or `git apply -R` |
| Default if unproven | keep gemma; two valid inconclusive runs close the question |
| Budget | 2 labelled runs + 2 `s5-security-hunt-workflow` runs per arm (≈3–5 h total). No new suite. Elapsed is report-only. |

Facts that shape the design (read from config, not the live stack):

- The seat is internal, tool-free, 8k, temperature 0, `max_concurrent: 8`, never an OWUI preset and
  never an auto-routing destination (`config/portal.yaml:2920-2946`). The switch keeps all of that.
- The hunt calls it through the Pipeline only: `PORTAL_HUNT_JUDGE_MODEL=hunt-reasoning`,
  `PORTAL_HUNT_JUDGE_BACKEND=omlx-general` (`scripts/native-mcp-service.sh:213-226`,
  `notables/pipeline.py`). Requests carry `portal_backend: omlx-general`, so a pin that cannot
  serve the hint is a loud 400, not a silent fallback.
- **The council helper is not a separate model.** All four `auto-council` seats (evidence,
  challenger, operator, synthesizer) are `gemma-4-26b-a4b-it-QAT-4bit` — the same weights as the
  hunt seat, so today the two share one resident. It is also **not on the product hunt path**:
  `product_jobs` runs cards → behaviours → notables → relate → judge and only *imports*
  `rerank.REPORT_FILE` for cost accounting; the council pass is only reachable from the
  `stage2`/`rerank` evaluation CLIs. It is in the switch so the evaluation arm loads no second
  model.
- Both seats end up on the model that the security conversation already uses, so a hunt run has
  one resident (Inkling) instead of two (Inkling + gemma-26B QAT, 15.3 GiB).

## 2. The switch (reversible, config only)

`coding_task/arm/hunt_core_inkling_arm.patch` — `hunt-reasoning.model_hint` and `auto-council`
(`model_hint`, 3 member `model:`, `synthesizer_model:`) → `Inkling-2-Mini-oQ4e-mtp`. Role prompts,
`context_limit`, `temperature`, `top_p`, `top_k`, `council` thresholds, `max_concurrent` and the
safety append are untouched (differences in sampling between the two cards are a separate A/B).

```bash
cd /Users/chris/projects/portal-5                     # the live checkout
git apply coding_task/arm/hunt_core_inkling_arm.patch # Inkling arm
./launch.sh rebuild && ./launch.sh up
# … run the arm …
git apply -R coding_task/arm/hunt_core_inkling_arm.patch   # back to gemma
./launch.sh rebuild && ./launch.sh up
```

If the lane is not merged into the live checkout yet, apply the worktree copy instead:
`git -C /Users/chris/projects/portal-5 apply /Users/chris/projects/portal-5-hunt-core-ab-ds/coding_task/arm/hunt_core_inkling_arm.patch`.

What each step needs, and what it does not:

- **Rebuild + up: required.** `config/portal.yaml` is baked into the pipeline image; there is no
  config-reload endpoint (`router/app.py` has no reload route).
- **`sync-config`: not needed.** Verified against the patched tree: it reports
  `backends.yaml workspace_routing: no change`, `.mcp.json: no change`, and
  `imports/openwebui/workspaces/: 0 created, 0 updated, 0 removed`. `workspace_routing` is
  preserved per workspace (`emit_workspace_routing`) and holds backend groups, not hints.
- **Seed: not needed.** Neither workspace is exposed to OWUI (`expose_to_owui: false`), so no
  preset changes.
- **Review-MCP kickstart: not needed.** `PORTAL_HUNT_JUDGE_MODEL` still names `hunt-reasoning`; only
  the seat's model moves.
- **The control arm needs no rebuild at all** — the deployed image already has gemma. Run control
  first, then apply, rebuild once, run Inkling twice, and revert only when the verdict is in.

Confirm the armed container (before spending a run):

```bash
docker exec portal5-pipeline grep -n "model_hint: Inkling-2-Mini-oQ4e-mtp" /app/config/portal.yaml
```

## 3. Preflight per arm (proves setup before rows count — seat process rules 3–4)

The judge reads `p_yes` from **yes/no token logprobs** (`judge.py:judge_cell` sends
`logprobs: true, top_logprobs`, `temperature: 0, reasoning_effort: none`). A model that answers but
serves no logprobs silently produces `unjudged: missing_logprobs` on every cell, so this single
probe decides whether an arm is even runnable:

```bash
curl -s -X POST http://127.0.0.1:9099/v1/chat/completions \
  -H "Authorization: Bearer $PIPELINE_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"hunt-reasoning","portal_backend":"omlx-general",
       "messages":[{"role":"user","content":"Answer with one word: yes or no. Is 2+2 equal to 4?"}],
       "temperature":0,"max_tokens":4,"logprobs":true,"top_logprobs":5,
       "reasoning_effort":"none","stream":false}' | python3 -m json.tool
```

- **Pass:** `choices[0].logprobs.content[0].top_logprobs` lists `yes`/`no` alternatives, and
  `"model"` is `Inkling-2-Mini-oQ4e-mtp` (arm) or `gemma-4-26b-a4b-it-QAT-4bit` (control).
- **Fail:** no `logprobs` key, or `"model"` is the other arm → the row would be void; for the
  Inkling arm a missing-logprobs result is a capability **loss** (the seat cannot rank leads),
  not an inconclusive.

Per arm, also record:

```bash
curl -fsS -H "Authorization: Bearer $OMLX_API_KEY" \
  http://127.0.0.1:8085/admin/api/activity | python3 -m json.tool
docker logs --since 30m portal5-pipeline 2>&1 | grep -E 'backend.selected|load_guard|capacity_fallback|507'
```

## 4. Instrument A — the labelled hunt (the number that decides)

Same command, same index, same window, same knowledge store, both arms. Window omitted on purpose:
the whole index is the window, so the arms cannot diverge on it. `--family kyoushi` declares the
reviewed index's family (the review's own name in the receipts); `--knowledge-families santos,russell`
bounds the similar-to-known prior to the two families this run is *not* scored against. Run the two
**control** runs first — the decision rule compares the arm against both of them.

```bash
cd /Users/chris/projects/portal-5
for k in LAB_SPLUNK_URL LAB_SPLUNK_USER LAB_SPLUNK_PASSWORD LAB_SPLUNK_INDEX PIPELINE_API_KEY; do
  export "$k=$(grep -E "^$k=" .env | cut -d= -f2- | tr -d '\"')"
done
export PORTAL_HUNT_JUDGE_URL=http://127.0.0.1:9099
export PORTAL_HUNT_JUDGE_MODEL=hunt-reasoning
export PORTAL_HUNT_JUDGE_BACKEND=omlx-general
export PORTAL_HUNT_EMBEDDING_URL=http://127.0.0.1:9099
export PORTAL_HUNT_EMBEDDING_MODEL=google/embeddinggemma-2
IDX=hb_kyoushi_s1_v2          # use the SAME index string for all four runs
OUT=/Volumes/data01/portal5_hunt/hunt_core_ab_20261126
KS=/Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb
KEYS=/Volumes/data01/portal5_hunt/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl

# per run: ARM in {gemma,inkling}, N in {1,2}
uv run python -m portal.modules.security.core.hunt.notables \
  --index "$IDX" --out "$OUT/$ARM-$N/kyoushi" --stage all --family kyoushi \
  --knowledge-store "$KS" --knowledge-families santos,russell
```

Merge weights stay at the built-in defaults in both arms — do **not** export
`PORTAL_HUNT_MERGE_WEIGHTS` for one arm and not the other (the vector only reorders the same
notables, so an arm-dependent vector would be the tuning the seat process forbids).

`hb_kyoushi_s1_v2` is the index the R2 control ran (`coding_task/REPORT_HUNT_VERDICT_R2_kyoushi.md`,
761.8 s wall); `hb_kyoushi_s1` is the probe-kit default. Whichever exists, use one value for all
four runs — the scoreboard refuses keys that name no source the run read (`_check_family`), which is
the guard against a mismatched index.

**Every run needs a fresh `--out`.** `JudgeCache` is keyed by the notable's content key only
(`judge_notables.py:170`), not by model, so pointing a second arm at an existing run dir would serve
the first arm's `p_yes` and `served_model` from `cache/judge.json` and score the wrong model under
the right name. The validity rule below (`judge served_models` is one model) is what catches it; a
fresh directory makes it impossible.

Score each Inkling run against the **gemma-1** run (the scoreboard prints the step diff, names only);
for the control runs, diff `gemma-2` against `gemma-1` the same way:

```bash
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out "$OUT/$ARM-$N/kyoushi" --keys "kyoushi=$KEYS" \
  --baseline "$OUT/gemma-1/kyoushi"
```

What the scoreboard already prints for each run, and which line is the endpoint:

| outcome | scoreboard line | role |
|---|---|---|
| covered labelled steps in the top 50 | `C0 modes  line N/M @50 …` | **primary (absolute outcome)** |
| recall given what was read | `C0 recall-of-reachable  line @50 …` | diagnostic |
| read/understanding ceiling | `C0 ceiling  steps R/T reachable  labelled lines read verbatim …` | validity + cards quality |
| judge separation on labelled notables | `judge  judged … AUC all …` / `judge auc_pooled …` | secondary (must not regress) |
| lead quality (cases, promotion) | `case …` block: `promotion`, `case_member_recall`, `case recall` | secondary |
| spend | `cost total=…s  searches=…` | report-only |

Machine form: add `--json` (same report). Served model per stage, from the run's own receipts:

```bash
python3 - "$OUT/$ARM-$N/kyoushi" <<'PY'
import json,sys,pathlib
run=pathlib.Path(sys.argv[1])
cards=json.loads((run/"sources.json").read_text())["cards"]
print("cards served:", sorted({c["model"].get("served_model") for c in cards}))
prog=json.loads((run/"progress.json").read_text())["stages"]
j=prog.get("judge",{})
print("judge served:", j.get("served_models"), "judged:", j.get("judged"),
      "unjudged:", j.get("unjudged_reasons"), "cut:", j.get("selection",{}).get("cut_reason"))
print("behaviours searches:", prog.get("behaviours",{}).get("clock"))
PY
```

The council helper (optional, same instrument, existing CLI — the council arm calls `auto-council`,
so it exercises whichever model the switch put there):

```bash
uv run python -m portal.modules.security.core.hunt.notables.stage2 \
  --out "$OUT/$ARM-$N/kyoushi" --keys "kyoushi=$KEYS"
```

It prints one row per arm — `stage1_judge`, `single_judge`, `council` — with `judged/bad/good/AUC/
yes-bad/yes-good/s-call/budget`, plus `council decisions … abstain …` and `council unjudged …`. The
council response carries no served-model field, so take the council's served model from the
pipeline log line for that window (`backend.selected`).

## 5. Instrument B — the real hunt workflow (COMPLETE/partial, splunk_requests)

**5.1 The design's acceptance runs — `s5-security-hunt-workflow`, twice per arm** (design §8
Phase 1.2). The scenario drives the analyst workflow through OWUI → Pipeline → review MCP and its
grader (`tests/qat/uat_behavioral.py:_grade_hunt_case`) checks exactly the design's clauses from
the *tool receipts*, not the prose: `hunt_start` + `hunt_status` called, a real `hunt-r2-…` id,
reported status equal to the receipt's, and — once terminal — `splunk_requests > 0` and a lead
count present, with the answer citing returned identifiers.

```bash
cd /Users/chris/projects/portal-5
for n in 1 2; do
  uv run python -m tests.qat --scenario s5-security-hunt-workflow \
    --output-dir "results/qat/hunt-core-$ARM-$n"
  cat "results/qat/hunt-core-$ARM-$n/QAT_REPORT.md"
done
```

Require: both rows PASS, both receipts terminal `COMPLETE` (a `PARTIAL` needs its
`partial_reason` in the job record and must not be the judge/notables stage), `splunk_requests > 0`,
and the same job id in answer and receipt.

**5.2 The proof kit — progress turn and the mid-hunt reviewer turn.** `owui_hunt_chat.py` sends the
"list sources and start a hunt" turn, waits on the durable job over native MCP, then asks for
leads and the first case. It prints the job id, terminal status, elapsed and `PASS`/`FAIL`:

```bash
cd /Users/chris/projects/portal-5
export PIPELINE_API_KEY=$(grep -E '^PIPELINE_API_KEY=' .env | cut -d= -f2- | tr -d '"')
IDX=hb_kyoushi_s1_v2                               # the same value as Instrument A
python3 scripts/proofs/owui_hunt_chat.py --index "$IDX" --require-sources
```

While that hunt is in flight, send one OWUI turn to `security-reviewer` asking for its job id and
current stage (design §8 Phase 1.3). It must quote the exact job id, report the tool's own stage,
and show no 507, no `capacity_fallback`, and no model other than Inkling in the pipeline log. In
this arm that turn and the hunt are the *same* resident — a second model appearing in
`admin/api/activity` during the turn is the failure this A/B exists to remove.

Add the job's own cost from its record under the review MCP's `PORTAL5_HUNT_DIR`
(default `~/AI_Output/review/hunts`):

```bash
J="$HOME/AI_Output/review/hunts/hunt-r2-<12hex>.json"   # or $PORTAL5_HUNT_DIR if the MCP sets it
python3 - "$J" <<'PY'
import json,sys
j=json.load(open(sys.argv[1]))
print("status", j.get("status"), "partial_reason", j.get("partial_reason"))
print("cost", j.get("cost"))          # splunk_requests, elapsed_s, model_requests, model_seconds
print("run dir", j.get("run_dir"))
PY
```

`hunt_status(detail=true)` returns the same `cost` block over MCP if the file is not reachable. The
job's run dir is scoreable by Instrument A's scoreboard command (`--keys "<jobid>=<keys>"`), which
is how a job's leads can be graded when you want one.

Concurrency stays at the seat's declared `max_concurrent: 8` in both arms. The design's 1/2/4
residency sweep measures the scheduler, not the model, and is not part of this decision.

## 6. Decision rule (fixed before the runs)

Let `c1,c2` be the control runs' `C0 modes line … @50` covered counts and `i1,i2` the Inkling ones;
`a_c`, `a_i` their `judge AUC all` (or `auc_pooled` when both print it).

**A labelled run counts only if all hold** (else it is void, not scored against a model):

1. preflight probe passes and reports the intended model;
2. the run's own receipts show the intended model on every stage that names one and no other
   (`cards served`, `judge served_models`); no 507 / `capacity_fallback` in the pipeline log for the
   run window;
3. `--stage all` completed all five stages, `C0 ceiling reachable` ≥ 1, `labelled lines read` > 0;
4. `judge unjudged` is empty apart from a declared budget cut (`selection.cut_reason`), and
   `judged` ≥ 300 (the R2/R3 runs judged 755–769 of ~800).

**Workflow acceptance** (per arm, required of both arms): both `s5-security-hunt-workflow` rows PASS,
each receipt terminal `COMPLETE` or `PARTIAL` with a `partial_reason` outside the judge/notables
stages, `splunk_requests > 0`, and the mid-hunt reviewer turn (§5.2) returns the exact job id with no
507 and no second model resident.

**Inkling wins** (patch stays, then the 2–3 day trial) if every labelled run is valid, the workflow
acceptance holds, and

- `min(i1,i2) >= max(c1,c2)` — its worse run covers at least as many labelled steps at @50 as the
  control's best run (strict separation, no averaging over a regression), **and**
- `min(a_i) >= max(a_c) - 0.05` — judge separation does not regress beyond noise, **and**
- the council arm, if measured, is not worse than the control council by more than 1 case in
  `council decisions`/`abstain` counts.

**Inconclusive → keep gemma** (seat process rule 9): every run valid but the @50 ranges overlap, or
the AUC gap is inside ±0.05. Two valid inconclusive runs close the question; it does not reopen
without a new decision.

**Inkling loses → revert at once** (do not spend the second run) if any valid run shows
`@50` at least 2 steps below both control runs, `AUC` more than 0.05 below the control's best, all
judge cells `missing_logprobs`, a silent model substitution, or a workflow failure
(no terminal status, `splunk_requests == 0`, 507, or fallback to a non-Inkling model for the seat).

Elapsed is reported and never a criterion (design §8 Phase 1.4).

## 7. Read volume is not neutral — state it in the verdict

`behaviours`/`notables` make no model calls, but the **cards** stage does, and the card keying drives
source placement and parsing. A lower `C0 ceiling reachable` in the Inkling arm is therefore a real
cards-quality loss, not only read noise; a higher one is a real gain. Quote `reachable`, `labelled
lines read verbatim` and `cost searches` beside the @50 number in the verdict so the diff can be
attributed to cards, ranking, or budget.

## 8. Not done by this lane

No live arm, no rebuild, no Splunk query, no Pipeline request. The patch was verified offline only:

- applies and reverts cleanly against HEAD (`git apply --check` both directions);
- the full unit suite is green with it applied (`4124 passed, 46 skipped`);
- `sync-config` is a no-op for it (no derived artefact changes);
- `tests.wfe.settings_audit.audit_config_seats(['hunt-reasoning','auto-council'])` reports
  `violations: []` in both states, and the armed `auto-council` roster resolves all four seats to
  `('omlx', 'Inkling-2-Mini-oQ4e-mtp')` with no `council_card_missing`/`council_model_unroutable`;
- the seat resolves `omlx-general → Inkling-2-Mini-oQ4e-mtp` (control: `→ gemma-4-26b-a4b-it-QAT-4bit`),
  so §3's expected `"model"` value is the served oMLX id.

The live proofs in §3–§5 are the orchestrator's.
