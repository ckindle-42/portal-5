"""Portal Wiki CLI — one-command doc regeneration + maintenance.

Usage:
    python3 -m portal_wiki render --all        # regenerate all views
    python3 -m portal_wiki render --check      # drift gate (exit non-zero if drifted)
    python3 -m portal_wiki status              # wiki status report
    python3 -m portal_wiki propose --dry-run   # list proposed units
    python3 -m portal_wiki archive <unit-id> --reason "<text>"
                                               # archive a unit (retained on disk)
    python3 -m portal_wiki archive --check     # archived units unreachable?
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
        # Step 1: refresh what units from current HEAD. This re-derives every
        # WHAT unit from live seeders, not just units related to your task —
        # a seeder/mapping drift unrelated to your change can rewrite dozens
        # of units at once (see unit-wiki-maintain "Gotchas"). Use `render
        # --check` instead if you only need to verify doc currency, and
        # review this diff in full — never `git add -A` — before committing.
        print(f"Refreshing what units from HEAD {commit}...")
        print("  WARNING: rewrites every WHAT unit whose live derivation differs from")
        print("  what's stored, whether or not it relates to your current task.")
        print("  Review the resulting diff in full before staging anything.")
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

    Read-only. Exit code reflects the absolute gate: non-zero when a claim
    fails or a dead doc ref exists, so this doubles as a pre-commit probe
    without going through the full validate harness. There is no baseline
    to tolerate drift. (P0 A1 removed the pin axis this used to also gate on.)
    """
    import json as _json

    from portal.platform.wiki.claims import evaluate_claims
    from portal.platform.wiki.drift import broken_path_refs, census
    from portal.platform.wiki.store import load_all, set_canonical_dir

    repo_root = Path(__file__).resolve().parent.parent
    set_canonical_dir(repo_root / "portal_wiki" / "canonical")

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
        print(f"  broken doc path refs  : {len(report['broken_path_refs'])}")
        for line in report["broken_path_refs"]:
            print(f"      ! {line}")
        print(f"  undeclared numeric    : {report['undeclared_numeric_units']} unit(s) (debt)")

    units = load_all()
    refs = broken_path_refs(repo_root)
    dirty = evaluate_claims(units, repo_root) or refs
    return 1 if dirty else 0


def cmd_archive(args: argparse.Namespace) -> int:
    """Archive a live unit, or verify archived units are unreachable.

    Archive moves the unit file to `portal_wiki/archive/` and appends a
    reasoned line to `portal_wiki/archive/INDEX.md`. Preconditions are
    enforced here, not trusted to the operator: a reason is required, no
    doc block may reference the id, no live unit may link it, and no cited
    source may be a live code/config path (overridable only via
    `--superseded-by` with a verified survivor).
    """
    from portal.platform.wiki.archive import archive_reachability, archive_unit
    from portal.platform.wiki.store import reset_canonical_dir, set_canonical_dir

    repo_root = Path(__file__).resolve().parent.parent
    set_canonical_dir(repo_root / "portal_wiki" / "canonical")

    if args.check:
        violations = archive_reachability(repo_root)
        if violations:
            print(f"FAIL: {len(violations)} archived unit(s) reachable from the live store")
            for v in violations:
                print(f"  ! {v}")
            reset_canonical_dir()
            return 1
        print("OK: no live unit or doc block references an archived unit")
        reset_canonical_dir()
        return 0

    if not args.unit_id:
        print("Usage: python3 -m portal_wiki archive <unit-id> --reason <text>")
        reset_canonical_dir()
        return 2

    ok, msg = archive_unit(
        args.unit_id,
        args.reason,
        repo_root,
        superseded_by=args.superseded_by,
    )
    print(msg if ok else f"refused: {msg}")
    reset_canonical_dir()
    return 0 if ok else 1


def cmd_re_ground(args: argparse.Namespace) -> int:
    """Re-ground a unit: replace its sources with verified code/config paths,
    tag verified-v1, and refuse to save unless the quality gate passes. This
    is the mechanical half of TASK_WIKI_ZERO_DEBT_V1 Phase 3 — the operator
    still reads the code; this command proves the result is re-sourced and
    gate-clean. (P0 A1 removed the pin this command used to also stamp.)
    """
    from portal.platform.wiki.quality import assess
    from portal.platform.wiki.schema import SourceRef
    from portal.platform.wiki.store import (
        load_unit,
        reset_canonical_dir,
        save_unit,
        set_canonical_dir,
    )

    repo_root = Path(__file__).resolve().parent.parent
    set_canonical_dir(repo_root / "portal_wiki" / "canonical")
    import subprocess as _sp

    unit = load_unit(args.unit_id)
    if unit is None:
        print(f"no live unit {args.unit_id}")
        reset_canonical_dir()
        return 2

    if not args.source:
        print(
            "Usage: python3 -m portal_wiki re-ground <unit-id> --source <path> [--source <path>...]"
        )
        reset_canonical_dir()
        return 2

    new_sources = []
    for raw in args.source:
        path = raw.split("#", 1)[0].strip()
        if path.startswith(("http://", "https://", "/")):
            print(f"refused: {raw} is not a repo-relative path")
            reset_canonical_dir()
            return 1
        if not (repo_root / path).exists():
            print(f"refused: source {path} does not exist")
            reset_canonical_dir()
            return 1
        new_sources.append(SourceRef(type="code", path=raw))

    head_sha = _sp.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True
    ).stdout.strip()
    unit.sources = new_sources
    tags = [t for t in (unit.tags or []) if t not in ("authored-v1", "verified-v1")]
    tags.append("verified-v1")
    unit.tags = sorted(set(tags))

    issues = list(assess([unit], repo_root).issues)
    if issues:
        print(f"refused: {len(issues)} quality issue(s) — fix the body")
        for i in issues[:10]:
            print(f"  ! {i}")
        reset_canonical_dir()
        return 1

    save_unit(unit)
    print(f"re-grounded {args.unit_id} @ {head_sha[:8]} ({len(new_sources)} code source(s))")
    reset_canonical_dir()
    return 0


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
    drift_p = sub.add_parser("drift", help="Drift census: claims, doc path refs")
    drift_p.add_argument("--json", action="store_true", help="Emit the raw census as JSON")

    # archive
    archive_p = sub.add_parser(
        "archive", help="Archive a unit (retained on disk) or check reachability"
    )
    archive_p.add_argument("unit_id", nargs="?", help="Unit id to archive")
    archive_p.add_argument("--reason", default="", help="Reason, phrased as a fact")
    archive_p.add_argument(
        "--superseded-by",
        default=None,
        help="Survivor unit that cites every code path of the archived unit",
    )
    archive_p.add_argument(
        "--check",
        action="store_true",
        help="Verify no live unit or doc block references an archived unit",
    )

    # re-ground
    rg_p = sub.add_parser("re-ground", help="Re-source a unit to code/config, tag verified-v1")
    rg_p.add_argument("unit_id", help="Unit id to re-ground")
    rg_p.add_argument(
        "--source", action="append", default=[], help="Code/config source path (repeatable)"
    )

    args = parser.parse_args()

    if args.command == "render":
        return cmd_render(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "drift":
        return cmd_drift(args)
    elif args.command == "archive":
        return cmd_archive(args)
    elif args.command == "re-ground":
        return cmd_re_ground(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
