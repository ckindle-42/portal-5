---
id: unit-claude-pre-testing-always-verify-code-freshness
kind: why
title: "CLAUDE.md \u2014 Pre-Testing: Always Verify Code Freshness"
sources:
- type: design
  path: CLAUDE.md
  section: 'Pre-Testing: Always Verify Code Freshness'
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1785348301.194371
updated_at: 1785348301.194371
---


**Before any testing, troubleshooting, or benchmark run**, verify that Docker containers are running the latest code from HEAD. Stale images silently invalidate results and cause false failures.

Check image build times against recent git commits:
```bash
docker images --format "table {{.Repository}}\t{{.CreatedAt}}" | grep portal
git log --oneline --format="%h %ai %s" -5
```

If any portal image predates a relevant commit (pipeline: `portal/platform/`, `config/`; MCP: `portal/modules/*/tools/`, `portal_mcp/`), rebuild first:
```bash
./launch.sh rebuild    # rebuilds pipeline + all MCP containers
```

The UAT driver, acceptance test v6, and bench_tps all print a freshness warning automatically at startup — if you see that warning, stop and rebuild before proceeding. Do not explain away stale-image failures as model or routing issues.
