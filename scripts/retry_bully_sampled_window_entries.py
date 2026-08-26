"""One-shot checkpoint surgery: drop the H5 sweep entries that ended in a
SampledWindowError so the next `run_bully_hunt_sweep_h5.sh` resume re-attempts
exactly those (and only those) under the new escalating-backoff retry
(b93f8ba6), instead of skipping them forever as "already done".

`EntryProgress.record()` marks an entry done even when its result carries an
`error` -- by design, so a crash mid-run never loses a graded entry -- but
that also means a resumed run will never retry a recorded error on its own.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

CHECKPOINT_PATH = Path("/tmp/bully_full_assembly_f4_checkpoint.json")

FAILED = {
    ("botsv3", "T1005"),
    ("botsv2", "T1566.001"),
    ("botsv2", "T1071.001"),
    ("botsv2", "T1053.005"),
    ("botsv2", "T1486"),
    ("botsv2", "T1190"),
    ("botsv2", "T1059.001"),
    ("botsv2", "T1091"),
    ("botsv2", "T1583.001"),
    ("botsv2", "T1005"),
}


def _matches(key: str) -> bool:
    dataset, technique, _entities = key.split(":", 2)
    return (dataset, technique) in FAILED


def main() -> int:
    if not CHECKPOINT_PATH.exists():
        print(f"no checkpoint at {CHECKPOINT_PATH}", file=sys.stderr)
        return 1

    backup = CHECKPOINT_PATH.with_suffix(".json.pre_retry_backup")
    shutil.copy2(CHECKPOINT_PATH, backup)
    print(f"backed up checkpoint to {backup}")

    data = json.loads(CHECKPOINT_PATH.read_text())
    before = len(data["hunt_entries_done"])
    dropped = [k for k in data["hunt_entries_done"] if _matches(k)]
    data["hunt_entries_done"] = [k for k in data["hunt_entries_done"] if not _matches(k)]
    data["hunt_results"] = [
        r for r in data["hunt_results"] if (r.get("dataset"), r.get("technique")) not in FAILED
    ]
    CHECKPOINT_PATH.write_text(json.dumps(data, indent=2))
    print(f"dropped {len(dropped)} of {before} done entries; {len(dropped)} will be re-attempted:")
    for k in dropped:
        print(f"  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
