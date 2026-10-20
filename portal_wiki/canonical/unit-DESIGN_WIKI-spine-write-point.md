---
id: unit-DESIGN_WIKI-spine-write-point
kind: why
title: Spine is the single write-point for documentation
sources:
- type: code
  path: portal/platform/wiki/render.py
- type: code
  path: scripts/validate_system.py
- type: code
  path: portal/platform/inference/sync_config.py
claims: []
confidence: high
tags:
- design
- spine
- verified-v1
- wiki
created_at: 1784941688.641715
updated_at: 1784941688.641715
---

The `portal_wiki/canonical/` spine stores authored knowledge. Live fact units are computed on demand through the wiki MCP and are not stored there. When a release needs managed documentation refreshed, `portal docs build` runs `render_all_generated_blocks` across the `TIER1_DOCS` set and renders the generated views.

The document build is separate from runtime config generation. `sync-config` writes routing, MCP, Open WebUI preset, and module artifacts; it does not compute or persist fact units and it does not rewrite documentation. The docs build replaces only content between `WIKI:GENERATED` markers, leaving human-authored narrative untouched.

There is no generated-doc or stored-fact freshness gate. Claim validation in `BS` checks authored units and computed fact units against live probes; the docs build is an explicit release-time operation.

Heading depth is projected at render time, not stored: a unit body keeps `## Why` at H2 because `quality.check_structure` requires a level-2 `## Why`, while the level it should render at depends on the host section. `project_body` shifts a body's ATX headings (outside code fences) by one uniform delta so the shallowest lands one level below its host, clamped to H1--H6, and `host_section_depth` reads that host depth after blanking prior generated blocks from the prefix so a body already rendered never parents the next one.

## Why

Authored guidance and live facts have different lifecycles: the canonical store owns the former, while the wiki MCP derives the latter from current inputs. Generated documents remain explicit build outputs, so a release can refresh them without coupling doc writes to runtime config regeneration.
