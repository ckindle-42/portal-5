"""Unit tests for scripts/check_updates.py check_python_deps direction-awareness
(TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2 D2).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "check_updates", Path(__file__).resolve().parents[2] / "scripts" / "check_updates.py"
)
cu = importlib.util.module_from_spec(_SPEC)
sys.modules["check_updates"] = cu
_SPEC.loader.exec_module(cu)


class _R:
    def __init__(self, rc, out):
        self.returncode = rc
        self.stdout = out
        self.stderr = ""


def _run_with(monkeypatch, result):
    monkeypatch.setattr(cu.subprocess, "run", lambda *a, **k: result)
    # skip the PyPI leg
    monkeypatch.setattr(Path, "read_text", lambda self: "")
    return cu.check_python_deps()


def test_venv_ahead_warns_against_uv_sync(monkeypatch):
    rep = _run_with(monkeypatch, _R(1, "- mlx==0.32.2\n~ torch==2.13.0 -> 2.11.0\n"))
    blob = "\n".join(rep.lines)
    assert "AHEAD" in blob and "Do NOT run" in blob
    assert rep.actionable


def test_venv_behind_recommends_uv_sync(monkeypatch):
    rep = _run_with(monkeypatch, _R(1, "+ somepkg==1.2.3\n"))
    blob = "\n".join(rep.lines)
    assert "behind uv.lock" in blob and "will catch it up" in blob


def test_check_run_failure_is_not_healthy(monkeypatch):
    def boom(*a, **k):
        raise subprocess.SubprocessError("uv not found")

    monkeypatch.setattr(cu.subprocess, "run", boom)
    monkeypatch.setattr(Path, "read_text", lambda self: "")
    rep = cu.check_python_deps()
    assert rep.status == "error"
    assert rep.actionable


def test_locked_packages_skips_non_pypi(monkeypatch, tmp_path):
    lock = (
        '[[package]]\nname = "a"\nversion = "1.0"\nsource = { registry = "https://pypi.org/simple" }\n\n'
        '[[package]]\nname = "portal"\nversion = "9"\nsource = { editable = "." }\n'
    )
    (tmp_path / "uv.lock").write_text(lock)
    monkeypatch.setattr(cu, "REPO_ROOT", tmp_path)
    assert cu._locked_packages() == [("a", "1.0", ())]


FORKED_LOCK = (
    '[[package]]\nname = "pillow"\nversion = "12.3.0"\n'
    'source = { registry = "https://pypi.org/simple" }\n'
    "resolution-markers = [\n"
    "    \"python_full_version < '3.11' and sys_platform == 'darwin'\",\n"
    "    \"python_full_version < '3.11' and sys_platform != 'darwin'\",\n"
    "]\n"
    'sdist = { url = "https://example.invalid/pillow-12.3.0.tar.gz" }\n\n'
    '[[package]]\nname = "pillow"\nversion = "13.0.0"\n'
    'source = { registry = "https://pypi.org/simple" }\n'
    "resolution-markers = [\n"
    "    \"python_full_version >= '3.11' and sys_platform == 'darwin'\",\n"
    "    \"python_full_version >= '3.11' and sys_platform != 'darwin'\",\n"
    "]\n"
    'sdist = { url = "https://example.invalid/pillow-13.0.0.tar.gz" }\n'
)


def test_locked_packages_keeps_resolution_markers(monkeypatch, tmp_path):
    (tmp_path / "uv.lock").write_text(FORKED_LOCK)
    monkeypatch.setattr(cu, "REPO_ROOT", tmp_path)
    forks = cu._locked_packages()
    assert [v for _, v, _ in forks] == ["12.3.0", "13.0.0"]
    assert all(m and all("python_full_version" in x for x in m) for _, _, m in forks)


def test_fork_can_install_reads_the_fix_requires_python():
    old = ("python_full_version < '3.11' and sys_platform != 'darwin'",)
    new = ("python_full_version >= '3.11' and sys_platform != 'darwin'",)
    assert not cu._fork_can_install(old, ">=3.11")
    assert cu._fork_can_install(new, ">=3.11")
    assert cu._fork_can_install(old, "")  # unknown -> try it anyway
    assert cu._fork_can_install((), ">=3.11")  # unforked -> always the runtime's own
    assert cu._spec_allows(">=3.10,<4", (3, 13, 1))
    assert not cu._spec_allows(">=3.11", (3, 10, 14))
    assert cu._spec_allows("~=3.10", (3, 13, 1))


def test_fork_labels_and_runtime_matching():
    old = ("python_full_version < '3.11' and sys_platform == 'darwin'",)
    new = ("python_full_version >= '3.11' and sys_platform != 'darwin'",)
    assert cu._py_range_label(old) == "py3.10"
    assert cu._py_range_label(new) == "py3.11+"
    assert not cu._fork_matches(old, (3, 13, 1))
    assert cu._fork_matches(new, (3, 13, 1))
    assert "py3.10 fork only — not this runtime (py3.13.1)" in cu._fork_note(old, (3, 13, 1))
    assert "fork only" not in cu._fork_note(new, (3, 13, 1))
    assert cu._fork_note((), (3, 13, 1)) == ""


def test_runtime_python_is_the_project_venv_not_the_caller(monkeypatch, tmp_path):
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "pyvenv.cfg").write_text(
        "home = /x\nversion_info = 3.13.12\nimplementation = CPython\n"
    )
    monkeypatch.setattr(cu, "REPO_ROOT", tmp_path)
    assert cu._runtime_python() == (3, 13, 12)


def test_runtime_python_reads_a_stdlib_venv_cfg(monkeypatch, tmp_path):
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "pyvenv.cfg").write_text(
        "home = /x\ninclude-system-site-packages = false\nversion = 3.11.9\n"
    )
    monkeypatch.setattr(cu, "REPO_ROOT", tmp_path)
    assert cu._runtime_python() == (3, 11, 9)


def test_runtime_python_falls_back_to_the_caller_without_a_venv(monkeypatch, tmp_path):
    monkeypatch.setattr(cu, "REPO_ROOT", tmp_path)
    assert cu._runtime_python() == tuple(sys.version_info[:3])


def test_python_vulns_marks_the_fork_the_runtime_does_not_use(monkeypatch, tmp_path):
    (tmp_path / "uv.lock").write_text(FORKED_LOCK)
    monkeypatch.setattr(cu, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cu, "_runtime_python", lambda: (3, 13, 1))
    monkeypatch.setattr(
        cu,
        "_post_json",
        lambda url, body: {
            "results": [{"vulns": [{"id": "GHSA-old"}]}, {"vulns": [{"id": "GHSA-new"}]}]
        },
    )
    monkeypatch.setattr(cu, "_osv_detail", lambda i, p, v="0": ("CRITICAL", "13.0.1", "bad"))
    lines = cu.check_python_vulns().lines
    old_line = next(ln for ln in lines if "pillow 12.3.0" in ln)
    new_line = next(ln for ln in lines if "pillow 13.0.0" in ln)
    assert "py3.10 fork only — not this runtime (py3.13.1)" in old_line
    assert "py3.11+ fork" in new_line and "fork only" not in new_line


def test_python_vulns_flags_only_fixable_as_actionable(monkeypatch):
    monkeypatch.setattr(cu, "_locked_packages", lambda: [("a", "1.0", ()), ("b", "2.0", ())])
    monkeypatch.setattr(
        cu,
        "_post_json",
        lambda url, body: {"results": [{"vulns": [{"id": "GHSA-1"}]}, {}]},
    )
    monkeypatch.setattr(cu, "_osv_detail", lambda i, p, v="0": ("HIGH", "1.1", "bad"))
    rep = cu.check_python_vulns()
    assert rep.status == "behind" and rep.security and not rep.security_in_gap
    monkeypatch.setattr(cu, "_osv_detail", lambda i, p, v="0": ("LOW", "", "bad"))
    assert cu.check_python_vulns().status == "current"


def test_python_vulns_osv_failure_is_error(monkeypatch):
    monkeypatch.setattr(cu, "_locked_packages", lambda: [("a", "1.0", ())])

    def boom(url, body):
        raise OSError("down")

    monkeypatch.setattr(cu, "_post_json", boom)
    assert cu.check_python_vulns().status == "error"


def test_vuln_fixes_takes_highest_per_vuln_lowest_fix(monkeypatch):
    fixed = {"A": ("LOW", "1.2", "a"), "B": ("HIGH", "1.5", "b"), "C": ("HIGH", "", "c")}
    monkeypatch.setattr(cu, "_osv_detail", lambda i, p, v: fixed[i])
    out = cu.vuln_fixes({("pkg", "1.0"): ["A", "B", "C"]})
    assert out[("pkg", "1.0")][:2] == ("HIGH", "1.5")


def test_storage_reports_owner_totals_and_ages_from_fake_tree(monkeypatch, tmp_path):
    root = tmp_path / "data01"
    backends = tmp_path / "backends.yaml"
    portal = tmp_path / "portal.yaml"
    backends.write_text(
        "backends:\n"
        "- group: general\n"
        "  id: ollama-general\n"
        "  models:\n"
        "  - id: team/active:v1\n"
        "  - id: team/active:v2\n"
        "- group: omlx\n"
        "  id: omlx-local\n"
        "  models:\n"
        "  - id: active-checkpoint\n"
        "  - id: mlx-community--checkpoint\n"
        "  type: omlx\n"
        "  aliases:\n"
        "    team/active:v1: active-checkpoint\n"
        "    team/alias-only:v1: active-checkpoint\n"
    )
    portal.write_text(
        "modules:\n"
        "  image:\n"
        "    enabled: false\n"
        "  video:\n"
        "    enabled: false\n"
        "  general:\n"
        "    enabled: true\n"
        "  media:\n"
        "    enabled: true\n"
        "workspaces:\n"
        "  media-lane:\n"
        "    module: media\n"
        "    description: Audio tools\n"
        "    variants:\n"
        "      image:\n"
        "        module: image\n"
        "        owui_system_prompt: |-\n"
        "          model='qwen-image'\n"
        "      video:\n"
        "        module: video\n"
        "        description: MLX-native LTX-2.3\n"
    )
    monkeypatch.setattr(cu, "_allocated_bytes", lambda info: info.st_size)

    def put(relative, content, age_days=0):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        if age_days:
            stamp = time.time() - age_days * 86400
            os.utime(path, (stamp, stamp))
        return path

    def manifest(tag, digest):
        path = cu._ollama_manifest_path(root, tag)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"layers": [{"digest": f"sha256:{digest}"}]}))

    manifest("team/active:v1", "shared")
    manifest("team/active:v2", "shared")
    manifest("team/alias-only:v1", "shared")
    manifest("team/unused:v1", "orphan")
    put("ollama/models/blobs/sha256-shared", b"shared")
    put("ollama/models/blobs/sha256-orphan", b"orphan")
    put("omlx-models/active-checkpoint/weights", b"active!")
    put("omlx-models/mlx-community--checkpoint/weights", b"copy")
    put("omlx-models/retired-checkpoint/weights", b"retired-ml")
    put("hf-cache/models--mlx-community--checkpoint/snapshots/a/weights", b"copy")
    put("hf-cache/models--Qwen--Qwen-Image-Edit-2509/blobs/image", b"image-data")
    put("hf-cache/models--dgrauet--ltx-2.3-mlx-q4/blobs/video", b"video")
    hf_shared = put("hf-cache/blobs/aa/image-weight", b"hf-cache-weight")
    hf_shared.with_name(f"{hf_shared.name}.refs").write_text(
        "models--Qwen--Qwen-Image-Edit-2509/blobs/image\n"
    )
    hf_duplicate = put("hf-cache/blobs/bb/duplicate-weight", b"duplicate-weight")
    hf_duplicate.with_name(f"{hf_duplicate.name}.refs").write_text(
        "models--mlx-community--checkpoint/blobs/weights\n"
    )
    put("gguf-staging/sage/Sage.gguf", b"staged", age_days=4)
    put("portal5_backups/old/snapshot.tar", b"backup", age_days=9)
    put("misc/notes.txt", b"other")

    report = cu._storage_report(
        root,
        backends,
        portal,
        total=1000 * 1024**3,
        free=200 * 1024**3,
    )
    lines = "\n".join(report.lines)
    assert report.status == "behind" and report.high_priority
    assert "fleet: 17 B" in lines
    assert "orphan model data: 16 B" in lines
    assert "duplicate: 20 B" in lines
    assert "disabled-module weights: 30 B" in lines
    assert "gguf-staging/sage 6 B (age 4d)" in lines
    assert "portal5_backups/old 6 B (age 9d)" in lines
    assert "reclaimable if approved:" in lines
    assert (root / "gguf-staging/sage/Sage.gguf").exists()
    custom_floor = cu._storage_report(
        root,
        backends,
        portal,
        total=1000 * 1024**3,
        free=200 * 1024**3,
        floor_gib=100,
        floor_percent=10,
    )
    assert custom_floor.status == "current" and not custom_floor.high_priority


def test_storage_low_space_uses_high_priority_pushover(monkeypatch, capsys):
    calls = []
    monkeypatch.setitem(
        cu.CHECKERS, "storage", lambda: cu.Report("storage", status="behind", high_priority=True)
    )
    monkeypatch.setattr(cu, "_pushover", lambda title, message, high: calls.append((title, high)))
    assert cu.main(["storage"]) == 0
    capsys.readouterr()
    assert calls == [("Storage space low", True)]
