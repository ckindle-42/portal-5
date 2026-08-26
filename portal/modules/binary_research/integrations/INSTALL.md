# Installing the binary-research trigger (agent-discovered)

You (the agent) are already running inside OpenCode or Claude Code / Pi, so you
know your own runtime better than any hardcoded path. **Discover** the correct
skills and commands directories for THIS runtime, then let the harness copy the
files in. Do not trust the example paths below as current — confirm them.

## 1. Identify the runtime
You already know which one you are; confirm from the environment:
- **OpenCode** — `command -v opencode` succeeds, an `~/.config/opencode/` or a
  project `.opencode/` dir exists, or `OPENCODE*` env vars are set.
- **Claude Code / Pi** — `command -v claude` succeeds, an `~/.claude/` or project
  `.claude/` dir exists, or `CLAUDE*` / `CLAUDECODE` env vars are set.

## 2. Discover the skills + commands directories
Don't hardcode. Find where THIS runtime loads skills and commands:
- Consult the runtime itself: `opencode --help` and the opencode config, or
  `claude --help` and the Claude Code config, for the skills/commands paths.
- Prefer the **project-local** dir when you're working inside a repo (the trigger
  travels with the project); otherwise the **user-global** dir.
- Examples to confirm (verify, don't trust): Claude Code → `~/.claude/skills/`,
  `~/.claude/commands/` (or `.claude/…` in-project); OpenCode →
  `~/.config/opencode/command/` (or `.opencode/command/`), plus OpenCode's
  configured skills path.
- If you cannot confirm a skills path, the command shim alone triggers the whole
  flow — install at least the command.

## 3. Install (the harness does the copy)
Once you've discovered the directories, hand them to the harness:
```bash
python -m portal.modules.binary_research.harness install-trigger \
  --skills-dir <discovered-skills-dir> \
  --commands-dir <discovered-commands-dir> \
  --dry-run          # inspect first; drop --dry-run to actually write
```
It copies the shipped `SKILL.md` → `<skills-dir>/binary-research/SKILL.md` and the
command shim → `<commands-dir>/binresearch.md`. Pass only the dir you found if you
found only one.

## 4. Verify
- `/binresearch` (and the `binary-research` skill) is now available in your runtime.
- Toolchain check: `python -m portal.modules.binary_research.harness preflight`
