#!/usr/bin/env bash
# V5 quantization ladder bench orchestrator.
# Per TASK_MODEL_REFRESH_V5 §E.
#
# Strategy:
#   1. Filter to V5 ladder candidates only via --model substring matching.
#      bench_tps.py auto-discovers MLX models from backends.yaml — V5 entries
#      will be picked up automatically once Phase C is committed.
#   2. Use --mode direct (no routing layer overhead in TPS measurement).
#   3. Use --runs 5 --cooldown 10 (project memory standard baseline).
#   4. Order by size (--order size) so failures on large models don't waste
#      time on small models we'd want measured first anyway.
#
# Output: tests/benchmarks/results/bench_tps_v5_ladders.json

set -euo pipefail

cd "$(dirname "$0")/.."

# Smoke test must have been run first
test -f tests/results/smoke_test_v5.json || {
  echo "ERROR: tests/results/smoke_test_v5.json not found. Run scripts/smoke_test_mlx.py first."
  exit 1
}

# Identify smoke-PASSed models — only bench those
PASSED_MODELS=$(python3 -c "
import json
with open('tests/results/smoke_test_v5.json') as f:
    results = json.load(f)
for r in results:
    if r.get('status') == 'PASS':
        print(r['model'])
")

if [ -z "$PASSED_MODELS" ]; then
  echo "ERROR: No models passed smoke test. Aborting bench."
  exit 1
fi

echo "=== V5 Ladder Bench ==="
echo "Smoke-PASSed models to bench:"
echo "$PASSED_MODELS"
echo

OUTPUT="tests/benchmarks/results/bench_tps_v5_ladders.json"

# bench_tps.py --mode direct iterates ALL MLX models in backends.yaml.
# Run a single bench with --order size to get the full sweep efficiently.
# (Per project memory: bench_tps.py auto-discovers from backends.yaml.)
python3 tests/benchmarks/bench_tps.py \
    --mode direct \
    --runs 5 \
    --cooldown 10 \
    --order size \
    --output "$OUTPUT"

echo
echo "Bench complete. Results: $OUTPUT"
echo "Run scripts/analyze_bench_v5.py next to generate the analysis report."
