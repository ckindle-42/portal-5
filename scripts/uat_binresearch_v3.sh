#!/usr/bin/env bash
# uat_binresearch_v3.sh — Live UAT for the binary research harness (V3).
#
# Exercises the real flow end-to-end against the live stack (not mocks):
#   1. RE toolchain MCP (:8930) health + re_tools() toolchain probe.
#   2. `brh init` scaffolds the static project structure under a throwaway
#      BINRESEARCH_PROJECTS_ROOT.
#   3. The sample_project's two-oracle smoke test (artifacts/ + verifiers/ +
#      .expected) is copied in; `brh verify` reports ALL FAIL before evidence
#      exists, then ALL PASS once 03_model.md carries the right hash/token.
#   4. A real `bash` tool call (target=container) round-trips through the
#      harness -> RE toolchain MCP -> DinD -> portal5-binresearch container
#      and back (sha256sum + strings against the mounted project).
#
# Requires: stack up, `./launch.sh build-binresearch` done, mcp-binresearch
# running (`docker compose -f deploy/portal-5/docker-compose.yml up -d dind
# mcp-binresearch`).
#
# Usage: ./scripts/uat_binresearch_v3.sh
# Exit codes: 0 = PASS, 1 = FAIL

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MCP_URL="${BINRESEARCH_MCP_URL:-http://127.0.0.1:8930}"
PROJECTS_ROOT="${HOME}/binresearch"
PROJECT_NAME="uat_smoke_$$"
SAMPLE_DIR="$ROOT_DIR/portal/modules/binary_research/examples/sample_project"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

cleanup() { rm -rf "${PROJECTS_ROOT:?}/${PROJECT_NAME}"; }
trap cleanup EXIT

echo "== 1. RE toolchain MCP health =="
health=$(curl -sf "$MCP_URL/health") || fail "MCP /health unreachable at $MCP_URL"
echo "$health" | grep -q '"status":"ok"' || fail "MCP /health did not report ok: $health"
pass "MCP health ok"

echo "== 2. re_tools() toolchain probe =="
tools_json=$(curl -sf -X POST "$MCP_URL/tools/re_tools" -H 'Content-Type: application/json' -d '{"arguments":{}}') \
    || fail "re_tools call failed"
missing=$(echo "$tools_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('missing', []))")
[ "$missing" = "[]" ] || fail "declared RE tools missing: $missing"
pass "all declared RE tools present"

echo "== 3. scaffold a fresh project =="
export BINRESEARCH_PROJECTS_ROOT="$PROJECTS_ROOT"
cd "$ROOT_DIR"
uv run python3 -m portal.modules.binary_research.harness init --project "$PROJECT_NAME" >/dev/null \
    || fail "brh init failed"
project_dir="$PROJECTS_ROOT/$PROJECT_NAME"
for f in .binresearch 00_inventory.md 01_hypotheses.md 03_model.md 04_checks.md 05_report.md trace.jsonl; do
    [ -e "$project_dir/$f" ] || fail "scaffold missing $f"
done
for d in artifacts verifiers 02_evidence; do
    [ -d "$project_dir/$d" ] || fail "scaffold missing $d/"
done
pass "static structure scaffolded at $project_dir"

echo "== 4. copy sample_project two-oracle smoke test =="
cp "$SAMPLE_DIR"/artifacts/* "$project_dir/artifacts/" || fail "copy artifacts failed"
cp "$SAMPLE_DIR"/verifiers/* "$project_dir/verifiers/" || fail "copy verifiers failed"
cp "$SAMPLE_DIR/.expected" "$project_dir/.expected" || fail "copy .expected failed"
pass "sample project copied in"

echo "== 5. verify reports ALL FAIL before evidence exists =="
if uv run python3 -m portal.modules.binary_research.harness verify --project "$PROJECT_NAME" >/tmp/brh_verify_pre.$$ 2>&1; then
    cat /tmp/brh_verify_pre.$$; fail "expected non-zero exit (ALL FAIL) before 03_model.md is filled"
fi
grep -q "ALL FAIL" /tmp/brh_verify_pre.$$ || { cat /tmp/brh_verify_pre.$$; fail "expected ALL FAIL verdict"; }
rm -f /tmp/brh_verify_pre.$$
pass "verify correctly reports ALL FAIL pre-evidence"

echo "== 6. real bash tool call through the harness -> MCP -> DinD -> RE container =="
result=$(uv run python3 -c "
from pathlib import Path
from portal.modules.binary_research.harness.policy import Policy
from portal.modules.binary_research.harness.re_client import REClient
from portal.modules.binary_research.harness.tools import run_tool

project_dir = Path('$project_dir')
policy = Policy(job_root=project_dir)
client = REClient(base_url='$MCP_URL')
print(run_tool(policy, 'bash', {'command': 'sha256sum artifacts/payload.bin'}, re_client=client, project='$PROJECT_NAME'))
")
echo "$result" | grep -q "20e92099aa968c101372515ee2d0ed11f428aa7191944c2bd6ce4051f16827f2" \
    || fail "container round-trip did not produce the expected sha256: $result"
pass "real container bash round-trip produced the correct sha256"

echo "== 7. write evidence via the harness write tool, then verify ALL PASS =="
# Read the expected SHA256/token from the sample project's own .expected fixture
# (not hardcoded here) and write them into 03_model.md the way the analysis loop
# would, to prove the verifiers' own oracle against the harness write tool.
uv run python3 -c "
from pathlib import Path
from portal.modules.binary_research.harness.policy import Policy
from portal.modules.binary_research.harness.tools import run_tool

project_dir = Path('$project_dir')
expected = dict(
    line.split('=', 1) for line in (project_dir / '.expected').read_text().splitlines() if '=' in line
)
policy = Policy(job_root=project_dir)
content = (
    '# 03_model\n\n'
    f\"- SHA256: {expected['SHA256']}\n\"
    f\"- Embedded token: {expected['TOKEN']}\n\"
)
print(run_tool(policy, 'write', {'path': '03_model.md', 'content': content}))
" || fail "harness write tool failed"

if ! uv run python3 -m portal.modules.binary_research.harness verify --project "$PROJECT_NAME" >/tmp/brh_verify_post.$$ 2>&1; then
    cat /tmp/brh_verify_post.$$; fail "expected zero exit (ALL PASS) after evidence written"
fi
grep -q "ALL PASS" /tmp/brh_verify_post.$$ || { cat /tmp/brh_verify_post.$$; fail "expected ALL PASS verdict"; }
rm -f /tmp/brh_verify_post.$$
pass "verify correctly reports ALL PASS post-evidence"

echo
echo "UAT PASSED: binary research harness V3 verified live end-to-end."
