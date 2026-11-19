---
id: unit-readme-update-single-command-git-pull-rebuild-model-refresh-re-seed
historical: true
kind: what
title: "README \u2014 Update (single command: git pull + rebuild + model refresh +\
  \ re-seed)"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: 'Update (single command: git pull + rebuild + model refresh + re-seed)'
confidence: high
tags:
- docs

---

./launch.sh update                  # Full update of all components
./launch.sh update --skip-models    # Skip Ollama + MLX model refresh (faster)
./launch.sh update --models-only    # Only refresh models
