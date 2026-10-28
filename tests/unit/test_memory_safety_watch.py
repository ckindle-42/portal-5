from __future__ import annotations

import os
import plistlib
from pathlib import Path

import pytest

from scripts import memory_safety_watch
from scripts.memory_safety_watch import (
    HostService,
    HostServiceState,
    ServiceCeiling,
    _host_native_services,
    _read_pids,
    _service_ceilings,
    _trip,
    check_host_services,
)

ROOT = Path(__file__).resolve().parents[2]
EMBED_LABEL = "com.portal5.eg2-embedding"
EMBED = [HostService("eg2-embedding", EMBED_LABEL, 8946)]
MEASURED_1GIB = {"eg2-embedding": ServiceCeiling(1.0, measured=True)}
PROVISIONAL_1GIB = {"eg2-embedding": ServiceCeiling(1.0, measured=False)}


def test_watch_trips_on_critical_pressure_or_low_swap_with_low_memory():
    assert _trip({"pressure_critical": True, "pressure_level": 4}, 1024, 20).startswith(
        "memory pressure is critical"
    )
    assert _trip(
        {"swap_free_mb": 791.3, "memory_free_pct": 12, "pressure_critical": False}, 1024, 20
    ) == ("swap free 791.3 MiB is below 1024 MiB and memory free 12% is below 20%")


def test_watch_ignores_low_swap_while_memory_is_plentiful():
    # The 2026-10-07 W2 false trip: macOS grows swap in 1 GiB files on demand,
    # so low free swap with 87% free memory is not a hazard.
    assert (
        _trip({"swap_free_mb": 791.3, "memory_free_pct": 87, "pressure_critical": False}, 1024, 20)
        is None
    )
    assert (
        _trip({"swap_free_mb": 2048, "memory_free_pct": 10, "pressure_critical": False}, 1024, 20)
        is None
    )
    assert _trip({"swap_free_mb": None, "memory_free_pct": None}, 1024, 20) is None


def test_watch_pid_file_ignores_invalid_and_own_pid(tmp_path):
    path = tmp_path / "pids"
    path.write_text(f"{os.getpid()}\nnot-a-pid\n42\n42\n1\n")

    assert _read_pids(path) == [42]


def test_omlx_emergency_unload_authenticates_status_and_unloads_idle_models(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        memory_safety_watch,
        "_dotenv_value",
        lambda name, default="": {
            "OMLX_URL": "http://omlx.test:8085",
            "OMLX_API_KEY": "test-key",
        }.get(name, default),
    )

    def fake_request(url, payload=None, *, opener=None, headers=None):
        calls.append((url, payload, headers))
        if url.endswith("/api/status"):
            return {"active_requests": 0, "waiting_requests": 0}
        if url.endswith("/admin/api/models"):
            return {"models": [{"id": "idle/model", "loaded": True, "pinned": False}]}
        return {}

    monkeypatch.setattr(memory_safety_watch, "_request_json", fake_request)
    log = tmp_path / "watch.log"

    memory_safety_watch._unload_omlx(log)

    assert calls[0][0].endswith("/admin/api/login")
    assert calls[1][0].endswith("/api/status")
    assert calls[1][2] == {"Authorization": "Bearer test-key"}
    assert calls[2][0].endswith("/admin/api/models")
    assert calls[3][0].endswith("/admin/api/models/idle%2Fmodel/unload")
    assert "idle oMLX unload" in log.read_text()


def test_ollama_base_rewrites_docker_host_for_the_host_watchdog(monkeypatch):
    monkeypatch.setattr(
        memory_safety_watch,
        "_dotenv_value",
        lambda name, default="": {"OLLAMA_URL": "http://host.docker.internal:11434/"}.get(
            name, default
        ),
    )
    assert memory_safety_watch._ollama_base() == "http://localhost:11434"


def test_omlx_unload_continues_past_a_model_already_evicted(tmp_path, monkeypatch):
    monkeypatch.setattr(
        memory_safety_watch,
        "_dotenv_value",
        lambda name, default="": {"OMLX_API_KEY": "k"}.get(name, default),
    )
    unloaded = []

    def fake_request(url, payload=None, *, opener=None, headers=None):
        if url.endswith("/api/status"):
            return {"active_requests": 0}
        if url.endswith("/admin/api/models"):
            return {"models": [{"id": "gone", "loaded": True}, {"id": "idle", "loaded": True}]}
        if url.endswith("/gone/unload"):
            raise OSError("400 Model not loaded")
        if url.endswith("/unload"):
            unloaded.append(url)
        return {}

    monkeypatch.setattr(memory_safety_watch, "_request_json", fake_request)
    log = tmp_path / "watch.log"
    memory_safety_watch._unload_omlx(log)

    assert unloaded and unloaded[0].endswith("/idle/unload")
    assert "oMLX unload failed model=gone" in log.read_text()


class FakeHost:
    """Stands in for launchctl/ps/footprint so no live service is touched."""

    def __init__(
        self,
        *,
        footprint: str = "    phys_footprint: 5.00 GB\n",
        job: str = "\tpid = 4242\n",
        ps: str = " 4242     1 /opt/portal/.venv/bin/python3\n",
    ) -> None:
        self.footprint = footprint
        self.job = job
        self.ps = ps
        self.calls: list[list[str]] = []

    def __call__(self, args, timeout=2.0):
        self.calls.append(list(args))
        if args[:2] == ["launchctl", "print"]:
            return self.job
        if args[0] == "ps":
            return self.ps
        if args[0] == "footprint":
            return self.footprint
        return ""

    def kickstarts(self) -> list[list[str]]:
        return [call for call in self.calls if call[:2] == ["launchctl", "kickstart"]]


def test_host_services_derive_labels_from_portal_config(tmp_path):
    config = tmp_path / "portal.yaml"
    config.write_text(
        "mcp_fleet:\n"
        "  - id: mlx_transcribe\n"
        "    port: 8924\n"
        "    host_native: true\n"
        "    launchd_label: com.portal5.mlx-transcribe\n"
        "    native_service: mlx-transcribe\n"
        "  - id: mflux\n"
        "    port: 8933\n"
        "    host_native: true\n"
        "    launchd_label: com.portal5.mflux\n"
        "  - id: documents\n"
        "    port: 8913\n"
        "    compose_service: mcp-documents\n"
        "host_jobs:\n"
        "  - label: com.portal5.eg2-embedding\n"
        "    port: 8946\n"
        "    service: eg2-embedding\n"
        "  - label: com.portal5.music-ace-mcp\n",
        encoding="utf-8",
    )

    assert _host_native_services(config) == [
        HostService("mlx-transcribe", "com.portal5.mlx-transcribe", 8924),
        HostService("mflux", "com.portal5.mflux", 8933),
        HostService("eg2-embedding", "com.portal5.eg2-embedding", 8946),
        HostService("music-ace-mcp", "com.portal5.music-ace-mcp", None),
    ]


def test_host_services_come_from_the_real_config_without_hardcoded_labels():
    keys = {service.key for service in _host_native_services()}
    assert {"eg2-embedding", "vl-retrieval", "mlx-speech", "mlx-transcribe", "mflux"} <= keys
    labels = {service.label for service in _host_native_services()}
    assert all(label.startswith("com.portal5.") for label in labels)


def test_service_ceilings_overlay_defaults_and_ignore_bad_entries():
    ceilings = _service_ceilings("eg2-embedding=0.5, nonsense, vl-retrieval=x")
    assert ceilings["eg2-embedding"] == ServiceCeiling(0.5, measured=True)
    assert ceilings["vl-retrieval"] == memory_safety_watch.DEFAULT_HOST_CEILINGS["vl-retrieval"]
    assert ceilings["mflux"].measured is False
    # An override never promotes a provisional ceiling to restart-eligible.
    assert _service_ceilings("wiki-mcp=1")["wiki-mcp"] == ServiceCeiling(1.0, measured=False)


def test_only_eg2_embedding_has_a_measured_ceiling():
    measured = {
        key
        for key, ceiling in memory_safety_watch.DEFAULT_HOST_CEILINGS.items()
        if ceiling.measured
    }
    assert measured == {"eg2-embedding"}
    assert memory_safety_watch.DEFAULT_HOST_CEILING.measured is False


def test_footprint_under_ceiling_never_restarts(tmp_path, monkeypatch):
    host = FakeHost(footprint="    phys_footprint: 2048 MB\n")
    monkeypatch.setattr(memory_safety_watch, "_command", host)
    log = tmp_path / "watch.log"

    for sample in range(3):
        assert (
            check_host_services(
                HostServiceState(),
                log,
                services=EMBED,
                ceilings={"eg2-embedding": ServiceCeiling(6.0, measured=True)},
                now=sample,
            )
            == []
        )

    assert host.kickstarts() == []
    assert not log.exists()


def test_over_ceiling_restarts_only_that_service_after_n_samples(tmp_path, monkeypatch):
    host = FakeHost(footprint="    phys_footprint: 5.00 GB\n")
    monkeypatch.setattr(memory_safety_watch, "_command", host)
    log = tmp_path / "watch.log"
    state = HostServiceState()

    for sample in range(2):
        assert (
            check_host_services(state, log, services=EMBED, ceilings=MEASURED_1GIB, now=sample)
            == []
        )
    assert host.kickstarts() == []
    assert "sample=2/3" in log.read_text()
    assert "ceiling_status=measured" in log.read_text()

    restarted = check_host_services(state, log, services=EMBED, ceilings=MEASURED_1GIB, now=2.0)

    assert [service.key for service in restarted] == ["eg2-embedding"]
    assert host.kickstarts() == [
        ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{EMBED_LABEL}"]
    ]
    text = log.read_text()
    assert "HOST SERVICE CEILING BREACH (restart): service=eg2-embedding" in text
    assert "footprint=5.00 GiB ceiling=1.00 GiB ceiling_status=measured" in text


def test_provisional_ceiling_logs_the_breach_and_never_restarts(tmp_path, monkeypatch):
    host = FakeHost(footprint="    phys_footprint: 7.00 GB\n")
    monkeypatch.setattr(memory_safety_watch, "_command", host)
    log = tmp_path / "watch.log"
    state = HostServiceState()
    transcribe = [HostService("mlx-transcribe", "com.portal5.mlx-transcribe", 8924)]

    for sample in range(5):
        assert check_host_services(state, log, services=transcribe, ceilings=None, now=sample) == []

    assert host.kickstarts() == []
    text = log.read_text()
    assert "HOST SERVICE CEILING BREACH (log-only): service=mlx-transcribe" in text
    assert "ceiling=6.00 GiB ceiling_status=provisional" in text
    assert text.count("HOST SERVICE CEILING BREACH") == 1


def test_provisional_override_of_a_measured_service_is_log_only(tmp_path, monkeypatch):
    host = FakeHost(footprint="    phys_footprint: 5.00 GB\n")
    monkeypatch.setattr(memory_safety_watch, "_command", host)
    log = tmp_path / "watch.log"
    state = HostServiceState()

    for sample in range(3):
        check_host_services(state, log, services=EMBED, ceilings=MEASURED_1GIB, now=sample)
    assert len(host.kickstarts()) == 1

    # Same footprint, but the ceiling is now flagged provisional: log-only from here on.
    state = HostServiceState()
    log.unlink()
    for sample in range(3):
        check_host_services(state, log, services=EMBED, ceilings=PROVISIONAL_1GIB, now=sample)

    assert len(host.kickstarts()) == 1
    assert "HOST SERVICE CEILING BREACH (log-only)" in log.read_text()


def test_under_ceiling_sample_resets_the_debounce(tmp_path, monkeypatch):
    host = FakeHost(footprint="    phys_footprint: 5.00 GB\n")
    monkeypatch.setattr(memory_safety_watch, "_command", host)
    log = tmp_path / "watch.log"
    state = HostServiceState()

    check_host_services(state, log, services=EMBED, ceilings=MEASURED_1GIB, now=0.0)
    check_host_services(state, log, services=EMBED, ceilings=MEASURED_1GIB, now=1.0)
    host.footprint = "    phys_footprint: 900 MB\n"
    check_host_services(state, log, services=EMBED, ceilings=MEASURED_1GIB, now=2.0)
    host.footprint = "    phys_footprint: 5.00 GB\n"
    for sample in (3.0, 4.0):
        check_host_services(state, log, services=EMBED, ceilings=MEASURED_1GIB, now=sample)

    assert host.kickstarts() == []


def test_restarts_are_rate_limited_per_service(tmp_path, monkeypatch):
    host = FakeHost(footprint="    phys_footprint: 5.00 GB\n")
    monkeypatch.setattr(memory_safety_watch, "_command", host)
    log = tmp_path / "watch.log"
    state = HostServiceState()

    for sample in range(3):
        check_host_services(
            state, log, services=EMBED, ceilings=MEASURED_1GIB, cooldown_s=60, now=sample
        )
    assert len(host.kickstarts()) == 1

    # Still over the ceiling, three more samples inside the cooldown: no second restart.
    for sample in range(10, 13):
        check_host_services(
            state, log, services=EMBED, ceilings=MEASURED_1GIB, cooldown_s=60, now=sample
        )
    assert len(host.kickstarts()) == 1

    # Past the cooldown the service may be restarted again.
    for sample in (62.0, 63.0, 64.0):
        check_host_services(
            state, log, services=EMBED, ceilings=MEASURED_1GIB, cooldown_s=60, now=sample
        )
    assert len(host.kickstarts()) == 2


def test_unmeasurable_service_is_logged_once_and_never_restarted(tmp_path, monkeypatch):
    host = FakeHost(job="")  # launchd job has no pid: not running
    monkeypatch.setattr(memory_safety_watch, "_command", host)
    log = tmp_path / "watch.log"
    state = HostServiceState()

    for sample in range(3):
        assert (
            check_host_services(
                state,
                log,
                services=EMBED,
                ceilings={"eg2-embedding": ServiceCeiling(0.1, measured=True)},
                now=sample,
            )
            == []
        )

    assert host.kickstarts() == []
    assert not [call for call in host.calls if call[0] == "footprint"]
    text = log.read_text()
    assert text.count("host service unmeasurable") == 1


def test_unparseable_footprint_output_is_unmeasurable(tmp_path, monkeypatch):
    host = FakeHost(footprint="footprint: task_for_pid failed\n")
    monkeypatch.setattr(memory_safety_watch, "_command", host)
    log = tmp_path / "watch.log"

    for sample in range(3):
        check_host_services(
            HostServiceState(),
            log,
            services=EMBED,
            ceilings={"eg2-embedding": ServiceCeiling(0.1, measured=True)},
            now=sample,
        )

    assert host.kickstarts() == []
    assert "host service unmeasurable, never restarted: service=eg2-embedding" in log.read_text()


def test_service_without_a_declared_ceiling_uses_the_provisional_global_default(
    tmp_path, monkeypatch
):
    host = FakeHost(footprint="    phys_footprint: 4.50 GB\n")
    monkeypatch.setattr(memory_safety_watch, "_command", host)
    log = tmp_path / "watch.log"
    state = HostServiceState()
    service = [HostService("wiki-mcp", "com.portal5.wiki-mcp", 8931)]

    for sample in range(3):
        assert check_host_services(state, log, services=service, ceilings={}, now=sample) == []

    assert host.kickstarts() == []
    text = log.read_text()
    assert f"ceiling={memory_safety_watch.DEFAULT_HOST_CEILING.gib:.2f} GiB" in text
    assert "ceiling_status=provisional" in text


def test_python_child_is_measured_when_launchd_job_is_a_shell_wrapper(tmp_path, monkeypatch):
    host = FakeHost(
        job="\tpid = 700\n",
        ps="  700     1 /bin/bash /opt/portal/scripts/native-mcp-service.sh eg2-embedding\n"
        "  701   700 /opt/portal/.venv/bin/python3 /opt/portal/eg2.py\n",
    )
    monkeypatch.setattr(memory_safety_watch, "_command", host)
    log = tmp_path / "watch.log"

    check_host_services(HostServiceState(), log, services=EMBED, ceilings=MEASURED_1GIB, now=0.0)

    measured = [call for call in host.calls if call[0] == "footprint"]
    assert measured == [["footprint", "-p", "701"]]


def test_services_only_mode_never_samples_trips_kills_or_unloads(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("services-only must not reach the trip path")

    for name in ("_snapshot", "_trip", "_kill_test_clients", "_unload_ollama", "_unload_omlx"):
        monkeypatch.setattr(memory_safety_watch, name, forbidden)
    monkeypatch.setattr(memory_safety_watch, "_log_top_processes", forbidden)
    host = FakeHost(footprint="    phys_footprint: 5.00 GB\n")
    monkeypatch.setattr(memory_safety_watch, "_command", host)
    log = tmp_path / "watch.log"

    assert (
        memory_safety_watch.watch_services(
            log=log, services=EMBED, service_ceilings=MEASURED_1GIB, once=True
        )
        == 0
    )

    assert host.kickstarts() == []
    assert "host service sample: services=1 restarted=[]" in log.read_text()


def test_services_only_restarts_a_measured_breach_after_three_samples(tmp_path, monkeypatch):
    host = FakeHost(footprint="    phys_footprint: 5.00 GB\n")
    monkeypatch.setattr(memory_safety_watch, "_command", host)
    log = tmp_path / "watch.log"
    sleeps: list[float] = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 3:
            raise SystemExit("three samples taken")

    monkeypatch.setattr(memory_safety_watch.time, "sleep", fake_sleep)

    with pytest.raises(SystemExit):
        memory_safety_watch.watch_services(log=log, services=EMBED, service_ceilings=MEASURED_1GIB)

    assert sleeps == [30.0, 30.0, 30.0]
    assert host.kickstarts() == [
        ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{EMBED_LABEL}"]
    ]


def test_main_services_only_selects_the_services_loop_with_a_30s_default(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def record(kind):
        def fake(**kwargs):
            calls.append((kind, kwargs))
            return 0

        return fake

    monkeypatch.setattr(memory_safety_watch, "watch", record("watch"))
    monkeypatch.setattr(memory_safety_watch, "watch_services", record("services"))

    assert memory_safety_watch.main(["--services-only", "--once"]) == 0
    assert memory_safety_watch.main(["--services-only", "--once", "--interval", "5"]) == 0
    assert memory_safety_watch.main(["--once"]) == 0

    assert [kind for kind, _ in calls] == ["services", "services", "watch"]
    assert calls[0][1]["interval_s"] == memory_safety_watch.DEFAULT_SERVICES_INTERVAL_S
    assert calls[1][1]["interval_s"] == 5.0
    assert calls[2][1]["interval_s"] == 2.0


def test_host_ml_watch_plist_runs_the_services_only_mode():
    with (ROOT / "deploy" / "launchd" / "com.portal5.host-ml-watch.plist").open("rb") as stream:
        plist = plistlib.load(stream)

    args = plist["ProgramArguments"]
    assert plist["Label"] == "com.portal5.host-ml-watch"
    assert args[0] == "__PORTAL_ROOT__/.venv/bin/python"
    assert args[1] == "__PORTAL_ROOT__/scripts/memory_safety_watch.py"
    assert "--services-only" in args
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] is True
    assert plist["StandardOutPath"].startswith("__LOG_DIR__/")
    assert plist["StandardErrorPath"].startswith("__LOG_DIR__/")


def test_launch_sh_installs_the_host_ml_watch_job_idempotently():
    util = (ROOT / "scripts" / "lib" / "util.sh").read_text(encoding="utf-8")

    assert '_hmw_label="com.portal5.host-ml-watch"' in util
    assert '_hmw_dst="$HOME/Library/LaunchAgents/${_hmw_label}.plist"' in util
    assert '"s#__LOG_DIR__#${HOME}/.portal5/logs#g"' in util
    assert 'launchctl print "gui/$(id -u)/${_hmw_label}"' in util
    assert 'launchctl bootstrap "gui/$(id -u)" "$_hmw_dst"' in util
    assert '"Host ML watchdog"' in util
