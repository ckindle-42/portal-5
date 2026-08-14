"""P0.3 (A4) — strip RELEASE `WIKI:GENERATED` fence markers back to plain
prose (body untouched). AW no longer governs the result. Idempotent."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def collapse_release_blocks(release_ids: set[str], repo_root: Path | None = None) -> dict:
    """Strip fence markers for `release_ids`; returns {doc: [ids collapsed]}."""
    sys.path.insert(0, str(repo_root or REPO_ROOT))
    from portal.platform.wiki.render import TIER1_DOCS

    root = repo_root or REPO_ROOT
    result: dict[str, list[str]] = {}
    for rel in TIER1_DOCS:
        p = root / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        original = text
        collapsed_here: list[str] = []
        for uid in sorted(release_ids):
            start = f"<!-- WIKI:GENERATED unit={uid} -->"
            end = "<!-- /WIKI:GENERATED -->"
            pattern = re.compile(
                re.escape(start) + r"\n(.*?)\n" + re.escape(end),
                re.DOTALL,
            )
            # count=0: a unit's block can legitimately repeat in one doc.
            new_text, n = pattern.subn(lambda m: m.group(1), text, count=0)
            if n:
                text = new_text
                collapsed_here.append(uid)
        if text != original:
            p.write_text(text, encoding="utf-8")
            result[rel] = collapsed_here
    return result


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.spine_p0_manifest import classify

    result = classify(REPO_ROOT)
    release_ids = set(result["release"])
    changed = collapse_release_blocks(release_ids, REPO_ROOT)
    total_blocks = sum(len(v) for v in changed.values())
    print(f"collapsed {total_blocks} RELEASE block(s) across {len(changed)} doc(s)")
    for rel, ids in sorted(changed.items()):
        print(f"  {rel}: {len(ids)} block(s)")
