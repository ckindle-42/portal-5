---
id: unit-readme-documentation
kind: what
title: "README \u2014 Documentation"
sources:
- type: code
  path: portal/platform/wiki/render.py
last_generated_commit: 97b85a5b4384209107aa2e6b3e7d009679ba5096
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.691113
updated_at: 1784946220.691113
---

The operator-facing manual is a set of reference docs at the repo root and under
`docs/`, all of which exist as tracked files:

| Guide | Contents |
|---|---|
| [MCP Dev Tooling](docs/MCP_DEV_TOOLING.md) | Claude Code & opencode integration, FastContext explorer, workflow examples |
| [How-To Guide](docs/HOWTO.md) | Working examples for every feature, including remote API access |
| [User Guide](docs/USER_GUIDE.md) | How to use workspaces, tools, personas |
| [Admin Guide](docs/ADMIN_GUIDE.md) | User management, configuration, security |
| [Alerts & Notifications](docs/ALERTS.md) | Operational alerts and daily summaries |
| [ComfyUI Setup](docs/COMFYUI_SETUP.md) | Image-model configuration and archived video status |
| [Fish Speech Setup](docs/FISH_SPEECH_SETUP.md) | Optional voice cloning TTS backend |
| [Cluster Scaling](docs/CLUSTER_SCALE.md) | Running multiple Ollama instances |
| [Agent Loop](docs/AGENT_LOOP.md) | Platform-core bounded agent loop (`portal/platform/agent/`), the `portal agent` CLI |
| [Backup & Restore](docs/BACKUP_RESTORE.md) | Data backup procedures |
| [Known Issues](KNOWN_ISSUES.md) | Current limitations and workarounds |

Most of these guides are generated shells whose substance lives in
`portal_wiki/canonical/` fact-units and is rendered into `<!-- WIKI:GENERATED -->`
blocks, so the docs stay current through `./launch.sh sync-config` rather than
hand edits.

## Why

The documentation is the operator contract, not a summary after the fact: the
guides cover exactly the surfaces the platform exposes (tooling, accounts, alerts,
media, clustering), so a new operator can find the answer for a feature without
reading source. Coupling the generated guides to wiki units means a doc cannot
silently drift from the config that produces it.
