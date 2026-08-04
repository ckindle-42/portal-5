---
id: unit-readme-cleanup
kind: what
title: "README \u2014 Cleanup"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: Cleanup
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.684323
updated_at: 1784946220.684323
---

./launch.sh clean           # Remove containers (keeps model weights)
./launch.sh clean-all       # Remove everything including models
./launch.sh rebuild         # Rebuild portal-pipeline Docker image after git pull
```

---
