---
id: unit-claude-portal-wiki-canonical-knowledge-layer
kind: why
title: "CLAUDE.md \u2014 Portal Wiki \u2014 Canonical Knowledge Layer"
sources:
- type: design
  path: CLAUDE.md
  section: "Portal Wiki \u2014 Canonical Knowledge Layer"
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1785348301.194391
updated_at: 1785348301.194391
---


The project has a self-maintaining knowledge backbone (`portal_wiki/`) that agents can query for cited, grounded answers instead of re-reading source.

**For agents:** use `wiki.search`, `wiki.get_unit`, `wiki.explain` (via `portal_wiki.mcp`) to look up architecture decisions, technique signatures, subsystem overviews, and design rationale. Every answer cites its source — never trust a wiki claim without its citation.

**For operators:** `portal_wiki/canonical/` contains the source-of-truth knowledge units (markdown + frontmatter). Edit the canonical unit, not rendered views. Views are generated to `docs/generated/` and marked `<!-- GENERATED -->`.

**CLAUDE.md is the one intentional exception.** As of `TASK_WIKI_SPINE_DOC_GENERATION_V3`, nearly every other doc in this repo (`README.md`, `docs/*.md`, `config/MODEL_CATALOG.md`, the test-execution prompts, etc.) is a shell whose substance is `<!-- WIKI:GENERATED unit=<id> -->` blocks rendered from `portal_wiki/canonical/` — see `docs/DESIGN_WIKI_GENERATION_LOOP_V1.md` for the mechanism. CLAUDE.md alone stays hand-authored (it is hard-excluded from migration in `portal/platform/wiki/migration.py`) because it is the agent entry point, not a reference doc. When a change at HEAD affects a fact recorded in a spine unit, update that unit (and re-run `./launch.sh sync-config`) in the same change — a stale unit is a stale doc across the whole surface it feeds, not just one file.

**What lives where:**
- `portal/platform/wiki/` — engine: schema, store, maintenance, rendering (top-level files are stack-agnostic, zero Portal imports — this is the extraction-guarantee boundary CI enforces via `AJ. wiki core backbone`)
- `portal/platform/wiki/adapters/` — Portal-specific wiring (Ollama inference, git source, security/intent/code seeders, module toggle resolver)
- `portal_wiki/canonical/` — the knowledge units themselves (git-versioned markdown, still at the repo-root data path — never moved)
- `portal_wiki/mcp.py` — agent-facing tools (search, get_unit, explain)
