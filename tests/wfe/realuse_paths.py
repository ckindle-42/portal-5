"""Stage realuse_v1 fixtures at the path the prompt names, and refuse a campaign that cannot."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

CHECKOUT = Path(__file__).resolve().parents[2]
_TREE_PREFIX = "tests/fixtures/realuse_v1/"
_UPLOAD_PREFIX = "/workspace/uploads/realuse_v1/"
_REPO_PREFIX = "fixtures/realuse_v1/"
_NAMED = re.compile(r"(?:/workspace/uploads/realuse_v1/|fixtures/realuse_v1/)[A-Za-z0-9_./-]+")


def _unsafe(rel: str) -> bool:
    return (not rel) or rel.startswith("/") or any(part in {".", ".."} for part in Path(rel).parts)


def _inside(child: Path, parent: Path) -> bool:
    child, parent = child.resolve(), parent.resolve()
    return child != parent and parent in child.parents


def upload_tree_suffix(repo_rel: str) -> str | None:
    """`tests/fixtures/realuse_v1/<id>/<file>` → `realuse_v1/<id>/<file>`."""
    text = str(repo_rel).replace("\\", "/")
    if not text.startswith(_TREE_PREFIX):
        return None
    rest = text[len(_TREE_PREFIX) :]
    if _unsafe(rest):
        return None
    return "realuse_v1/" + rest


def stage_upload_tree(
    repo_rel: str,
    src: Path,
    *,
    output_root: Path | None = None,
    run_root: Path | None = None,
    sandbox_root: Path | None = None,
) -> list[Path]:
    """Copy one upload fixture onto the host mount, the row `in/` tree, and the sandbox."""
    suffix = upload_tree_suffix(repo_rel)
    if suffix is None or not src.is_file():
        return []
    targets: list[tuple[Path, Path]] = []
    if output_root is not None:
        targets.append((output_root / "uploads" / suffix, output_root / "uploads" / "realuse_v1"))
    if run_root is not None:
        targets.append((run_root / "in" / suffix, run_root / "in" / "realuse_v1"))
    if sandbox_root is not None:
        targets.append((sandbox_root / suffix, sandbox_root / "realuse_v1"))
    written: list[Path] = []
    for dest, root in targets:
        if not _inside(dest, root):
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        written.append(dest)
    return written


def named_paths(task: dict) -> list[str]:
    """Prompt paths and fixture-list paths a selected task requires to be readable."""
    found: list[str] = []
    for rel in task.get("fixtures") or []:
        text = str(rel).replace("\\", "/")
        if text.startswith(_TREE_PREFIX):
            found.append("/workspace/uploads/" + text.removeprefix("tests/fixtures/"))
        elif text.startswith(_REPO_PREFIX):
            found.append(text)
    users = [
        str(turn.get("user") or "") for turn in (task.get("turns") or []) if isinstance(turn, dict)
    ]
    for match in _NAMED.findall("\n".join(users)):
        clean = match.rstrip(".")
        if clean.endswith("/") or "." not in Path(clean).name:
            continue
        found.append(clean)
    out: list[str] = []
    seen: set[str] = set()
    for item in found:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _ensure(named: str, *, output_root: Path, repo: Path) -> str | None:
    if named.startswith(_REPO_PREFIX):
        dest = repo / named
        if _unsafe(named) or not _inside(dest, repo / "fixtures" / "realuse_v1"):
            return f"unreadable: {named}"
        if not dest.is_file() or not os.access(dest, os.R_OK):
            return f"unreadable: {named}"
        return None
    if not named.startswith(_UPLOAD_PREFIX):
        return f"unreadable: {named}"
    suffix = "realuse_v1/" + named[len(_UPLOAD_PREFIX) :]
    if _unsafe(suffix[len("realuse_v1/") :]):
        return f"unreadable: {named}"
    src = repo / "tests" / "fixtures" / suffix
    dest = output_root / "uploads" / suffix
    mount = output_root / "uploads" / "realuse_v1"
    if not src.is_file() or not os.access(src, os.R_OK) or not _inside(dest, mount):
        return f"unreadable: {named}"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    except OSError as exc:
        return f"unreadable: {named} ({exc})"
    if not dest.is_file() or not os.access(dest, os.R_OK):
        return f"unreadable: {named}"
    return None


def audit(tasks: list[dict], *, output_root: Path, repo: Path) -> tuple[int, list[str]]:
    """Stage every upload path and return (count, failure lines)."""
    seen: set[str] = set()
    failures: list[str] = []
    for task in tasks:
        for named in named_paths(task):
            if named in seen:
                continue
            seen.add(named)
            err = _ensure(named, output_root=output_root, repo=repo)
            if err:
                failures.append(err)
    return len(seen), failures


def selected_tasks(
    plan: Path,
    *,
    tier: str,
    all_suites: bool,
    arm: str | None,
    suite: str | None,
    task: str | None,
    workspace: str | None,
    advance: Path | None,
) -> list[dict]:
    """Tasks the campaign matrix will run, one copy of each suite task."""
    from tests.wfe.campaign import expand_matrix, load_advance
    from tests.wfe.runner import load_suite

    rows = expand_matrix(
        plan,
        1,
        all_suites,
        arm,
        suite,
        task,
        workspace,
        tier,
        load_advance(advance),
    )
    cache: dict[Path, dict[str, dict]] = {}
    tasks: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (str(row.get("suite_path") or ""), str(row.get("task_id") or ""))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        path = Path(key[0])
        if path not in cache:
            cache[path] = {item["id"]: item for item in load_suite(path)}
        chosen = cache[path].get(key[1])
        if chosen:
            tasks.append(chosen)
    return tasks


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="tests.wfe.realuse_paths")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--plan", type=Path)
    ap.add_argument("--tier", default="confirm", choices=("screen", "confirm", "realuse"))
    ap.add_argument("--all-suites", action="store_true")
    ap.add_argument("--arm")
    ap.add_argument("--suite")
    ap.add_argument("--task")
    ap.add_argument("--workspace")
    ap.add_argument("--advance", type=Path)
    ap.add_argument("--output-root", type=Path)
    return ap


def preflight(
    argv: list[str] | None = None,
    *,
    output_root: Path | None = None,
    repo: Path | None = None,
) -> int:
    """Resolve every fixture path the selected tasks name. Exit 1 if any is unreadable."""
    args, _unknown = _parser().parse_known_args(argv)
    plan = args.plan or (CHECKOUT / "tests/wfe/workloads.yaml")
    if not plan.is_file():
        print(f"fixture preflight: FAIL\n  unreadable: plan {plan}")
        return 1
    root = args.output_root or output_root
    if root is None:
        from tests.wfe.eval_mode import OUTPUT_ROOT

        root = OUTPUT_ROOT
    checkout = repo or CHECKOUT
    tasks = selected_tasks(
        plan,
        tier=args.tier,
        all_suites=args.all_suites,
        arm=args.arm,
        suite=args.suite,
        task=args.task,
        workspace=args.workspace,
        advance=args.advance,
    )
    count, failures = audit(tasks, output_root=root, repo=checkout)
    if failures:
        print(f"fixture preflight: FAIL ({len(failures)} unreadable)")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"fixture preflight: PASS ({count} path(s))")
    return 0


def main() -> int:
    return preflight()


if __name__ == "__main__":
    sys.exit(main())
