# Portal 5 — Branch Consolidation & Git Policy

## Current State (as of review)

```
Remote branches:
  origin/main                    ← canonical, HEAD
  origin/feature/complete-buildout  ← merged (PR #2, PR #3 both merged)
  origin/fix/launch-gaps            ← merged (PR #1 merged)
```

Both remote branches are fully merged into main. They contain no unique commits.

---

## Immediate Cleanup (run these now)

```bash
cd /path/to/portal-5
git checkout main
git pull origin main

# Verify both branches are fully merged (no unique commits)
echo "=== feature/complete-buildout unique commits ==="
git log main..origin/feature/complete-buildout --oneline
# Expected: no output (fully merged)

echo "=== fix/launch-gaps unique commits ==="
git log main..origin/fix/launch-gaps --oneline
# Expected: no output (fully merged)

# Delete remote branches
git push origin --delete feature/complete-buildout
git push origin --delete fix/launch-gaps

# Clean up local tracking refs
git remote prune origin
git branch -a

# Expected final output:
# * main
#   remotes/origin/HEAD -> origin/main
#   remotes/origin/main
```

---

## Git Policy Going Forward

### During Stabilization (now → v5.0 stable tag)

**Work exclusively in main.** No feature branches. No fix branches.

```bash
# Correct workflow:
git checkout main
git pull origin main
# make changes
git add -A
git commit -m "fix(type): description"
git push origin main
```

Every commit goes directly to main. This keeps the history linear and makes
the review agents' delta runs accurate — they read git log to understand what
changed.

**Commit message format:**
```
type(scope): short description

Types: feat, fix, chore, docs, test, refactor
Scope: pipeline, mcp, compose, launch, docs, init, personas, tests, config

Examples:
  fix(pipeline): correct semaphore _value access to use locked()
  feat(launch): add restart command for individual services
  docs(readme): update workspace table to 13 entries
  test(pipeline): add workspace consistency test for 3-source check
  chore(branches): delete merged feature/* and fix/* branches
```

### When v5.0 Is Stable

After the review agents give a clean bill of health and the release is tagged:

```bash
# Tag the stable release
git tag -a v5.0.0 -m "Portal 5.0.0 — stable release"
git push origin v5.0.0

# Create dev branch for new feature work
git checkout -b dev
git push origin dev

# From this point, new features go in dev:
git checkout dev
# make feature changes
git add -A && git commit -m "feat(scope): description"
git push origin dev
# When ready: open PR dev → main
```

### Mature Workflow (post-v5.0)

```
main  ← stable, tagged releases, PRs from dev only
dev   ← active development, PRs from feature/* branches
feature/*  ← individual features, branched from dev
```

Never commit directly to main after v5.0 is tagged.
Always PR with at least one review before merging to main.

---

## CLAUDE.md Update Required

Add this section to `CLAUDE.md` under a new `## Git Workflow` heading:

```markdown
## Git Workflow

### During Stabilization (now)
- **Work in main only** — no branches until v5.0 stable tag
- Every commit directly to main via push
- Run tests before every push: `pytest tests/ -q --tb=no`
- Commit format: `type(scope): description`

### After v5.0 Tagged
- main = stable releases only (PRs from dev)
- dev = active work (default branch)
- feature/* = individual features (PRs to dev)

### Never
- Never force push
- Never commit .env
- Never commit pyproject.toml changes that add cloud/external deps
- Never modify Open WebUI source code
```
