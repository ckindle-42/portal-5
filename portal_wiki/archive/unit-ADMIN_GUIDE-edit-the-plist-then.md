---
id: unit-ADMIN_GUIDE-edit-the-plist-then
historical: true
kind: why
title: "ADMIN_GUIDE \u2014 Edit the plist, then:"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: 'Edit the plist, then:'
confidence: high
tags:
- docs
- ADMIN_GUIDE

---

launchctl unload ~/Library/LaunchAgents/homebrew.mxcl.ollama.plist
launchctl load  ~/Library/LaunchAgents/homebrew.mxcl.ollama.plist
