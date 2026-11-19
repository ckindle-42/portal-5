#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
: "${PIPELINE_API_KEY:?Set the orchestrator Pipeline credential in the environment}"
export PORTAL_HUNT_JUDGE_URL=http://localhost:9099
export PORTAL_HUNT_JUDGE_MODEL=hunt-reasoning
export PORTAL_HUNT_EMBEDDING_URL=http://localhost:9099
export PORTAL_HUNT_EMBEDDING_MODEL=google/embeddinggemma-2

mkdir -p coding_task/scratch
run_dir=$(mktemp -d "$PWD/coding_task/scratch/neon-live.XXXXXXXX")
echo "Run directory: $run_dir"
hunt=portal.modules.security.core.hunt.notables
data=/Volumes/data01/portal5_hunt
store=$data/knowledge/knowledge_v2_20261116.duckdb
while read -r family index knowledge; do
    uv run python -m "$hunt" --index "$index" --out "$run_dir/$family" --stage all \
        --family "$family" --knowledge-store "$store" --knowledge-families "$knowledge" \
        2>&1 | tee "$run_dir/$family.run.log"
done <<'FAMILIES'
botsv2 botsv2 kyoushi,santos,russell
kyoushi hb_kyoushi_s1 santos,russell
santos hb_ait_santos kyoushi,russell
russell hb_ait_russellmitchell kyoushi,santos
FAMILIES
uv run python -m "$hunt.scoreboard" --out "$run_dir" \
    --keys "botsv2=$data/corpora/botsv2_keys/keys.jsonl" \
    --keys "kyoushi=$data/corpora/hunt_bed/kyoushi_s1_ingest/keys.jsonl" \
    --keys "santos=$data/corpora/ait_lds_v21/santos_ingest/keys.jsonl" \
    --keys "russell=$data/corpora/ait_lds_v21/russellmitchell_ingest/keys.jsonl" \
    | tee "$run_dir/score.log"
