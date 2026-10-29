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
    put("hf-cache/models--dgrauet--ltx-2.5-mlx-q4/blobs/video", b"video")
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
        query_ollama=False,
        installed_blobs={
            "team/active:v1": {"sha256-shared"},
            "team/active:v2": {"sha256-shared"},
            "team/alias-only:v1": {"sha256-shared"},
            "team/unused:v1": {"sha256-orphan"},
        },
    )
    lines = "\n".join(report.lines)
    assert report.status == "behind" and report.high_priority
    assert "fleet: 47 B" in lines
    assert "installed-but-unconfigured: 6 B" in lines
    assert "orphan model data: 10 B" in lines
    assert "duplicate: 20 B" in lines
    assert "disabled-module weights: 0 B" in lines
    assert "gguf-staging/sage 6 B (age 4d)" in lines
    assert "portal5_backups/old 6 B (age 9d)" in lines
    assert (
        "safe to reclaim: 10 B" in lines
        and "operator decision: 12 B" in lines
        and "reclaimable" not in lines
    )
    assert (root / "gguf-staging/sage/Sage.gguf").exists()
    custom_floor = cu._storage_report(
        root,
        backends,
        portal,
        total=1000 * 1024**3,
        free=200 * 1024**3,
        floor_gib=100,
        floor_percent=10,
        query_ollama=False,
        installed_blobs={},
    )
    assert custom_floor.status == "current" and not custom_floor.high_priority


def _storage_yaml(tmp_path, backends_text, portal_text="modules:\n  media:\n    enabled: true\n"):
    backends = tmp_path / "backends.yaml"
    portal = tmp_path / "portal.yaml"
    backends.write_text(backends_text)
    portal.write_text(portal_text)
    return backends, portal


def test_storage_qwen_image_and_z_image_belong_to_media(monkeypatch, tmp_path):
    root = tmp_path / "data01"
    backends, portal = _storage_yaml(
        tmp_path,
        "backends: []\n",
        "modules:\n  image:\n    enabled: false\n  media:\n    enabled: true\n"
        "workspaces:\n  lane:\n    module: image\n    owui_system_prompt: |-\n"
        "      model='qwen-image'\n      model='schnell'\n",
    )
    monkeypatch.setattr(cu, "_allocated_bytes", lambda info: info.st_size)
    for relative, content in (
        ("hf-cache/models--Qwen--Qwen-Image-2512/blobs/image", b"qwen-img"),
        ("hf-cache/models--Tongyi-MAI--Z-Image-Turbo/blobs/turbo", b"z-image"),
        ("hf-cache/models--black-forest-labs--FLUX.1-schnell/blobs/flux", b"flux-wt"),
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    report = cu._storage_report(
        root,
        backends,
        portal,
        total=1000,
        free=900,
        floor_gib=0,
        floor_percent=0,
        query_ollama=False,
        installed_blobs={},
    )
    fleet = next(line for line in report.lines if line.startswith("fleet:"))
    disabled = next(line for line in report.lines if line.startswith("disabled-module weights:"))
    assert "Qwen-Image-2512" in fleet and "Z-Image-Turbo" in fleet
    assert "FLUX.1-schnell" in fleet
    assert "Qwen-Image" not in disabled and "Z-Image" not in disabled and "FLUX" not in disabled


def test_storage_v2_store_and_llamacpp_builds_are_referenced(monkeypatch, tmp_path):
    root = tmp_path / "data01"
    backends, portal = _storage_yaml(
        tmp_path,
        "backends:\n"
        "- group: general\n"
        "  id: ollama-general\n"
        "  models:\n"
        "  - id: team/active:v1\n"
        "  - id: hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0\n",
    )
    monkeypatch.setattr(cu, "_allocated_bytes", lambda info: info.st_size)

    def write(relative, content):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content) if isinstance(content, str) else path.write_bytes(content)

    write(
        "ollama/models/manifests-v2/ollama.com/team/active/v1",
        json.dumps({"layers": [{"digest": "sha256:v2blob"}]}),
    )
    write(
        "ollama/models/manifests/registry.ollama.ai/library/llamacpp/" + ("a" * 64),
        json.dumps({"layers": [{"digest": "sha256:engine"}]}),
    )
    write(
        "ollama/models/manifests/hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF/Q8_0",
        json.dumps({"config": {"digest": "sha256:sec"}}),
    )
    write("ollama/models/blobs/sha256-v2blob", b"v2-weight")
    write("ollama/models/blobs/sha256-engine", b"engine!!")
    write("ollama/models/blobs/sha256-sec", b"security!")
    write("ollama/models/blobs/sha256-loose", b"loose")
    report = cu._storage_report(
        root,
        backends,
        portal,
        total=1000,
        free=900,
        floor_gib=0,
        floor_percent=0,
        query_ollama=False,
        installed_blobs={"team/active:v1": set()},
    )
    fleet = next(line for line in report.lines if line.startswith("fleet:"))
    orphan = next(line for line in report.lines if line.startswith("orphan model data:"))
    assert "team/active:v1" in fleet
    assert "llamacpp:" in fleet
    assert "hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0" in fleet
    assert "sha256-loose" in orphan
    assert "sha256-v2blob" not in orphan and "sha256-engine" not in orphan
    assert "unverified" not in "\n".join(report.lines)


def test_storage_ollama_down_is_unverified_and_not_reclaimable(monkeypatch, tmp_path):
    root = tmp_path / "data01"
    backends, portal = _storage_yaml(tmp_path, "backends: []\n", "modules: {}\n")
    monkeypatch.setattr(cu, "_allocated_bytes", lambda info: info.st_size)
    blob = root / "ollama/models/blobs/sha256-dead"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"x" * 20)
    manifest = root / "ollama/models/manifests/registry.ollama.ai/library/ghost/latest"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"layers": [{"digest": "sha256:dead"}]}))
    stage = root / "gguf-staging/screen/file.gguf"
    stage.parent.mkdir(parents=True)
    stage.write_bytes(b"s" * 4)
    report = cu._storage_report(
        root,
        backends,
        portal,
        total=1000,
        free=900,
        floor_gib=0,
        floor_percent=0,
        query_ollama=False,
        installed_blobs=None,
    )
    lines = "\n".join(report.lines)
    assert "root ollama:" in lines and "unverified" in lines
    assert "orphan model data: 0 B" in lines
    assert "safe to reclaim: 0 B" in lines and "operator decision: 4 B" in lines
    assert "reclaimable" not in lines
    assert "sha256-dead" not in lines


def test_installed_ollama_blobs_reads_from_lines_and_fails_closed(monkeypatch):
    payloads = [
        {"models": [{"name": "gemma4:e4b"}]},
        {
            "modelfile": (
                "FROM /Volumes/data01/ollama/models/blobs/sha256-abc\nPARAMETER temperature 0.7\n"
            )
        },
    ]

    class _Body:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_open(request, timeout=0):
        return _Body(payloads.pop(0))

    monkeypatch.setattr(cu.urllib.request, "urlopen", fake_open)
    assert cu._installed_ollama_blobs() == {"gemma4:e4b": {"sha256-abc"}}

    def boom(*args, **kwargs):
        raise cu.urllib.error.URLError("down")

    monkeypatch.setattr(cu.urllib.request, "urlopen", boom)
    assert cu._installed_ollama_blobs() is None


def test_storage_model_ref_pattern_keeps_ids_and_drops_dates():
    text = (
        "hf.co/openbmb/MiniCPM5-1B-GGUF:Q4_K_M "
        "incoai/Qwen3.8-27B-DFlash2 "
        "qwen3-vl:4b-instruct-q4_K_M "
        "Qwen3.8-27B-DFlash2 "
        "added 2026-08-26 portal-pipeline:9099 qwen"
    )
    refs = cu._model_refs_in_text(text)
    assert "hf.co/openbmb/MiniCPM5-1B-GGUF:Q4_K_M" in refs
    assert "incoai/Qwen3.8-27B-DFlash2" in refs
    assert "qwen3-vl:4b-instruct-q4_K_M" in refs
    assert "Qwen3.8-27B-DFlash2" in refs
    assert not any(name.startswith("2026") or name == "qwen" for name in refs)
    assert "portal-pipeline:9099" not in refs


def test_storage_extractors_see_live_in_use_ids():
    portal = cu.REPO_ROOT / "config" / "portal.yaml"
    refs = cu._config_model_refs(portal.read_text(encoding="utf-8"), portal.parent)
    refs.update(cu._code_model_refs())
    assert any("Qwen3.8-27B-DFlash2" in name for name in refs)
    assert "qwen3-vl:4b-instruct-q4_K_M" in refs
    assert any(name.startswith("hf.co/") and "MiniCPM5" in name for name in refs)
    tokens = cu._media_alias_tokens()
    for slug in (
        "Qwen--Qwen-Image-2512",
        "Qwen--Qwen-Image-Edit-2509",
        "Tongyi-MAI--Z-Image-Turbo",
        "black-forest-labs--FLUX.1-schnell",
        "black-forest-labs--FLUX.2-klein-4B",
        "dgrauet--ltx-2.5-mlx-q4",
    ):
        assert cu._matches_media_alias(slug), slug
    assert not cu._matches_media_alias("incoai--Qwen3.8-27B-DFlash2")
    assert not cu._matches_media_alias("Qwen--Qwen2.5-7B-Instruct")
    assert "qwen" not in tokens and "dev" not in tokens and "flux2" not in tokens
    assert "qwenimage" in tokens and "zimageturbo" in tokens and "schnell" in tokens
    assert "flux2klein4b" in tokens and "dgrauetltx25mlxq4" in tokens


def test_storage_media_off_weights_are_an_operator_decision(monkeypatch, tmp_path):
    root = tmp_path / "data01"
    backends, portal = _storage_yaml(
        tmp_path,
        "backends: []\n",
        "modules:\n  image:\n    enabled: true\n  video:\n    enabled: true\n"
        "  media:\n    enabled: false\n",
    )
    monkeypatch.setattr(cu, "_allocated_bytes", lambda info: info.st_size)
    for relative, content in (
        ("hf-cache/models--Qwen--Qwen-Image-2512/blobs/image", b"qwen-img"),
        ("hf-cache/models--Tongyi-MAI--Z-Image-Turbo/blobs/turbo", b"z-image"),
        ("hf-cache/models--black-forest-labs--FLUX.1-schnell/blobs/flux", b"flux-wt"),
        ("hf-cache/models--dgrauet--ltx-2.5-mlx-q4/blobs/video", b"ltx-wt!"),
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    report = cu._storage_report(
        root,
        backends,
        portal,
        total=1000,
        free=900,
        floor_gib=0,
        floor_percent=0,
        query_ollama=False,
        installed_blobs={},
    )
    disabled = next(line for line in report.lines if line.startswith("disabled-module weights:"))
    fleet = next(line for line in report.lines if line.startswith("fleet:"))
    lines = "\n".join(report.lines)
    assert "Qwen-Image-2512" in disabled and "Z-Image-Turbo" in disabled
    assert "FLUX.1-schnell" in disabled and "ltx-2.5-mlx-q4" in disabled
    assert "Qwen-Image" not in fleet and "FLUX" not in fleet and "ltx-2.5" not in fleet
    assert "safe to reclaim: 0 B" in lines and "operator decision: 29 B" in lines


def test_storage_persona_and_code_defaults_count_as_fleet(monkeypatch, tmp_path):
    root = tmp_path / "data01"
    config = tmp_path / "cfg"
    config.mkdir()
    backends = config / "backends.yaml"
    portal = config / "portal.yaml"
    backends.write_text("backends: []\n")
    portal.write_text("modules:\n  media:\n    enabled: true\n")
    persona_dir = config / "personas"
    persona_dir.mkdir()
    (persona_dir / "draft.yaml").write_text("# drafter incoai/Qwen3.8-27B-DFlash2\n")
    monkeypatch.setattr(cu, "_allocated_bytes", lambda info: info.st_size)

    def put(relative: str, content: bytes) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    put("ollama/models/blobs/sha256-vl", b"vl-model")
    put("ollama/models/blobs/sha256-mini", b"mini-cpm")
    put("ollama/models/blobs/sha256-loose", b"loose-blob")
    put("omlx-models/Qwen3.8-27B-DFlash2/weights", b"dflash")
    put("omlx-models/zz-orphan-dir/weights", b"orphan-dir")
    put("hf-cache/models--incoai--Qwen3.8-27B-DFlash2/weights", b"hf-copy!")
    report = cu._storage_report(
        root,
        backends,
        portal,
        total=1000,
        free=900,
        floor_gib=0,
        floor_percent=0,
        query_ollama=False,
        installed_blobs={
            "qwen3-vl:4b-instruct-q4_K_M": {"sha256-vl"},
            "hf.co/openbmb/MiniCPM5-1B-GGUF:Q4_K_M": {"sha256-mini"},
        },
    )
    fleet = next(line for line in report.lines if line.startswith("fleet:"))
    orphan = next(line for line in report.lines if line.startswith("orphan model data:"))
    duplicate = next(line for line in report.lines if line.startswith("duplicate:"))
    lines = "\n".join(report.lines)
    assert "qwen3-vl:4b-instruct-q4_K_M" in fleet
    assert "MiniCPM5-1B" in fleet
    assert "Qwen3.8-27B-DFlash2" in fleet
    assert "sha256-loose" in orphan and "zz-orphan-dir" in orphan
    assert "incoai--Qwen3.8-27B-DFlash2" in duplicate
    assert "safe to reclaim: 20 B" in lines and "operator decision: 0 B" in lines
    assert "installed-but-unconfigured: 0 B" in lines


def _storage_bytes(root: Path, relative: str, payload: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_storage_omlx_symlink_attributes_hf_cache_bytes_to_link_owner(monkeypatch, tmp_path):
    root = tmp_path / "data01"
    backends, portal = _storage_yaml(
        tmp_path,
        "backends:\n"
        "- group: omlx\n"
        "  id: omlx-local\n"
        "  type: omlx\n"
        "  models:\n"
        "  - id: active-checkpoint\n",
        "modules:\n  media:\n    enabled: true\n",
    )
    monkeypatch.setattr(cu, "_allocated_bytes", lambda info: info.st_size)

    def snapshot(slug: str, payload: bytes) -> Path:
        _storage_bytes(root, f"hf-cache/models--{slug}/blobs/weights", payload)
        snap = root / "hf-cache" / f"models--{slug}" / "snapshots" / "rev"
        snap.mkdir(parents=True)
        return snap

    active = snapshot("org--active-checkpoint", b"a" * 40)
    retired = snapshot("org--retired-checkpoint", b"r" * 10)
    media = snapshot("dgrauet--ltx-2.5-mlx-q4", b"m" * 7)
    omlx = root / "omlx-models"
    omlx.mkdir()
    (omlx / "active-checkpoint").symlink_to(active)
    (omlx / "retired-alias").symlink_to(active)
    (omlx / "retired-checkpoint").symlink_to(retired)
    (omlx / "unused-ltx").symlink_to(media)
    report = cu._storage_report(
        root,
        backends,
        portal,
        total=1000,
        free=900,
        floor_gib=0,
        floor_percent=0,
        query_ollama=False,
        installed_blobs={},
    )
    lines = "\n".join(report.lines)
    fleet = next(line for line in report.lines if line.startswith("fleet:"))
    orphan = next(line for line in report.lines if line.startswith("orphan model data:"))
    active_record = (
        "omlx-models/active-checkpoint → hf-cache/models--org--active-checkpoint/snapshots/rev"
    )
    retired_record = (
        "omlx-models/retired-checkpoint → hf-cache/models--org--retired-checkpoint/snapshots/rev"
    )
    assert "fleet: 47 B" in lines and active_record in fleet
    assert "models--dgrauet--ltx-2.5-mlx-q4" in fleet
    assert "retired-alias" not in lines
    assert "orphan model data: 10 B" in lines and retired_record in orphan
    assert "models--org--active-checkpoint" not in orphan
    assert "ltx-2.5" not in orphan
    assert "safe to reclaim: 10 B" in lines
    assert lines.count("models--org--active-checkpoint") == 1


def test_storage_hf_hub_symlink_counts_root_layout_once(monkeypatch, tmp_path):
    root = tmp_path / "data01"
    backends, portal = _storage_yaml(
        tmp_path,
        "backends: []\n",
        "modules:\n  media:\n    enabled: true\n",
    )
    monkeypatch.setattr(cu, "_allocated_bytes", lambda info: info.st_size)
    _storage_bytes(root, "hf-cache/models--dgrauet--ltx-2.5-mlx-q4/blobs/weights", b"v" * 25)
    hub = root / "hf-cache" / "hub"
    hub.mkdir()
    (hub / "models--dgrauet--ltx-2.5-mlx-q4").symlink_to(
        Path("..") / "models--dgrauet--ltx-2.5-mlx-q4"
    )
    report = cu._storage_report(
        root,
        backends,
        portal,
        total=1000,
        free=900,
        floor_gib=0,
        floor_percent=0,
        query_ollama=False,
        installed_blobs={},
    )
    lines = "\n".join(report.lines)
    fleet = next(line for line in report.lines if line.startswith("fleet:"))
    assert "fleet: 25 B" in lines
    assert (
        "hf-cache/hub/models--dgrauet--ltx-2.5-mlx-q4 → hf-cache/models--dgrauet--ltx-2.5-mlx-q4"
    ) in fleet
    assert "safe to reclaim: 0 B" in lines
    assert "orphan model data: 0 B" in lines


def test_storage_dangling_symlink_is_shown_and_not_reclaimed(monkeypatch, tmp_path):
    root = tmp_path / "data01"
    backends, portal = _storage_yaml(
        tmp_path,
        "backends:\n"
        "- group: omlx\n"
        "  id: omlx-local\n"
        "  type: omlx\n"
        "  models:\n"
        "  - id: active-checkpoint\n",
    )
    monkeypatch.setattr(cu, "_allocated_bytes", lambda info: info.st_size)
    omlx = root / "omlx-models"
    omlx.mkdir(parents=True)
    missing = root / "hf-cache" / "models--missing--weights" / "snapshots" / "gone"
    (omlx / "active-checkpoint").symlink_to(missing)
    report = cu._storage_report(
        root,
        backends,
        portal,
        total=1000,
        free=900,
        floor_gib=0,
        floor_percent=0,
        query_ollama=False,
        installed_blobs={},
    )
    lines = "\n".join(report.lines)
    assert (
        "omlx-models/active-checkpoint → hf-cache/models--missing--weights/snapshots/gone"
    ) in lines
    assert "fleet: 0 B" in lines
    assert "orphan model data: 0 B" in lines
    assert "safe to reclaim: 0 B" in lines


def test_storage_low_space_uses_high_priority_pushover(monkeypatch, capsys):
    calls = []
    monkeypatch.setitem(
        cu.CHECKERS, "storage", lambda: cu.Report("storage", status="behind", high_priority=True)
    )
    monkeypatch.setattr(cu, "_pushover", lambda title, message, high: calls.append((title, high)))
    assert cu.main(["storage"]) == 0
    capsys.readouterr()
    assert calls == [("Storage space low", True)]
