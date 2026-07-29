---
id: unit-user-guide-workspaces
kind: what
title: "USER_GUIDE \u2014 Workspaces"
sources:
- type: doc
  path: docs/USER_GUIDE.md
  commit: 05e42ec2
  section: Workspaces
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.513955
updated_at: 1784946220.513955
---

Select your workspace from the model dropdown in the top bar. Each workspace
routes your request to the best-suited AI model for that task.

| Workspace | Best for |
|---|---|
| 🤖 Portal Auto Router | Not sure which to use — routes automatically |
| 💻 Portal Code Expert | Writing code, debugging, code review |
| ⚡ Portal Agentic Coder (Heavy) | Long-horizon multi-file agentic coding (Qwen3-Coder-Next 80B) |
| 🔒 Portal Security Analyst | Security questions, hardening guidance |
| 🔴 Portal Red Team | Offensive security, penetration testing |
| 🔵 Portal Blue Team | Incident response, threat detection, defense |
| ✍️ Portal Creative Writer | Stories, scripts, creative content |
| 🧠 Portal Deep Reasoner | Complex analysis, long reasoning chains |
| 🏛️ Portal Council Review | Evidence-backed review of decisions, plans, proposals, and policies |
| 📄 Portal Document Builder | Create Word/Excel/PowerPoint files |
| 🎬 Portal Video Creator | Shelved; hidden from the model dropdown and not currently in operation |
| 🎵 Portal Music Producer | Generate music and audio |
| 🔍 Portal Research Assistant | Research and information synthesis |
| 👁️ Portal Vision | Image analysis, visual tasks |
| 📊 Portal Data Analyst | Data analysis, statistics |
| 🔍 Portal SPL Engineer | Splunk SPL queries and detection searches |
| ⚖️ Portal Compliance Analyst | NERC CIP gap analysis, policy review, audit prep |
| 🧪 Portal Mistral Reasoner | Structured reasoning, strategic planning |

Council Review is opt-in because it runs three isolated reviewers and a final
synthesizer. Give it the goal, constraints, available evidence, and options or
artifact to review. It returns a code-determined recommendation, reviewer
participation, dissent, missing evidence, and next actions. A reviewer that
abstains or returns an invalid response does not silently shrink the quorum.
