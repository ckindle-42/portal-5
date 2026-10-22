"""HX. tests cite only tracked paths — PASS on HEAD, FAIL when seeded.

The seeded cases are the two failures the gate exists for: a test reading a
`coding_task/` scratch path (main went red everywhere but the author's
worktree, 2026-10-22) and a test naming an absolute checkout path.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation.test_hygiene import check_test_paths_tracked

ROOT = Path(__file__).resolve().parents[2]

# Seeded tokens are assembled from pieces so this file passes the gate it tests.
_CODING = "coding" + "_task/"
_HOME = "/Users/" + "x/"
_IGNORED = "tests/fixtures/" + "local/"


def _repo(tmp_path: Path, files: dict[str, str], ignore: str = "") -> Path:
    """A throwaway git checkout with `files` in its index and `ignore` as .gitignore."""
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (tmp_path / ".gitignore").write_text(ignore, encoding="utf-8")
    git = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def _status(root: Path) -> tuple[str, str]:
    status, detail, _subs = check_test_paths_tracked(root)
    return status, detail


def test_check_passes_on_head() -> None:
    status, detail, subs = check_test_paths_tracked()
    assert status == "PASS", detail
    assert [sub["status"] for sub in subs] == ["PASS"] * 4


def test_check_is_registered() -> None:
    from scripts.validation import all_checks

    assert any(slug == "test_paths_tracked" for slug, _label, _fn in all_checks())


def test_tracked_fixture_passes(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        {
            "tests/unit/test_x.py": 'FIXTURE = "tests/fixtures/replay.json"\n',
            "tests/fixtures/replay.json": "{}",
        },
    )
    assert _status(root)[0] == "PASS"


def test_coding_task_reference_fails(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        {"tests/unit/test_x.py": f'CORPUS = "{_CODING}private/doc.pdf"\n'},
        ignore=_CODING + "\n",
    )
    status, detail = _status(root)
    assert status == "FAIL"
    assert "coding_task" in detail


def test_absolute_home_path_fails(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        {"tests/unit/test_x.py": f'ROOT = "{_HOME}projects/portal-5-other/config/backends.yaml"\n'},
    )
    status, detail = _status(root)
    assert status == "FAIL"
    assert "absolute" in detail


@pytest.mark.parametrize("suffix", ["replay.json", ""])
def test_gitignored_path_fails(tmp_path: Path, suffix: str) -> None:
    root = _repo(
        tmp_path,
        {"tests/unit/test_x.py": f'FIXTURE = "{_IGNORED}{suffix}"\n'},
        ignore=_IGNORED + "\n",
    )
    status, detail = _status(root)
    assert status == "FAIL"
    assert "gitignored" in detail


def test_local_only_marker_exempts_but_is_reported(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        {
            "tests/unit/test_x.py": (
                f'FIXTURE = "{_IGNORED}replay.json"  # local-only: recorded clip\n'
            )
        },
        ignore=_IGNORED + "\n",
    )
    status, detail = _status(root)
    assert status == "PASS"
    assert "1 local-only exempt" in detail


def test_docstring_and_fstring_mentions_are_prose(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        {
            "tests/unit/test_x.py": (
                f'"""See {_CODING}BRIEF.md and {_HOME}notes.md."""\n'
                f'MESSAGE = f"wrote {_IGNORED}out.json"\n'
            )
        },
        ignore=_CODING + "\n" + _IGNORED + "\n",
    )
    assert _status(root)[0] == "PASS"


@pytest.mark.parametrize(
    "source",
    [
        _CODING + "v9_compliance/note.md",
        _HOME + "projects/portal-5-other/config/backends.yaml",
        "../portal-5-" + "other/config/backends.yaml",
    ],
)
def test_unit_source_outside_the_repo_fails(tmp_path: Path, source: str) -> None:
    unit = (
        "---\n"
        "id: unit-seeded\n"
        "kind: what\n"
        "title: Seeded\n"
        "sources:\n"
        f"- type: design\n  path: {source}\n"
        "---\n\nbody\n"
    )
    root = _repo(tmp_path, {"portal_wiki/canonical/unit-seeded.md": unit})
    status, detail = _status(root)
    assert status == "FAIL"
    assert "unit source" in detail
