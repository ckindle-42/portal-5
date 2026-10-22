"""HK incremental mode — changed-only filtering when PORTAL5_VALIDATE_CHANGED_ONLY=1."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.validation import compliance_public_text as hk


def _small_repo(tmp_path: Path, content: dict[str, str]) -> Path:
    """Create a minimal git repo, make one commit, then stage a second."""
    repo = tmp_path
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    for rel, body in content.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "first"], check=True)
    return repo


def test_full_scan_without_env_var(tmp_path: Path) -> None:
    """Without the env var, audit() scans all tracked files and reports full scan."""
    root = _small_repo(
        tmp_path,
        {
            "reports/compliance/README.md": "public summary",
            "reports/other/summary.json": json.dumps({"n": 3, "answer": "short"}),
        },
    )
    status, detail, findings = hk.audit(root, content=False)
    assert status == "PASS"
    assert findings == []
    status2, detail2, _ = hk.audit(root, content=True)
    assert "content scan ran" in detail2
    assert "changed-only" not in detail2


def test_changed_only_scans_only_diff(tmp_path: Path) -> None:
    """With PORTAL5_VALIDATE_CHANGED_ONLY=1, changed-files list is passed to head_findings."""
    repo = tmp_path
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / "reports" / "compliance" / "README.md").parent.mkdir(parents=True, exist_ok=True)
    (repo / "reports" / "compliance" / "README.md").write_text("public summary")
    (repo / "unchanged.txt").write_text("still the same")
    (repo / "change_me.txt").write_text("old content")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "first"], check=True)
    first_commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "branch", "origin/main", first_commit], check=True)
    (repo / "change_me.txt").write_text("new content")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "second"], check=True)

    changed = hk._changed_files(repo)
    assert "change_me.txt" in changed
    assert "unchanged.txt" not in changed
    assert "reports/compliance/README.md" not in changed

    status, detail, findings = hk.audit(repo, content=True, _changed_only=True)
    assert "changed-only" in detail
    assert status == "PASS"  # no operator text in either file


def test_changed_only_env_var(tmp_path: Path, monkeypatch) -> None:
    """PORTAL5_VALIDATE_CHANGED_ONLY=1 triggers changed-only implicitly."""
    root = _small_repo(
        tmp_path,
        {
            "reports/compliance/README.md": "public summary",
            "change_me.txt": "old content",
        },
    )
    (root / "change_me.txt").write_text("new content")
    (root / "unchanged.txt").write_text("still the same")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "second"], check=True)

    monkeypatch.setenv("PORTAL5_VALIDATE_CHANGED_ONLY", "1")
    status, detail, _ = hk.audit(root, content=True)
    assert "changed-only" in detail
    assert status == "PASS"


def test_no_merge_base_falls_back_to_full(tmp_path: Path) -> None:
    """When there is no common ancestor, _changed_files falls back to all tracked."""
    root = tmp_path
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@test"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    (root / "first.txt").write_text("a")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "first"], check=True)

    changed = hk._changed_files(root)
    assert changed == ["first.txt"]
