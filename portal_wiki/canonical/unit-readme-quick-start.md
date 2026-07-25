---
id: unit-readme-quick-start
kind: what
title: "README \u2014 Quick Start"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: Quick Start
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.678459
updated_at: 1784946220.678459
---

```bash
git clone https://github.com/ckindle-42/portal-5.git
cd portal-5
./launch.sh up
```

**First run pulls ~16 GB of data and takes 10–45 minutes depending on your
connection.** You will see progress in the terminal. When it finishes:

```
[portal-5] ✅ Stack is ready
[portal-5] Web UI:     http://localhost:8080
[portal-5] Grafana:    http://localhost:3000
[portal-5] Admin creds saved to: .env (do not commit this file)
```

Open **http://localhost:8080** and sign in with the admin credentials printed to
your terminal.

---
