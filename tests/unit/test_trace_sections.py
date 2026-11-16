"""`portal trace` section parsers and verdicts — pure functions, no network or docker."""

from __future__ import annotations

import os
import plistlib
from pathlib import Path

import pytest
import typer

from portal.modules.security.cli import trace_lab
from portal.platform.inference.cli.trace import (
    containers,
    context,
    engines,
    host,
    lab,
    pins,
    workspaces,
)
from portal.platform.inference.cli.trace.command import selected
from portal.platform.inference.cli.trace.model import Hop, Status

# ── context ──────────────────────────────────────────────────────────────────


def test_host_url_rewrites_container_hostnames_for_the_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PIPELINE_URL", "http://portal-pipeline:9099")
    monkeypatch.setenv("OLLAMA_URL", "http://host.docker.internal:11434")
    monkeypatch.setenv("OMLX_URL", "http://127.0.0.1:8085")
    assert context.host_url("PIPELINE_URL", "http://127.0.0.1:9099") == "http://127.0.0.1:9099"
    assert context.host_url("OLLAMA_URL", "") == "http://127.0.0.1:11434"
    assert context.host_url("OMLX_URL", "") == "http://127.0.0.1:8085"
    monkeypatch.setenv("PORTAL_REVIEW_PIPELINE_URL", "http://10.0.1.5:9099")
    assert (
        context.host_url("PIPELINE_URL", "http://127.0.0.1:9099", "PORTAL_REVIEW_PIPELINE_URL")
        == "http://10.0.1.5:9099"
    )


# ── host ─────────────────────────────────────────────────────────────────────


def _plist(**extra: object) -> bytes:
    payload: dict[str, object] = {"Label": "com.portal5.omlx"}
    payload.update(extra)
    return plistlib.dumps(payload)


def test_plist_helpers_default_and_read_declared_values() -> None:
    cfg = host.parse_plist(
        _plist(ProcessType="Standard", EnvironmentVariables={"PATH": "/bin"}, RunAtLoad=True)
    )
    assert host.process_type(cfg) == "Standard"
    assert host.env_keys(cfg) == ["PATH"]
    assert host.schedule(cfg) == "oneshot"
    assert host.process_type({}) == "Standard"
    assert host.env_keys({}) == []


def test_schedule_separates_resident_from_periodic_jobs() -> None:
    assert host.schedule({"KeepAlive": True}) == "resident"
    assert host.schedule({"KeepAlive": {"SuccessfulExit": False}}) == "resident"
    assert host.schedule({"RunAtLoad": True, "StartInterval": 120}) == "periodic"
    assert host.schedule({"StartCalendarInterval": {"Hour": 4}}) == "periodic"
    assert host.schedule({"RunAtLoad": True}) == "oneshot"


def test_install_dir_sends_root_daemons_to_the_system_domain() -> None:
    assert host.install_dir({"UserName": "root"}) == Path("/Library/LaunchDaemons")
    assert host.install_dir({}) == host._DEFAULT_INSTALL_DIR
    assert host.is_daemon({"UserName": "root"}) and not host.is_daemon({})


def test_parse_job_state_reads_runs_pid_and_last_exit() -> None:
    printed = (
        "\tgui/501/com.portal5.omlx = {\n"
        "\tstate = running\n"
        "\tpid = 94943\n"
        "\truns = 13028\n"
        "\tlast exit code = 0\n"
        "\trun interval = 120 seconds\n"
    )
    state = host.parse_job_state(printed, loaded=True)
    assert (state.running, state.pid, state.runs, state.last_exit, state.interval_s) == (
        True,
        94943,
        13028,
        0,
        120,
    )
    assert host.parse_job_state("", loaded=False).loaded is False


def test_program_paths_and_missing_paths(tmp_path: Path) -> None:
    cfg = {"ProgramArguments": ["/bin/bash", str(tmp_path / "job.sh")]}
    assert host.program_paths(cfg) == ["/bin/bash", str(tmp_path / "job.sh")]
    assert host.missing_program_paths(cfg) == [str(tmp_path / "job.sh")]
    assert host.program_paths({"Program": "/bin/true"}) == ["/bin/true"]
    assert host.program_paths({}) == []


def test_parse_priority_takes_the_first_number() -> None:
    assert host.parse_priority(" 20\n") == 20
    assert host.parse_priority("  4") == 4
    assert host.parse_priority("") is None


def test_priority_hop_fails_engines_at_background_priority() -> None:
    hop = host.priority_hop("com.portal5.omlx", 4)
    assert hop.status is Status.FAIL
    assert "Background" in hop.expected
    assert host.priority_hop("com.portal5.omlx", 20).status is Status.PASS


def test_priority_hop_allows_a_scheduled_helper_above_background() -> None:
    assert host.priority_hop("com.portal5.log-rotate", 10).status is Status.WARN
    assert host.priority_hop("com.portal5.log-rotate", 4).status is Status.FAIL


def test_installed_hop_reports_a_missing_plist() -> None:
    hops = host.installed_hop("com.portal5.omlx", {}, None)
    assert hops[0].status is Status.FAIL
    assert hops[0].observed.startswith("installed=missing")


def test_installed_hop_compares_process_type_and_env_keys() -> None:
    cfg = {"ProcessType": "Standard", "EnvironmentVariables": {"PATH": "/bin", "HOME": "/h"}}
    installed = host.parse_plist(
        _plist(ProcessType="Background", EnvironmentVariables={"PATH": "/bin"})
    )
    hops = host.installed_hop("com.portal5.omlx", cfg, installed)
    assert hops[0].status is Status.FAIL  # ProcessType differs
    assert hops[1].status is Status.FAIL  # HOME missing
    assert hops[1].detail == "missing=HOME"


def test_installed_hop_fails_a_missing_program_and_warns_on_stale_args(tmp_path: Path) -> None:
    cfg = {"ProgramArguments": ["/usr/bin/true", "/usr/local/libexec/portal5-powermetrics"]}
    installed = {"ProgramArguments": ["/usr/bin/true", "/usr/local/libexec/portal5-powermetrics"]}
    hops = host.installed_hop("com.portal5.powermetrics", cfg, installed)
    program = next(hop for hop in hops if hop.name.startswith("program "))
    assert program.status is Status.FAIL
    assert "/usr/local/libexec/portal5-powermetrics" in program.observed

    stale = {"ProgramArguments": ["/usr/bin/true", "/usr/local/bin/portal5-powermetrics"]}
    hops = host.installed_hop("com.portal5.powermetrics", cfg, stale)
    args = next(hop for hop in hops if hop.name.startswith("args "))
    assert args.status is Status.WARN and "installer" in args.detail


def test_installed_hop_warns_on_unsubstituted_placeholders() -> None:
    cfg = {"ProgramArguments": ["__OMLX_VENV__/bin/python", "-m", "omlx.cli"]}
    hop = host.program_hop("com.portal5.omlx", cfg)
    assert hop.status is Status.WARN and "__OMLX_VENV__" in hop.observed


def test_installed_hop_skips_argument_drift_for_templated_plists() -> None:
    cfg = {"ProgramArguments": ["/bin/bash", "__PORTAL_ROOT__/scripts/x.sh"]}
    installed = {"ProgramArguments": ["/bin/bash", "/opt/portal/scripts/x.sh"]}
    names = [hop.name for hop in host.installed_hop("com.portal5.x", cfg, installed)]
    assert not any(name.startswith("args ") for name in names)


def test_process_hop_requires_a_resident_job_to_have_a_pid() -> None:
    cfg = {"KeepAlive": True}
    hop = host.process_hop("com.portal5.omlx", cfg, host.JobState(loaded=True, runs=3, last_exit=0))
    assert hop.status is Status.FAIL and hop.observed == "pid=none (KeepAlive)"
    missing = host.process_hop("com.portal5.omlx", cfg, host.JobState(loaded=False))
    assert missing.status is Status.FAIL and missing.observed == "not loaded"


def test_process_hop_passes_a_periodic_job_on_its_last_run() -> None:
    cfg = {"RunAtLoad": True, "StartInterval": 120}
    healthy = host.process_hop(
        "com.portal5.omlx-watchdog",
        cfg,
        host.JobState(loaded=True, runs=13028, last_exit=0, interval_s=120),
    )
    assert healthy.status is Status.PASS
    assert healthy.observed == "runs=13028 last exit=0 every 120s"
    failed = host.process_hop(
        "com.portal5.omlx-watchdog", cfg, host.JobState(loaded=True, runs=2, last_exit=1)
    )
    assert failed.status is Status.FAIL and "last exit=1" in failed.observed
    never = host.process_hop(
        "com.portal5.omlx-watchdog", cfg, host.JobState(loaded=True, runs=0, last_exit=None)
    )
    assert never.status is Status.WARN


# ── containers ───────────────────────────────────────────────────────────────


def _container(**extra: object) -> containers.ContainerRow:
    base = containers.ContainerRow(
        name="portal5-pipeline",
        image_ref="portal-5-portal-pipeline",
        image_id="sha256:ec00421ec0495",
        created=1794780837.0,
        started=1794791084.0,
        service="portal-pipeline",
    )
    values = {**base.__dict__, **extra}
    return containers.ContainerRow(**values)  # type: ignore[arg-type]


def test_parse_iso_handles_docker_nanoseconds() -> None:
    assert containers.parse_iso("2026-11-16T01:04:44.232912389Z") == pytest.approx(1794791084.23)
    assert containers.parse_iso("2026-11-16T01:04:44Z") == containers.parse_iso(
        "2026-11-16T01:04:44.000Z"
    )
    assert containers.parse_iso("not a date") == 0.0


def test_same_image_matches_short_and_full_ids() -> None:
    assert containers.same_image("sha256:ec00421ec0495", "ec00421ec049")
    assert not containers.same_image("sha256:ec00421ec0495", "111111111111")
    assert not containers.same_image("", "")


def test_newest_image_is_the_first_row_for_that_repository() -> None:
    rows = containers.parse_images(
        "aaa\tportal-5-portal-pipeline\tlatest\n"
        "bbb\tportal-5-portal-pipeline\told\n"
        "ccc\tportal5-open-webui\tv0.13.0-hardened\n"
    )
    assert containers.newest_image(rows, "portal-5-portal-pipeline") is not None
    assert containers.newest_image(rows, "portal-5-portal-pipeline").image_id == "aaa"  # type: ignore[union-attr]
    assert containers.newest_image(rows, "absent") is None
    assert containers.parse_images("<none>\t<none>\t<none>")[0].repo == "<none>"


def test_copied_paths_ignores_multistage_sources(tmp_path: Path) -> None:
    dockerfile = (
        "FROM python:3.11-slim\n"
        "COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker\n"
        "COPY pyproject.toml ./\n"
        "COPY portal/ ./portal/\n"
        "COPY scripts/pipeline-entrypoint.sh /app/scripts/pipeline-entrypoint.sh\n"
    )
    assert containers.copied_paths(dockerfile) == [
        "pyproject.toml",
        "portal",
        "scripts/pipeline-entrypoint.sh",
    ]


def test_parse_container_reads_the_compose_labels() -> None:
    row = containers.parse_container(
        {
            "Name": "/portal5-pipeline",
            "Image": "sha256:abc",
            "Created": "2026-11-16T01:04:42.679393304Z",
            "State": {"StartedAt": "2026-11-16T01:04:44.232912389Z"},
            "Config": {
                "Image": "portal-5-portal-pipeline",
                "Labels": {"com.docker.compose.service": "portal-pipeline"},
            },
            "Mounts": [
                {"Destination": "/app/config/backends.yaml", "Source": "/repo/config/backends.yaml"}
            ],
        }
    )
    assert row.name == "portal5-pipeline"
    assert row.service == "portal-pipeline"
    assert row.repo == "portal-5-portal-pipeline"
    assert containers.mounts_of(row.mounts) == {
        "/app/config/backends.yaml": "/repo/config/backends.yaml"
    }


def test_image_freshness_fails_when_a_newer_build_exists() -> None:
    newest = containers.ImageRow("sha256:aaaaaaaaaaaa", "portal-5-portal-pipeline", "latest")
    stale = containers.image_freshness_hop(_container(), newest)
    assert stale.status is Status.FAIL
    assert "not recreated" in stale.detail
    fresh = containers.image_freshness_hop(_container(image_id="sha256:aaaaaaaaaaaa"), newest)
    assert fresh.status is Status.PASS


def test_start_hop_fails_when_the_container_predates_its_image() -> None:
    assert containers.start_after_build_hop(_container(), 1794792000.0).status is Status.FAIL
    assert containers.start_after_build_hop(_container(), 1794000000.0).status is Status.PASS
    assert containers.start_after_build_hop(_container(started=0.0), 1.0).status is Status.WARN


def test_revision_hop_warns_before_the_label_existed_and_fails_after() -> None:
    predated = containers.revision_hop(
        "repo", "", "abc123456789", [], 1000.0, ("c52e81568aa", 2000.0)
    )
    assert predated.status is Status.WARN and "predates" in predated.detail
    late = containers.revision_hop("repo", "", "abc123456789", [], 3000.0, ("c52e81568aa", 2000.0))
    assert late.status is Status.FAIL and "rebuild" in late.detail
    assert containers.revision_hop("repo", "", "abc123456789", []).status is Status.FAIL
    assert containers.revision_hop("repo", "abc123456789", "abc123456789", []).status is Status.PASS
    dirty = containers.revision_hop("repo", "abc123456789", "abc123456789", ["M portal/x.py"])
    assert dirty.status is Status.WARN
    assert containers.revision_hop("repo", "999123456789", "abc123456789", []).status is Status.FAIL


def test_label_commit_reads_the_pickaxe_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(containers, "_git", lambda root, args: "c52e81568abc 1794790000")
    assert containers.label_commit(Path("/repo"), "Dockerfile.pipeline") == (
        "c52e81568abc",
        1794790000.0,
    )
    monkeypatch.setattr(containers, "_git", lambda root, args: "")
    assert containers.label_commit(Path("/repo"), "Dockerfile.mcp") == ("", 0.0)


def test_config_hop_lists_baked_files_that_differ_from_the_repo(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "portal.yaml").write_text("current\n")
    hashes = {
        "/app/config/portal.yaml": "0" * 64,
        "/app/config/backends.yaml": containers.sha256_file(tmp_path / "config" / "portal.yaml"),
    }
    row = _container(mounts=[])
    hop = containers.config_hop(row, tmp_path, hashes)
    assert hop.status is Status.WARN
    assert "config/portal.yaml" in hop.detail
    assert hop.observed == "mounted=0 baked=2"


def test_config_hop_skips_bind_mounted_files(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "portal.yaml").write_text("current\n")
    digest = containers.sha256_file(tmp_path / "config" / "portal.yaml")
    hashes = {"/app/config/portal.yaml": digest, "/app/config/backends.yaml": digest}
    mounts = [{"Destination": "/app/config/portal.yaml", "Source": "/repo/config/portal.yaml"}]
    hop = containers.config_hop(_container(mounts=mounts), tmp_path, hashes)
    assert hop.status is Status.PASS
    assert hop.observed == "mounted=1 baked=1"


def test_parse_hash_lines_accepts_either_column_order() -> None:
    digest = "a" * 64
    parsed = containers.parse_hash_lines(f"{digest}  /app/config/portal.yaml\n")
    assert parsed == {"/app/config/portal.yaml": digest}
    assert containers.parse_hash_lines("/app/config/x " + digest) == {"/app/config/x": digest}
    assert containers.parse_hash_lines("sha256sum: not found") == {}


# ── workspaces ───────────────────────────────────────────────────────────────


def test_production_seats_covers_variants_and_excludes_bench() -> None:
    portal = {
        "workspaces": {
            "auto": {},
            "auto-coding": {
                "model_hint": "granite:8b",
                "variants": {"lite": {"model_hint": "granite:2b"}, "inherit": {}},
            },
            "bench-lane": {"model_hint": "bench-granite41-8b"},
        }
    }
    assert workspaces.production_seats(portal) == [
        workspaces.Seat("auto-coding", "granite:8b"),
        workspaces.Seat("auto-coding::lite", "granite:2b"),
        workspaces.Seat("auto-coding::inherit", "granite:8b"),
    ]


def test_parse_sse_ignores_noise_and_the_terminator() -> None:
    assert workspaces.parse_sse('data: {"choices": []}') == {"choices": []}
    assert workspaces.parse_sse("data: [DONE]") is None
    assert workspaces.parse_sse(": keep-alive") is None
    assert workspaces.parse_sse("data: not-json") is None
    assert workspaces.parse_sse("") is None


def test_summarize_turn_derives_ttft_rate_and_usage() -> None:
    events = [
        (0.50, {"choices": [{"delta": {"content": "O"}}]}),
        (1.00, {"choices": [{"delta": {"content": "K"}}]}),
        (1.10, {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 2}}),
    ]
    stats = workspaces.summarize_turn(events)
    assert (stats.ttft_s, stats.text, stats.content_chunks) == (0.50, "OK", 2)
    assert stats.completion_tokens == 2
    assert stats.prompt_tokens == 10
    assert stats.decode_tps == pytest.approx(4.0)


def _seat() -> workspaces.Seat:
    return workspaces.Seat("auto-general", "huihui_ai/qwen3.5-abliterated:9b-ctx8k")


def test_seat_hop_fails_a_refusal_and_an_empty_stream() -> None:
    refused = workspaces.seat_hop(_seat(), workspaces.StreamedTurn(507, body="does not fit"))
    assert refused.status is Status.FAIL and refused.observed == "refused 507"
    empty = workspaces.seat_hop(_seat(), workspaces.StreamedTurn(200, ["w", "b", "m"]))
    assert empty.status is Status.FAIL and empty.observed == "empty stream"


def test_seat_hop_fails_a_turn_without_usage() -> None:
    stats = workspaces.TurnStats(ttft_s=0.4, text="OK", content_chunks=1)
    hop = workspaces.seat_hop(_seat(), workspaces.StreamedTurn(200, ["w", "b", "m"], stats))
    assert hop.status is Status.FAIL
    assert "usage=missing" in hop.observed


def test_seat_hop_passes_a_healthy_turn_and_warns_on_substitution() -> None:
    stats = workspaces.TurnStats(ttft_s=0.4, decode_tps=41.0, completion_tokens=18, text="OK")
    served = ["w", "b", "huihui_ai/qwen3.5-abliterated:9b-ctx8k"]
    hop = workspaces.seat_hop(_seat(), workspaces.StreamedTurn(200, served, stats))
    assert hop.status is Status.PASS
    assert "backend=b" in hop.observed and "decode=41.0t/s" in hop.observed
    other = workspaces.seat_hop(
        _seat(), workspaces.StreamedTurn(200, ["w", "b", "some-other-model"], stats)
    )
    assert other.status is Status.WARN


# ── pins ─────────────────────────────────────────────────────────────────────


def _pin_tree(tmp_path: Path) -> Path:
    module = tmp_path / "portal" / "x.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        'BACKEND_DEFAULT = "omlx-general"\n'
        'PORTAL_BACKEND_ID: str = "ollama-general"\n'
        'DEFAULT_JUDGE_BACKEND = "omlx-general"\n'
        'SEAT_SYSTEM = "You are one sealed seat on a council. Judge only this unit."\n'
        'SYSTEM_PROMPT = "omlx-general"\n'
        "def f():\n"
        '    LOCAL_BACKEND = "omlx-general"\n'
    )
    return tmp_path


def test_discover_pins_reads_module_literals_and_skips_prompts(tmp_path: Path) -> None:
    found = {pin.name: pin.value for pin in pins.discover_pins(_pin_tree(tmp_path))}
    assert found == {
        "BACKEND_DEFAULT": "omlx-general",
        "PORTAL_BACKEND_ID": "ollama-general",
        "DEFAULT_JUDGE_BACKEND": "omlx-general",
    }


def test_classify_splits_backends_from_seats_and_models() -> None:
    backends = [pins.Backend("omlx-general", "omlx", "http://x", {})]
    assert pins.classify("omlx-general", backends, set()) == "backend"
    assert pins.classify("auto-coding", backends, {"auto-coding"}) == "seat"
    assert pins.classify("granite4.1:8b-ctx8k", backends, {"auto-coding"}) == "model"


def test_load_backends_expands_urls_and_keeps_aliases(tmp_path: Path) -> None:
    path = tmp_path / "backends.yaml"
    path.write_text(
        "backends:\n"
        "  - id: omlx-general\n"
        "    type: omlx\n"
        "    url: ${OMLX_URL:-http://host.docker.internal:8085}\n"
        "    aliases:\n"
        "      gemma4:26b-a4b-it-qat-ctx8k: gemma-4-26b-a4b-it-QAT-4bit\n"
    )
    loaded = pins.load_backends(path)
    assert loaded[0].backend_id == "omlx-general"
    assert loaded[0].url == "http://host.docker.internal:8085"
    assert loaded[0].aliases == {"gemma4:26b-a4b-it-qat-ctx8k": "gemma-4-26b-a4b-it-QAT-4bit"}


def test_alias_hop_verdict_follows_the_engine_model_list() -> None:
    backend = pins.Backend("omlx-general", "omlx", "http://x", {})
    served = engines.EngineModels(omlx={"gemma-4-26b-a4b-it-QAT-4bit"})
    assert pins.alias_hop(backend, "hint", "gemma-4-26b-a4b-it-QAT-4bit", served).status is (
        Status.PASS
    )
    assert pins.alias_hop(backend, "hint", "gone", served).status is Status.FAIL


def test_backend_hops_fails_once_when_its_engine_did_not_answer() -> None:
    backend = pins.Backend("omlx-general", "omlx", "http://x", {"a": "b", "c": "d"})
    hops = pins.backend_hops(backend, engines.EngineModels())
    assert len(hops) == 1
    assert hops[0].status is Status.FAIL
    assert hops[0].detail == "2 alias(es) unverified"


# ── engines ──────────────────────────────────────────────────────────────────


def test_model_ids_reads_openai_and_status_shapes() -> None:
    assert engines.model_ids({"data": [{"id": "a"}, {"id": ""}]}) == {"a"}
    assert engines.model_ids({"models": [{"id": "b"}]}) == {"b"}
    assert engines.model_ids("nope") == set()


def test_parse_omlx_status_reports_ceiling_and_loaded() -> None:
    gib = 1024**3
    ceiling, loaded, used = engines.parse_omlx_status(
        {
            "final_ceiling": 48 * gib,
            "current_model_memory": 12 * gib,
            "models": [{"id": "m1", "loaded": True}, {"id": "m2", "loaded": False}],
        }
    )
    assert (ceiling, used) == (48.0, 12.0)
    assert loaded == ["m1"]
    assert engines.parse_omlx_status(None) == (None, [], None)


def test_parse_ollama_ps_sizes_residents() -> None:
    rows = engines.parse_ollama_ps({"models": [{"name": "gemma:2b", "size": 2 * 1024**3}]})
    assert rows == [("gemma:2b", 2.0)]
    assert engines.parse_ollama_ps({}) == []


def test_parse_seat_fit_keeps_the_three_verdict_lists() -> None:
    verdicts = engines.parse_seat_fit(
        {"never_fit": ["a"], "undeclared_never_fit": ["a", "b"], "unserved": []}
    )
    assert verdicts["undeclared_never_fit"] == ["a", "b"]
    assert set(verdicts) == {"never_fit", "undeclared_never_fit", "unserved"}
    assert engines.parse_seat_fit(None)["never_fit"] == []


def test_seat_fit_basis_names_the_budget_the_verdicts_used() -> None:
    basis = engines.seat_fit_basis(
        {"available_gib": 17.234, "budget_source": "oMLX final_ceiling (live)"}
    )
    assert basis == "available=17.2GiB oMLX final_ceiling (live)"
    assert engines.seat_fit_basis({}) == ""


def test_parse_nvidia_smi_and_nice_rows() -> None:
    assert engines.parse_nvidia_smi("P0, 1303, 250.00, 54.57\n") == {
        "pstate": "P0",
        "clocks": "1303",
        "power_limit": "250.00",
        "power_draw": "54.57",
    }
    assert engines.parse_nvidia_smi("") == {}
    assert engines.parse_nice_table("  6631   0 /usr/bin/ollama\nnoise\n") == [
        ("6631", "0", "/usr/bin/ollama")
    ]


# ── lab ──────────────────────────────────────────────────────────────────────


def test_parse_server_info_reads_version_and_name() -> None:
    text = '{"entry": [{"content": {"version": "9.2.1", "serverName": "lab-splunk"}}]}'
    assert trace_lab.parse_server_info(text) == {"version": "9.2.1", "serverName": "lab-splunk"}
    assert trace_lab.parse_server_info("not json") == {}
    assert trace_lab.parse_server_info("{}") == {}


def test_load_lab_env_exports_the_splunk_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LAB_SPLUNK_URL", raising=False)
    monkeypatch.delenv("LAB_SPLUNK_INDEX", raising=False)
    env = tmp_path / ".env"
    env.write_text("LAB_SPLUNK_URL=https://10.0.1.30:8089\nLAB_SPLUNK_INDEX=portal5_lab\n")
    trace_lab.load_lab_env(env)
    assert os.environ["LAB_SPLUNK_URL"] == "https://10.0.1.30:8089"
    assert os.environ["LAB_SPLUNK_INDEX"] == "portal5_lab"


class _LabBackend:
    def __init__(self, hits: dict[tuple[str, str], int]) -> None:
        self.hits = hits
        self.calls: list[tuple[str, str]] = []

    def query(self, technique: str, window: dict[str, str]) -> dict[str, object]:
        self.calls.append((technique, window["earliest"]))
        rows = [{"host": "lab-host"}] * self.hits.get((technique, window["earliest"]), 0)
        return {"rows": rows}


def test_labelled_event_hop_falls_back_to_the_corpus_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        trace_lab,
        "spl_for",
        lambda technique: "index=portal5_lab" if technique == "T1059.001" else None,
    )
    backend = _LabBackend({("T1059.001", "-400d"): 25})
    hop = trace_lab.labelled_event_hop(backend)
    assert hop["status"] == "PASS"
    assert "rows=25" in hop["observed"] and "window=-400d" in hop["observed"]
    assert backend.calls == [("T1059.001", "-7d"), ("T1059.001", "-400d")]


def test_labelled_event_hop_fails_with_every_empty_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trace_lab, "spl_for", lambda technique: "index=portal5_lab")
    hop = trace_lab.labelled_event_hop(_LabBackend({}))
    assert hop["status"] == "FAIL"
    assert "T1059.001-7d=0" in hop["observed"] and "T1059.001-400d=0" in hop["observed"]


def _lab_hop(**extra: object) -> dict[str, str]:
    hop = {"name": "splunk auth", "status": "PASS", "observed": "ok"}
    hop.update({key: str(value) for key, value in extra.items()})
    return hop


def test_lab_section_adapts_contributed_hops() -> None:
    hops = lab.run({"lab": lambda: [_lab_hop()]})
    assert [(hop.name, hop.status, hop.observed) for hop in hops] == [
        ("splunk auth", Status.PASS, "ok")
    ]


def test_lab_section_fails_when_no_module_contributes_it() -> None:
    hop = lab.run({})[0]
    assert hop.status is Status.FAIL and "no module contributes" in hop.observed


def test_lab_section_fails_when_the_module_raises_or_returns_junk() -> None:
    def boom() -> list[dict[str, str]]:
        raise RuntimeError("splunk is down")

    raised = lab.run({"lab": boom})[0]
    assert raised.status is Status.FAIL and "splunk is down" in raised.observed
    junk = lab.run({"lab": lambda: [{"name": "x", "status": "MAYBE"}]})[0]
    assert junk.status is Status.FAIL and "not a valid" in junk.detail + junk.observed
    empty = lab.run({"lab": lambda: []})[0]
    assert empty.status is Status.FAIL and "no hops" in empty.observed


# ── section selection ────────────────────────────────────────────────────────


def test_section_selection_accepts_keys_numbers_and_prefixes() -> None:
    def keys(values: list[str] | None) -> list[str]:
        return [key for key, _title, _run in selected(values)]

    assert keys(None) == ["host", "containers", "workspaces", "pins", "engines", "lab"]
    assert keys(["1"]) == ["host"]
    assert keys(["containers"]) == ["containers"]
    assert keys(["c"]) == ["containers"]
    assert keys(["lab", "host"]) == ["host", "lab"]
    with pytest.raises(typer.BadParameter):
        selected(["nope"])


def test_hops_render_without_a_trailing_space() -> None:
    assert not Hop("x", Status.PASS).observed


def test_seat_hop_accepts_the_resolved_router_lane() -> None:
    seat = workspaces.Seat("auto", "huihui_ai/qwen3.5-abliterated:9b-ctx8k")
    hints = {"auto": seat.hint, "auto-daily": "hf.co/bartowski/NVIDIA-Nemotron-30B:Q4_K_M-ctx32k"}
    stats = workspaces.TurnStats(ttft_s=0.4, completion_tokens=24, text="OK")
    served = ["auto-daily", "ollama-general", "hf.co/bartowski/NVIDIA-Nemotron-30B:Q4_K_M-ctx32k"]
    hop = workspaces.seat_hop(seat, workspaces.StreamedTurn(200, served, stats), hints)
    assert hop.status is Status.PASS
    assert hop.expected == "hf.co/bartowski/NVIDIA-Nemotron-30B:Q4_K_M-ctx32k"
    assert "via=auto-daily" in hop.observed


def test_seat_hop_still_warns_when_the_resolved_lane_leaves_its_seat() -> None:
    seat = workspaces.Seat("auto-vision", "qwen3-vl:32b-ctx8k")
    hints = {"auto-vision": seat.hint, "auto-reasoning": "k2-horizon:36b-ctx64k"}
    stats = workspaces.TurnStats(ttft_s=0.4, completion_tokens=24, text="OK")
    off = workspaces.seat_hop(
        seat, workspaces.StreamedTurn(200, ["auto-reasoning", "b", "some-other"], stats), hints
    )
    assert off.status is Status.WARN
    assert off.expected == "k2-horizon:36b-ctx64k"


def test_seat_hop_keeps_the_seat_hint_for_an_unknown_resolved_lane() -> None:
    seat = workspaces.Seat("auto", "huihui_ai/qwen3.5-abliterated:9b-ctx8k")
    stats = workspaces.TurnStats(ttft_s=0.4, completion_tokens=24, text="OK")
    hop = workspaces.seat_hop(
        seat,
        workspaces.StreamedTurn(200, ["bench-x", "b", "some-other"], stats),
        {"auto": seat.hint},
    )
    assert hop.status is Status.WARN
    assert hop.expected == seat.hint
