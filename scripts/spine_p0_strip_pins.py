"""P0.2 (A1) — mechanically strip `last_generated_commit:` frontmatter from
every live canonical unit. `portal_wiki/archive/*.md` is deliberately left
alone: the exit criteria only require the field gone "outside archive/
history" — archived units are frozen historical records.

YAML-parses every touched file after the edit to confirm it still round-trips
through `KnowledgeUnit.from_markdown`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_PIN_LINE_RE = re.compile(r"^last_generated_commit:.*\n", re.MULTILINE)


def strip_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    new_text, n = _PIN_LINE_RE.subn("", text, count=1)
    if n == 0:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT))
    from portal.platform.wiki.schema import KnowledgeUnit

    canonical = REPO_ROOT / "portal_wiki" / "canonical"
    changed = 0
    for path in sorted(canonical.glob("*.md")):
        if strip_file(path):
            changed += 1
            # Round-trip verify: parse must succeed and must not carry a pin.
            unit = KnowledgeUnit.from_markdown(path.read_text(encoding="utf-8"))
            assert not hasattr(unit, "last_generated_commit"), path
    print(f"stripped last_generated_commit from {changed} canonical unit(s)")
    remaining = [
        p
        for p in canonical.glob("*.md")
        if "last_generated_commit" in p.read_text(encoding="utf-8")
    ]
    if remaining:
        print(f"WARNING: {len(remaining)} file(s) still mention last_generated_commit:")
        for p in remaining[:10]:
            print(f"  {p}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
