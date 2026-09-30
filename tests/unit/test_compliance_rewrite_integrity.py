"""P1R - a history rewrite changes only what it had a reason to change."""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "rewrite_integrity", REPO / "scripts" / "compliance" / "truth" / "rewrite_integrity.py"
)
ri = importlib.util.module_from_spec(spec)
sys.modules["rewrite_integrity"] = ri
spec.loader.exec_module(ri)

MARK = ri.MARKER


def _g(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _commit(repo, files, message, parent=None):
    """Write a commit with exactly ``files`` as its tree; return its sha."""
    index = repo / ".git" / "tmp_index"
    env = {
        "GIT_INDEX_FILE": str(index),
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": "/usr/bin:/bin",
    }
    if index.exists():
        index.unlink()
    for path, body in files.items():
        blob = subprocess.run(
            ["git", "-C", str(repo), "hash-object", "-w", "--stdin"],
            input=body,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "update-index",
                "--add",
                "--cacheinfo",
                f"100644,{blob},{path}",
            ],
            env=env,
            check=True,
        )
    tree = subprocess.run(
        ["git", "-C", str(repo), "write-tree"], env=env, capture_output=True, text=True, check=True
    ).stdout.strip()
    cmd = ["git", "-C", str(repo), "commit-tree", tree, "-m", message] + (
        ["-p", parent] if parent else []
    )
    return subprocess.run(cmd, env=env, capture_output=True, text=True, check=True).stdout.strip()


def _history(tmp_path, *, public_after, test_after_1, test_after_2):
    repo = tmp_path / "r"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    o1 = _commit(
        repo,
        {
            "data/nerc.json": "NERC public text",
            "tests/t.py": "operator secret words",
            "reports/run.json": "answers",
        },
        "one",
    )
    o2 = _commit(
        repo,
        {
            "data/nerc.json": "NERC public text",
            "tests/t.py": "operator secret words v2",
            "reports/run.json": "answers",
        },
        "two",
        o1,
    )
    n1 = _commit(repo, {"data/nerc.json": public_after, "tests/t.py": test_after_1}, "one")
    n2 = _commit(repo, {"data/nerc.json": public_after, "tests/t.py": test_after_2}, "two", n1)
    return repo / ".git", [(o1, n1), (o2, n2)], n2


def _detector(text):
    return "secret" in text


def test_a_clean_rewrite_passes(tmp_path):
    git_dir, pairs, tip = _history(
        tmp_path,
        public_after="NERC public text",
        test_after_1=f"operator {MARK} words",
        test_after_2=f"operator {MARK} words v2",
    )
    result = ri.check(git_dir, pairs, tip, ["data/*"], _detector)
    assert result["verdict"] == "PASS", result
    assert result["counts"]["kept_changes"] == 2


def test_a_protected_path_touched_anywhere_fails(tmp_path):
    git_dir, pairs, tip = _history(
        tmp_path,
        public_after=f"NERC {MARK} text",
        test_after_1=f"operator {MARK} words",
        test_after_2=f"operator {MARK} words v2",
    )
    result = ri.check(git_dir, pairs, tip, ["data/*"], _detector)
    rules = {v["rule"] for v in result["violations"]}
    assert result["verdict"] == "FAIL"
    assert "1:protected path changed" in rules
    assert "1:redaction marker in a protected path at the tip" in rules


def test_a_kept_file_changed_without_a_finding_fails(tmp_path):
    git_dir, pairs, tip = _history(
        tmp_path,
        public_after="NERC public text",
        test_after_1=f"operator {MARK} words",
        test_after_2=f"operator {MARK} words v2",
    )
    result = ri.check(git_dir, pairs, tip, ["data/*"], lambda text: False)
    assert result["verdict"] == "FAIL"
    assert {v["rule"] for v in result["violations"]} == {
        "3:kept path changed without a finding in its original"
    }


def test_without_a_detector_rule_3_is_not_run_not_passed(tmp_path):
    git_dir, pairs, tip = _history(
        tmp_path,
        public_after="NERC public text",
        test_after_1=f"operator {MARK} words",
        test_after_2=f"operator {MARK} words v2",
    )
    result = ri.check(git_dir, pairs, tip, ["data/*"])
    assert result["rule_3"].startswith("NOT RUN") and result["counts"]["unverified"] == 2
    assert result["verdict"] == "PASS"


def test_read_commit_map(tmp_path):
    m = tmp_path / "commit-map"
    m.write_text(
        "old                                      new\n" + "a" * 40 + " " + "b" * 40 + "\n"
    )
    assert ri.read_commit_map(m) == [("a" * 40, "b" * 40)]


def test_report_refuses_the_public_tree(tmp_path):
    (tmp_path / "p.txt").write_text("data/*\n")
    code = ri.main(
        [
            "--git-dir",
            str(tmp_path),
            "--commit-map",
            str(tmp_path / "m"),
            "--tip",
            "HEAD",
            "--protected",
            str(tmp_path / "p.txt"),
            "--out",
            str(REPO / "reports" / "compliance" / "x.json"),
        ]
    )
    assert code == 2
