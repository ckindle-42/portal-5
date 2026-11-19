---
id: unit-readme-cleanup
historical: true
kind: what
title: "README \u2014 Cleanup"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: Cleanup
confidence: high
tags:
- docs

---

./launch.sh clean           # Remove containers (keeps model weights)
./launch.sh clean-all       # Remove everything including models
./launch.sh rebuild         # Rebuild portal-pipeline Docker image after git pull
```

---
