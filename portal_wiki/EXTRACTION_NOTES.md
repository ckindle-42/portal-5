# Extraction-Readiness Audit — Portal Wiki

**Status:** audit complete, extraction NOT triggered
**Audited:** 2026-07-04
**Base HEAD:** `3fdbae3`

## Core/Adapter Boundary

The boundary holds.  `portal_wiki/core/` has ZERO Portal-specific imports:

| Module | Portal imports | Status |
|--------|---------------|--------|
| `core/schema.py` | None | ✅ clean |
| `core/interfaces.py` | None | ✅ clean |
| `core/store.py` | None | ✅ clean |
| `core/maintain.py` | None | ✅ clean |
| `core/render.py` | None | ✅ clean |

All Portal-specific wiring lives in `adapters/`:

| Module | Portal dependency | Purpose |
|--------|------------------|---------|
| `adapters/portal_inference.py` | Ollama (localhost:11434) | Local inference |
| `adapters/git_source.py` | Git repo | Source connector |
| `adapters/seed_security.py` | bench_security | Security knowledge seeding |
| `adapters/seed_intent.py` | CLAUDE.md, docs/ | Intent seeding |
| `adapters/seed_code.py` | Git repo | Code seeding |

## What a Standalone Build Would Swap

1. **Inference backend** — replace `PortalInference` with any OpenAI-compatible endpoint
2. **Source connectors** — replace `GitSourceConnector` with any repo/doc source
3. **MCP transport** — replace portal-specific MCP registration with standalone HTTP server

## What a Standalone Build Would Keep

1. **Core schema** — KnowledgeUnit, SourceRef, validation (stack-agnostic)
2. **Core store** — git-backed markdown storage (portable by default)
3. **Core maintenance** — staleness detection, snapshot-diff (no Portal deps)
4. **Core rendering** — view generation from canonical units (no Portal deps)
5. **Provenance enforcement** — mandatory source citation (architectural, not stack-specific)

## Packaging Sketch

```
pip install portal-wiki          # core + CLI
pip install portal-wiki[ollama]  # + Ollama adapter
pip install portal-wiki[git]     # + Git source connector
```

## Non-Portal User Configuration

```yaml
# portal_wiki.yaml
inference:
  endpoint: https://api.openai.com/v1
  model: gpt-4o-mini
  api_key: ${OPENAI_API_KEY}

sources:
  - type: git
    path: /path/to/repo
  - type: markdown
    path: /path/to/docs

storage:
  canonical_dir: ./canonical
```

## Conclusion

Extraction is a refactor (swap adapters), not a rewrite (rebuild core).  The product option is preserved.
