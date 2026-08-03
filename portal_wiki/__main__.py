"""Portal Wiki CLI — one-command doc regeneration + maintenance.

Usage:
    python3 -m portal_wiki render --all        # regenerate all views
    python3 -m portal_wiki render --check      # drift gate (exit non-zero if drifted)
    python3 -m portal_wiki status              # wiki status report
    python3 -m portal_wiki propose --dry-run   # list proposed units
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path


def _hash_dir(d: Path) -> str:
    """Hash all files in a directory for change detection."""
    h = hashlib.sha256()
    for f in sorted(d.rglob("*")):
        if f.is_file():
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


def cmd_render(args: argparse.Namespace) -> int:
    """Render wiki views."""
    from portal.platform.wiki.adapters.git_source import GitSourceConnector
    from portal.platform.wiki.maintain import update_what_units
    from portal.platform.wiki.render import render_admin_guide, render_architecture_map
    from portal.platform.wiki.store import set_canonical_dir

    repo_root = Path(__file__).resolve().parent.parent
    canonical = repo_root / "portal_wiki" / "canonical"
    set_canonical_dir(canonical)

    gc = GitSourceConnector(repo_root)
    commit = gc.get_current_commit()

    # Registry of all views — add new renderers here
    views = {
        "admin_guide": render_admin_guide,
        "architecture_map": render_architecture_map,
    }

    if args.check:
        # Drift gate: render to temp dir, compare against committed
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for _name, renderer in views.items():
                renderer(tmp_path)

            # Compare
            generated = repo_root / "docs" / "generated"
            if not generated.exists():
                print("FAIL: docs/generated/ does not exist — run render --all first")
                return 1

            drifted = []
            for f in sorted(tmp_path.glob("*.md")):
                committed = generated / f.name
                if not committed.exists() or f.read_text() != committed.read_text():
                    drifted.append(f.name)

            if drifted:
                print(f"FAIL: docs drifted — {', '.join(drifted)}")
                print("Run: python3 -m portal_wiki render --all")
                return 1
            else:
                print("OK: docs/current")
                return 0

    # --all: regenerate everything
    if args.all:
        # Step 1: refresh what units from current HEAD
        print(f"Refreshing what units from HEAD {commit}...")
        updated = update_what_units(commit, dry_run=args.dry_run)
        print(f"  Updated {len(updated)} what units")

        # Step 2: render every registered view
        output = repo_root / "docs" / "generated"
        for name, renderer in views.items():
            print(f"Rendering {name}...")
            path = renderer(output)
            print(f"  → {path}")

        print(f"\nDone. {len(views)} views rendered to docs/generated/")
        return 0

    print("Usage: python3 -m portal_wiki render [--all|--check]")
    return 1


def cmd_status(args: argparse.Namespace) -> int:
    """Wiki status report."""
    from portal.platform.wiki.adapters.git_source import GitSourceConnector
    from portal.platform.wiki.maintain import wiki_status
    from portal.platform.wiki.store import set_canonical_dir

    repo_root = Path(__file__).resolve().parent.parent
    set_canonical_dir(repo_root / "portal_wiki" / "canonical")

    gc = GitSourceConnector(repo_root)
    commit = gc.get_current_commit()
    status = wiki_status(commit)

    print("Portal Wiki Status:")
    for k, v in status.items():
        print(f"  {k}: {v}")
    return 0


def cmd_drift(args: argparse.Namespace) -> int:
    """Drift census — the re-runnable form of the code-to-doc audit.

    Read-only unless `--pin-baseline` is passed. Exit code reflects the ratchet:
    non-zero when a claim fails or unbaselined drift exists, so this doubles as
    a pre-commit probe without going through the full validate harness.
    """
    import json as _json

    from portal.platform.wiki.claims import evaluate_claims
    from portal.platform.wiki.drift import (
        BASELINE_RELPATH,
        broken_path_refs,
        census,
        pin_health,
        render_baseline,
    )
    from portal.platform.wiki.store import load_all, set_canonical_dir

    repo_root = Path(__file__).resolve().parent.parent
    set_canonical_dir(repo_root / "portal_wiki" / "canonical")

    if args.pin_baseline:
        units = load_all()
        pins = pin_health(repo_root, units)
        refs = broken_path_refs(repo_root)
        target = repo_root / BASELINE_RELPATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_baseline(pins, refs), encoding="utf-8")
        print(f"Pinned baseline → {BASELINE_RELPATH}")
        print(
            f"  phantom_pins={len(pins.phantom)} unpinned={len(pins.unpinned)} "
            f"broken_refs={len(refs)}"
        )
        return 0

    report = census(repo_root)
    if args.json:
        print(_json.dumps(report, indent=2, default=str))
    else:
        print("Portal Wiki drift census")
        print(f"  units                 : {report['units_total']}")
        print(f"  generated doc blocks  : {report['generated_blocks']}")
        print(f"  claims declared       : {report['claims_declared']}")
        print(f"  claim violations      : {len(report['claim_violations'])}")
        for line in report["claim_violations"]:
            print(f"      ! {line}")
        pins = report["pins"]
        print(
            f"  pins                  : {pins['fresh']} fresh / {pins['stale']} stale / "
            f"{pins['phantom']} phantom / {pins['unpinned']} unpinned of {pins['total']}"
        )
        print(f"  broken doc path refs  : {len(report['broken_path_refs'])}")
        for line in report["broken_path_refs"]:
            print(f"      ! {line}")
        print(f"  undeclared numeric    : {report['undeclared_numeric_units']} unit(s) (debt)")
        for key, items in report["ratchet"].items():
            if items:
                print(f"  RATCHET {key}: {len(items)} unbaselined")
                for item in items[:10]:
                    print(f"      ! {item}")

    units = load_all()
    unbaselined = any(report["ratchet"].values())
    return 1 if (evaluate_claims(units, repo_root) or unbaselined) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Portal Wiki CLI")
    sub = parser.add_subparsers(dest="command")

    # render
    render_p = sub.add_parser("render", help="Regenerate wiki views")
    render_p.add_argument("--all", action="store_true", help="Regenerate all views")
    render_p.add_argument(
        "--check", action="store_true", help="Drift gate (exit non-zero if drifted)"
    )
    render_p.add_argument("--dry-run", action="store_true", help="Dry run (no writes)")

    # status
    sub.add_parser("status", help="Wiki status report")

    # drift
    drift_p = sub.add_parser("drift", help="Drift census: claims, pins, doc path refs")
    drift_p.add_argument("--json", action="store_true", help="Emit the raw census as JSON")
    drift_p.add_argument(
        "--pin-baseline",
        action="store_true",
        help="Rewrite config/spine_drift_baseline.yaml from current findings",
    )

    args = parser.parse_args()

    if args.command == "render":
        return cmd_render(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "drift":
        return cmd_drift(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
