---
id: unit-mcp-dev-tooling-2-export-the-pipeline-api-key-into-the-environment
kind: what
title: "MCP_DEV_TOOLING \u2014 2. Export the pipeline API key into the environment"
sources:
- type: doc
  path: docs/MCP_DEV_TOOLING.md
  commit: 05e42ec2
  section: 2. Export the pipeline API key into the environment
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.574263
updated_at: 1784946220.574263
---

export $(grep PIPELINE_API_KEY .env | xargs)
