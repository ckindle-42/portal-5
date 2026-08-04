---
id: unit-LAB_SETUP-on-demand-targets-from-lab-targets-yaml
kind: why
title: "LAB_SETUP \u2014 On-Demand Targets (from lab_targets.yaml)"
sources:
- type: design
  path: docs/LAB_SETUP.md
  section: On-Demand Targets (from lab_targets.yaml)
last_generated_commit: ''
confidence: high
tags:
- docs
- LAB_SETUP
created_at: 1783195000.868694
updated_at: 1783195000.868694
---


```bash
./launch.sh lab-targets list                                           # show catalog
./launch.sh lab-targets up vulhub-log4shell-solr                       # by catalog id
./launch.sh lab-targets up struts2/s2-045                              # by raw vulhub path
./launch.sh lab-targets ephemeral vulhub-log4shell-solr -- <bench cmd> # up → bench → down
./launch.sh lab-targets down vulhub-log4shell-solr
./launch.sh lab-targets status
```
