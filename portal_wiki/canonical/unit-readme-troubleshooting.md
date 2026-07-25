---
id: unit-readme-troubleshooting
kind: what
title: "README \u2014 Troubleshooting"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: Troubleshooting
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.688112
updated_at: 1784946220.688112
---

**Services not starting:**
```bash
./launch.sh status          # See which services failed
docker compose -f deploy/portal-5/docker-compose.yml logs <service-name>
```

**Out of disk space:**
```bash
docker system df            # See Docker disk usage
./launch.sh clean           # Remove containers
