---
id: unit-lab-setup-on-demand-targets-from-lab-targets-yaml
kind: what
title: "LAB_SETUP \u2014 On-Demand Targets (from lab_targets.yaml)"
sources:
- type: doc
  path: docs/LAB_SETUP.md
  commit: 05e42ec2
  section: On-Demand Targets (from lab_targets.yaml)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.520446
updated_at: 1784946220.520446
---

```bash
./launch.sh lab-targets list                                           # show catalog
./launch.sh lab-targets up vulhub-log4shell-solr                       # by catalog id
./launch.sh lab-targets up struts2/s2-045                              # by raw vulhub path
./launch.sh lab-targets ephemeral vulhub-log4shell-solr -- <bench cmd> # up → bench → down
./launch.sh lab-targets down vulhub-log4shell-solr
./launch.sh lab-targets status
```
