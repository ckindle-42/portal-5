# Core module acceptance — compliance and hunt (2026-11-27)

## Verdict and evidence rules

| module | current verdict | what is proven | what is not proven |
|---|---|---|---|
| compliance | **NOT ACCEPTED** | the 2026-11-24 policy-conversation QAT row passed; the store contains real regulatory/operator material | no current six-case acceptance run exists; the latest multi-framework row failed retrieval/read/answer contracts |
| hunt | **NOT ACCEPTED** | the latest product job completed real Splunk work and produced notables/cases; an older workflow QAT row passed | the latest full labelled botsv2 run fails the plan's semantic case/coverage/honesty bars; product `COMPLETE` is not detection correctness |

These are different outcomes and must not be collapsed:

1. **Setup void / blocked:** the intended engine, model, store, corpus, credentials, or index was not serving; a required setup stage is absent. No semantic row counts.
2. **Workflow failure:** the real product path did not start, poll, finish, retrieve, or truthfully report its own receipt.
3. **Semantic failure:** the workflow completed but the answer/leads/cases did not satisfy the module's own correctness bar.
4. **Pass:** setup is valid, the workflow is truthful, and every semantic bar below holds on the same current revision. A stitched set of historical green rows is not acceptance (`docs/design/CORE_SET_MEMORY_ARCHITECTURE_20261126.md:332-346`).

A QAT row proves its own grader only. In particular, `s5-security-hunt-workflow` checks tool receipts and truthful reporting (`tests/qat/uat_behavioral.py:2245-2357`), not attack recall; `s5-compliance-multiframework` checks retrieved citations and conclusion qualification (`:2388-2408`, `:2934-2989`), not the six CIP answer shapes. Raw notable/case counts likewise say nothing about whether the right evidence was found.

All live commands below are for the **orchestrator in `/Users/chris/projects/portal-5`**. This preparation lane started no run and made no inference request. Export credentials without printing them:

```bash
cd /Users/chris/projects/portal-5
for k in PIPELINE_API_KEY OWUI_API_KEY OMLX_API_KEY LAB_SPLUNK_URL LAB_SPLUNK_USER LAB_SPLUNK_PASSWORD; do
  export "$k=$(grep -E "^$k=" .env | cut -d= -f2- | tr -d '\"')"
done
SHA=$(git rev-parse HEAD)
```

---

## 1. Compliance

### 1.1 What “works as designed” means

There are two product paths, and both must pass:

- **Interactive analyst (`auto-compliance`)** retrieves the governing requirement and actual operator sections, compares the specific duty, distinguishes sourced facts from assumptions, scopes absence to the corpus examined, and never certifies compliance. Other frameworks have catalog lookups only when their corpus is not ingested (`config/portal.yaml:2902-2914`).
- **Focused reading (`auto-compliance::reading`, compatibility id `compliance-reading`)** carries a conversation, calls `compliance_context(mode="material")` for requirement material, reads further only when needed, quotes both sides verbatim, reports strictness/narrowing as fact, and calls an obligation with no operator material **unverified**, not a confirmed gap (`config/portal.yaml:3140-3177`).

The existing instruments are sufficient; no new suite is needed:

1. `scripts/compliance_acceptance.py --adapter workspace`: six real CIP-007-6 cases, three runs each, through the deployed workspace. The cases and their real `derived_from` section ids are in `portal/modules/compliance/data/private/local/config/compliance/cases/cip_007_6.yaml:49-141`.
2. Existing QAT journeys `s5-compliance-multiframework` and `s5-compliance-policy-conversation`: the real OWUI analyst path and its retrieved receipts.

The six deterministic workspace guards are HTTP 200, turn within budget, nonempty answer, measured prompt tokens, known/unexceeded serving window, required tool calls, and grounded/resolving citations (`scripts/compliance_acceptance.py:706-793`). They are necessary, not sufficient: the case manifest explicitly says the string rubric was deleted and an agent must read each transcript and judge understanding (`cip_007_6.yaml:9-19`).

### 1.2 Pass bar and latest measured results

The governing acceptance task says:

> “Six cases × three runs × every loop-capable seat.” (`coding_task/TASK_COMPLIANCE_PROVE_CIP_007_V1.md:411-416`)

and:

> “One live instrument, three runs per cell, real port, artifacts under the git rev, a truncation guard per call…” (`:505-517`)

For the single current production seat, acceptance therefore requires:

- **18/18 planned workspace cells present and deterministic-PASS** in `status.json`; no resumed cell whose seat/prompt identity differs from the live campaign;
- **18/18 transcript-level semantic PASS**, with the reviewer naming the `derived_from` sections and the satisfied answer property for each case;
- both current QAT compliance rows **PASS**, with retrieved evidence for every citation and no raw tool payload in the visible answer;
- no failure is reclassified as reasoning until the spec's rungs 0–3 (settings, prompt, tool, material/scope) are exhausted (`TASK_COMPLIANCE_PROVE_CIP_007_V1.md:427-461`).

Current measurements:

| instrument | date | result | receipt |
|---|---|---|---|
| six-case workspace acceptance | 2026-11-27 read | **no runs**: `_acceptance_runs()` returned `[]` | `portal/modules/compliance/data/private/local/reports/compliance/acceptance`; emptiness confirmed through `scripts/validation/compliance_acceptance.py:_acceptance_runs` |
| `s5-compliance-multiframework` | 2026-11-27 ~20:00Z, main `29df39df6` | **FAIL, 1,646.7 s**; GDPR citation absent from retrieved receipts; two store-issued section ids read empty; raw tool JSON in answer | chat `987f595f-2d17-4c99-aecd-230928bb282e`; live facts recorded in `coding_task/BRIEF_COMPLIANCE_MULTIFRAME_ROOT_20261127.md:3-9` |
| same multi-framework scenario, earlier row | 2026-11-24 | PASS, 518.974 s — historical, superseded by the latest failure | `results/qat/stage5-verify-compliance-live-20261124/results.jsonl`, chat `d53e51a9-dcdb-4b78-8ff1-ac5c431c006d` |
| `s5-compliance-policy-conversation` | 2026-11-24 | PASS, 635.35 s, 23 verbatim quotes | `results/qat/stage5-browser-verify-5fixes-v6-20261124/results.jsonl`, chat `3350d324-1a94-4d20-afd8-90415ccc929f` |

A read-only SQLite check on 2026-11-27 found 202 `source_documents`, 202 `document_revisions`, 24,351 `source_sections`, 276 `requirement_nodes`, 3,476 `relationship_assertions`, and 527 `assessment_results` in `portal/modules/compliance/data/compliance_store.db`. Both section ids from the failed turn exist. No active document title/logical id matches GDPR or General Data Protection Regulation. That makes the empty reads a tool/route problem, **not missing rows**, and makes the GDPR QAT expectation a separate corpus/specification mismatch.

### 1.3 Setup proof before rows count

Run these read-only checks from the live checkout. Any failure blocks the run rather than becoming a model-quality score.

```bash
cd /Users/chris/projects/portal-5
git rev-parse HEAD
git status --short
for url in \
  http://127.0.0.1:9099/health \
  http://127.0.0.1:8937/health \
  http://127.0.0.1:8948/health; do
  curl -fsS "$url" | python3 -m json.tool
done

docker exec portal5-pipeline grep -nE \
  'auto-compliance:|model_hint: hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k|gemma4:26b-a4b-it-q4_K_M-ctx128k' \
  /app/config/portal.yaml
curl -fsS http://127.0.0.1:11434/api/ps | python3 -m json.tool
curl -fsS -H "Authorization: Bearer $OMLX_API_KEY" \
  http://127.0.0.1:8085/admin/api/activity | python3 -m json.tool
```

The configured hints must resolve to the intended workspaces/routes. A resident model name alone is not enough: each acceptance turn must record its served model, engine, route, prompt tokens, and serving window (`scripts/compliance/truth/served_turn.py:24-100`).

Prove the real store and the two ids implicated in the latest failure without writing to it:

```bash
uv run python - <<'PY'
import sqlite3
p = "file:portal/modules/compliance/data/compliance_store.db?mode=ro"
db = sqlite3.connect(p, uri=True)
for table in ("source_documents", "document_revisions", "source_sections",
              "requirement_nodes", "relationship_assertions", "assessment_results"):
    print(table, db.execute(f"select count(*) from {table}").fetchone()[0])
for ref in ("isection-116a10435ed3cb06dea6", "isection-471254a65df9d368cdb6"):
    print(ref, db.execute(
        "select section_id, revision_id, title from source_sections where section_id=?", (ref,)
    ).fetchone())
print("GDPR documents:", db.execute("""
    select d.logical_id, d.title from source_documents d
    join document_revisions r using(logical_id)
    where r.recorded_to is null
      and (lower(d.title) like '%gdpr%' or lower(d.logical_id) like '%gdpr%'
           or lower(d.title) like '%general data protection%')
""").fetchall())
PY
uv run python - <<'PY'
import yaml
from portal.modules.compliance.core import requirement_scope
from portal.modules.compliance.core.repository import Repository
from portal.modules.compliance.core.section_index import resolve_sections
path = "portal/modules/compliance/data/private/local/config/compliance/cases/cip_007_6.yaml"
cases = yaml.safe_load(open(path))["cases"]
repo = Repository()
try:
    for case in cases:
        scope = requirement_scope.resolve(repo, case["ref"])
        print(case["id"], case["ref"], scope.method, len(scope.leaves))
    ids = sorted({ref for case in cases for ref in case["derived_from"]})
    missing = sorted(set(ids) - set(resolve_sections(repo, ids)))
    print("derived_from ids:", len(ids), "missing:", missing)
    assert not missing
finally:
    repo.close()
PY
uv run python - <<'PY'
from scripts.validation.compliance_acceptance import _acceptance_runs
print(_acceptance_runs())
PY
```

The six manifest refs and every `derived_from` id must resolve in this same store. The workspace runner now writes `preflight.json` through the existing Pipeline-era `pin_v2`: it requires a workspace, a positive context limit, at least one serving route, and a readable template for **each** engine on that route. This replaces the native-Ollama-only pin for workspace runs; the native preflight remains for explicit reader/legacy runs (`tests/wfe/compliance_preflight.py:414-464`).

**Corpus/spec precondition for the multi-framework QAT:** either a real GDPR revision containing Art. 32(1)(a) must be ingested and pinned, or the scenario/grader must be changed to require an explicitly grounded “GDPR is not in the ingested corpus” answer. With the currently declared NERC-only corpus (`config/portal.yaml:2905-2914`), requiring GDPR in retrieved receipts is not an honest pass condition.

### 1.4 Exact live acceptance commands

First land the sibling compliance root fixes, rebuild/restart through `./launch.sh` as required, and repeat §1.3. Then run:

```bash
cd /Users/chris/projects/portal-5
ACCEPTANCE_RUN=1 RUNS=3 ./scripts/run_compliance_acceptance.sh
REV=$(git rev-parse HEAD)
ART="portal/modules/compliance/data/private/local/reports/compliance/acceptance/$REV"
cat "$ART/workspace.stage-exit"                 # required: 0
python3 -m json.tool "$ART/manifest.json"
python3 -m json.tool "$ART/preflight.json"
python3 -m json.tool "$ART/status.json"         # required: 18 cells, all passed=true

for scenario in s5-compliance-multiframework s5-compliance-policy-conversation; do
  uv run python -m tests.qat --scenario "$scenario" \
    --output-dir "results/qat/core-compliance-$REV-$scenario"
  cat "results/qat/core-compliance-$REV-$scenario/QAT_REPORT.md"
done
```

The wrapper deliberately exits 0 for supervisor safety; `workspace.stage-exit` and `status.json` are authoritative. It restarts only the compliance native service onto the live revision, as the existing wrapper is designed to do (`scripts/run_compliance_acceptance.sh:67-83`).

**Expected runtime:** 18 workspace turns with the instrument's default 900 s per-turn ceiling = at most **4.5 hours** plus setup; plan a multi-hour quiet-host run. Each QAT scenario has two 900 s turns, so up to about **30 minutes each**; observed recent durations were 8.6–27.4 minutes for multi-framework and 10.6 minutes for policy conversation (`tests/qat/uat_behavioral.py:625-640`).

Read every cell JSON, not just `status.json`: `turn.served_model`, `turn.serving.engine/serving_window`, `prompt_tokens_high_water`, `tool_calls`, `tool_outputs`, `pipeline_errors`, `wall_s`, `failed_assertions`, and the full answer. A cell with missing token/window measurement fails rather than reading as zero. Record the semantic verdict and reasons beside those cells; the runner does not automate that judgment.

### 1.5 Failure classification and dispatchable defects

| symptom | classification | required action |
|---|---|---|
| health/route/template unreadable, intended model not serving, missing store/case ids | setup void | repair setup, re-pin, rerun; no semantic verdict |
| unknown/exceeded window, missing usage, wrong served model, template drift | rung 0 / invalid row | fix settings/serving path and rerun that cell |
| tool returns refs but no text, empty read for a store-issued id, malformed address accepted silently | rung 2 product defect | fix tool/address contract, not the grader |
| needed section absent from an otherwise valid population | rung 3 scope/corpus defect | fix scope/join or ingest the real source; never manufacture text |
| retrieved both sides but wrong comparison/conclusion | semantic product/model failure | apply the spec's rung 1 then rung 4 rule; do not change thresholds to force a pass |
| raw tool JSON in visible answer | workflow/product defect | fix the emitting serialization layer and prove it in QAT |

Open items, each dispatchable as one lane:

1. **Read-roundtrip root fix (already owned by the compliance root lane):** trace native MCP result → Pipeline tool receipt → answer serialization; make every emitted section id read back its text and remove raw tool JSON from visible content, then rerun the failed chat scenario.
2. **GDPR corpus/QAT reconciliation:** ingest and revision-pin the real GDPR Art. 32 text, or change the scenario to require grounded corpus absence; do not accept a memory citation or delete the retrieval assertion merely to turn the row green.
3. **Turn-cost root fix:** account for the 1,646.7 s by hops/nested `compliance_ask`/prefill, then remove redundant hops and schema/tool payload duplication without weakening retrieval; acceptance must stay inside 900 s per turn.
4. **Six-case evidence gap:** run the repaired workspace instrument 18 times and complete the transcript-level semantic review; a green QAT policy row cannot substitute for it.

---

## 2. Hunt

### 2.1 What “works as designed” means

The hunter must understand an already-indexed estate without being given attack values, localise and read evidence with declared coverage/censorship, emit checkable notables, assemble cross-source cases, and rank them for a human analyst. A notable is a signal occurrence; a case is the product unit and requires at least two independent pieces of evidence (`docs/hunt/ORCACYBER_HUNT_PLAN.md:186-222`). The judge orders evidence; it is not a pass gate and must not silently drop cases.

The proof must remain blind: labels build/tune on training families, proof indexes stay out of the knowledge store, and final proof is on unlearned data. `PROOF_INDEXES` includes Wheeler, CloudObs AWS, botsv1, and the other reserved sets (`portal/modules/security/core/hunt/notables/knowledge.py:27-55`).

Use the existing instruments:

1. **Semantic:** `python -m portal.modules.security.core.hunt.notables --stage all` on the real labelled indexes, then `notables.scoreboard` with their out-of-band keys. The existing four-family runner is `coding_task/RUN_HUNT_REDESIGN.sh`.
2. **Product workflow:** two current `s5-security-hunt-workflow` runs through OWUI → Pipeline → review MCP, plus `scripts/proofs/owui_hunt_chat.py --require-sources` for the progress → terminal leads/case conversation.
3. `scripts/hunt_run.py` and `scripts/hunt_investigate.py` are the retired host-hour path, not the acceptance instrument for the current notables/case product.

### 2.2 Pass bar and latest measured results

The OrcaCyber plan fixes the semantic bar (`docs/hunt/ORCACYBER_HUNT_PLAN.md:547-565`):

> “Pass bar, all four: 1. No build-family regression … 2. Coverage … 3. Cases … 4. Honesty…”

Expanded without changing it:

1. **Validity:** intended model on cards/judge, all five stages (`cards`, `behaviours`, `notables`, `relate`, `judge`), no 507/`capacity_fallback`, reachable ceiling ≥1, labelled lines read >0, judge `judged ≥300`, and no unjudged rows except a declared budget cut (`docs/findings/HUNT_CORE_AB_PLAN_20261126.md:266-275`).
2. **No build-family regression:** recall-of-reachable @50 at least kyoushi **11/11**, santos **11/12**, russell **14/15**, in each family's own mode (`docs/hunt/ORCACYBER_HUNT_PLAN.md:263-271`, `:550-551`).
3. **Wide coverage:** botsv2 `keys_reachable ≥12/24` and `steps_reachable ≥10/14`. This is explicitly conditional on Splunk setup Stage 3 or 4. Without that setup, report per-key causes/no regression and mark full acceptance **blocked**, never passed (`:552-557`).
4. **Cases:** at least **3/4 botsv2 scenarios** have a top-50 case containing a B/P member naming an artefact under strict credit; every case has ≥2 evidence pieces; promotion effect is separate (`:407-410`, `:558-559`).
5. **Honesty:** measured marginal weights, `alerts existed >0`, no score increase when promoted rows are removed, and attribution/marginal reported per generator (`:560-562`).
6. **Workflow:** two QAT rows PASS and both durable jobs terminal **COMPLETE**, `splunk_requests >0`, lead count present, exact same job id in answer/receipt, no 507 or model substitution. The mid-hunt reviewer/progress-results proof must also return exact ids (`docs/design/CORE_SET_MEMORY_ARCHITECTURE_20261126.md:381-399`).

Latest measurements:

| instrument | date | measured result | receipt |
|---|---|---|---|
| full labelled botsv2 `--stage all`, rescored with current scoreboard | live run 2026-11-21; rescore 2026-11-27 | **semantic FAIL**: keys reachable **8/20**, steps reachable **8/14** (B+P **6/11**); loose recall **0/14 @50, 1/14 @100, 1/14 all**; strict **0 at every cut**; qualifying cases **0/4 @50** (also 0/4 all); alerts existed **0** | `/Volumes/data01/portal5_hunt/hunt_proof_r4_solo/botsv2`; keys `/Volumes/data01/portal5_hunt/corpora/botsv2_keys/keys.jsonl` |
| same run, judge/scoreboard cost | 2026-11-21 | 422 judged, 378 unjudged with declared `judge_stage_budget_exhausted`; AUC all **0.791**, pooled **0.661**; served `gemma-4-26b-a4b-it-QAT-4bit`; **1,601.824 s** scoreboard stage cost, 2,088 searches, 323,939 events read | same `progress.json` and current scoreboard output |
| latest product job | 2026-11-27 19:38–19:42Z | **workflow only**: `COMPLETE`, 243.203 s wall, 674 Splunk requests, 2,969 behaviour events, 352 notables, 95 cases, `judge_enabled=false` | `/Users/chris/AI_Output/review/hunts/hunt-r2-cc890dc7d144.json` and its run directory |
| latest committed QAT workflow row found | 2026-11-23 | PASS, 74.022 s; older than the product job and not semantic evidence | `results/qat/release_1_0_20261124T050451Z/results.jsonl`, chat `698b032c-a7f6-4d1b-8f8c-0619fe9b8b80` |

The historical “PASS” for this botsv2 run meant the clock/infrastructure fixes completed all five stages (`/Volumes/data01/hunt_proofs/POST_R3_PROOFS_FROM_AGY_20261125.md:48-57`). The current scoreboard shows why that label cannot be promoted to module correctness. The same off-tree file's held-out Wheeler/CloudObs claims (`:59-84`) are **historical only**: they do not document every current coverage/case/honesty gate above and must not be rerun casually.

Reproduce the stored botsv2 numbers without Splunk or inference:

```bash
cd /Users/chris/projects/portal-5
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out /Volumes/data01/portal5_hunt/hunt_proof_r4_solo/botsv2 \
  --keys botsv2=/Volumes/data01/portal5_hunt/corpora/botsv2_keys/keys.jsonl --json
```

### 2.3 Setup proof before rows count

```bash
cd /Users/chris/projects/portal-5
for url in http://127.0.0.1:9099/health http://127.0.0.1:8943/health; do
  curl -fsS "$url" | python3 -m json.tool
done
docker exec portal5-pipeline grep -nA16 '^  hunt-reasoning:' /app/config/portal.yaml
curl -fsS http://127.0.0.1:11434/api/ps | python3 -m json.tool
curl -fsS -H "Authorization: Bearer $OMLX_API_KEY" \
  http://127.0.0.1:8085/admin/api/activity | python3 -m json.tool

# Read-only Splunk index inventory/counts through the product's own source.
uv run python - <<'PY'
import json
from portal.modules.security.core.review.window import SplunkWindowSource
print(json.dumps(SplunkWindowSource().health(), indent=2))
PY

DATA=/Volumes/data01/portal5_hunt
for f in \
  "$DATA/knowledge/knowledge_v2_20261116.duckdb" \
  "$DATA/corpora/botsv2_keys/keys.jsonl" \
  "$DATA/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl" \
  "$DATA/corpora/ait_lds_v21/santos_ingest/keys.jsonl" \
  "$DATA/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl"; do
  test -s "$f" || { echo "missing required input: $f"; exit 2; }
done
uv run python - <<'PY'
import duckdb
from portal.modules.security.core.hunt.notables.knowledge import PROOF_INDEXES
p = "/Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb"
db = duckdb.connect(p, read_only=True)
print("items by split:", db.execute(
    "select split, count(*) from knowledge_items group by split order by split"
).fetchall())
print("items by family:", db.execute(
    "select family, count(*) from knowledge_items group by family order by family"
).fetchall())
proof = sorted(PROOF_INDEXES)
print("proof-index leakage:", db.execute(
    "select index_name, count(*) from knowledge_items where lower(index_name) in "
    f"({','.join('?' for _ in proof)}) group by index_name", proof
).fetchall())
PY
```

Require the four training indexes in the Splunk inventory, nonzero build knowledge, and **zero proof-index leakage**. The current store read found 2,557 knowledge rows; the labelled run's own reliability receipt loaded 2,431 eligible items after exclusions. Those are different quantities and must not be interchanged.

Before the labelled run, the orchestrator must also make the existing capability probe (this one is inference, not part of the read-only setup):

```bash
curl -fsS -X POST http://127.0.0.1:9099/v1/chat/completions \
  -H "Authorization: Bearer $PIPELINE_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"hunt-reasoning","portal_backend":"omlx-general",
       "messages":[{"role":"user","content":"Answer with one word: yes or no. Is 2+2 equal to 4?"}],
       "temperature":0,"max_tokens":4,"logprobs":true,"top_logprobs":5,
       "reasoning_effort":"none","stream":false}' | python3 -m json.tool
```

Require yes/no `top_logprobs` and the intended served model. Missing logprobs makes the labelled judge row void; it is not a low detection score (`docs/findings/HUNT_CORE_AB_PLAN_20261126.md:78-106`). Finally, prove the Splunk Stage 3/4 acceleration/index-time setup named by `docs/hunt/SPLUNK_REALISM_AND_SETUP.md`; without it only the conditional/degraded bar can be evaluated.

### 2.4 Exact live acceptance commands

Use one immutable SHA, fresh output directories, and sequential runs. Do not export per-arm merge weights. The existing runner supplies the correct index/family/holdout mapping and scores all four families:

```bash
cd /Users/chris/projects/portal-5
export PORTAL_HUNT_JUDGE_URL=http://127.0.0.1:9099
export PORTAL_HUNT_JUDGE_MODEL=hunt-reasoning
export PORTAL_HUNT_JUDGE_KEY_ENV=PIPELINE_API_KEY
export PORTAL_HUNT_JUDGE_BACKEND=omlx-general
export PORTAL_HUNT_EMBEDDING_URL=http://127.0.0.1:9099
export PORTAL_HUNT_EMBEDDING_MODEL=google/embeddinggemma-2
export PORTAL_HUNT_EMBEDDING_KEY_ENV=PIPELINE_API_KEY
unset HUNT_WEIGHTS_FROM PORTAL_HUNT_MERGE_WEIGHTS
coding_task/RUN_HUNT_REDESIGN.sh 2>&1 | tee "coding_task/scratch/core-hunt-$SHA.log"
```

The runner prints its fresh `coding_task/scratch/redesign-live.XXXXXXXX` directory. Preserve that directory and read `<run>/score.log`, each `<family>.run.log`, `progress.json`, `sources.json`, `spine.json`, `notables.jsonl`, and `ledger.jsonl`. In the scoreboard require the §2.2 lines: `C0 modes`, `C0 ceiling`, `C0 recall-of-reachable`, `case recall`, `case evidence pieces`, `promotion effect`, `alerts existed`, generator attribution/marginal, and `cost total`. `COMPLETE`/exit 0 without those lines is not a semantic pass.

Then run the real analyst workflow twice and the progress/results proof once:

```bash
for n in 1 2; do
  uv run python -m tests.qat --scenario s5-security-hunt-workflow \
    --output-dir "results/qat/core-hunt-$SHA-$n"
  cat "results/qat/core-hunt-$SHA-$n/QAT_REPORT.md"
done
uv run python scripts/proofs/owui_hunt_chat.py \
  --index hb_kyoushi_s1 --require-sources
```

If a QAT row leaves its job `RUNNING`, continue polling that same id; its PASS is only a progress-row pass until the durable job is terminal. To exercise the mid-hunt reviewer turn, send this in a second shell while a proof hunt is running, substituting its real id:

```bash
curl -fsS -X POST http://127.0.0.1:8080/api/chat/completions \
  -H "Authorization: Bearer $OWUI_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"security-reviewer","stream":false,"exec_audit":true,
       "messages":[{"role":"user","content":"For hunt hunt-r2-<12hex>, call hunt_status with that exact job id and report its current stage. Do not start another hunt."}]}' \
  | python3 -m json.tool
```

Require the exact id and receipted stage, with no 507, `capacity_fallback`, or unexpected second model in the Pipeline/activity logs for that window.

For every returned `hunt-r2-<12hex>`, read the durable job under `$PORTAL5_HUNT_DIR` (default `$HOME/AI_Output/review/hunts`):

```bash
python3 - "$HOME/AI_Output/review/hunts/hunt-r2-<12hex>.json" <<'PY'
import json, sys
j = json.load(open(sys.argv[1]))
print({k: j.get(k) for k in ("job_id", "index", "status", "stage", "partial_reason",
                             "coverage_complete", "judge_enabled", "run_dir")})
print("wall_s", round(j["finished"] - j["started"], 3))
print("cost", j.get("cost"))
print("stages", list((j.get("progress") or {}).get("stages") or {}))
PY
```

**Expected runtime:** recent labelled families took about **12–30 minutes each**; budget roughly **1–2 hours sequential** for four families, more on an untuned wide corpus. The latest botsv2 scoreboard cost was 26.7 minutes, plus 113.573 s recorded for `relate`. Recent product jobs took 4.1, 4.6, and 6.0 minutes, but conversation polling/reporting adds time; allow **15–45 minutes** for two workflow runs plus the progress/results proof. Elapsed time is reported, not used to hide a semantic failure.

**Held-out rule:** do **not** run Wheeler, CloudObs AWS, botsv1, or any other `PROOF_INDEXES` member now. The plan permits that one-shot proof only after steps 1–3 are green and every constant is frozen; seeing numbers and then changing code voids it (`docs/hunt/ORCACYBER_HUNT_PLAN.md:567-575`).

### 2.5 Failure classification and dispatchable defects

| symptom | classification | required action |
|---|---|---|
| service/index/store unavailable, proof labels in knowledge, wrong model, 507/fallback | setup void | fix setup and rerun; never score against the model |
| no logprobs or undeclared unjudged rows | invalid labelled row | fix seat capability/judge receipt; do not read as detection failure |
| nonterminal job, zero Splunk requests, wrong/missing job id, untruthful reported counts | workflow product failure | fix product tool/job path and rerun QAT |
| all stages complete but low reachable coverage or low recall | semantic product failure | attribute from ceiling/causes/read ledger; do not call it infrastructure merely because the run exited 0 |
| top-50 strict case recall below 3/4, one-evidence cases | semantic case-construction failure | fix S2/S3; notable count and narrative quality do not substitute |
| missing Stage 3/4 Splunk acceleration/index extraction | conditional setup block | complete setup before claiming the 12/24 and 10/14 wide-corpus bars |

Open items:

1. **Wide coverage (S1/S6 + setup):** finish the sanctioned Splunk Stage 3/4 work, prove indexed/accelerated enumeration, then raise reachable coverage by read policy—not by increasing budgets or fitting weights to botsv2.
2. **Case correctness (S2/S3):** build episodes/cases over the entity spine and enforce two-evidence strict artefact credit until ≥3/4 botsv2 scenarios have a qualifying top-50 case; current result is 0/4.
3. **Estate detections (S4):** repair structural alert recognition/entity extraction so botsv2 reports `alerts existed >0` with evidence; current full run reports zero and fails the honesty bar.
4. **Product judge evidence gap:** the latest product job has `judge_enabled=false`; either run a sanctioned product job with `hunt_start(judge=true)` and verify its served judge, or explicitly limit the product claim to unjudged workflow while relying on labelled CLI semantics. Do not imply the latest job proved judgement.
5. **Fresh same-SHA acceptance:** rerun all four training families and two workflows after the fixes; the 2026-11-21/23/27 receipts measure different paths and cannot be stitched into a current pass.

---

## Release decision

Compliance and hunt remain release-blocking. The next acceptance report must be a new, same-revision live receipt set that satisfies every applicable bar above. If the conditional Splunk setup is not complete, the honest hunt result is **blocked on wide-corpus acceptance**, not “works”; if GDPR remains absent, the honest multi-framework result is **blocked on corpus/spec reconciliation**, not a retrieved-GDPR pass.
