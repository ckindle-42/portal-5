#!/usr/bin/env bash
#
# Portal 5 — One-Shot Diarized Transcription + Persona-Reviewed Word Doc
#
# Drop an audio file (mp3, m4a, wav, ogg, flac) anywhere in the project,
# run this script with the path, and get back a polished .docx that the
# transcriptanalyst persona drafted, rendered, and reviewed end-to-end.
#
# What this script does (no Open WebUI chat involvement except via API):
#
#   1. POST audio to mlx-transcribe (:8924) → diarized JSON + Markdown
#   2. POST transcript to OWUI (/api/chat/completions) targeting the
#      transcriptanalyst persona → persona drafts polished content +
#      calls create_word_document tool to render the .docx
#   3. POST the rendered .docx path back to the persona for review →
#      persona reads its own output, reports any issues, confirms quality
#   4. Copy final .docx and transcript artifacts next to the source audio
#
# The persona is in the loop for both DRAFT and REVIEW, exactly like the
# OWUI chat flow would do if the chat-drop UX were working. This script
# is the manual bridge until TASK_OWUI_AUDIO_DROP_001 is executed.
#
# Prerequisites (one-time):
#   - TASK-WORKSPACE-001 + TASK-TRANSCRIBE-001 merged
#   - HF_TOKEN in .env, pyannote licenses accepted on HuggingFace
#   - ./launch.sh start-transcribe (mlx-transcribe on :8924)
#   - mcp-documents container running (docx render via persona's tool call)
#   - Open WebUI API key generated and exported as OWUI_API_KEY
#     (OWUI → Settings → Account → API Keys → Create New)
#   - jq installed: brew install jq
#
# Usage:
#   ./scripts/transcribe_and_complete.sh meeting.m4a
#   ./scripts/transcribe_and_complete.sh meeting.m4a --speakers 2
#   ./scripts/transcribe_and_complete.sh meeting.m4a --speakers 3 --title "Q3 Planning"
#
# Environment variables:
#   OWUI_API_KEY          (required) Open WebUI API key (Bearer token)
#   OWUI_URL              (default http://localhost:8080) Open WebUI base URL
#   TRANSCRIBE_URL        (default http://localhost:8924) mlx-transcribe URL
#   PERSONA_MODEL         (default transcriptanalyst) persona slug to invoke
#   AI_OUTPUT_DIR         (default ~/AI_Output) workspace root from TASK-WORKSPACE-001
#
# Exit codes:
#   0 success
#   1 service unreachable
#   2 transcription error
#   3 persona/chat error
#   4 docx render or review failed
#   5 argument or environment error

set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────

OWUI_URL="${OWUI_URL:-http://localhost:8080}"
TRANSCRIBE_URL="${TRANSCRIBE_URL:-http://localhost:8924}"
PERSONA_MODEL="${PERSONA_MODEL:-transcriptanalyst}"
AI_OUTPUT_DIR="${AI_OUTPUT_DIR:-${HOME}/AI_Output}"

# ─── Helpers ─────────────────────────────────────────────────────────────────

err() { printf '\033[31mERROR:\033[0m %s\n' "$*" >&2; }
info() { printf '\033[36m▸\033[0m %s\n' "$*" >&2; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*" >&2; }
section() { printf '\n\033[1m── %s ──\033[0m\n' "$*" >&2; }

require() {
  command -v "$1" >/dev/null 2>&1 || { err "Required command not found: $1"; exit 5; }
}

usage() {
  sed -n '3,40p' "$0" | sed 's/^# \{0,1\}//' >&2
  exit "${1:-0}"
}

# ─── Argument parsing ────────────────────────────────────────────────────────

AUDIO_FILE=""
SPEAKERS=""
LANGUAGE=""
TITLE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage 0 ;;
    --speakers) SPEAKERS="$2"; shift 2 ;;
    --language) LANGUAGE="$2"; shift 2 ;;
    --title)    TITLE="$2"; shift 2 ;;
    -*)         err "Unknown flag: $1"; usage 5 ;;
    *)          AUDIO_FILE="$1"; shift ;;
  esac
done

[[ -z "$AUDIO_FILE" ]] && { err "Missing audio file path"; usage 5; }

# Resolve to absolute path; expand ~
AUDIO_FILE="$(cd "$(dirname "$AUDIO_FILE")" && pwd)/$(basename "$AUDIO_FILE")"

[[ -f "$AUDIO_FILE" ]] || { err "Not a file: $AUDIO_FILE"; exit 5; }

case "$(echo "$AUDIO_FILE" | tr '[:upper:]' '[:lower:]')" in
  *.mp3|*.m4a|*.wav|*.ogg|*.flac|*.webm|*.mp4|*.aac) ;;
  *) err "Unsupported audio extension: $AUDIO_FILE"; exit 5 ;;
esac

[[ -z "${OWUI_API_KEY:-}" ]] && {
  err "OWUI_API_KEY not set. Generate one in OWUI → Settings → Account → API Keys."
  err "Then: export OWUI_API_KEY=sk-..."
  exit 5
}

[[ -z "$TITLE" ]] && TITLE="Transcript: $(basename "${AUDIO_FILE%.*}")"

require curl
require jq

AUDIO_BASENAME="$(basename "$AUDIO_FILE")"
AUDIO_DIR="$(dirname "$AUDIO_FILE")"
AUDIO_SIZE_MB="$(du -m "$AUDIO_FILE" | cut -f1)"

# ─── Stage 0 — Service preflight ─────────────────────────────────────────────

section "Preflight"

info "mlx-transcribe at $TRANSCRIBE_URL"
HEALTH="$(curl -sf --max-time 5 "$TRANSCRIBE_URL/health")" || {
  err "mlx-transcribe unreachable. Run: ./launch.sh start-transcribe"
  exit 1
}
echo "$HEALTH" | jq -r '"  Whisper:      \(.whisper_model)\n  Diarization:  \(.diarization_model)\n  Loaded:       \(.diarization_loaded)"' >&2

info "Open WebUI at $OWUI_URL"
curl -sf --max-time 5 -H "Authorization: Bearer $OWUI_API_KEY" \
  "$OWUI_URL/api/models" >/dev/null || {
  err "Cannot reach OWUI API at $OWUI_URL/api/models. Check OWUI_URL and OWUI_API_KEY."
  exit 1
}

# Verify the persona/model exists in OWUI's model list
MODELS_JSON="$(curl -sf -H "Authorization: Bearer $OWUI_API_KEY" "$OWUI_URL/api/models")"
if ! echo "$MODELS_JSON" | jq -e --arg m "$PERSONA_MODEL" '.data[] | select(.id == $m)' >/dev/null 2>&1; then
  # Some OWUI versions return models at .models or as a flat array
  if ! echo "$MODELS_JSON" | jq -e --arg m "$PERSONA_MODEL" '..|.id? // empty | select(. == $m)' >/dev/null 2>&1; then
    err "Persona '$PERSONA_MODEL' not found in OWUI's model list."
    err "Check that openwebui_init.py registered it, or pass --persona <slug> override."
    exit 5
  fi
fi
ok "Persona '$PERSONA_MODEL' is registered"

# ─── Stage 1 — Transcribe + Diarize ──────────────────────────────────────────

section "Stage 1 — Transcription + Diarization"

info "File:     $AUDIO_BASENAME (${AUDIO_SIZE_MB} MB)"
info "Speakers: ${SPEAKERS:-auto-detect}"
info "Language: ${LANGUAGE:-auto-detect}"

if [[ "$AUDIO_SIZE_MB" -gt 100 && -z "$SPEAKERS" ]]; then
  info "⚠️  Large file with no --speakers hint; auto-detect may split speakers"
fi

CURL_FORM=(-F "file=@$AUDIO_FILE" -F "language=${LANGUAGE:-auto}")
[[ -n "$SPEAKERS" ]] && CURL_FORM+=(-F "num_speakers=$SPEAKERS")

T0=$(date +%s)
TRANSCRIBE_RESP="$(mktemp -t transcribe-resp-XXXXXX.json)"
trap 'rm -f "$TRANSCRIBE_RESP" "${REVIEW_PROMPT_FILE:-}" "${DRAFT_PROMPT_FILE:-}"' EXIT

# Long timeout — 1 hour wall clock, plenty for any practical file
HTTP_CODE="$(curl -sf -w "%{http_code}" --max-time 3600 \
  -X POST "$TRANSCRIBE_URL/v1/audio/transcribe-with-speakers" \
  "${CURL_FORM[@]}" \
  -o "$TRANSCRIBE_RESP" \
  )" || {
    err "Transcription request failed (HTTP $HTTP_CODE)"
    [[ -s "$TRANSCRIBE_RESP" ]] && head -c 600 "$TRANSCRIBE_RESP" >&2
    exit 2
}

T1=$(date +%s)
ELAPSED=$((T1 - T0))

if jq -e '.error' "$TRANSCRIBE_RESP" >/dev/null 2>&1; then
  err "Service reported: $(jq -r '.error' "$TRANSCRIBE_RESP")"
  exit 2
fi

SPEAKER_COUNT=$(jq -r '.speaker_count' "$TRANSCRIBE_RESP")
DURATION=$(jq -r '.duration' "$TRANSCRIBE_RESP")
LANG=$(jq -r '.language' "$TRANSCRIBE_RESP")
MD_PATH=$(jq -r '.md_path' "$TRANSCRIBE_RESP")
JSON_PATH=$(jq -r '.json_path' "$TRANSCRIBE_RESP")
MARKDOWN=$(jq -r '.markdown' "$TRANSCRIBE_RESP")

ok "Transcription complete in ${ELAPSED}s"
printf '  Speakers:  %s\n' "$SPEAKER_COUNT" >&2
printf '  Duration:  %ss (%.1fm)\n' "$DURATION" "$(echo "$DURATION / 60" | bc -l)" >&2
printf '  Language:  %s\n' "$LANG" >&2
printf '  Markdown:  %s\n' "$MD_PATH" >&2
printf '  JSON:      %s\n' "$JSON_PATH" >&2

# ─── Stage 2 — Persona drafts + calls create_word_document tool ──────────────

section "Stage 2 — Persona Draft + Word Document Render"

info "Sending transcript to persona '$PERSONA_MODEL' (DRAFT phase)"
info "  Persona will format content and call create_word_document tool"

# The user message tells the persona what we want and gives it the transcript.
# Phrasing matters: the persona's system prompt is wired to call
# create_word_document when the user asks for a docx, so we must ask explicitly.

DRAFT_PROMPT_FILE="$(mktemp -t draft-prompt-XXXXXX.json)"

DRAFT_USER_MESSAGE=$(cat <<EOF
I have a diarized transcript that needs to become a polished Word document.

**Source:** $AUDIO_BASENAME (${SPEAKER_COUNT} speakers, $(printf '%.1f' "$(echo "$DURATION / 60" | bc -l)") minutes)

**Task:**
1. Review the transcript below for quality
2. Produce a polished version: title block, clean speaker turns with timestamps, plus a brief executive summary at the top with key topics and any action items you identify
3. Call the **create_word_document** tool with title="$TITLE" and the polished content as markdown — render it as a proper .docx file
4. Report back the docx path the tool returns

Do not summarize away content; preserve all speaker turns. Add structure and analysis on top of the raw transcript.

**Diarized transcript:**

$MARKDOWN
EOF
)

# Build the chat payload with files=[] (no RAG), stream=false for synchronous
jq -n \
  --arg model "$PERSONA_MODEL" \
  --arg user_msg "$DRAFT_USER_MESSAGE" \
  '{
    model: $model,
    messages: [
      { role: "user", content: $user_msg }
    ],
    stream: false
  }' > "$DRAFT_PROMPT_FILE"

DRAFT_RESP="$(mktemp -t draft-resp-XXXXXX.json)"
trap 'rm -f "$TRANSCRIBE_RESP" "$DRAFT_PROMPT_FILE" "$DRAFT_RESP" "${REVIEW_PROMPT_FILE:-}" "${REVIEW_RESP:-}"' EXIT

T2=$(date +%s)
HTTP_CODE="$(curl -sf -w "%{http_code}" --max-time 1800 \
  -X POST "$OWUI_URL/api/chat/completions" \
  -H "Authorization: Bearer $OWUI_API_KEY" \
  -H "Content-Type: application/json" \
  -d @"$DRAFT_PROMPT_FILE" \
  -o "$DRAFT_RESP" \
  )" || {
    err "OWUI chat completion failed (HTTP $HTTP_CODE)"
    [[ -s "$DRAFT_RESP" ]] && head -c 600 "$DRAFT_RESP" >&2
    exit 3
}
T3=$(date +%s)

DRAFT_CONTENT=$(jq -r '.choices[0].message.content // empty' "$DRAFT_RESP")
[[ -z "$DRAFT_CONTENT" ]] && {
  err "Persona returned empty content. Full response:"
  jq . "$DRAFT_RESP" >&2
  exit 3
}

ok "Persona DRAFT phase complete in $((T3 - T2))s"

# Extract the docx path from the persona's response.
# The persona is instructed to "report back the docx path".
# create_word_document returns a server path like /app/data/generated/foo_<uid>.docx
# which on the host maps to ${AI_OUTPUT_DIR}/foo_<uid>.docx (compose bind mount).

# Strategy: scan for *.docx in the response, take the last one (most likely the
# final output rather than an intermediate mention), strip server prefix.
DOCX_NAME=$(echo "$DRAFT_CONTENT" \
  | grep -oE '[A-Za-z0-9_.-]+_[a-f0-9]+\.docx' \
  | tail -n1 || true)

# Fallback: scan the whole response for any .docx path
if [[ -z "$DOCX_NAME" ]]; then
  DOCX_NAME=$(echo "$DRAFT_CONTENT" \
    | grep -oE '[/A-Za-z0-9_.-]+\.docx' \
    | tail -n1 \
    | xargs basename 2>/dev/null || true)
fi

if [[ -z "$DOCX_NAME" ]]; then
  err "Persona response did not include a .docx filename."
  err "The persona may not have called create_word_document correctly."
  err "First 800 chars of persona response:"
  echo "${DRAFT_CONTENT:0:800}" >&2
  exit 4
fi

DOCX_HOST_PATH="${AI_OUTPUT_DIR}/${DOCX_NAME}"

if [[ ! -f "$DOCX_HOST_PATH" ]]; then
  # Some OWUI/MCP versions place the file under generated/documents/
  ALT_PATH="${AI_OUTPUT_DIR}/generated/documents/${DOCX_NAME}"
  if [[ -f "$ALT_PATH" ]]; then
    DOCX_HOST_PATH="$ALT_PATH"
  else
    err "Persona reported docx '$DOCX_NAME' but file not found at:"
    err "  $DOCX_HOST_PATH"
    err "  $ALT_PATH"
    err "Check that mcp-documents has the AI_OUTPUT_DIR bind mount."
    exit 4
  fi
fi

DOCX_SIZE=$(wc -c < "$DOCX_HOST_PATH")
ok "Word document rendered: $DOCX_HOST_PATH (${DOCX_SIZE} bytes)"

# ─── Stage 3 — Persona reviews the rendered .docx ────────────────────────────

section "Stage 3 — Persona Review"

info "Sending rendered docx back to persona for review"

REVIEW_USER_MESSAGE=$(cat <<EOF
Quick review pass. The previous draft has been rendered as a Word document at:

  **$DOCX_HOST_PATH** (${DOCX_SIZE} bytes)

Use the **read_word_document** tool to read it back. Then report:

1. Does the content match what you drafted? (Did markdown render cleanly into headings/bullets?)
2. Any formatting issues you can spot (broken headings, lost speaker labels, missing timestamps)?
3. Final assessment: APPROVED, MINOR_ISSUES, or NEEDS_REWORK with specifics.

Be brief and specific. If everything looks good, just say so.
EOF
)

REVIEW_PROMPT_FILE="$(mktemp -t review-prompt-XXXXXX.json)"

# Multi-turn: include the prior turn so persona has context
jq -n \
  --arg model "$PERSONA_MODEL" \
  --arg first_user "$DRAFT_USER_MESSAGE" \
  --arg first_asst "$DRAFT_CONTENT" \
  --arg review "$REVIEW_USER_MESSAGE" \
  '{
    model: $model,
    messages: [
      { role: "user", content: $first_user },
      { role: "assistant", content: $first_asst },
      { role: "user", content: $review }
    ],
    stream: false
  }' > "$REVIEW_PROMPT_FILE"

REVIEW_RESP="$(mktemp -t review-resp-XXXXXX.json)"

T4=$(date +%s)
HTTP_CODE="$(curl -sf -w "%{http_code}" --max-time 600 \
  -X POST "$OWUI_URL/api/chat/completions" \
  -H "Authorization: Bearer $OWUI_API_KEY" \
  -H "Content-Type: application/json" \
  -d @"$REVIEW_PROMPT_FILE" \
  -o "$REVIEW_RESP" \
  )" || {
    err "OWUI review request failed (HTTP $HTTP_CODE)"
    [[ -s "$REVIEW_RESP" ]] && head -c 600 "$REVIEW_RESP" >&2
    # Don't exit — review is bonus, the docx is already rendered
    REVIEW_CONTENT="(review skipped due to API error)"
}
T5=$(date +%s)

REVIEW_CONTENT="${REVIEW_CONTENT:-$(jq -r '.choices[0].message.content // empty' "$REVIEW_RESP")}"
[[ -z "$REVIEW_CONTENT" ]] && REVIEW_CONTENT="(persona review returned empty content)"

ok "Persona REVIEW phase complete in $((T5 - T4))s"

# Save review alongside the docx for the audit trail
REVIEW_FILE="${DOCX_HOST_PATH%.docx}_review.md"
{
  printf '# Persona Review — %s\n\n' "$DOCX_NAME"
  printf '**Reviewed:** %s\n' "$(date '+%Y-%m-%d %H:%M:%S')"
  printf '**Persona:** %s\n' "$PERSONA_MODEL"
  printf '**Source audio:** %s\n\n' "$AUDIO_BASENAME"
  printf '---\n\n'
  printf '%s\n' "$REVIEW_CONTENT"
} > "$REVIEW_FILE"

# ─── Stage 4 — Stage outputs next to the source audio ────────────────────────

section "Stage 4 — Copying outputs next to source"

# md, json, docx, review — all four next to the original audio
for src in "$MD_PATH" "$JSON_PATH" "$DOCX_HOST_PATH" "$REVIEW_FILE"; do
  if [[ -f "$src" ]]; then
    dest="$AUDIO_DIR/$(basename "$src")"
    cp -p "$src" "$dest"
    ok "  $(basename "$dest")"
  fi
done

# ─── Stage 5 — Summary ───────────────────────────────────────────────────────

section "Done"

cat >&2 <<EOF
Source:     $AUDIO_FILE
Speakers:   $SPEAKER_COUNT
Duration:   $(printf '%.1f' "$(echo "$DURATION / 60" | bc -l)") min
Language:   $LANG
Total time: $((T5 - T0))s

Outputs (in $AUDIO_DIR):
  $(basename "$MD_PATH")        — speaker-labeled markdown
  $(basename "$JSON_PATH")      — structured JSON
  $(basename "$DOCX_HOST_PATH")  — Word document (persona-drafted, rendered, reviewed)
  $(basename "$REVIEW_FILE")     — persona's review notes

Persona review verdict:
  $(echo "$REVIEW_CONTENT" | grep -iE 'APPROVED|MINOR_ISSUES|NEEDS_REWORK' | head -n1 \
      || echo "(see ${REVIEW_FILE##*/} for full review)")

EOF

# ─── Machine-readable summary on stdout (for piping/scripting) ───────────────
jq -n \
  --arg audio "$AUDIO_FILE" \
  --arg docx "$AUDIO_DIR/$(basename "$DOCX_HOST_PATH")" \
  --arg md "$AUDIO_DIR/$(basename "$MD_PATH")" \
  --arg json "$AUDIO_DIR/$(basename "$JSON_PATH")" \
  --arg review "$AUDIO_DIR/$(basename "$REVIEW_FILE")" \
  --argjson speakers "$SPEAKER_COUNT" \
  --argjson duration "$DURATION" \
  --arg lang "$LANG" \
  --arg verdict "$(echo "$REVIEW_CONTENT" | grep -iEo 'APPROVED|MINOR_ISSUES|NEEDS_REWORK' | head -n1 || echo 'UNKNOWN')" \
  '{
    audio_file: $audio,
    speaker_count: $speakers,
    duration_s: $duration,
    language: $lang,
    docx_path: $docx,
    markdown_path: $md,
    json_path: $json,
    review_path: $review,
    persona_verdict: $verdict
  }'
