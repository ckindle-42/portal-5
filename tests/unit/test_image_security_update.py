"""Unit tests for scripts/image_security_update.py's guarded Open WebUI pin
(no docker): hardened build, backup + health gate + rollback, and newer releases
are only proposed."""

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
OLD_REV, UPSTREAM_REV = "aaaaaaaaaaaa", "bbbbbbbbbbbb"
COMPOSE_TEXT = (
    "services:\n"
    "  open-webui:\n"
    f"    image: {iu.OWUI_IMAGE}\n"
    "    build:\n"
    "      context: .\n"
    "      dockerfile: Dockerfile.openwebui\n"
    "      args:\n"
    f"        OPENWEBUI_VERSION: {iu.OWUI_RELEASE}\n"
    "    pull_policy: never\n"
    "  other:\n"
    "    image: example:1\n"
)


def _cp(out: str = "", rc: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], rc, out, "")


def _patch(
    monkeypatch,
    tmp_path,
    *,
    built=NEW,
    healthy=(True,),
    rejected=(),
    latest="",
    rev=UPSTREAM_REV,
    on_tag=None,
):
    calls: list = []
    images = {iu.OWUI_IMAGE: OLD}
    revs = {OLD: OLD_REV, NEW: rev}
    path = tmp_path / "docker-compose.yml"
    path.write_text(COMPOSE_TEXT)

    def docker(*args, timeout=900):
        calls.append(("docker", *args))
        if args[0] == "inspect":
            return _cp(OLD)
        if args[:2] == ("image", "inspect"):
            img = images.get(args[2], args[2])
            return _cp(revs.get(img, "") if "revision" in args[-1] else img)
        if args[0] == "tag":
            if on_tag is not None:
                rc = on_tag(args[1], args[2], images)
                if rc is not None:
                    return _cp(rc=rc)
            images[args[2]] = images.get(args[1], args[1])
            return _cp()
        return _cp()

    def compose(*args, timeout=900):
        calls.append(("compose", *args))
        if args[0] == "build":
            images[iu._pinned_image()] = built  # a build tags the service's image
        return _cp()

    health = iter(healthy)
    monkeypatch.setattr(iu, "_docker", docker)
    monkeypatch.setattr(iu, "_compose", compose)
    monkeypatch.setattr(iu, "_wait_healthy", lambda *a: next(health))
    monkeypatch.setattr(iu, "_backup", lambda n: calls.append(("backup", n)) or True)
    monkeypatch.setattr(iu, "_restore", lambda n: calls.append(("restore", n)) or True)
    monkeypatch.setattr(iu, "_latest_release", lambda *a, **k: latest)
    monkeypatch.setattr(iu, "COMPOSE", path)
    monkeypatch.setattr(iu, "STATE", tmp_path / "state.json")
    if rejected:
        iu._save({"rejected": {"open-webui": list(rejected)}})
    return calls, images, path


def test_pin_is_read_from_the_build_arg(monkeypatch, tmp_path):
    path = tmp_path / "docker-compose.yml"
    path.write_text(
        COMPOSE_TEXT.replace(f"OPENWEBUI_VERSION: {iu.OWUI_RELEASE}", "OPENWEBUI_VERSION: v0.13.0")
    )
    monkeypatch.setattr(iu, "COMPOSE", path)
    assert iu._pinned_release() == "v0.13.0"
    assert iu._pinned_image() == iu.OWUI_IMAGE  # the image tag is bumped separately


def test_current_build_is_left_alone(monkeypatch, tmp_path):
    calls, _images, _compose = _patch(monkeypatch, tmp_path, built=OLD)
    ok, msg = iu.owui_update()
    assert ok and "current" in msg
    assert ("compose", "build", "open-webui") in calls
    assert not any(c[0] == "backup" for c in calls)
    assert not any(c[:2] == ("compose", "up") for c in calls)


def test_newer_release_is_proposed_not_applied(monkeypatch, tmp_path):
    calls, _images, compose = _patch(monkeypatch, tmp_path, built=OLD, latest="v9.9.9")
    ok, msg = iu.owui_update()
    assert ok and "newer release v9.9.9" in msg
    assert not any(c[0] == "backup" for c in calls)
    text = compose.read_text()
    assert f"image: {iu._image_ref('v9.9.9')}" not in text
    assert "OPENWEBUI_VERSION: v9.9.9" not in text


def test_apply_builds_instead_of_pulling(monkeypatch, tmp_path):
    calls, _images, _compose = _patch(monkeypatch, tmp_path)
    ok, msg = iu.owui_update()
    assert ok and "updated" in msg
    assert ("compose", "build", "open-webui") in calls
    assert not any(c[:2] == ("docker", "pull") for c in calls)


def test_new_build_backs_up_data_before_recreating(monkeypatch, tmp_path):
    calls, images, _compose = _patch(monkeypatch, tmp_path)
    ok, msg = iu.owui_update()
    assert ok and "updated" in msg
    backup = calls.index(next(c for c in calls if c[0] == "backup"))
    up = calls.index(("compose", "up", "-d", "--no-deps", "open-webui"))
    assert calls.index(("compose", "build", "open-webui")) < backup
    assert calls.index(("compose", "stop", "open-webui")) < backup < up
    assert images[iu.OWUI_ROLLBACK] == OLD  # previous build survives `image prune`


def test_unhealthy_build_is_rolled_back_and_rejected(monkeypatch, tmp_path):
    calls, images, _compose = _patch(monkeypatch, tmp_path, healthy=(False, True))
    ok, msg = iu.owui_update()
    assert not ok and "rolled back" in msg and "(healthy)" in msg
    assert any(c[0] == "restore" for c in calls)
    assert images[iu.OWUI_IMAGE] == OLD
    assert iu._load()["rejected"]["open-webui"] == [UPSTREAM_REV]


def test_rejected_build_is_not_retried(monkeypatch, tmp_path):
    calls, _images, _compose = _patch(monkeypatch, tmp_path, rejected=[UPSTREAM_REV])
    ok, msg = iu.owui_update()
    assert ok and "rejected" in msg
    assert not any(c[0] == "backup" for c in calls)


def test_rejected_revision_falls_back_to_the_release(monkeypatch, tmp_path):
    _calls, _images, _compose = _patch(monkeypatch, tmp_path, healthy=(False, True), rev="")
    ok, _msg = iu.owui_update(bump="v0.13.0")
    assert not ok
    assert iu._load()["rejected"]["open-webui"] == ["v0.13.0"]


def test_bump_rewrites_both_pin_fields_and_applies(monkeypatch, tmp_path):
    calls, _images, compose = _patch(monkeypatch, tmp_path)
    ok, msg = iu.owui_update(bump="v0.13.0")
    assert ok and "updated" in msg
    text = compose.read_text()
    assert f"image: {iu._image_ref('v0.13.0')}" in text
    assert "OPENWEBUI_VERSION: v0.13.0" in text
    backup = calls.index(next(c for c in calls if c[0] == "backup"))
    up = calls.index(("compose", "up", "-d", "--no-deps", "open-webui"))
    assert calls.index(("compose", "stop", "open-webui")) < backup < up


def test_unhealthy_bump_restores_the_previous_compose_pin(monkeypatch, tmp_path):
    calls, images, compose = _patch(monkeypatch, tmp_path, healthy=(False, True))
    before = compose.read_text()
    ok, msg = iu.owui_update(bump="v0.13.0")
    assert not ok and "rolled back" in msg
    assert compose.read_text() == before
    assert images[iu.OWUI_IMAGE] == OLD
    assert any(c[0] == "restore" for c in calls)


def test_bump_without_tag_uses_newest_release(monkeypatch, tmp_path):
    _calls, _images, compose = _patch(monkeypatch, tmp_path, latest="v0.13.0")
    ok, _msg = iu.owui_update(bump="")
    assert ok and f"image: {iu._image_ref('v0.13.0')}" in compose.read_text()


def test_bump_dry_run_does_not_touch_compose(monkeypatch, tmp_path):
    calls, _images, compose = _patch(monkeypatch, tmp_path)
    before = compose.read_text()
    ok, msg = iu.owui_update(dry_run=True, bump="v0.13.0")
    assert ok and "[dry-run] would bump" in msg
    assert compose.read_text() == before
    assert not any(c[0] in ("compose", "backup") for c in calls)


def test_bump_refuses_non_release_tag(monkeypatch, tmp_path):
    calls, _images, _compose = _patch(monkeypatch, tmp_path)
    ok, msg = iu.owui_update(bump="main")
    assert not ok and "release tag" in msg
    assert not any(c[0] in ("compose", "backup") for c in calls)


def test_hardened_image_inherits_the_upstream_revision_label():
    # Dockerfile.openwebui adds no LABEL, so docker keeps the upstream base's revision —
    # what _revision() reads for rejected-build bookkeeping.
    dockerfile = (_ROOT / "deploy" / "portal-5" / "Dockerfile.openwebui").read_text()
    assert "LABEL" not in dockerfile


def test_nothing_else_pulls_open_webui():
    compose = (_ROOT / "deploy" / "portal-5" / "docker-compose.yml").read_text()
    svc = re.search(r"^  open-webui:\n(.*?)(?=^  \S)", compose, re.MULTILINE | re.DOTALL)
    # Built from a pinned upstream release (Dockerfile.openwebui patches its bundled wheels);
    # compose never pulls or rebuilds it implicitly.
    assert svc and re.search(r"OPENWEBUI_VERSION: v\d+\.\d+\.\d+", svc.group(1))
    assert ":main" not in svc.group(1)
    assert "pull_policy: never" in svc.group(1)
    dockerfile = (_ROOT / "deploy" / "portal-5" / "Dockerfile.openwebui").read_text()
    assert "FROM ghcr.io/open-webui/open-webui:${OPENWEBUI_VERSION}" in dockerfile
    launch = (_ROOT / "launch.sh").read_text()
    pulls = [ln for ln in launch.splitlines() if re.search(r"docker compose pull\b", ln)]
    assert pulls and all("grep -vx open-webui" in ln for ln in pulls)


def test_rollback_uses_rollback_tag_when_old_id_is_gone(monkeypatch, tmp_path):
    def on_tag(src, dst, images):
        if src == OLD and dst != iu.OWUI_ROLLBACK:
            return 1  # the bare id was pruned; only :rollback still names it
        if dst == iu.OWUI_ROLLBACK:
            images[dst] = OLD
            return 0
        if src == iu.OWUI_ROLLBACK:
            images[dst] = images[src]
            return 0
        return None

    calls, images, _compose = _patch(monkeypatch, tmp_path, healthy=(False, True), on_tag=on_tag)
    ok, msg = iu.owui_update()
    assert not ok and "rolled back" in msg and "(healthy)" in msg
    assert images[iu.OWUI_IMAGE] == OLD
    assert ("docker", "tag", iu.OWUI_ROLLBACK, iu.OWUI_IMAGE) in calls
    assert ("docker", "tag", OLD, iu.OWUI_IMAGE) not in calls


def test_failed_rollback_stops_the_container_and_names_the_step(monkeypatch, tmp_path):
    def on_tag(src, dst, images):
        if dst == iu.OWUI_ROLLBACK:
            images[dst] = images.get(src, src)
            return 0
        if src == iu.OWUI_ROLLBACK:
            return 1
        return None

    calls, _images, _compose = _patch(monkeypatch, tmp_path, healthy=(False, True), on_tag=on_tag)
    ok, msg = iu.owui_update()
    assert not ok and "FAILED at retag" in msg
    retag = calls.index(("docker", "tag", iu.OWUI_ROLLBACK, iu.OWUI_IMAGE))
    assert any(c[:3] == ("compose", "stop", "open-webui") for c in calls[retag + 1 :])
    assert not any(c[:2] == ("compose", "up") for c in calls[retag + 1 :])


def test_failed_rollback_tag_does_not_recreate_the_container(monkeypatch, tmp_path):
    calls, images, _compose = _patch(monkeypatch, tmp_path, on_tag=lambda *_a: 1)
    ok, msg = iu.owui_update()
    assert not ok and "untouched" in msg
    assert iu.OWUI_ROLLBACK not in images
    assert not any(c[:2] == ("compose", "up") for c in calls)
    assert not any(c[:2] == ("compose", "stop") for c in calls)
    assert not any(c[0] == "backup" for c in calls)


def test_failed_bump_build_restores_the_previous_pin(tmp_path, monkeypatch):
    import scripts.image_security_update as m

    compose = tmp_path / "docker-compose.yml"
    original = (
        "services:\n  open-webui:\n    image: portal5-open-webui:v0.12.3-hardened\n"
        "    build:\n      args:\n        OPENWEBUI_VERSION: v0.12.3\n  other:\n    image: x\n"
    )
    compose.write_text(original)
    monkeypatch.setattr(m, "COMPOSE", compose)
    monkeypatch.setattr(
        m,
        "_docker",
        lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "sha:old", "stderr": ""})(),
    )
    monkeypatch.setattr(
        m,
        "_compose",
        lambda *a, **k: type("R", (), {"returncode": 1, "stdout": "", "stderr": "x"})(),
    )
    ok, msg = m.owui_update(bump="v0.12.4")
    assert ok and "build of v0.12.4 failed" in msg
    assert compose.read_text() == original


def test_rollback_is_tagged_before_the_build(monkeypatch, tmp_path):
    # containerd image store: the build drops the untagged running image (10-30 abort).
    calls, images, _compose = _patch(monkeypatch, tmp_path)
    ok, _msg = iu.owui_update()
    assert ok
    tag = calls.index(("docker", "tag", OLD, iu.OWUI_ROLLBACK))
    assert tag < calls.index(("compose", "build", "open-webui"))
    assert images[iu.OWUI_ROLLBACK] == OLD


def test_gone_running_image_falls_back_to_the_pinned_image_for_rollback(monkeypatch, tmp_path):
    def gone(src, _dst, _images):
        return 1 if src == OLD else None

    calls, images, _compose = _patch(monkeypatch, tmp_path, on_tag=gone)
    ok, msg = iu.owui_update()
    assert ok and "updated" in msg
    assert ("docker", "tag", iu.OWUI_IMAGE, iu.OWUI_ROLLBACK) in calls


def test_unknown_arguments_never_run_the_update(monkeypatch, tmp_path):
    calls, _images, _compose = _patch(monkeypatch, tmp_path)
    assert iu.main(["--help"]) == 2
    assert iu.main(["--bump", "v0.12.5", "--force"]) == 2
    assert not calls
    assert iu._unknown_args(["--dry-run", "--bump", "v0.12.5"]) == []
    assert iu._unknown_args(["--bump"]) == []
