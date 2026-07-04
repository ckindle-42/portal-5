---
id: unit-HOWTO-users-you-ai-output-generated-transcripts-transcri
kind: why
title: "HOWTO \u2014 /Users/you/AI_Output/generated/transcripts/transcript_a3f2b1c4d5e6.md"
sources:
- type: design
  path: docs/HOWTO.md
  section: /Users/you/AI_Output/generated/transcripts/transcript_a3f2b1c4d5e6.md
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.849167
updated_at: 1783195000.849167
---

```

Then in OWUI, ask the persona to "format the transcript at <md_path>".

**Tool timeout for long files:** OWUI's default MCP tool timeout is shorter than processing time for files >5 min. To raise it:
```bash
echo "TOOL_SERVER_REQUEST_TIMEOUT=1800" >> .env  # 30 minutes
./launch.sh restart open-webui
```

**Performance (M4 Pro, 10-min 2-speaker audio):** ~60–130s end-to-end. Versus Docker fallback path: ~4–8 min (CPU-bound). Time scales roughly linearly with audio length.

**Speaker count drift:** for files >15 min, pyannote can occasionally split one speaker into multiple IDs across long silences. If the result has more speakers than you expected, ask the persona to re-run with `num_speakers=<your_count>` to constrain.

**Verify:**
```bash
curl http://localhost:8924/health
