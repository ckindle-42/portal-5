---
id: unit-claude-checkpoint-backup-discipline-non-negotiable
kind: why
title: "CLAUDE.md \u2014 Checkpoint Backup Discipline \u2014 Non-Negotiable"
sources:
- type: design
  path: CLAUDE.md
  section: "Checkpoint Backup Discipline \u2014 Non-Negotiable"
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1785348301.1943738
updated_at: 1785348301.1943738
---


**Multi-hour bench/sweep checkpoint files (e.g. `/tmp/agentic_blue_sweep.json`) must be backed up before they are ever cleared, deleted, or overwritten — no exceptions, not even "I already reported the numbers in chat."** A `cp checkpoint.json checkpoint_$(date +%Y%m%dT%H%M%S).json.bak` costs nothing; re-running a 20-scenario × 3-trial sweep across several models costs hours. This applies whenever you are about to:
- `rm`/overwrite a checkpoint to seed a fresh run
- Launch a new sweep that reuses the same output path as a just-completed one
- Any point where the next command could destroy data from a run that took more than a few minutes to produce

The failure mode this guards against: backing up *some* runs and not others out of momentum or urgency, then losing exactly the run you didn't back up. Treat the backup step as part of the launch sequence itself (write it into the same command block that clears the old checkpoint), not a separate judgment call to remember. If you skip it and then need to clear the checkpoint, back it up in that same moment before proceeding — never clear first and back up "after."

---
