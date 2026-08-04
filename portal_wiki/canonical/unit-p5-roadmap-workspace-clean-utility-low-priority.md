---
id: unit-p5-roadmap-workspace-clean-utility-low-priority
kind: what
title: "P5_ROADMAP \u2014 workspace-clean Utility (LOW priority)"
sources:
- type: code
  path: launch.sh
- type: code
  path: portal/platform/mcp_host/workspace.py
- type: code
  path: scripts/mlx-speech.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5902588
updated_at: 1784946220.5902588
---

A `workspace-clean` command is planned but does not exist: `launch.sh` has no such
subcommand. What the code does determine is the layout the utility would operate
on. `portal/platform/mcp_host/workspace.py` resolves the shared workspace root
from `WORKSPACE_DIR` or `AI_OUTPUT_DIR` (default `~/AI_Output` on the host) and
creates per-category `generated/` subdirectories on demand, so the generated tree
grows without any age-based purge. The only time-based cleanup in the repo is the
speech janitor `_cleanup_stale_audio` in `scripts/mlx-speech.py`, which deletes
stale audio older than a bounded max age. A general workspace cleaner therefore
remains open roadmap work with no code footprint yet.

## Why

The shared output directory grows unbounded because nothing prunes old generated
artifacts, and the unit records both the gap and why it stays low priority. The
only expiry-driven janitor that exists is scoped to one category (`mlx-speech.py`),
generalizing it to the full workspace is planned but unimplemented, so the body
asserts the layout the planned command would target and the absence of the command
in `launch.sh`.
