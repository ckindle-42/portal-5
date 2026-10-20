"""Unit tests for scripts/image_security_update.py's guarded Open WebUI pin
(no docker): backup + health gate + rollback, and newer releases are only proposed."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
_SPEC = importlib.util.spec_from_file_location(
    "image_security_update", _ROOT / "scripts" / "image_security_update.py"
)
iu = importlib.util.module_from_spec(_SPEC)
sys.modules["image_security_update"] = iu
_SPEC.loader.exec_module(iu)

OLD, NEW = "sha256:old", "sha256:new"


def _cp(out: str = "", rc: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], rc, out, "")


def _patch(monkeypatch, tmp_path, *, pulled=NEW, healthy=(True,), rejected=(), latest=""):
    calls: list = []
    tags = {iu.OWUI_IMAGE: OLD}
    revs = {OLD: "aaaaaaaaaaaa", NEW: "bbbbbbbbbbbb"}
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        "services:\n"
        "  open-webui:\n"
        f"    image: {iu.OWUI_IMAGE}\n"
        "    pull_policy: missing\n"
        "  other:\n"
        "    image: example:1\n"
    )

    def docker(*args, timeout=900):
        calls.append(("docker", *args))
        if args[0] == "inspect":
            return _cp(OLD)
        if args[0] == "pull":
            tags[args[1]] = pulled
            return _cp()
        if args[0] == "tag":
            tags[args[2]] = args[1]
            return _cp()
        if args[:2] == ("image", "inspect"):
            img = tags.get(args[2], args[2])
            return _cp(revs[img] if "revision" in args[-1] else img)
        return _cp()

    health = iter(healthy)
    monkeypatch.setattr(iu, "_docker", docker)
    monkeypatch.setattr(iu, "_compose", lambda *a, **k: calls.append(("compose", *a)) or _cp())
    monkeypatch.setattr(iu, "_wait_healthy", lambda *a: next(health))
    monkeypatch.setattr(iu, "_backup", lambda n: calls.append(("backup", n)) or True)
    monkeypatch.setattr(iu, "_restore", lambda n: calls.append(("restore", n)) or True)
    monkeypatch.setattr(iu, "_latest_release", lambda *a, **k: latest)
    monkeypatch.setattr(iu, "COMPOSE", compose)
    monkeypatch.setattr(iu, "STATE", tmp_path / "state.json")
    if rejected:
        iu._save({"rejected": {"open-webui": list(rejected)}})
    return calls, tags


def test_current_build_is_left_alone(monkeypatch, tmp_path):
    calls, _ = _patch(monkeypatch, tmp_path, pulled=OLD)
    ok, msg = iu.owui_update()
    assert ok and "current" in msg
    assert not any(c[0] in ("compose", "backup") for c in calls)


def test_newer_release_is_proposed_not_applied(monkeypatch, tmp_path):
    calls, _ = _patch(monkeypatch, tmp_path, pulled=OLD, latest="v9.9.9")
    ok, msg = iu.owui_update()
    assert ok and "newer release v9.9.9" in msg
    assert not any(c[0] in ("compose", "backup") for c in calls)
    assert f"image: {iu.OWUI_REPO}:v9.9.9" not in (tmp_path / "docker-compose.yml").read_text()


def test_new_build_backs_up_data_before_recreating(monkeypatch, tmp_path):
    calls, tags = _patch(monkeypatch, tmp_path)
    ok, msg = iu.owui_update()
    assert ok and "updated" in msg
    backup = calls.index(next(c for c in calls if c[0] == "backup"))
    up = calls.index(("compose", "up", "-d", "--no-deps", "open-webui"))
    assert calls.index(("compose", "stop", "open-webui")) < backup < up
    assert tags[iu.OWUI_ROLLBACK] == OLD  # previous build survives `image prune`


def test_unhealthy_build_is_rolled_back_and_rejected(monkeypatch, tmp_path):
    calls, tags = _patch(monkeypatch, tmp_path, healthy=(False, True))
    ok, msg = iu.owui_update()
    assert not ok and "rolled back" in msg and "(healthy)" in msg
    assert any(c[0] == "restore" for c in calls)
    assert tags[iu.OWUI_IMAGE] == OLD
    assert iu._load()["rejected"]["open-webui"] == ["bbbbbbbbbbbb"]


def test_rejected_build_is_not_retried(monkeypatch, tmp_path):
    calls, _ = _patch(monkeypatch, tmp_path, rejected=["bbbbbbbbbbbb"])
    ok, msg = iu.owui_update()
    assert ok and "rejected" in msg
    assert not any(c[0] in ("compose", "backup") for c in calls)


def test_bump_rewrites_pin_and_applies_behind_health_gate(monkeypatch, tmp_path):
    calls, _ = _patch(monkeypatch, tmp_path)
    ok, msg = iu.owui_update(bump="v0.13.0")
    assert ok and "updated" in msg
    assert f"image: {iu.OWUI_REPO}:v0.13.0" in (tmp_path / "docker-compose.yml").read_text()
    backup = calls.index(next(c for c in calls if c[0] == "backup"))
    up = calls.index(("compose", "up", "-d", "--no-deps", "open-webui"))
    assert calls.index(("compose", "stop", "open-webui")) < backup < up


def test_bump_without_tag_uses_newest_release(monkeypatch, tmp_path):
    _calls, _ = _patch(monkeypatch, tmp_path, latest="v0.13.0")
    ok, _msg = iu.owui_update(bump="")
    assert ok and f"image: {iu.OWUI_REPO}:v0.13.0" in (tmp_path / "docker-compose.yml").read_text()


def test_bump_dry_run_does_not_touch_compose(monkeypatch, tmp_path):
    calls, _ = _patch(monkeypatch, tmp_path)
    before = (tmp_path / "docker-compose.yml").read_text()
    ok, msg = iu.owui_update(dry_run=True, bump="v0.13.0")
    assert ok and "[dry-run] would bump" in msg
    assert (tmp_path / "docker-compose.yml").read_text() == before
    assert not any(c[0] in ("compose", "backup") for c in calls)


def test_bump_refuses_non_release_tag(monkeypatch, tmp_path):
    calls, _ = _patch(monkeypatch, tmp_path)
    ok, msg = iu.owui_update(bump="main")
    assert not ok and "release tag" in msg
    assert not any(c[0] in ("compose", "backup") for c in calls)


def test_nothing_else_pulls_open_webui():
    compose = (_ROOT / "deploy" / "portal-5" / "docker-compose.yml").read_text()
    svc = re.search(r"^  open-webui:\n(.*?)(?=^  \S)", compose, re.MULTILINE | re.DOTALL)
    assert svc and re.search(r"image: ghcr\.io/open-webui/open-webui:v\d+\.\d+\.\d+", svc.group(1))
    assert ":main" not in svc.group(1)
    assert "pull_policy: missing" in svc.group(1)
    launch = (_ROOT / "launch.sh").read_text()
    pulls = [ln for ln in launch.splitlines() if re.search(r"docker compose pull\b", ln)]
    assert pulls and all("grep -vx open-webui" in ln for ln in pulls)
