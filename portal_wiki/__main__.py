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
    from portal_wiki.adapters.git_source import GitSourceConnector
    from portal_wiki.core.maintain import update_what_units
    from portal_wiki.core.render import render_admin_guide, render_architecture_map
    from portal_wiki.core.store import set_canonical_dir

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
            for name, renderer in views.items():
                renderer(tmp_path)

            # Compare
            generated = repo_root / "docs" / "generated"
            if not generated.exists():
                print("FAIL: docs/generated/ does not exist — run render --all first")
                return 1

            drifted = []
            for f in sorted(tmp_path.glob("*.md")):
                committed = generated / f.name
                if not committed.exists():
                    drifted.append(f.name)
                elif f.read_text() != committed.read_text():
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
    from portal_wiki.adapters.git_source import GitSourceConnector
    from portal_wiki.core.maintain import wiki_status
    from portal_wiki.core.store import set_canonical_dir

    repo_root = Path(__file__).resolve().parent.parent
    set_canonical_dir(repo_root / "portal_wiki" / "canonical")

    gc = GitSourceConnector(repo_root)
    commit = gc.get_current_commit()
    status = wiki_status(commit)

    print("Portal Wiki Status:")
    for k, v in status.items():
        print(f"  {k}: {v}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Portal Wiki CLI")
    sub = parser.add_subparsers(dest="command")

    # render
    render_p = sub.add_parser("render", help="Regenerate wiki views")
    render_p.add_argument("--all", action="store_true", help="Regenerate all views")
    render_p.add_argument("--check", action="store_true", help="Drift gate (exit non-zero if drifted)")
    render_p.add_argument("--dry-run", action="store_true", help="Dry run (no writes)")

    # status
    sub.add_parser("status", help="Wiki status report")

    args = parser.parse_args()

    if args.command == "render":
        return cmd_render(args)
    elif args.command == "status":
        return cmd_status(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
