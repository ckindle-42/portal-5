---
id: unit-DESIGN_WIKI-spine-write-point
kind: why
title: Spine is the single write-point for documentation
sources:
- type: design
  path: docs/DESIGN_WIKI_GENERATION_LOOP_V1.md
  commit: d869257b
  section: '1'
- type: code
  path: portal/platform/wiki/render.py
  commit: d869257b
last_generated_commit: d869257b
confidence: high
tags:
- design
- wiki
- spine
created_at: 1784941688.641715
updated_at: 1784941688.641715
---

The `portal_wiki/canonical/` spine is the single place truth is edited. Every downstream doc is a **shell** whose substance is rendered from spine units. You edit one unit; a process regenerates every downstream file that draws on it. You never update the same fact in two places.

This inverts the traditional documentation model (hand-maintain prose, then audit for drift) into a mechanical one: drift is impossible because the doc has no independent prose to drift -- its content IS the unit body, filled in by `render_all_generated_blocks` during `sync-config`.

The enforcement gate is AW in `validate_system.py`: it diffs each WIKI:GENERATED block against its unit's current body. A mismatch means `sync-config` was not re-run after a source change.
