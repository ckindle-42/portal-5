"""`portal trace` section parsers and verdicts — pure functions, no network or docker."""

from __future__ import annotations

import plistlib
from pathlib import Path
from typing import Any

import pytest
import typer

from portal.modules.security.cli import trace_lab
from portal.platform.inference.cli.trace import (
    containers,
    engines,
    host,
    lab,
    media,
    owui,
    pins,
    workspaces,
)
from portal.platform.inference.cli.trace.command import selected
from portal.platform.inference.cli.trace.model import Hop, Status


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


def test_installed_hop_warns_on_unsubstituted_placeholders() -> None:
    cfg = {"ProgramArguments": ["__OMLX_VENV__/bin/python", "-m", "omlx.cli"]}
    hop = host.program_hop("com.portal5.omlx", cfg, ("/opt/omlx-live/venv/bin/python", "-m"))
    assert hop.status is Status.WARN and "__OMLX_VENV__" in hop.observed
    assert "loaded=/opt/omlx-live/venv/bin/python" in hop.detail


def test_parse_arguments_reads_the_loaded_job_block() -> None:
    printed = (
        "\tgui/501/com.portal5.omlx = {\n"
        "\targuments = {\n"
        "\t\t/opt/omlx-live/venv/bin/python\n"
        "\t\t-m\n"
        "\t\tomlx.cli\n"
        "\t\tserve\n"
        "\t}\n"
        "\tstate = running\n"
    )
    state = host.parse_job_state(printed, loaded=True)
    assert state.arguments == (
        "/opt/omlx-live/venv/bin/python",
        "-m",
        "omlx.cli",
        "serve",
    )
    assert host.parse_arguments("no block here") == ()


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


def test_image_freshness_compares_the_container_with_its_own_reference() -> None:
    fresh = containers.image_freshness_hop(_container(), "sha256:ec00421ec0495")
    assert fresh.status is Status.PASS
    assert fresh.observed == "running=ec00421ec049 portal-5-portal-pipeline=ec00421ec049"
    stale = containers.image_freshness_hop(_container(), "sha256:aaaaaaaaaaaa")
    assert stale.status is Status.FAIL
    assert "not recreated" in stale.detail


def test_open_webui_rollback_tag_does_not_make_the_container_stale() -> None:
    # portal5-open-webui:rollback is written in the same second as the image it copies;
    # the repository's "newest" image is not what the container's reference resolves to.
    row = _container(
        name="portal5-open-webui",
        image_ref="portal5-open-webui:v0.13.0-hardened",
        image_id="sha256:fa60cb07e276",
    )
    assert containers.image_freshness_hop(row, "sha256:fa60cb07e276").status is Status.PASS


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
    stale = containers.image_freshness_hop(_container(), "sha256:aaaaaaaaaaaa")
    assert stale.status is Status.FAIL
    assert "not recreated" in stale.detail
    fresh = containers.image_freshness_hop(
        _container(image_id="sha256:aaaaaaaaaaaa"), "sha256:aaaaaaaaaaaa"
    )
    assert fresh.status is Status.PASS


def test_start_hop_fails_when_the_container_predates_its_image() -> None:
    assert containers.start_after_build_hop(_container(), 1794792000.0).status is Status.FAIL
    assert containers.start_after_build_hop(_container(), 1794000000.0).status is Status.PASS
    assert containers.start_after_build_hop(_container(started=0.0), 1.0).status is Status.WARN


def test_revision_hop_warns_before_the_label_existed_and_fails_after() -> None:
    predated = containers.revision_hop(
        "repo", "", "abc123456789", [], 1000.0, ("c52e81568aa", 2000.0), current=False
    )
    assert predated.status is Status.WARN and "predates" in predated.detail
    late = containers.revision_hop(
        "repo", "", "abc123456789", [], 3000.0, ("c52e81568aa", 2000.0), current=False
    )
    assert late.status is Status.FAIL and "rebuild" in late.detail
    assert (
        containers.revision_hop("repo", "", "abc123456789", [], current=False).status is Status.FAIL
    )
    assert (
        containers.revision_hop("repo", "abc123456789", "abc123456789", [], current=True).status
        is Status.PASS
    )
    dirty = containers.revision_hop(
        "repo", "abc123456789", "abc123456789", ["M portal/x.py"], current=True
    )
    assert dirty.status is Status.WARN
    assert (
        containers.revision_hop("repo", "999123456789", "abc123456789", [], current=False).status
        is Status.FAIL
    )


def test_parse_hash_lines_accepts_either_column_order() -> None:
    digest = "a" * 64
    parsed = containers.parse_hash_lines(f"{digest}  /app/config/portal.yaml\n")
    assert parsed == {"/app/config/portal.yaml": digest}
    assert containers.parse_hash_lines("/app/config/x " + digest) == {"/app/config/x": digest}
    assert containers.parse_hash_lines("sha256sum: not found") == {}


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


def test_summarize_turn_counts_reasoning_apart_from_answer_content() -> None:
    """A reasoning-only turn is not an empty one: the deltas say which happened."""
    notice = "⚠️ The model did not produce an answer. Please retry."
    events = [
        (0.40, {"choices": [{"delta": {"reasoning": "the user wants "}}]}),
        (0.90, {"choices": [{"delta": {"reasoning": "one word"}}]}),
        (7.10, {"choices": [{"delta": {"content": notice}, "finish_reason": "length"}]}),
        (7.20, {"choices": [], "usage": {"completion_tokens": 24, "source": "pipeline"}}),
    ]
    stats = workspaces.summarize_turn(events)
    assert (stats.reasoning_deltas, stats.content_chunks) == (2, 1)
    assert stats.text == notice
    assert stats.usage_source == "pipeline"


def test_summarize_turn_treats_inline_think_as_reasoning_not_answer() -> None:
    """A leaked inline ``<think>`` is reasoning: the seat grades WARN, never PASS as an answer."""
    unclosed = workspaces.summarize_turn(
        [
            (0.40, {"choices": [{"delta": {"content": "<think>The user asks"}}]}),
            (0.90, {"choices": [{"delta": {"content": ": extract names"}}]}),
            (1.00, {"choices": [], "usage": {"completion_tokens": 24}}),
        ]
    )
    assert unclosed.text == "" and unclosed.reasoning_deltas == 2
    hop = workspaces.seat_hop(_seat(), workspaces.StreamedTurn(200, ["w", "b", "m"], unclosed))
    assert hop.status is Status.WARN  # reasoning-only, not "no answer content"
    assert "reasoning-only" in hop.observed

    closed = workspaces.summarize_turn(
        [
            (0.40, {"choices": [{"delta": {"content": "<think>plan</think>OK"}}]}),
            (0.50, {"choices": [], "usage": {"completion_tokens": 2}}),
        ]
    )
    assert (closed.text, closed.reasoning_deltas) == ("OK", 1)
    served = ["w", "b", "huihui_ai/qwen3.5-abliterated:9b-ctx8k"]
    assert workspaces.seat_hop(_seat(), workspaces.StreamedTurn(200, served, closed)).status is (
        Status.PASS
    )


def test_seat_hop_tells_a_reasoning_only_turn_from_an_empty_one() -> None:
    """Live 2026-11-16: both seats read "tokens=0 usage missing"; the engine log said
    `reasoning_only=True` on one and nothing on the other, and the trace could not tell."""
    notice = "⚠️ The model did not produce an answer. Please retry."
    reasoning = workspaces.TurnStats(
        text=notice, content_chunks=1, reasoning_deltas=24, completion_tokens=24
    )
    hop = workspaces.seat_hop(_seat(), workspaces.StreamedTurn(200, ["w", "b", "m"], reasoning))
    assert hop.status is Status.WARN  # the turn's own 24-token budget, not a dead seat
    assert "reasoning-only (24 reasoning deltas" in hop.observed
    assert "reasoning=24" in hop.observed and "raise MAX_TOKENS" in hop.detail

    empty = workspaces.TurnStats(
        ttft_s=15.0,
        text=notice,
        content_chunks=1,
        completion_tokens=0,
        usage_source="pipeline",
    )
    hop = workspaces.seat_hop(_seat(), workspaces.StreamedTurn(200, ["w", "b", "m"], empty))
    assert hop.status is Status.FAIL  # no reasoning and no answer: the stream carried nothing
    assert "no answer content" in hop.observed
    assert "usage=pipeline" in hop.observed and "reasoning-only" not in hop.observed

    answered = workspaces.TurnStats(ttft_s=0.4, text="OK", content_chunks=2, completion_tokens=2)
    served = ["w", "b", "huihui_ai/qwen3.5-abliterated:9b-ctx8k"]
    hop = workspaces.seat_hop(_seat(), workspaces.StreamedTurn(200, served, answered))
    assert hop.status is Status.PASS


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


def test_classify_splits_backends_from_seats_and_models() -> None:
    backends = [pins.Backend("omlx-general", "omlx", "http://x", {})]
    assert pins.classify("omlx-general", backends, set()) == "backend"
    assert pins.classify("auto-coding", backends, {"auto-coding"}) == "seat"
    assert pins.classify("granite4.1:8b-ctx8k", backends, {"auto-coding"}) == "model"


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


def test_parse_seat_fit_keeps_the_verdict_lists() -> None:
    verdicts = engines.parse_seat_fit(
        {
            "never_fit": ["a"],
            "undeclared_never_fit": ["a", "b"],
            "over_budget": ["a", "c"],
            "undeclared_over_budget": ["a", "c"],
            "unserved": [],
        }
    )
    assert verdicts["undeclared_never_fit"] == ["a", "b"]
    assert verdicts["undeclared_over_budget"] == ["a", "c"]
    assert set(verdicts) == {
        "never_fit",
        "undeclared_never_fit",
        "over_budget",
        "undeclared_over_budget",
        "unserved",
    }
    assert engines.parse_seat_fit(None)["never_fit"] == []


def test_seat_fit_verdict_fails_never_fit_and_warns_over_budget() -> None:
    fatal = engines.seat_fit_verdict(
        {
            "never_fit": ["a"],
            "undeclared_never_fit": ["a"],
            "over_budget": ["a", "b"],
            "undeclared_over_budget": ["a", "b"],
            "available_gib": 27.5,
            "budget_source": "oMLX final_ceiling (live)",
        }
    )
    assert fatal.status is Status.FAIL and "never_fit=1" in fatal.observed
    live = engines.seat_fit_verdict(
        {
            "never_fit": [],
            "undeclared_never_fit": [],
            "over_budget": ["a", "b"],
            "undeclared_over_budget": ["a", "b"],
            "available_gib": 27.5,
            "budget_source": "oMLX final_ceiling (live)",
        }
    )
    assert live.status is Status.WARN
    assert "over_budget=2" in live.observed and "available=27.5GiB" in live.observed
    clean = engines.seat_fit_verdict({"never_fit": [], "over_budget": [], "unserved": []})
    assert clean.status is Status.PASS


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


def test_parse_server_info_reads_version_and_name() -> None:
    text = '{"entry": [{"content": {"version": "9.2.1", "serverName": "lab-splunk"}}]}'
    assert trace_lab.parse_server_info(text) == {"version": "9.2.1", "serverName": "lab-splunk"}
    assert trace_lab.parse_server_info("not json") == {}
    assert trace_lab.parse_server_info("{}") == {}


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


def test_section_selection_accepts_keys_numbers_and_prefixes() -> None:
    def keys(values: list[str] | None) -> list[str]:
        return [key for key, _title, _run in selected(values)]

    expected = [
        "host",
        "containers",
        "workspaces",
        "pins",
        "aliases",
        "engines",
        "owui",
        "media",
        "lab",
    ]
    assert keys(None) == expected
    assert keys(["1"]) == ["host"]
    assert keys(["containers"]) == ["containers"]
    assert keys(["c"]) == ["containers"]
    assert keys(["media"]) == ["media"]
    assert keys(["m"]) == ["media"]
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


def test_expected_catalog_names_exposed_variants_under_their_synthetic_id() -> None:
    portal = {
        "workspaces": {
            "a": {
                "name": "A",
                "variants": {"v": {"name": "V", "expose_to_owui": True}, "hidden": {"name": "H"}},
            },
            "task-router": {"name": "Task model", "module": "eval"},
        }
    }
    assert pins.expected_catalog(portal) == {"a": "A", "a::v": "V", "task-router": "Task model"}


def test_owui_receipt_hop_needs_the_sandbox_value() -> None:
    # native OWUI tool flow renders the call itself; the trace hop proves tool_calls
    bare = workspaces.StreamedTurn(200, [], workspaces.TurnStats(text="488895"))
    assert owui.receipt_hop(bare).status is Status.PASS
    wrong = workspaces.StreamedTurn(200, [], workspaces.TurnStats(text="488925"))
    assert owui.receipt_hop(wrong).status is Status.FAIL


def test_owui_turn_request_uses_native_chat_tool_fields() -> None:
    preset = {
        "id": "auto-coding",
        "meta": {"toolIds": ["server:mcp:portal_code"]},
        "params": {"function_calling": "native"},
    }
    body = owui.completion_body(preset, "prompt", "chat", "message", "session")
    assert body["model"] == "auto-coding"
    assert body["chat_id"] == "chat" and body["id"] == "message"
    assert body["session_id"] == "session" and body["stream"] is True
    assert body["tool_ids"] == ["server:mcp:portal_code"]
    assert body["features"] == {
        "web_search": False,
        "code_interpreter": False,
        "image_generation": False,
        "memory": False,
    }
    assert body["params"]["function_calling"] == "native"
    assert owui.WORKSPACE == "auto-coding"


class TestVideoHops:
    """The video hop's verdicts — pure functions, no network."""

    def test_video_enabled_follows_the_config_switch(self) -> None:
        assert media.video_enabled({"modules": {"video": {"enabled": True}}}) is True
        assert media.video_enabled({"modules": {"video": {"enabled": False}}}) is False
        assert media.video_enabled({"modules": {}}) is False
        assert media.video_enabled({}) is False

    def test_turn_hop_passes_when_the_reply_carries_the_artifact_url(self) -> None:
        hop = media.turn_hop(
            "Done — video job finished: http://owui:8080/api/v1/files/abc/content/ltx_x.mp4", ""
        )
        assert hop.status is Status.PASS
        assert "url=" in hop.observed

    def test_turn_hop_fails_an_error_and_a_url_less_reply(self) -> None:
        assert media.turn_hop("", "TimeoutError: chat timed out").status is Status.FAIL
        assert media.turn_hop("I could not generate the video.", "").status is Status.FAIL

    def test_readback_hop_passes_real_mp4_bytes(self) -> None:
        class Resp:
            status_code = 200
            content = b"\x00\x00\x00\x20ftypisom" + b"payload" * 10

        def fake_get(url: str, **_kw: object) -> Resp:
            return Resp()

        original = media.httpx.get
        media.httpx.get = fake_get  # type: ignore[assignment]
        try:
            hop = media.readback_hop("http://owui/f.mp4", "key")
        finally:
            media.httpx.get = original  # type: ignore[assignment]
        assert hop.status is Status.PASS
        assert "mp4=True" in hop.observed

    def test_readback_hop_fails_an_error_page(self) -> None:
        class Resp:
            status_code = 404
            content = b"<html>not found</html>"

        def fake_get(url: str, **_kw: object) -> Resp:
            return Resp()

        original = media.httpx.get
        media.httpx.get = fake_get  # type: ignore[assignment]
        try:
            hop = media.readback_hop("http://owui/f.mp4", "key")
        finally:
            media.httpx.get = original  # type: ignore[assignment]
        assert hop.status is Status.FAIL

    def test_clip_hop_reports_the_written_artifact(self, tmp_path: Path) -> None:
        clip = tmp_path / "ltx_abc.mp4"
        clip.write_bytes(b"x" * 2_000_000)
        hop = media.clip_hop(clip, since=0.0)
        assert hop.status is Status.PASS
        assert "ltx_abc.mp4" in hop.observed and "2.0MB" in hop.observed

    def test_clip_hop_fails_when_the_renderer_wrote_nothing(self) -> None:
        hop = media.clip_hop(None, since=0.0)
        assert hop.status is Status.FAIL
        assert "no new" in hop.observed


def test_media_module_hop_warns_while_disabled() -> None:
    disabled = {"modules": {"image": {"enabled": False}}}
    hop = media.module_hop(disabled)
    assert hop is not None
    assert hop.status is Status.WARN
    assert "modules.image.enabled is false" in hop.observed
    assert media.module_hop({"modules": {"image": {"enabled": True}}}) is None
    assert media.module_hop({}) is None  # missing key falls back to enabled


def test_media_artifact_url_extracts_the_published_files_url() -> None:
    url = (
        "http://owui:8080/api/v1/files/2f3a1b9c-0000-0000-0000-000000000000/content/mflux_ab12.png"
    )
    assert media.artifact_url(f"Here it is: {url}") == url
    assert media.artifact_url("no link here") == ""
    bare = media.artifact_url("done http://owui/a.png.")
    assert bare == "http://owui/a.png"


def test_media_artifact_hop_verdicts(monkeypatch: pytest.MonkeyPatch) -> None:
    turn = workspaces.StreamedTurn(
        200,
        [],
        workspaces.TurnStats(
            text="see http://owui/api/v1/files/abcd1234-0000-0000-0000-000000000000/content/mflux_x.png"
        ),
    )
    monkeypatch.setattr(media, "read_back", lambda _u, _k: (True, "http 200, 9 bytes"))
    assert media.artifact_hop(turn, "key").status is Status.PASS
    monkeypatch.setattr(media, "read_back", lambda _u, _k: (False, "http 404, 0 bytes"))
    assert media.artifact_hop(turn, "key").status is Status.FAIL
    empty = workspaces.StreamedTurn(200, [], workspaces.TurnStats(text="no url"))
    assert media.artifact_hop(empty, "key").status is Status.FAIL
    failed = workspaces.StreamedTurn(0, error="boom")
    assert media.artifact_hop(failed, "key").status is Status.FAIL


def test_media_run_warns_disabled_and_needs_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media, "env_value", lambda name, default="": "")
    hops = media.run(_ctx(), {"modules": {"image": {"enabled": False}}})
    assert [h.status for h in hops] == [Status.WARN, Status.WARN, Status.WARN]
    assert "modules.image.enabled is false" in hops[0].observed
    assert "music module disabled" in hops[2].observed
    monkeypatch.setattr(
        media, "env_value", lambda name, default="": "key" if name == "OWUI_API_KEY" else ""
    )
    hops = media.run(_ctx(), {"modules": {"image": {"enabled": True}}})
    assert hops[0].name == "image preset" and hops[0].status is Status.WARN


def test_media_run_appends_video_and_music_warns_while_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(media, "env_value", lambda name, default="": "")
    portal = {"modules": {"image": {"enabled": True}, "video": {"enabled": False}}}
    hops = media.run(_ctx(), portal)
    assert hops[-2].name == "video artifact turn"
    assert hops[-2].status is Status.WARN
    assert "video module disabled" in hops[-2].observed
    assert "modules.video.enabled" in hops[-2].detail
    assert hops[-1].name == "music artifact turn"
    assert hops[-1].status is Status.WARN
    assert "music module disabled" in hops[-1].observed
    assert "modules.music.enabled" in hops[-1].detail


class TestMusicHops:
    """The music hop's verdicts — pure functions, no network."""

    def test_music_enabled_follows_the_config_switch(self) -> None:
        assert media.music_enabled({"modules": {"music": {"enabled": True}}}) is True
        assert media.music_enabled({"modules": {"music": {"enabled": False}}}) is False
        assert media.music_enabled({"modules": {}}) is False
        assert media.music_enabled({}) is False

    def test_music_artifact_hop_passes_a_reply_that_reads_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        turn = workspaces.StreamedTurn(
            200,
            [],
            workspaces.TurnStats(
                text="done http://owui:8080/api/v1/files/2f3a1b9c-0000-0000-0000-000000000000"
                "/content/music_ab12.wav"
            ),
        )
        monkeypatch.setattr(media, "read_back", lambda _u, _k: (True, "http 200, 882340 bytes"))
        hop = media.music_artifact_hop(turn, "key")
        assert hop.status is Status.PASS
        assert "200 + bytes" in hop.expected

    def test_music_artifact_hop_fails_an_error_and_a_url_less_reply(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(media, "read_back", lambda _u, _k: (False, "http 404, 0 bytes"))
        failed = workspaces.StreamedTurn(0, error="ConnectError: refused")
        assert media.music_artifact_hop(failed, "key").status is Status.FAIL
        empty = workspaces.StreamedTurn(200, [], workspaces.TurnStats(text="no link"))
        assert media.music_artifact_hop(empty, "key").status is Status.FAIL
        url = "done http://owui/api/v1/files/abcd1234-0000-0000-0000-000000000000/content/x.wav"
        turn = workspaces.StreamedTurn(200, [], workspaces.TurnStats(text=url))
        assert media.music_artifact_hop(turn, "key").status is Status.FAIL

    def test_music_hops_need_the_api_key_and_preset_while_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(media, "env_value", lambda name, default="": "")
        portal = {"modules": {"music": {"enabled": True}}}
        assert media.music_hops(_ctx(), portal)[0].observed == "not run: no OWUI_API_KEY"
        monkeypatch.setattr(
            media, "env_value", lambda name, default="": "key" if name == "OWUI_API_KEY" else ""
        )
        hop = media.music_hops(_ctx(), portal)[0]
        assert hop.status is Status.WARN and "preset missing" in hop.observed


def _ctx() -> Any:
    from portal.platform.inference.cli.trace.context import TraceContext

    return TraceContext(
        repo_root=Path(__file__).resolve().parents[1],
        pipeline_url="http://127.0.0.1:9099",
        api_key="k",
        omlx_url="http://127.0.0.1:8085",
        ollama_url="http://127.0.0.1:11434",
        owui_url="http://127.0.0.1:8080",
        budget_s=60.0,
        timeout_s=30.0,
    )
