---
id: unit-DESIGN_WIKI-fence-contract
kind: why
title: 'Fence contract: GENERATED + HUMAN-OWNED are the only valid content types'
sources:
- type: code
  path: portal/platform/wiki/migration.py
- type: code
  path: portal/platform/wiki/render.py
claims: []
confidence: high
tags:
- design
- fences
- verified-v1
- wiki
created_at: 1784941607.159859
updated_at: 1784941607.159859
---

 A migrated doc contains exactly two managed content types. First, `WIKI:GENERATED` blocks, delimited by an opening `&lt;!-- WIKI:GENERATED unit=&lt;id&gt; --&gt;` marker and a closing `&lt;!-- /WIKI:GENERATED --&gt;` marker, whose content is filled from the spine unit body by `render_all_generated_blocks`. The marker is placed once by hand; the renderer only replaces content between markers and never invents a location, so the inside of a generated fence is never hand-edited. Second, `WIKI:HUMAN-OWNED` fences, whose current opening form carries a `reason="..."` attribute; the older bare V1 form without a reason is detected and treated as unreasoned, which fails `doc_is_migrated`. Human-owned fences hold irreducible judgment -- rationale, caveats, opinions. A fact (a count, a path, a name, a behavior of the code) belongs in a unit; a judgment may live in a fence.

`doc_is_migrated` demands more than clean fences: at least one generated block, a human-fence share at or below the `_HUMAN_FENCE_MAX` bound, every fence reasoned, and zero `substantive_remainder`. Inert markdown structure -- headings, horizontal rules, blank lines, table separator rows, standalone tags, non-WIKI HTML comments -- may sit outside fences without triggering discovery.

## Why

The fence contract is what makes "migrated" a mechanically checkable property instead of a claim. V2 made the reason attribute a hard requirement because an unreasoned fence is indistinguishable from dumping narrative into a doc to dodge discovery. The generated-block floor and the bounded human-fence ratio close the mirror-image loophole: a doc cannot pass by fencing everything, which is the exact game `doc_is_migrated` and the validate gate exist to catch.
