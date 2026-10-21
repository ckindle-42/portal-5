"""engine_autoupdate — the contract-gated engine update decisions (no network,
no engines: every side effect is monkeypatched)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import engine_autoupdate as eu
from scripts import omlx_venv_install as omlx_install


@pytest.fixture(autouse=True)
def _no_router_repin(monkeypatch):
    """A sourced .env sets LLM_ROUTER_MODEL, which would send _repin_router to live Ollama."""
    monkeypatch.delenv("LLM_ROUTER_MODEL", raising=False)


def test_repin_router_loads_the_router_model_pinned(monkeypatch):
    sent = []

    class _Resp:
        def read(self):
            return b"{}"

    def _urlopen(req, timeout):
        sent.append((req.full_url, json.loads(req.data)))
        return _Resp()

    monkeypatch.setenv("LLM_ROUTER_MODEL", "router-tag")
    monkeypatch.setattr(eu.urllib.request, "urlopen", _urlopen)
    eu._repin_router()
    assert sent == [(f"{eu.OLLAMA_URL}/api/generate", {"model": "router-tag", "keep_alive": -1})]


@pytest.fixture
def ollama(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(eu, "ollama_running", lambda: "0.34.2")
    monkeypatch.setattr(eu, "ollama_latest", lambda: "0.34.4")
    monkeypatch.setattr(eu, "ollama_install", lambda v: calls.append(("install", v)))
    monkeypatch.setattr(eu, "ollama_prune", lambda keep: calls.append(("prune", keep)))
    monkeypatch.setattr(eu, "omlx_prune", lambda keep: calls.append(("prune", keep)))
    monkeypatch.setattr(eu, "_model_count", lambda: 90)
    monkeypatch.setattr(eu, "_alert", lambda *a, **k: calls.append(("alert", a[0])))
    return calls


def test_current_prerelease_and_rejected_are_skipped(monkeypatch, ollama):
    monkeypatch.setattr(eu, "ollama_latest", lambda: "0.34.2")
    assert eu.update_engine("ollama", {}, False) is False
    monkeypatch.setattr(eu, "ollama_latest", lambda: "0.40.0rc0")
    assert eu.update_engine("ollama", {}, False) is False
    monkeypatch.setattr(eu, "ollama_latest", lambda: "0.34.4")
    assert eu.update_engine("ollama", {"rejected": {"ollama": ["0.34.4"]}}, False) is False
    assert not [c for c in ollama if c[0] == "install"]


def test_contract_pass_keeps_the_update(monkeypatch, ollama):
    monkeypatch.setattr(eu, "ollama_switch", lambda v, n: ollama.append(("switch", v)) or "ok")
    monkeypatch.setattr(eu, "contract", lambda e: 0)
    state: dict = {}
    assert eu.update_engine("ollama", state, False) is False
    assert ("switch", "0.34.2") not in ollama
    assert state["history"][-1]["result"] == "updated"


def test_contract_failure_rolls_back_and_rejects(monkeypatch, ollama):
    monkeypatch.setattr(eu, "ollama_switch", lambda v, n: ollama.append(("switch", v)) or "ok")
    rcs = iter([1, 0])  # new version fails, rolled-back version passes
    monkeypatch.setattr(eu, "contract", lambda e: next(rcs))
    state: dict = {}
    assert eu.update_engine("ollama", state, False) is False
    assert ("switch", "0.34.2") in ollama
    assert state["rejected"]["ollama"] == ["0.34.4"]
    assert state["history"][-1] == state["history"][-1] | {
        "result": "rolled_back",
        "rollback_rc": 0,
    }


def test_unapproved_data01_popup_rolls_back_without_rejecting(monkeypatch, ollama):
    """No one clicked Allow on the macOS volume-access popup: that is not a
    verdict on the release — roll back and retry on the next daily run."""
    outcomes = iter(["tcc", "ok"])
    monkeypatch.setattr(eu, "ollama_switch", lambda v, n: next(outcomes))
    monkeypatch.setattr(eu, "contract", lambda e: 0)
    state: dict = {}
    assert eu.update_engine("ollama", state, False) is True
    assert "0.34.4" not in state.get("rejected", {}).get("ollama", [])
    assert state["history"][-1]["result"] == "awaiting_approval"


def test_busy_detects_a_running_sweep(monkeypatch):
    class R:
        stdout = "python -m tests.wfe.campaign --campaign-id x\n"

    monkeypatch.setattr(eu, "_run", lambda *a, **k: R())
    assert eu.busy()


def test_omlx_unapproved_popup_rolls_back_without_rejecting(monkeypatch):
    calls: list = []
    monkeypatch.setattr(eu, "omlx_running", lambda: "0.6.4")
    monkeypatch.setattr(eu, "omlx_latest", lambda: "0.7.0")
    monkeypatch.setattr(eu, "omlx_model_count", lambda: 36)
    monkeypatch.setattr(eu, "omlx_backup", lambda tag: None)
    monkeypatch.setattr(eu, "omlx_restore", lambda tag: calls.append("restore"))
    monkeypatch.setattr(eu, "omlx_upgrade", lambda version, n: "tcc")
    monkeypatch.setattr(eu, "omlx_point_at", lambda v: calls.append(("point", v)) or True)
    monkeypatch.setattr(eu, "_omlx_restart", lambda: True)
    monkeypatch.setattr(eu, "contract", lambda e: 0)
    monkeypatch.setattr(eu, "_alert", lambda *a, **k: None)
    state: dict = {}
    assert eu.update_engine("omlx", state, False) is True
    assert ("point", "0.6.4") in calls and "restore" in calls
    assert not state.get("rejected", {}).get("omlx")


def _mock_omlx_subprocess(calls: list[list[str]], version: str):
    def run(cmd: list[str], timeout: int = 1800):
        calls.append(cmd)
        if cmd[0] == "codesign":
            return subprocess.CompletedProcess(
                cmd, 0, "Authority=Developer ID Application: Python", ""
            )
        if "-m" in cmd and "venv" in cmd:
            stage = Path(cmd[-1])
            (stage / "bin").mkdir(parents=True)
            (stage / "bin" / "python").touch()
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if "-c" in cmd:
            code = cmd[-1]
            output = "cp313\n" if "sys.version_info" in code else "arm64\n"
            if "importlib.metadata" in code:
                output += f"{version}\n"
            return subprocess.CompletedProcess(cmd, 0, output, "")
        if "pip" in cmd:
            Path(cmd[0]).with_name("omlx").write_text(f"#!{cmd[0]}\n")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    return run


def _mock_release_wheel(monkeypatch):
    monkeypatch.setattr(
        omlx_install,
        "_release_asset",
        lambda version, tag: (
            f"omlx-{version}-{tag}-{tag}-macosx_15_0_universal2.whl",
            "https://github.com/release.whl",
        ),
    )

    def download(url, filename):
        Path(filename).write_bytes(b"mock wheel")
        return str(filename), None

    monkeypatch.setattr(omlx_install.urllib.request, "urlretrieve", download)


def test_omlx_venv_installer_creates_release_venv_with_mocked_subprocess(monkeypatch, tmp_path):
    _mock_release_wheel(monkeypatch)
    calls: list[list[str]] = []
    target = tmp_path / "omlx-live" / "venv"
    python = Path("/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13")
    omlx_install.install("0.7.2", target, python, _mock_omlx_subprocess(calls, "0.7.2"))
    assert (target / "bin" / "python").is_file()
    assert (target / "bin" / "omlx").read_text().splitlines()[0] == f"#!{target}/bin/python"
    assert any(cmd[0] == "codesign" for cmd in calls)
    assert any("-m" in cmd and "venv" in cmd for cmd in calls)


def test_omlx_venv_upgrade_installs_wheel_into_staged_copy(monkeypatch, tmp_path):
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").touch()
    (venv / "installed-version").write_text("0.6.4")
    monkeypatch.setattr(eu, "OMLX_VENV", venv)
    monkeypatch.setattr(eu, "omlx_venv_active", lambda: True)
    monkeypatch.setattr(eu, "_omlx_restart", lambda: True)
    monkeypatch.setattr(eu, "omlx_model_count", lambda: 2)
    monkeypatch.setattr(eu, "_await_visible", lambda *a, **k: True)
    _mock_release_wheel(monkeypatch)
    calls: list[list[str]] = []
    monkeypatch.setattr(eu, "_run", _mock_omlx_subprocess(calls, "0.7.2"))
    assert eu.omlx_upgrade("0.7.2", 2) == "ok"
    assert (venv.with_name("venv.previous") / "installed-version").read_text() == "0.6.4"
    assert (venv / "bin" / "omlx").read_text().splitlines()[0] == f"#!{venv}/bin/python"
    assert any(
        "pip" in cmd
        and "install" in cmd
        and "omlx-0.7.2-cp313-cp313-macosx_15_0_universal2.whl" in cmd[-1]
        for cmd in calls
    )


def test_omlx_rollback_reinstalls_previous_release_wheel(monkeypatch, tmp_path):
    venv = tmp_path / "venv"
    previous = venv.with_name("venv.previous")
    for path, version in ((venv, "0.7.2"), (previous, "0.6.4")):
        (path / "bin").mkdir(parents=True)
        (path / "bin" / "python").touch()
        (path / "installed-version").write_text(version)
    monkeypatch.setattr(eu, "OMLX_VENV", venv)
    monkeypatch.setattr(eu, "omlx_venv_active", lambda: True)
    monkeypatch.setattr(eu, "omlx_running", lambda: "0.7.2")
    monkeypatch.setattr(eu, "_omlx_restart", lambda: True)
    _mock_release_wheel(monkeypatch)
    calls: list[list[str]] = []
    monkeypatch.setattr(eu, "_run", _mock_omlx_subprocess(calls, "0.6.4"))
    assert eu.omlx_point_at("0.6.4") is True
    assert (venv / "installed-version").read_text() == "0.6.4"
    assert (venv / "bin" / "omlx").read_text().splitlines()[0] == f"#!{venv}/bin/python"
    assert any(
        "pip" in cmd
        and "install" in cmd
        and "omlx-0.6.4-cp313-cp313-macosx_15_0_universal2.whl" in cmd[-1]
        for cmd in calls
    )


def test_omlx_label_detection_uses_portal_label_only_when_venv_loaded(monkeypatch, tmp_path):
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").touch()
    monkeypatch.setattr(eu, "OMLX_VENV", venv)
    monkeypatch.setattr(
        eu,
        "_run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "loaded", ""),
    )
    assert eu.omlx_service_label() == "com.portal5.omlx"
    monkeypatch.setattr(
        eu,
        "_run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 113, "", "not loaded"),
    )
    assert eu.omlx_service_label() == "sh.brew.omlx"


def test_omlx_latest_version_comes_from_github_release(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(
        eu,
        "_get",
        lambda url: seen.append(url) or {"tag_name": "v0.7.2"},
    )
    assert eu.omlx_latest() == "0.7.2"
    assert seen == ["https://api.github.com/repos/jundot/omlx/releases/latest"]


def test_ollama_prune_keeps_only_listed_releases(monkeypatch, tmp_path):
    arch, home = tmp_path / "engines", tmp_path / "home"
    for d in (
        arch / "ollama-0.40.4",
        arch / "ollama-0.40.3",
        arch / "ollama-0.40.0",
        home / "ollama-0.34.2",
    ):
        d.mkdir(parents=True)
    (home / "ollama-live").mkdir()
    monkeypatch.setattr(eu, "OLLAMA_ARCHIVE", arch)
    monkeypatch.setattr(eu, "HOME", home)
    eu.ollama_prune({"0.40.4", "0.40.3"})
    assert sorted(p.name for p in arch.iterdir()) == ["ollama-0.40.3", "ollama-0.40.4"]
    assert sorted(p.name for p in home.iterdir()) == ["ollama-live"]


def test_omlx_prune_keeps_only_listed_kegs(monkeypatch, tmp_path):
    for v in ("0.6.4", "0.7.0", "0.7.1"):
        (tmp_path / v).mkdir()
    monkeypatch.setattr(eu, "OMLX_CELLAR", tmp_path)
    eu.omlx_prune({"0.7.0", "0.7.1"})
    assert sorted(p.name for p in tmp_path.iterdir()) == ["0.7.0", "0.7.1"]
