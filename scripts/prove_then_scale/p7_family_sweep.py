"""PROVE_THEN_SCALE_V1 §P7 — the family sweep, in dependency order.

Runs the map reading over every register requirement, standards in the
recorded dependency order (:data:`sweep.STANDARD_ORDER`), within a standard in
the standard's own numbering. Per standard it records: requirements read,
determinations written, corroborations, rejections, wall time, and the cache
behaviour at the standard boundary (each standard's first call re-prefills its
own fixed body; within it, the shared body holds).

Sequential, single operator, no concurrent traffic. Total wall time is the
number that says whether 255 requirements is an overnight job or a coffee
break, and the per-requirement cost is the number that scales to the cluster.

Usage: uv run python scripts/prove_then_scale/p7_family_sweep.py [--only CIP-007-6]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core import sweep  # noqa: E402
from portal.modules.compliance.core.cip_register import Register  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402

ART = REPO_ROOT / "reports" / "compliance" / "prove_then_scale" / "p7_family_sweep.json"

SEAT = "gemma4:26b-a4b-it-q4_K_M-ctx32k"


def revisions_in_order() -> list[str]:
    """The register's standard revisions, as revision ids, in family dependency
    order. A family with several revisions in the register sweeps each — the
    register is the requirement universe, and a revision the register carries
    is a revision the operator owns."""
    reg = Register.load()
    revisions: list[str] = []
    for family, _reason in sweep.STANDARD_ORDER:
        revs = sorted(
            {
                n.id.split(" ")[0]
                for n in reg.nodes
                if n.id.split(" ")[0].rsplit("-", 1)[0] == family
            }
        )
        revisions.extend(revs)
    seen_families = {r.rsplit("-", 1)[0] for r in revisions}
    for rev in sorted({n.id.split(" ")[0] for n in reg.nodes}):
        if rev.rsplit("-", 1)[0] not in seen_families:
            revisions.append(rev)
    return revisions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="", help="sweep one standard revision (resume aid)")
    args = parser.parse_args()

    existing: dict = {}
    if ART.exists():
        existing = json.loads(ART.read_text())
    done = {s["standard"] for s in existing.get("standards", []) if not s.get("error")}

    revisions = [args.only] if args.only else revisions_in_order()
    repo = Repository()
    standards: list[dict] = list(existing.get("standards", []))
    try:
        started = time.time()
        for revision in revisions:
            if revision in done:
                print(f"skip {revision} (already recorded)")
                continue
            print(f"== {revision} ==")
            summary = sweep.sweep_standard(repo, revision, model=SEAT, write=True)
            standards.append(summary)
            ART.write_text(
                json.dumps(
                    {
                        "seat": SEAT,
                        "order": [s for s, _ in sweep.STANDARD_ORDER],
                        "standards": standards,
                        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    },
                    indent=2,
                    default=str,
                )
            )
            if "error" in summary:
                print(f"  ERROR: {summary['error']}")
                continue
            print(
                f"  {summary['n_requirements']} requirements, {summary['total_wall_s']} s, "
                f"determined {summary['determined']}, corroborated {summary['corroborated']}, "
                f"cache collapse x{summary['cache_collapse_ratio']}"
            )
        total_wall = sum(s.get("total_wall_s", 0) for s in standards if not s.get("error"))
        n_reqs = sum(s.get("n_requirements", 0) for s in standards if not s.get("error"))
        print(
            f"\nfamily so far: {n_reqs} requirements, {total_wall:.0f} s total, "
            f"{(total_wall / n_reqs if n_reqs else 0):.1f} s/requirement"
        )
    finally:
        repo.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
