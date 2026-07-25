---
id: unit-agent-loop-shape
kind: what
title: "AGENT_LOOP \u2014 Shape"
sources:
- type: doc
  path: docs/AGENT_LOOP.md
  commit: 05e42ec2
  section: Shape
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5049548
updated_at: 1784946220.5049548
---

```
goal --> [validate bounds] --> loop:
           decide (grounded)  ->  execute (module Executor)  ->  fold observations
             ^                                                      |
             +---------------- iterate until stop / budget ---------+
         record (optional)  ->  portal_wiki/proposed/  (CI gate: confirm/reject)
```
