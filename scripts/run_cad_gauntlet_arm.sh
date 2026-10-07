#!/bin/bash
# Run ONE CAD gauntlet v2 arm to completion, unattended, with transcripts and a DONE marker.
#
#   scripts/run_cad_gauntlet_arm.sh LABEL ARM_KEY OVERRIDE_JSON_OR_- REPS [TASK ...]
#
# LABEL         result label (files: tests/benchmarks/results/cad_gauntlet_v2_<LABEL>_<ts>.json)
# ARM_KEY       key used inside the result (e.g. m0)
# OVERRIDE      path to a JSON file merged into the auto-cad workspace config, or "-" for none
# REPS          repetitions per task
# TASK ...      optional task ids to limit the run (default: all 8)
#
# Run arms strictly one at a time (one request in flight). Transcripts go to
# reports/cad/traces/<LABEL>/ (git-ignored); completion is appended to reports/cad/matrix_status.log.
set -u
cd "$(git rev-parse --show-toplevel)" || exit 1
LABEL=$1; KEY=$2; OVR=$3; REPS=$4; shift 4
export CAD_GAUNTLET_TRACE_DIR="reports/cad/traces/$LABEL"
mkdir -p reports/cad/traces
ARGS=(--label "$LABEL" --reps "$REPS" --arm "$KEY=auto-cad")
if [ "$OVR" != "-" ]; then ARGS+=(--override "$KEY=$(cat "$OVR")"); fi
for t in "$@"; do ARGS+=(--task "$t"); done
uv run python tests/benchmarks/bench_cad_gauntlet_v2.py "${ARGS[@]}" >> "reports/cad/matrix_$LABEL.log" 2>&1
echo "DONE $LABEL $(date -u +%FT%TZ)" >> reports/cad/matrix_status.log
