---
id: unit-design-wiki-archive-mechanism
kind: mixed
title: "DESIGN \u2014 wiki archive mechanism (retained on disk, out of the working\
  \ set)"
sources:
- type: code
  path: portal/platform/wiki/archive.py
- type: code
  path: portal/platform/wiki/store.py
- type: code
  path: portal_wiki/__main__.py
- type: code
  path: tests/unit/test_wiki_archive.py
- type: code
  path: tests/unit/test_detector_precision.py
last_generated_commit: eb7d36d65f646843737e645ab547ece867863723
claims: []
confidence: high
tags:
- wiki
- archive
- design
- verified-v1
created_at: 1785700000.0
updated_at: 1785700000.0
---

## What

Archiving is not deletion. A unit that nothing in the codebase determines the
truth of leaves the working set but keeps its file, moved to
`portal_wiki/archive/` with its frontmatter untouched and a reasoned line
appended to `portal_wiki/archive/INDEX.md`. `store.load_archived()` is the only
read path that sees archived units; `load_all()` and every consumer built on it
(search, coverage, drift, quality, render) operate on the live set alone, so an
archived unit cannot surface in an answer or a census.

The preconditions for archiving live in `archive_unit()`, not in the operator's
discipline. A unit is refused when the reason is missing, when a `WIKI:GENERATED`
doc block references the id, when another live unit's body links it, or when any
cited source is a live file or directory — "live" meaning a real, non-generated
path on disk (`is_live_source` asks the filesystem, not an extension allowlist,
and line-anchored `WIKI:GENERATED` markers reject spine-written markdown). The
code-source refusal
is the only one overridable, and only through `--superseded-by <survivor>`, which
requires a survivor unit that already cites every code path the archived unit
cited — so a re-groundable unit cannot be archived to avoid re-grounding it.

## Why

The catalog is additive-only by project convention — the retired MLX proxy still
lives on disk under `scripts/_archive/mlx-retired-3a0c58e/`. Deleting a unit that
a Tier-1 doc block references, or that a live unit links in prose, would break
the render and grounding gates with no diagnostic. Keeping archived units on disk
and provably unreachable turns "archive it" into a safe, reversible operation
with an audit trail: `archive_reachability()` walks the live store and every
Tier-1 doc, and the `BT` validate check fails if any archived id is re-reached
through a stray reference. The `INDEX.md` reason is phrased as a fact ("cites
only docs/HOWTO.md, which is generated output") rather than a category label, so
the decision to archive is itself reviewable long after the commit that made it.
