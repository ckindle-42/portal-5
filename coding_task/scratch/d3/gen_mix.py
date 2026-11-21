"""Per-generator judge mix for any stored run dir (no Splunk, no network)."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


def report(path: Path) -> None:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    judged = [r for r in rows if r.get("p_yes") is not None]
    first = next((i for i, r in enumerate(rows) if r.get("p_yes") is None), len(rows))
    print(f"{path}\n  total {len(rows)} judged {len(judged)} judged-prefix {first}")
    per = defaultdict(lambda: {"n": 0, "judged": 0, "py": []})
    for i, r in enumerate(rows):
        gen = r.get("generator") or ""
        per[gen]["n"] += 1
        if i < first:
            per[gen]["judged"] += 1
        if r.get("p_yes") is not None:
            per[gen]["py"].append(float(r["p_yes"]))
    for gen, s in sorted(per.items(), key=lambda kv: -kv[1]["n"]):
        py = s["py"]
        yes = sum(1 for v in py if v >= 0.5) / len(py) if py else None
        print(
            f"  {gen:18s} n {s['n']:4d} judged {s['judged']:4d} mean_p {round(sum(py) / len(py), 3) if py else None} yes {None if yes is None else round(yes, 3)}"
        )
    # served model / answer text spread
    ans = defaultdict(int)
    for r in rows:
        j = r.get("judge") or {}
        ans[(j.get("served_model"), (j.get("answer") or "").strip()[:12])] += 1
    for k, v in sorted(ans.items(), key=lambda kv: -kv[1])[:6]:
        print("  answer", k, v)
    print(
        "  nearest_known present", sum(1 for r in rows if r.get("nearest_known")), "of", len(rows)
    )


for arg in sys.argv[1:]:
    report(Path(arg))
