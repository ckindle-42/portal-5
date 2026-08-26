"""Project resolution + structure detect/init."""

from pathlib import Path

from portal.modules.binary_research.harness import workspace as w


def test_root_from_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("BINRESEARCH_PROJECTS_ROOT", str(tmp_path))
    assert w.projects_root() == tmp_path


def test_resolve_name_under_root(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("BINRESEARCH_PROJECTS_ROOT", str(tmp_path))
    assert w.resolve_project("demo") == (tmp_path / "demo").resolve()


def test_resolve_path(tmp_path: Path):
    d = tmp_path / "explicit"
    d.mkdir()
    assert w.resolve_project(str(d)) == d.resolve()


def test_init_and_detect(tmp_path: Path):
    p = tmp_path / "p"
    w.init_project(p)
    assert w.is_initialized(p)
    assert (p / ".binresearch").exists()
    for f in ("00_inventory.md", "05_report.md", "trace.jsonl"):
        assert (p / f).exists()


def test_cwd_autodetect(monkeypatch, tmp_path: Path):
    p = tmp_path / "proj"
    w.init_project(p)
    sub = p / "artifacts"
    monkeypatch.chdir(sub)
    assert w.resolve_project(None) == p.resolve()


def test_has_artifacts_and_count(tmp_path: Path):
    p = tmp_path / "p"
    w.init_project(p)
    assert not w.has_artifacts(p)
    (p / "artifacts" / "x.bin").write_bytes(b"\x00")
    assert w.has_artifacts(p)
    assert w.verifier_count(p) == 0
    (p / "verifiers" / "a.sh").write_text("#!/bin/bash\nexit 0\n")
    (p / "verifiers" / "b.sh").write_text("#!/bin/bash\nexit 0\n")
    assert w.verifier_count(p) == 2
