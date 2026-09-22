#!/usr/bin/env python3
"""LOAD_AND_CONVERSE_V1 §P3.2 — propose links across the WHOLE family.

``build_links`` runs for every register standard revision, not only the ones a
past campaign or an autosync change happened to touch. Until now the only
producers were the campaigns (a handful of standards) and ``nerc_autosync``
(only standards whose lifecycle moved) — so most requirements never had a
proposal run at all, and *an absent proposal* was indistinguishable from *an
absence*. ``record_links`` now persists per-requirement absence
(``requirement_absence``, migration 19), so the census can tell the two apart.

The report is written incrementally, one standard at a time, in the same
``links`` shape the autosync emits, so ``diagnose_dead_standards.py
--links-report`` reads it unchanged.

    uv run python scripts/compliance/family_links.py
    uv run python scripts/compliance/family_links.py --standards CIP-002-5.1a,CIP-003-8
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core import candidate_links, section_index  # noqa: E402
from portal.modules.compliance.core.cip_register import Register  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402

DEFAULT_OUT = (
    REPO_ROOT / "reports" / "compliance" / "load_and_converse" / "p3" / "family_links.json"
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--standards", default="", help="comma-separated subset (default: all)")
    ap.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    ap.add_argument("--resume", action="store_true", help="skip standards already recorded")
    args = ap.parse_args()

    register = Register.load()
    all_standards = sorted({n.standard for n in register.nodes})
    if args.standards:
        wanted = {s.strip() for s in args.standards.split(",") if s.strip()}
        unknown = wanted - set(all_standards)
        if unknown:
            print(f"FAIL: not register standards: {sorted(unknown)}", file=sys.stderr)
            return 3
        standards = [s for s in all_standards if s in wanted]
    else:
        standards = all_standards

    links_report: dict[str, dict] = {}
    if args.resume and args.out.is_file():
        links_report = dict(json.loads(args.out.read_text()).get("links", {}))

    repo = Repository()
    try:
        # the population every absence claim is entitled to: the whole projected
        # operator corpus, not a window
        plan = section_index.build_plan(repo, jurisdiction="internal")
        receipt = section_index.boundary_receipt(repo, plan)
        print(
            f"boundary: {len(receipt['eligible_sections'])} eligible, "
            f"{len(receipt['examined_sections'])} examined, "
            f"complete={receipt['complete']}, corpus_whole={receipt['corpus_whole']}"
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)

        for std in standards:
            if args.resume and std in links_report:
                print(f"skip {std} (already recorded)")
                continue
            started = time.time()
            links = candidate_links.build_links(repo, std)
            payload = candidate_links.record_links(repo, links, boundary_receipt=receipt)
            payload["wall_s"] = round(time.time() - started, 1)
            links_report[std] = payload
            args.out.write_text(
                json.dumps(
                    {
                        "run_started_basis": "whole projected operator corpus (boundary receipt)",
                        "n_eligible_sections": len(receipt["eligible_sections"]),
                        "links": links_report,
                    },
                    indent=2,
                    default=str,
                )
                + "\n"
            )
            print(
                f"{std:16s} requirements={payload['requirements']:3d} "
                f"edges={payload['edges_recorded']:3d} "
                f"absent={len(payload['requirements_with_no_candidate']):3d} "
                f"{payload['wall_s']:6.1f}s"
            )
    finally:
        repo.close()
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
