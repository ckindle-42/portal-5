#!/usr/bin/env bash
# smoke_stream.sh — Live streaming gate for Portal 5 pipeline.
#
# Sends a single streaming request to /v1/chat/completions and verifies:
#   1. At least one SSE data chunk arrives (streaming is live, not silent).
#   2. The stream terminates with data: [DONE] (not hung or truncated).
#
# Usage:
#   ./scripts/smoke_stream.sh                        # uses defaults
#   PIPE=http://localhost:9099 ./scripts/smoke_stream.sh
#   PIPELINE_API_KEY=mykey ./scripts/smoke_stream.sh
#
# Exit codes: 0 = PASS, 1 = FAIL
# Used by: ./launch.sh test (streaming gate)

PIPE="${PIPE:-http://localhost:9099}"
API_KEY="${PIPELINE_API_KEY:-portal-pipeline}"
TIMEOUT="${SMOKE_STREAM_TIMEOUT:-30}"

# Load .env if API_KEY is still the default placeholder
if [ "$API_KEY" = "portal-pipeline" ] && [ -f "$(dirname "$0")/../.env" ]; then
    # shellcheck disable=SC1090
    set -a; source "$(dirname "$0")/../.env" 2>/dev/null || true; set +a
    API_KEY="${PIPELINE_API_KEY:-portal-pipeline}"
fi

echo "Streaming smoke gate → $PIPE"

# Stream response to a temp file; capture HTTP code separately
_tmpfile=$(mktemp)
trap 'rm -f "$_tmpfile"' EXIT

# Don't use || echo "000" — curl exits non-zero when the server closes a streaming
# connection, even after writing a valid 200 response.  Capture the code via -w
# and check _tmpfile content for the real error signal.
HTTP_CODE=$(curl -s -o "$_tmpfile" -w "%{http_code}" \
    --max-time "$TIMEOUT" \
    -X POST "$PIPE/v1/chat/completions" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"auto","messages":[{"role":"user","content":"Say PONG in one word."}],"stream":true,"max_tokens":16}' \
    2>/dev/null) || true

# curl writes N bytes to $_tmpfile and "%{http_code}" to stdout; on streaming
# connection-close curl may exit non-zero but HTTP_CODE is still valid.
if [ -z "$HTTP_CODE" ] || [ "$HTTP_CODE" = "000" ]; then
    echo "FAIL — could not connect to pipeline at $PIPE"
    exit 1
fi

if [ "$HTTP_CODE" != "200" ]; then
    echo "FAIL — HTTP $HTTP_CODE (expected 200)"
    exit 1
fi

CHUNK_COUNT=$(grep -c '^data: {' "$_tmpfile" 2>/dev/null || echo 0)
HAS_DONE=$(grep -c '^data: \[DONE\]' "$_tmpfile" 2>/dev/null || echo 0)

if [ "$CHUNK_COUNT" -lt 1 ]; then
    echo "FAIL — no data chunks received (expected ≥1 SSE delta)"
    cat "$_tmpfile"
    exit 1
fi

if [ "$HAS_DONE" -lt 1 ]; then
    echo "FAIL — stream did not terminate with [DONE]"
    cat "$_tmpfile"
    exit 1
fi

echo "PASS — $CHUNK_COUNT SSE chunk(s), [DONE] received"
exit 0
