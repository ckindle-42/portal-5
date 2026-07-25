---
id: unit-DESIGN_WIKI-fence-contract
kind: why
title: 'Fence contract: GENERATED + HUMAN-OWNED are the only valid content types'
sources:
- type: design
  path: docs/DESIGN_WIKI_GENERATION_LOOP_V1.md
  commit: d869257b
  section: '2'
- type: code
  path: portal/platform/wiki/migration.py
  commit: d869257b
last_generated_commit: d869257b
confidence: high
tags:
- design
- wiki
- fences
created_at: 1784941607.159859
updated_at: 1784941607.159859
---

A migrated doc contains exactly two types of managed content:

1. **WIKI:GENERATED blocks** -- delimited by `&lt;!-- WIKI:GENERATED unit=&lt;id&gt; --&gt;` and `&lt;!-- /WIKI:GENERATED --&gt;`. Content is filled from a spine unit by `render_all_generated_blocks`. Never hand-edit inside this fence -- edit the unit instead.

2. **WIKI:HUMAN-OWNED fences** -- delimited by `&lt;!-- WIKI:HUMAN-OWNED --&gt;` and `&lt;!-- /WIKI:HUMAN-OWNED --&gt;`. Irreducible human judgment (rationale, caveats, opinions). This is first-class, not a loophole for un-migrated facts. A fact (a count, a path, a name, a behavior of the code) belongs in a unit; a judgment may live here.

Any substantive line outside both fences is **un-migrated content** -- a discovery hit. Inert markdown structure (headings, horizontal rules, blank lines) may exist outside fences without triggering discovery.
