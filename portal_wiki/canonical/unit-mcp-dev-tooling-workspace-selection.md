---
id: unit-mcp-dev-tooling-workspace-selection
kind: what
title: "MCP_DEV_TOOLING \u2014 Workspace selection"
sources:
- type: doc
  path: docs/MCP_DEV_TOOLING.md
  commit: 05e42ec2
  section: Workspace selection
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5750148
updated_at: 1784946220.5750148
---

```bash
opencode .                                          # default: portal/codingagentic (Laguna-XS.2 33B)
opencode . --model portal/agenticheavy              # heavy 80B MoE for complex multi-file refactors
opencode . --model portal/agenticlite               # AgentWorld 35B direct (lighter load, 45 t/s)
opencode . --model portal/auto-coding               # one-shot code generation (Qwen3-Coder 30B)
opencode . --model portal/auto-reasoning            # deep reasoning for architectural decisions
opencode . --model portal/auto-security             # defensive security code review
opencode . --model portal/pentestlead               # authorized penetration testing assistance
opencode . --model portal/purpleteamexec            # tool-calling security with live lab access
opencode . --model portal/auto-data                 # data science, SQL, analysis
opencode . --model portal/auto-research             # web-augmented research and summarization
```

**Migration table** (old alias picker key -> new picker key, `CLOSEOUT_ALIAS_REMOVAL.md`):

| Old (retired) | New |
|---|---|
| `auto-coding-agentic` | `codingagentic` (opencode default) |
| `auto-agentic` | `agenticheavy` |
| `auto-agentic-lite` | `agenticlite` |
| `auto-coding-uncensored` | `codinguncensored` |
| `auto-coding-uncensored-agentic` | `codinguncensoredagentic` |
| `auto-pentest` | `pentestlead` |
| `auto-redteam` | `pentester` |
| `auto-blueteam` | `blueteamdefender` |
| `auto-purpleteam` | `purpleteamlead` |
| `auto-purpleteam-exec` | `purpleteamexec` |
| `auto-security-uncensored` | `securityuncensored` |

`opencode . --model portal/auto-agentic-ornith` and `--model portal/auto-coding-northmini`
were never functional through opencode's `--model` flag (opencode rejects any model key not
declared in `opencode.jsonc`'s `provider.portal.models` block client-side, before the request
ever reaches the pipeline — verified live, `err: UnknownError`) — neither was ever one of the
20 curated picker entries. Ornith/North-Mini are reachable as `auto-coding` variants via
direct API (`?variant=ornith` / `?variant=northmini`) or OWUI, just not through opencode's
picker.

Run `opencode models` to list all available workspaces + curated personas (discovery is
driven by `GET /v1/models`, which now agrees with `opencode.jsonc` — see
`DESIGN_OPENCODE_ADDRESSING_V1.md` §3.2).
