# Fix Task — ComfyUI FLUX Workflow + Grafana TPS Panel

**Agent:** Claude Code  
**Run from:** `cd ~/portal-5` (repo root)  
**Stack state required:** Stack does NOT need to be running for the code edits.  
ComfyUI only needs to be running for the verification step at the end.

---

## Context

Two bugs identified from acceptance run and code review:

1. **ComfyUI image generation is broken** — `portal_mcp/generation/comfyui_mcp.py`  
   The FLUX_WORKFLOW uses `CheckpointLoaderSimple` which requires a bundled SD checkpoint.
   FLUX UNet files are not bundled checkpoints — ComfyUI rejects the workflow at queue time.
   Additionally the KSampler's `"negative"` input is wired to a raw empty string `""` instead
   of a conditioning tensor, and the DualCLIPLoader has hardcoded wrong file paths.

2. **Grafana TPS panel missing** — `config/grafana/dashboards/portal5_overview.json`  
   `portal_tokens_per_second` is a Histogram with both `model` and `workspace` labels.
   The dashboard has "Tokens Per Second by Model" but no "Tokens Per Second by Workspace"
   panel. The "Current Request Rate" panel is floating alone at `y=55, x=16, w=8` with
   nothing at `x=0–16` of that row.

---

## ⛔ Rules

- Edit only the four files listed in each task. No other files.
- Do NOT modify `portal_pipeline/router_pipe.py` — the metrics instrumentation there is correct.
- Do NOT modify `portal5_acceptance.py` or any test file.
- Run the verification commands at the end. All must pass before marking done.

---

## Task 1 — Fix `portal_mcp/generation/comfyui_mcp.py`

### What to change

**Step 1a — Add env-var constants for FLUX model filenames** (after the `IMAGE_BACKEND` line):

```python
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://localhost:8188")
IMAGE_BACKEND = os.getenv("IMAGE_BACKEND", "flux")  # "flux" or "sdxl"

# FLUX model filenames — must match filenames in ComfyUI's models/ subdirectories.
# Run: ls ~/ComfyUI/models/unet/ ~/ComfyUI/models/clip/ ~/ComfyUI/models/vae/
# to find actual downloaded filenames, then set these in .env.
FLUX_UNET_FILE = os.getenv("FLUX_UNET_FILE", "flux1-schnell.safetensors")
FLUX_CLIP_L_FILE = os.getenv("FLUX_CLIP_L_FILE", "clip_l.safetensors")
FLUX_CLIP_T5_FILE = os.getenv("FLUX_CLIP_T5_FILE", "t5xxl_fp8_e4m3fn.safetensors")
FLUX_VAE_FILE = os.getenv("FLUX_VAE_FILE", "ae.safetensors")
```

**Step 1b — Replace FLUX_WORKFLOW entirely.**

The current `FLUX_WORKFLOW` has three bugs:
- Node `"1"` uses `CheckpointLoaderSimple` → must be `UNETLoader`
- `DualCLIPLoader` has hardcoded wrong paths (`text_encoder/model.safetensors`, `text_encoder_2/model-00001-of-00002.safetensors`)
- KSampler `"negative"` input is `""` (raw string) → must be a conditioning tensor

Replace the entire `FLUX_WORKFLOW` dict with this corrected version:

```python
# FLUX.1-schnell workflow
# FLUX uses split checkpoints: UNet (UNETLoader), CLIP pair (DualCLIPLoader), VAE (VAELoader).
# CheckpointLoaderSimple is for standard SD checkpoints only — FLUX UNet files are
# not bundled checkpoints and will be rejected by CheckpointLoaderSimple.
# Node layout:
#   1: UNETLoader        → model[0]
#   2: VAELoader         → vae[0]
#   3: EmptyLatentImage  → latent[0]
#   4: DualCLIPLoader    → clip[0]
#   5: CLIPTextEncode (positive)  → conditioning[0]
#   6: CLIPTextEncode (negative)  → conditioning[0]  ← empty text; KSampler needs a tensor
#   7: FluxGuidance      → conditioning[0]
#   8: KSampler          → latent[0]
#   9: VAEDecode         → image[0]
#  10: SaveImage
# ComfyUI v0.16: node IDs must be strings; connections as [node_id, output_index].
FLUX_WORKFLOW = {
    "1": {
        "inputs": {"unet_name": FLUX_UNET_FILE},
        "class_type": "UNETLoader",
    },
    "2": {
        "inputs": {"vae_name": FLUX_VAE_FILE},
        "class_type": "VAELoader",
    },
    "3": {
        "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
        "class_type": "EmptyLatentImage",
    },
    "4": {
        "inputs": {
            "clip_name1": FLUX_CLIP_L_FILE,
            "clip_name2": FLUX_CLIP_T5_FILE,
            "type": "flux",
        },
        "class_type": "DualCLIPLoader",
    },
    "5": {
        "inputs": {"text": "", "clip": ["4", 0]},
        "class_type": "CLIPTextEncode",
    },
    "6": {
        # Empty negative conditioning — KSampler requires a conditioning tensor,
        # not a raw string. FLUX ignores negative prompts at low CFG but the node
        # graph must be wired with a valid CLIPTextEncode output.
        "inputs": {"text": "", "clip": ["4", 0]},
        "class_type": "CLIPTextEncode",
    },
    "7": {
        "inputs": {"conditioning": ["5", 0], "guidance": 3.5},
        "class_type": "FluxGuidance",
    },
    "8": {
        "inputs": {
            "seed": 42,
            "steps": 4,
            "cfg": 1.0,
            "sampler_name": "euler",
            "scheduler": "simple",
            "model": ["1", 0],
            "positive": ["7", 0],
            "negative": ["6", 0],
            "latent_image": ["3", 0],
            "denoise": 1,
        },
        "class_type": "KSampler",
    },
    "9": {
        "inputs": {"samples": ["8", 0], "vae": ["2", 0]},
        "class_type": "VAEDecode",
    },
    "10": {
        "inputs": {"filename_prefix": "portal_", "images": ["9", 0]},
        "class_type": "SaveImage",
    },
}
```

**Step 1c — Fix `generate_image()` FLUX branch.**

Find the `else:` branch inside `generate_image()` that handles FLUX (it follows the `if IMAGE_BACKEND == "sdxl":` block). Replace it with:

```python
    else:
        # FLUX workflow node map (see FLUX_WORKFLOW definition):
        #   3 = EmptyLatentImage, 4 = DualCLIPLoader, 5 = CLIPTextEncode (positive),
        #   6 = CLIPTextEncode (negative), 7 = FluxGuidance, 8 = KSampler
        workflow["5"]["inputs"]["text"] = prompt   # positive CLIPTextEncode
        workflow["3"]["inputs"]["width"] = width
        workflow["3"]["inputs"]["height"] = height
        workflow["8"]["inputs"]["seed"] = seed     # KSampler is now node 8
        workflow["8"]["inputs"]["steps"] = min(max(steps, 1), 20)
        workflow["8"]["inputs"]["cfg"] = min(max(cfg, 0), 10)
        # Propagate current env-var filenames so runtime .env overrides are respected
        workflow["1"]["inputs"]["unet_name"] = FLUX_UNET_FILE
        workflow["2"]["inputs"]["vae_name"] = FLUX_VAE_FILE
        workflow["4"]["inputs"]["clip_name1"] = FLUX_CLIP_L_FILE
        workflow["4"]["inputs"]["clip_name2"] = FLUX_CLIP_T5_FILE
```

The old branch referenced node `"7"` for KSampler — that node is now `"8"`. Do not leave any `workflow["7"]["inputs"]["seed"]` reference in the FLUX branch.

### Verify Task 1

```bash
# Syntax check
python3 -c "import ast; ast.parse(open('portal_mcp/generation/comfyui_mcp.py').read()); print('OK')"

# Structural checks — all must print OK
python3 -c "
src = open('portal_mcp/generation/comfyui_mcp.py').read()
flux_section = src.split('SDXL_WORKFLOW')[0].split('FLUX_WORKFLOW =')[1]

checks = [
    ('UNETLoader present',               'UNETLoader' in flux_section),
    ('CheckpointLoaderSimple absent',    'CheckpointLoaderSimple' not in flux_section),
    ('negative wired to node-6',         '\"negative\": [\"6\", 0]' in flux_section),
    ('FLUX_UNET_FILE in constants',      'FLUX_UNET_FILE = os.getenv' in src),
    ('FLUX_CLIP_L_FILE in constants',    'FLUX_CLIP_L_FILE = os.getenv' in src),
    ('FLUX_CLIP_T5_FILE in constants',   'FLUX_CLIP_T5_FILE = os.getenv' in src),
    ('FLUX_VAE_FILE in constants',       'FLUX_VAE_FILE = os.getenv' in src),
    ('generate_image uses node-8 seed',  'workflow[\"8\"][\"inputs\"][\"seed\"]' in src),
    ('no stale node-7 seed ref',         'workflow[\"7\"][\"inputs\"][\"seed\"]' not in src),
    ('env-var propagation in generate',  'FLUX_UNET_FILE' in src.split('def generate_image')[1]),
]
for name, ok in checks:
    print(f'  {\"OK\" if ok else \"FAIL\"}: {name}')
all_ok = all(ok for _, ok in checks)
print('PASS' if all_ok else 'FAIL — fix issues above before continuing')
"
```

Expected output: every line prints `OK`, final line prints `PASS`.

---

## Task 2 — Fix `config/grafana/dashboards/portal5_overview.json`

### What to change

**Step 2a — Add the missing "Tokens Per Second by Workspace" panel.**

Find the existing "Current Request Rate" panel entry in the JSON. It currently looks like:

```json
{
  "id": 18,
  "type": "stat",
  "title": "Current Request Rate",
  ...
  "gridPos": { "h": 8, "w": 8, "x": 16, "y": 55 },
```

Replace the entire "Current Request Rate" panel object with TWO panels — the new workspace TPS panel first, then the repositioned Current Request Rate:

```json
    {
      "id": 25,
      "type": "timeseries",
      "title": "Tokens Per Second by Workspace",
      "description": "Rolling average tokens/sec per workspace. Shows which workspaces are driving inference load.",
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 55 },
      "targets": [
        {
          "expr": "sum by(workspace) (rate(portal_tokens_per_second_sum[5m])) / sum by(workspace) (rate(portal_tokens_per_second_count[5m]))",
          "legendFormat": "{{workspace}}",
          "datasource": { "type": "prometheus", "uid": "prometheus" }
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "none",
          "custom": { "lineWidth": 2 }
        }
      },
      "options": {
        "legend": { "displayMode": "table", "placement": "bottom", "calcs": ["mean", "max", "last"] }
      }
    },
    {
      "id": 18,
      "type": "stat",
      "title": "Current Request Rate",
      "description": "Aggregate request throughput across all workspaces (req/min).",
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 55 },
      "targets": [
        {
          "expr": "sum(rate(portal_requests_total[5m])) * 60",
          "datasource": { "type": "prometheus", "uid": "prometheus" }
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "reqpm",
          "color": { "mode": "fixed", "fixedColor": "green" }
        }
      },
      "options": {
        "colorMode": "value",
        "graphMode": "area",
        "reduceOptions": {
          "calcs": ["lastNotNull"]
        }
      }
    }
```

Note: `"Current Request Rate"` changes from `w=8, x=16` → `w=12, x=12`. The new TPS panel fills `x=0, w=12`. Together they fill the full 24-column row.

**Step 2b — Bump dashboard version** from `"version": 4` to `"version": 5`.

### Verify Task 2

```bash
python3 -c "
import json
with open('config/grafana/dashboards/portal5_overview.json') as f:
    d = json.load(f)

panels_55 = [p for p in d['panels'] if p.get('gridPos', {}).get('y') == 55]
all_ids   = [p['id'] for p in d['panels']]

checks = [
    ('JSON valid',                    True),
    ('25 total panels',               len(d['panels']) == 25),
    ('no duplicate panel IDs',        len(all_ids) == len(set(all_ids))),
    ('2 panels at y=55',              len(panels_55) == 2),
    ('TPS workspace at x=0 w=12',     any(p['title']=='Tokens Per Second by Workspace'
                                          and p['gridPos']['x']==0
                                          and p['gridPos']['w']==12 for p in panels_55)),
    ('Request Rate at x=12 w=12',     any(p['title']=='Current Request Rate'
                                          and p['gridPos']['x']==12
                                          and p['gridPos']['w']==12 for p in panels_55)),
    ('TPS expr has workspace label',  any('workspace' in t.get('expr','')
                                          for p in panels_55
                                          if 'Workspace' in p.get('title','')
                                          for t in p.get('targets', []))),
    ('dashboard version == 5',        d['version'] == 5),
]
for name, ok in checks:
    print(f'  {\"OK\" if ok else \"FAIL\"}: {name}')
print('PASS' if all(ok for _,ok in checks) else 'FAIL — fix issues above')
"
```

Expected output: every line prints `OK`, final line prints `PASS`.

---

## Task 3 — Wire FLUX env vars in `deploy/portal-5/docker-compose.yml`

### What to change

Find the `mcp-comfyui` service's `environment:` block. It currently contains:

```yaml
      - COMFYUI_MCP_PORT=8910
      - MCP_PORT=8910
      - COMFYUI_URL=${COMFYUI_URL:-http://host.docker.internal:8188}
      - IMAGE_BACKEND=${IMAGE_BACKEND:-flux}
```

Add the four FLUX filename vars immediately after `IMAGE_BACKEND`:

```yaml
      - COMFYUI_MCP_PORT=8910
      - MCP_PORT=8910
      - COMFYUI_URL=${COMFYUI_URL:-http://host.docker.internal:8188}
      - IMAGE_BACKEND=${IMAGE_BACKEND:-flux}
      - FLUX_UNET_FILE=${FLUX_UNET_FILE:-flux1-schnell.safetensors}
      - FLUX_CLIP_L_FILE=${FLUX_CLIP_L_FILE:-clip_l.safetensors}
      - FLUX_CLIP_T5_FILE=${FLUX_CLIP_T5_FILE:-t5xxl_fp8_e4m3fn.safetensors}
      - FLUX_VAE_FILE=${FLUX_VAE_FILE:-ae.safetensors}
```

### Verify Task 3

```bash
for var in FLUX_UNET_FILE FLUX_CLIP_L_FILE FLUX_CLIP_T5_FILE FLUX_VAE_FILE; do
  grep -q "$var" deploy/portal-5/docker-compose.yml \
    && echo "OK: $var in docker-compose.yml" \
    || echo "FAIL: $var missing from docker-compose.yml"
done
```

---

## Task 4 — Document FLUX env vars in `.env.example`

### What to change

Find the `IMAGE_MODEL=flux-schnell` line. Add the four FLUX filename vars immediately after it, before the `# Video model` comment:

```bash
IMAGE_MODEL=flux-schnell
# FLUX model filenames in ComfyUI's models directories (unet/, clip/, vae/).
# After downloading, run: ls ~/ComfyUI/models/unet/ ~/ComfyUI/models/clip/ ~/ComfyUI/models/vae/
# Set these to match the actual .safetensors filenames found.
# Defaults match the files produced by ./launch.sh download-comfyui-models (flux-schnell).
FLUX_UNET_FILE=flux1-schnell.safetensors
FLUX_CLIP_L_FILE=clip_l.safetensors
FLUX_CLIP_T5_FILE=t5xxl_fp8_e4m3fn.safetensors
FLUX_VAE_FILE=ae.safetensors
```

### Verify Task 4

```bash
for var in FLUX_UNET_FILE FLUX_CLIP_L_FILE FLUX_CLIP_T5_FILE FLUX_VAE_FILE; do
  grep -q "^${var}=" .env.example \
    && echo "OK: $var in .env.example" \
    || echo "FAIL: $var missing from .env.example"
done
```

---

## Final Verification — Run all checks together

```bash
echo "=== Task 1: comfyui_mcp.py ===" && \
python3 -c "
import ast
src = open('portal_mcp/generation/comfyui_mcp.py').read()
ast.parse(src)
flux = src.split('SDXL_WORKFLOW')[0].split('FLUX_WORKFLOW =')[1]
checks = [
    ('UNETLoader present',             'UNETLoader' in flux),
    ('CheckpointLoaderSimple absent',  'CheckpointLoaderSimple' not in flux),
    ('negative wired to node-6',       '\"negative\": [\"6\", 0]' in flux),
    ('FLUX_UNET_FILE constant',        'FLUX_UNET_FILE = os.getenv' in src),
    ('FLUX_CLIP_L_FILE constant',      'FLUX_CLIP_L_FILE = os.getenv' in src),
    ('FLUX_CLIP_T5_FILE constant',     'FLUX_CLIP_T5_FILE = os.getenv' in src),
    ('FLUX_VAE_FILE constant',         'FLUX_VAE_FILE = os.getenv' in src),
    ('generate_image node-8 seed',     'workflow[\"8\"][\"inputs\"][\"seed\"]' in src),
    ('no stale node-7 seed',           'workflow[\"7\"][\"inputs\"][\"seed\"]' not in src),
    ('env propagation in generate',    'FLUX_UNET_FILE' in src.split('def generate_image')[1]),
]
[print(f'  {\"OK\" if ok else \"FAIL\"}: {n}') for n,ok in checks]
print('PASS' if all(ok for _,ok in checks) else 'FAIL')
" && \
echo "" && echo "=== Task 2: portal5_overview.json ===" && \
python3 -c "
import json
d = json.load(open('config/grafana/dashboards/portal5_overview.json'))
p55 = [p for p in d['panels'] if p.get('gridPos',{}).get('y')==55]
ids = [p['id'] for p in d['panels']]
checks = [
    ('25 panels',              len(d['panels'])==25),
    ('no dup IDs',             len(ids)==len(set(ids))),
    ('2 panels at y=55',       len(p55)==2),
    ('TPS-ws x=0 w=12',        any(p['title']=='Tokens Per Second by Workspace' and p['gridPos']['x']==0 and p['gridPos']['w']==12 for p in p55)),
    ('Rate x=12 w=12',         any(p['title']=='Current Request Rate' and p['gridPos']['x']==12 and p['gridPos']['w']==12 for p in p55)),
    ('TPS expr workspace',     any('workspace' in t.get('expr','') for p in p55 if 'Workspace' in p.get('title','') for t in p.get('targets',[]))),
    ('version==5',             d['version']==5),
]
[print(f'  {\"OK\" if ok else \"FAIL\"}: {n}') for n,ok in checks]
print('PASS' if all(ok for _,ok in checks) else 'FAIL')
" && \
echo "" && echo "=== Tasks 3+4: docker-compose + .env.example ===" && \
for var in FLUX_UNET_FILE FLUX_CLIP_L_FILE FLUX_CLIP_T5_FILE FLUX_VAE_FILE; do
  grep -q "$var" deploy/portal-5/docker-compose.yml && echo "  OK: $var in docker-compose" || echo "  FAIL: $var missing from docker-compose"
  grep -q "^${var}=" .env.example && echo "  OK: $var in .env.example" || echo "  FAIL: $var missing from .env.example"
done && \
echo "" && echo "=== All tasks complete ==="
```

Expected: every line `OK`, each section ends `PASS`, final line `=== All tasks complete ===`.

---

## Optional — Live ComfyUI smoke test (requires ComfyUI running)

If ComfyUI is running at `http://localhost:8188`, verify the fixed workflow is accepted:

```bash
python3 -c "
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def test():
    async with streamablehttp_client('http://localhost:8910/mcp') as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            result = await s.call_tool('list_workflows', {})
            print('Checkpoints:', result.content[0].text[:200])

asyncio.run(test())
"
```

Expected: a list of `.safetensors` filenames. If ComfyUI is not running, skip this step — the code fixes are verified by the structural checks above.

---

## Files modified by this task

| File | Change |
|---|---|
| `portal_mcp/generation/comfyui_mcp.py` | Replace FLUX_WORKFLOW (UNETLoader, env-var filenames, proper negative node); fix `generate_image` node refs |
| `config/grafana/dashboards/portal5_overview.json` | Add "Tokens Per Second by Workspace" panel; reposition "Current Request Rate"; bump version 4→5 |
| `deploy/portal-5/docker-compose.yml` | Add 4 FLUX filename env vars to `mcp-comfyui` service |
| `.env.example` | Document 4 FLUX filename vars after `IMAGE_MODEL` |
