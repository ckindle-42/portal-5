---
id: unit-COMFYUI_SETUP-step-2-export-comfyui-workflow-templates
kind: why
title: "COMFYUI_SETUP \u2014 Step 2 \u2014 Export ComfyUI workflow templates"
sources:
- type: design
  path: docs/COMFYUI_SETUP.md
  section: "Step 2 \u2014 Export ComfyUI workflow templates"
last_generated_commit: ''
confidence: high
tags:
- docs
- COMFYUI_SETUP
created_at: 1783195000.830699
updated_at: 1783195000.830699
---


The Wan 2.2 workflow dicts in `portal_mcp/generation/video_mcp.py` are stubs until exported. For each variant:

1. Open ComfyUI → Workflow → Browse Templates → Video
2. Load the template ("Wan2.2 14B T2V", "Wan2.2 5B TI2V", "Wan2.2-Animate-14B", "Wan2.2-S2V-14B")
3. Verify the model loads and runs a test prompt
4. Export as JSON and use the node graph to populate the corresponding `_WAN22_*_WORKFLOW` dict in `portal_mcp/generation/video_mcp.py`

Until step 2 is completed, calling a `wan22-*` model preset will raise a `RuntimeError` with instructions.
