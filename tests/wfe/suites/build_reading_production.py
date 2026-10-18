"""Build tests/wfe/suites/reading_production.jsonl, compliance-reading's narrow suite
(WFE P3 triage §7; master plan S8/O5).

The same planted-corpus determinations and register lookups auto-compliance measures,
mixed for the reading seat over its reading tool subset — NO new gold: the
determinations come from build_compliance_production.determinations() (the PLANT keys
remain the gold, forbidden in tool output), the lookups from build_compliance_production
.lookups(). 12 tasks, 4 in the screen tier, kinds determination (6) / lookup (6):

- determination (6)  covered, hole, tier-conflict, applicability (the four screen
                     classes) plus aspirational and temporal;
- lookup (6)         requirement parts whose verbatim text sets exactly one interval.

Two suite-wide lessons are enforced by tests, not just intended:
- files are never named as sentence-openers ("In terms.docx, ..." — a seat read that
  as the filename). Every instruction names a document as "the operator corpus
  document <id>", never "In <id>,";
- numeric expectations are anchored: a lookup's interval is graded inside its
  "interval" key WITH its unit ("35 calendar days"), never as a bare-substring digit.

    uv run python tests/wfe/suites/build_reading_production.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.wfe.suites import build_compliance_production as comp

OUT = Path(__file__).with_name("reading_production.jsonl")
#: The determination control classes the narrow suite carries, in order; the first two
#: screen. The remaining planted classes (deontic, cross-reference, future-effective,
#: implicit-change) stay in auto-compliance's full suite.
DET_CLASSES = ("covered", "hole", "tier-conflict", "applicability", "aspirational", "temporal")
DET_SCREEN = 2
LOOKUPS = 6
LOOKUP_SCREEN = 2
LANE = "reading"


def build() -> list[dict]:
    tasks: list[dict] = []
    by_class: dict[str, dict] = {}
    for t in comp.determinations():
        seg = t["id"].split("-det-", 1)[1]
        cls = next((c for c in DET_CLASSES if seg == c or seg.startswith(c + "-")), None)
        if cls:
            by_class.setdefault(cls, t)
    missing = [c for c in DET_CLASSES if c not in by_class]
    if missing:
        raise RuntimeError(f"planted corpus lacks determination classes: {missing}")
    for n, cls in enumerate(DET_CLASSES):
        t = dict(by_class[cls])
        t.update(
            {
                "id": f"read-det-{cls}-{n:02d}",
                "lane": LANE,
                "screen": n < DET_SCREEN,
            }
        )
        tasks.append(t)
    for n, t in enumerate(comp.lookups(LOOKUPS)):
        t = dict(t)
        rid = t["id"].removeprefix("comp-prod-lookup-")
        t.update({"id": f"read-lookup-{n:02d}-{rid}", "lane": LANE, "screen": n < LOOKUP_SCREEN})
        tasks.append(t)
    for t in tasks:
        if missing := comp.undefined_values(t["instruction"]):
            raise RuntimeError(f"{t['id']}: answer values used but not defined: {missing}")
        # the documents-suite lesson: a document is never a sentence-opener
        if re.search(r"(?:^|[.\n]\s*)In [A-Z0-9][A-Z0-9._-]*\s*[,\u2014]", t["instruction"]):
            raise RuntimeError(f"{t['id']}: instruction opens a sentence with 'In <file>,'")
    tasks.sort(key=lambda t: not t["screen"])
    return tasks


def main() -> None:
    tasks = build()
    OUT.write_text("".join(json.dumps(t) + "\n" for t in tasks))
    print(f"wrote {OUT.name}: {len(tasks)} tasks, {sum(t['screen'] for t in tasks)} screen")


if __name__ == "__main__":
    main()
