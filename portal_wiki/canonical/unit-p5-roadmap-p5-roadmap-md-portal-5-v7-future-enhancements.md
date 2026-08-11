---
id: unit-p5-roadmap-p5-roadmap-md-portal-5-v7-future-enhancements
kind: what
title: "P5_ROADMAP \u2014 Portal 5 v7 Future Enhancements"
sources:
- type: code
  path: pyproject.toml
- type: code
  path: CHANGELOG.md
last_generated_commit: e095c559e99efc7621e4be2ca5c8286763abee6c
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5889852
updated_at: 1784946220.5889852
---

The roadmap document at the repo root is the tracking file for open Portal 5
work. Its header states the current release as 8.0.0, which matches the `version`
field in `pyproject.toml`. Completed work is not kept in the open queue:
`CHANGELOG.md` records shipped milestones, and the roadmap marks all v5.0 through
v6.1.0 items as DONE there. The live set of open items, each with its
implementation or absence in code, is tracked in the roadmap's open-work section
rather than being repeated in a doc copy here.

## Why

This unit exists because the roadmap header was once extracted as if it were a
fact about the system. The only code-determined facts it contains are the release
version in `pyproject.toml` and the location of the completed-work record in
`CHANGELOG.md`; the roadmap itself is a planning artifact, not a fact source, so
the unit now asserts only those two anchors and does not restate the roadmap
body.
