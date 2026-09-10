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

The `portal_wiki/canonical/` spine is the single write-point for documentation: a fact is edited in one unit, and `render_all_generated_blocks` rewrites every `WIKI:GENERATED` block that references it across the `TIER1_DOCS` set. Downstream docs are shells -- their generated substance is the unit body, not a separate copy -- so the same fact is never maintained in two places.

This inverts the traditional model of hand-maintaining prose and then auditing for drift. A generated block cannot drift independently because it has no independent prose: `sync-config` invokes `render_all_generated_blocks`, and only the content between the `WIKI:GENERATED` markers is replaced, leaving human-authored narrative untouched.

The enforcement gate is validate check AW in `scripts/validate_system.py`: `check_wiki_facts_current` diffs each generated block against its unit's current body via `check_generated_blocks_current`, so a mismatch is a precise signal that `sync-config` was not re-run after the source unit changed. AW also verifies fact-units against live config and that migrated docs carry no un-fenced substance.

Heading depth is projected at render time, not stored: a unit body keeps `## Why` at H2 because `quality.check_structure` requires a level-2 `## Why`, while the level it should render at depends on the host section. `project_body` shifts a body's ATX headings (outside code fences) by one uniform delta so the shallowest lands one level below its host, clamped to H1--H6, and `host_section_depth` reads that host depth after blanking prior generated blocks from the prefix so a body already rendered never parents the next one. Both the write path and `check_generated_blocks_current` route through `project_body`, so the currency diff compares projected body to projected body and AW stays exact.

## Why

Concentrating the write-point in the spine is what makes doc currency mechanical rather than reviewable. If facts lived in two places, nothing could stop them from diverging except an audit nobody schedules; the block-fill contract turns divergence into a per-block diff failure a pre-commit gate can catch. AW diffs against the unit body rather than a hash or timestamp because only an exact body comparison produces the precise, actionable mismatch that a coarse directory-changed signal cannot.
