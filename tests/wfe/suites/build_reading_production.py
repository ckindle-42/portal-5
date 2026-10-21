"""Build tests/wfe/suites/reading_production.jsonl, auto-compliance::reading's narrow suite
(WFE P3 triage §7; master plan S8/O5).

The same planted-corpus determinations and register lookups auto-compliance measures,
mixed for the reading seat over its reading tool subset — NO new gold: the
determinations come from build_compliance_production.determinations() (the PLANT keys
remain the gold, forbidden in tool output), the lookups from build_compliance_production
.lookups(). 36 tasks, 12 in the screen tier, kinds determination (12) / lookup (24):

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
from tests.wfe.suites._publish import publish_text

OUT = Path(__file__).with_name("reading_production.jsonl")
#: ALL TWELVE planted determinations and ALL TWENTY-FOUR register lookups the
#: compliance generator yields — 36 tasks, no padding needed: the planted corpus and
#: the register's single-interval parts are exactly that deep. The four screen
#: classes screen; the first eight lookups screen.
DET_SCREEN_CLASSES = ("covered", "hole", "tier-conflict", "applicability")
LOOKUPS = 24
LOOKUP_SCREEN = 8
LANE = "reading"


def build() -> list[dict]:
    tasks: list[dict] = []
    screened: set[str] = set()
    for t in comp.determinations():
        seg = t["id"].split("-det-", 1)[1]
        cls = next((c for c in DET_SCREEN_CLASSES if seg == c or seg.startswith(c + "-")), None)
        screen = False
        if cls and cls not in screened:
            screened.add(cls)
            screen = True  # exactly one screen row per screen class: four in all
        n = len(tasks)
        tasks.append(dict(t, id=f"read-det-{n:02d}-{seg}", lane=LANE, screen=screen))
    if sum(t["screen"] for t in tasks if t["kind"] == "determination") != len(DET_SCREEN_CLASSES):
        raise RuntimeError("the four screen classes did not all land in the suite")
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
    if len(tasks) != 36:
        raise RuntimeError(f"expected 36 tasks (12 determinations + 24 lookups), got {len(tasks)}")
    tasks.sort(key=lambda t: not t["screen"])
    return tasks


def main() -> None:
    tasks = build()
    publish_text(OUT, "".join(json.dumps(t) + "\n" for t in tasks))
    print(f"wrote {OUT.name}: {len(tasks)} tasks, {sum(t['screen'] for t in tasks)} screen")


if __name__ == "__main__":
    main()
