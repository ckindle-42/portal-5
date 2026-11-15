# Hunt R2 slice 2 — knowledge store handoff (lane/hunt-knowledge-s2)

Code on this branch: the DuckDB knowledge store with structural leave-one-family-out
(`knowledge.py`), the similar-to-known generator and similarity-prioritised judge
(`similar.py`, `run.py`), the manifest build + audit command (`manifest.py`), and an
injectable source on the real run path (`__main__.main(argv, *, search=None)`).
Everything below is **unproven against the live system** — the worker never touches the
lab, the Pipeline or the keys. The orchestrator runs these commands in order.

Prerequisites:
- Live Pipeline at a build that serves `POST /v1/embeddings` (main `64b2ba637` or later)
  and the `security-reviewer` / `hunt-reasoning` workspaces. This branch's code calls the
  live route; the route itself is not on this branch.
- Lab Splunk reachable with `LAB_SPLUNK_URL / LAB_SPLUNK_USER / LAB_SPLUNK_PASSWORD`.
- Out-of-band keys and gather trees for the build families (worker never read them):
  kyoushi keys live under `/Volumes/data01/portal5_hunt/corpora/hunt_bed` (the
  `keys.jsonl` written by `scripts/hunt_bed/keys_kyoushi.py`, join rate 100%);
  santos / russellmitchell under `/Volumes/data01/portal5_hunt/corpora/ait_lds_v21`
  (same `labels/` mirror format — if their `keys.jsonl` was never built, run
  `keys_kyoushi.py --labels <scenario labels dir> --ingest <ingest out dir>` first).
  Set the six `*_KEYS` / `*_GATHER` variables below to the real paths.
- botsv2 scenario key (for choosing a non-attack day and for scoring):
  `/Volumes/data01/portal5_hunt/corpora/hunt_bed/bots_keys/bots_key.jsonl`.

## ORCHESTRATOR RUNS

Environment for every command (from the checkout that holds this branch):

```bash
export LAB_SPLUNK_URL="$(grep -E '^LAB_SPLUNK_URL=' .env | cut -d= -f2- | tr -d '\"')"
export LAB_SPLUNK_USER="$(grep -E '^LAB_SPLUNK_USER=' .env | cut -d= -f2- | tr -d '\"')"
export LAB_SPLUNK_PASSWORD="$(grep -E '^LAB_SPLUNK_PASSWORD=' .env | cut -d= -f2- | tr -d '\"')"
export LAB_SPLUNK_INDEX="$(grep -E '^LAB_SPLUNK_INDEX=' .env | cut -d= -f2- | tr -d '\"')"
export PIPELINE_API_KEY="$(grep -E '^PIPELINE_API_KEY=' .env | cut -d= -f2- | tr -d '\"')"
export PORTAL_HUNT_JUDGE_URL=http://127.0.0.1:9099/v1/chat/completions
export PORTAL_HUNT_JUDGE_MODEL=hunt-reasoning
export PORTAL_HUNT_EMBEDDING_URL=http://127.0.0.1:9099
export PORTAL_HUNT_EMBEDDING_MODEL=google/embeddinggemma-2
# If the live Pipeline rejects that model, its 400 names the accepted ones:
#   curl -s -X POST http://127.0.0.1:9099/v1/embeddings \
#     -H "Authorization: Bearer $PIPELINE_API_KEY" -H 'Content-Type: application/json' \
#     -d '{"input":["probe"],"model":"probe"}'
# Export the accepted name instead. The store records the model; a run with a
# different model fails loudly rather than mixing vector spaces.
KYOUSHI_KEYS=...; KYOUSHI_GATHER=...     # keys.jsonl + gather/ root, hb_kyoushi_s1
SANTOS_KEYS=...; SANTOS_GATHER=...       # hb_ait_santos
RUSSELL_KEYS=...; RUSSELL_GATHER=...     # hb_ait_russellmitchell
OUT=results/hunt/knowledge_s2
```

### 1. Cards + behaviours for every build family (the keying the manifest reuses)

The manifest normalises labelled lines with the behaviours stage's *recorded* keying
(`role_overrides` on each card). Run both stages once per family; reruns are cached.

```bash
for pair in "hb_kyoushi_s1 kyoushi" "hb_ait_santos santos" "hb_ait_russellmitchell russell"; do
  set -- $pair
  uv run python -m portal.modules.security.core.hunt.notables --index "$1" --out "$OUT/$2" --stage cards
  uv run python -m portal.modules.security.core.hunt.notables --index "$1" --out "$OUT/$2" --stage behaviours
done
```

Expected: per-source card lines and `behaviours: events_read=… kept=…` per family;
receipts in `$OUT/<family>/sources.json`, `behaviours.duckdb`, `progress.json`.
Bad: a family whose cards show `understood=false` for the labelled sources — the
manifest will report `no_card`/`unparsed` counts and may produce no items (step 2 fails).

### 2. Build + audit the store (one command)

```bash
uv run python -m portal.modules.security.core.hunt.notables.manifest build \
  --source "name=kyoushi,index=hb_kyoushi_s1,kind=keys,keys=$KYOUSHI_KEYS,gather=$KYOUSHI_GATHER,cards=$OUT/kyoushi" \
  --source "name=santos,index=hb_ait_santos,kind=keys,keys=$SANTOS_KEYS,gather=$SANTOS_GATHER,cards=$OUT/santos" \
  --source "name=russell,index=hb_ait_russellmitchell,kind=keys,keys=$RUSSELL_KEYS,gather=$RUSSELL_GATHER,cards=$OUT/russell" \
  --manifest "$OUT/manifest.jsonl" --store "$OUT/knowledge.duckdb"
```

What it does: reads each family's out-of-band keys, normalises every labelled line and
a deterministic stride sample of unlabelled lines from the keyed gather files with the
recorded card keying, writes the manifest, then **audits every item** by running its
provenance query (`index + host + source + quoted role-value terms`) against the lab.

Expected stdout: one line per family/label —
`  kyoushi known_bad <step>: items=N located=N rows=M` — then
`audit: items=… located_events=…`, then the build receipt JSON (`items`,
`unique_statements`, `families`, `embedding_model`, `dimensions`, `manifest_sha256`).
Receipts: `$OUT/manifest.jsonl`, `$OUT/knowledge.duckdb`, `$OUT/knowledge.receipt.json`
(includes `family_details` with lines/labelled/good_sampled/no_card/unparsed counts and
the full audit).
Bad (exit 1, loud): `… knowledge items locate no events: <family>/<label> … query=…`
(any item whose query returns nothing — e.g. host spelling differs between gather and
index); `family … produced no knowledge items` (cards/keying missing); `proof index …`
(wheeler / cloudobs_aws / botsv1 and their `hb_` variants are rejected before any read).

### 3. Kyoushi run with santos+russell knowledge

```bash
uv run python -m portal.modules.security.core.hunt.notables \
  --index hb_kyoushi_s1 --out "$OUT/kyoushi" --stage notables \
  --generators alerts,peer_rare,deviation,similar_to_known \
  --family kyoushi --knowledge-store "$OUT/knowledge.duckdb" \
  --knowledge-families santos,russell
uv run python -m portal.modules.security.core.hunt.notables \
  --index hb_kyoushi_s1 --out "$OUT/kyoushi" --stage judge
```

Expected: `similar_to_known: existed=… kept=… reliability_auc=… score=…` with
`excluded_family=kyoushi`, `loaded_families=[russell, santos]` in the notables receipt;
judge receipt `ranking.priority_generator=similar_to_known`, `prioritized>0`.
(`hunt-reasoning` is the default because the former `security-reviewer` model was Ollama-only
and returned HTTP 400 from the `omlx-general` pin after its oMLX alias was removed.)
Receipts: `$OUT/kyoushi/notables.jsonl` (similar notables carry `nearest_known` with
labels + provenance queries and `generator_reliability`), `progress.json`,
`cache/judge.json`. Wall time: `seconds` per stage in `progress.json`.
Bad: `leave-one-family-out violation` or `no knowledge items remain` (the structural
guard fired); `store model … differs from Pipeline model` (env mismatch).
Score per-step recall of the similar notables (top 50/100) with the slice-1
`recall_steps` scorer against the kyoushi keys — evidence overlap per labelled step.

### 4. Santos run with kyoushi+russell knowledge

```bash
uv run python -m portal.modules.security.core.hunt.notables \
  --index hb_ait_santos --out "$OUT/santos" --stage notables \
  --generators alerts,peer_rare,deviation,similar_to_known \
  --family santos --knowledge-store "$OUT/knowledge.duckdb" \
  --knowledge-families kyoushi,russell
uv run python -m portal.modules.security.core.hunt.notables \
  --index hb_ait_santos --out "$OUT/santos" --stage judge
```

Expected / receipts / bad: as step 3 with `excluded_family=santos`,
`loaded_families=[kyoushi, russell]`, receipts under `$OUT/santos/`. Score per-step
recall against the santos keys the same way.

### 5. Cross-lineage check: labelled_corpus known-bad against botsv2

5a. Audit how `labelled_corpus` carries its labels (before any score). The bed registry
says labels ride in `source`, `host`, `p5_item`, `evidence_origin`; the audit shows
which field actually carries values, their event counts, and that each value locates
real events:

```bash
uv run python -m portal.modules.security.core.hunt.notables.manifest audit-labels \
  --index labelled_corpus --fields source,p5_item,evidence_origin
```

Expected: per field `carriage=indexed|search-time distinct=N located=K/K` plus a JSON
report with the top values and counts. Pick the field whose values are technique /
attack names (`LABEL_FIELD` below). Bad (exit 1): `label values locate no events`.

5b. Cards + behaviours for the two new indexes (bounded samples; botsv2 is 226M events
— the stages read samples and indexed facts only):

```bash
for pair in "labelled_corpus labelled_corpus" "botsv2 botsv2"; do
  set -- $pair
  uv run python -m portal.modules.security.core.hunt.notables --index "$1" --out "$OUT/$2" --stage cards
  uv run python -m portal.modules.security.core.hunt.notables --index "$1" --out "$OUT/$2" --stage behaviours
done
```

5c. Build the cross-lineage store: Windows/cloud known-bad from `labelled_corpus`
(technique basis), known-good from santos' unlabelled lines only, and a botsv2
family anchor from a **non-attack day** (choose `BOTS_GOOD_START:BOTS_GOOD_END` from
the bots key — the anchor exists so leave-one-family-out can exclude family `bots`;
it is never scored):

```bash
uv run python -m portal.modules.security.core.hunt.notables.manifest build \
  --source "name=attack_data,index=labelled_corpus,kind=labelled,label_field=$LABEL_FIELD,cards=$OUT/labelled_corpus" \
  --source "name=santos,index=hb_ait_santos,kind=keys,part=good,keys=$SANTOS_KEYS,gather=$SANTOS_GATHER,cards=$OUT/santos" \
  --source "name=bots,index=botsv2,kind=window,good_window=$BOTS_GOOD_START:$BOTS_GOOD_END,cards=$OUT/botsv2" \
  --manifest "$OUT/cross_manifest.jsonl" --store "$OUT/cross.duckdb"
```

Expected: audit lines for `attack_data known_bad <technique>`, `santos known_good
unlabelled`, `bots known_good non_attack_day`, all located; receipts
`$OUT/cross_manifest.jsonl`, `$OUT/cross.duckdb`, `$OUT/cross.receipt.json`.

5d. Score botsv2 behaviours against that store:

```bash
uv run python -m portal.modules.security.core.hunt.notables \
  --index botsv2 --out "$OUT/botsv2" --stage notables \
  --generators similar_to_known \
  --family bots --knowledge-store "$OUT/cross.duckdb"
```

Expected: `excluded_family=bots`, `loaded_families=[attack_data, santos]`,
`reliability.method=leave_one_family_out`; notables whose `nearest_known` include
`attack_data` items (Windows/cloud techniques, with their provenance queries) are the
cross-lineage signal. Receipts: `$OUT/botsv2/notables.jsonl`, `progress.json`.
Grade against the botsv2 scenario/artefact key (`score_bots.py` approach). **An honest
negative — no attack_data match ranks near the labelled scenarios — is a complete
result**; report it as such. Same-lineage santos→kyoushi recall is not this proof.

## UNPROVEN

- Everything above: no command in this block was run against the lab, the Pipeline or
  the keys by the worker. Store build, audit locate-rates, embeddings throughput,
  per-step recall, judge separation and wall time are all unmeasured.
- The exact on-disk paths of the santos / russellmitchell `keys.jsonl` and gather roots
  (and whether those keys were ever built) — the worker was not permitted to read the
  answer-key tree; the `*_KEYS` / `*_GATHER` variables must be resolved by the
  orchestrator. The keys format is taken from `scripts/hunt_bed/keys_kyoushi.py`.
- The accepted embedding model name on the live Pipeline (`google/embeddinggemma-2`
  comes from main's `config/backends.yaml platform_embedder`; confirm via the 400).
- That gather host spellings match Splunk `host` values for every keyed family — the
  audit is designed to fail loudly where they do not; expect to fix specs, not code.
- That the behaviours stage's recorded keying exists for every labelled source
  (step 1 must run first; `no_card`/`unparsed` counts in `family_details` show gaps).
- Which `labelled_corpus` field carries technique labels, and whether it is indexed —
  step 5a answers this live; `LABEL_FIELD` is deliberately not hardcoded.
- The botsv2 non-attack-day window — must come from the out-of-band bots key.
- Cross-lineage transfer itself (Windows/cloud known-bad → botsv2): the one positive
  measurement so far (AUC 0.92) is same-lineage santos→kyoushi with sampled negatives.
- Product path (review MCP / Open WebUI) still runs R1 code from main; this slice is
  the module entry point only.
