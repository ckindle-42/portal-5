#!/usr/bin/env bash
# Integration smoke test for OWUI audio-drop UX after TASK-OWUI-AUDIO-DROP-001.
# Checks all four configuration changes the task makes are live and effective.
#
# Run after: docker compose up + ./scripts/openwebui_init.py
# Expected: all checks PASS, exit 0.

set -uo pipefail  # don't -e; we want to count fails

PASS=0
FAIL=0

check() {
  local name="$1" cmd="$2"
  if eval "$cmd" >/dev/null 2>&1; then
    printf '  ✓ %s\n' "$name"
    ((PASS++))
  else
    printf '  ✗ %s\n' "$name"
    ((FAIL++))
  fi
}

echo "TASK-OWUI-AUDIO-DROP-001 smoke test"
echo "===================================="

echo
echo "1. Environment variables in OWUI container"
check "AIOHTTP_CLIENT_TIMEOUT >= 1800" \
  'docker compose -f deploy/portal-5/docker-compose.yml exec -T open-webui sh -c "[ \${AIOHTTP_CLIENT_TIMEOUT:-0} -ge 1800 ]"'
check "AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA >= 1800" \
  'docker compose -f deploy/portal-5/docker-compose.yml exec -T open-webui sh -c "[ \${AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA:-0} -ge 1800 ]"'
check "WEBUI_SECRET_KEY is set and not the placeholder" \
  'docker compose -f deploy/portal-5/docker-compose.yml exec -T open-webui sh -c "[ -n \"\${WEBUI_SECRET_KEY:-}\" ] && [ \"\${WEBUI_SECRET_KEY:-}\" != \"CHANGEME-AUTOGEN\" ]"'
check "AUDIO_STT_ENGINE is empty (auto-STT disabled per TASK-WORKSPACE-001)" \
  'docker compose -f deploy/portal-5/docker-compose.yml exec -T open-webui sh -c "[ -z \"\${AUDIO_STT_ENGINE:-}\" ]"'

echo
echo "2. MCP tool registration via API"
if [[ -z "${OWUI_API_KEY:-}" ]]; then
  echo "  ⚠ Set OWUI_API_KEY to run API checks; skipping section 2"
else
  check "portal_mlx_transcribe registered" \
    'curl -sf -H "Authorization: Bearer ${OWUI_API_KEY}" http://localhost:8080/api/v1/configs/tool_servers | jq -e ".[] | select(.info.id == \"portal_mlx_transcribe\")"'

  echo
  echo "3. Persona tool binding"
  check "transcriptanalyst persona present in /api/models" \
    'curl -sf -H "Authorization: Bearer ${OWUI_API_KEY}" http://localhost:8080/api/models | jq -e "..|.id? // empty | select(. == \"transcriptanalyst\")"'
fi

echo
echo "4. Service reachability (the chain that needs to work end-to-end)"
check "mlx-transcribe healthy" \
  'curl -sf http://localhost:8924/health | jq -e ".service == \"mlx-transcribe\""'
check "mcp-documents healthy" \
  'curl -sf http://localhost:8919/health 2>/dev/null || docker compose -f deploy/portal-5/docker-compose.yml exec -T mcp-documents curl -sf http://localhost:8919/health'
check "OWUI can reach mlx-transcribe via host.docker.internal" \
  'docker compose -f deploy/portal-5/docker-compose.yml exec -T open-webui sh -c "curl -sf http://host.docker.internal:8924/health"'

echo
echo "Result: $PASS passed, $FAIL failed"
exit $((FAIL > 0 ? 1 : 0))
