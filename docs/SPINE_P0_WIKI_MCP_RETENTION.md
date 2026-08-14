# P0.5 — Wiki MCP (:8931) retire-or-keep record

`TASK_BULLY_P0_SPINE_REDUCTION_V1.md` A6 / P0.5. `[GATE]`: this call was made
without a live operator sign-off in this run — flagged for review.

## Evidence gathered

```
grep -n "8931" config/portal.yaml
grep -rn "wiki_search|wiki_get_unit|wiki_explain|portal_wiki.mcp" --include=*.py portal/ \
  | grep -v "portal/platform/wiki|validation|test"
```

- `config/portal.yaml` registers `portal-wiki` at port 8931 with
  `expose_to_pipeline: true` and `expose_to_ide: true`.
- No `portal/` module outside `portal/platform/wiki/`, `scripts/validation/`,
  or `tests/` imports `portal_wiki.mcp` or calls `wiki_search` /
  `wiki_get_unit` / `wiki_explain`.
- No persona YAML (`config/personas/*.yaml`) wires the wiki MCP as an
  available tool for a workspace; the one persona whose name contains
  "wiki" (`codebasewikidocumentationskill.yaml`) is an unrelated LSP-based
  codebase-documentation generator with no reference to `portal_wiki` or the
  wiki MCP tools — a name collision, not a consumer.
- **The one real, live consumer**: `CLAUDE.md` Rule 13 ("Fact-Units Are the
  Discovery Index — Before grepping, query the wiki: `wiki_search` /
  `wiki_get_unit` / `wiki_explain`") and this build's own
  `TASK_BULLY_00_MASTER_V1.md` §13, both of which mandate that a Claude Code
  agent working this repository query the wiki MCP before cold-grepping. This
  is not a theoretical consumer — every phase of this build (P0 included) is
  executed by an agent operating under that instruction, with the
  `mcp__portal-wiki__*` tools live in the agent's toolset via
  `expose_to_ide: true`.

## Call: **KEEP**

Retiring the wiki MCP would sever the mandated agent-discovery workflow this
whole project (CLAUDE.md, and every `TASK_BULLY_*` file inheriting the
master's grounding contract) depends on. The single consumer is the Claude
Code agent/operator discovery path — not any Portal 5 runtime or pipeline
code path — noted here for future review: if that discovery contract is ever
retired from CLAUDE.md, the MCP retirement question should be revisited
against this record rather than re-derived from scratch.

No config change follows from this call: `config/portal.yaml`'s `wiki` MCP
fleet entry, `.mcp.json`'s `portal-wiki` server entry, and
`portal_wiki/wiki_mcp.py` are retained as-is.
