"""`portal trace` section parsers and verdicts — pure functions, no network or docker."""

from __future__ import annotations

import plistlib
from pathlib import Path

import pytest
import typer

from portal.modules.security.cli import trace_lab
from portal.platform.inference.cli.trace import containers, engines, host, lab, pins, workspaces
from portal.platform.inference.cli.trace.command import selected
from portal.platform.inference.cli.trace.model import Hop, Status

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
    assert host.expects_running(cfg) is True
    assert host.process_type({}) == "Standard"
    assert host.env_keys({}) == []


def test_launchctl_pid_reads_the_running_pid_only() -> None:
    assert host.launchctl_pid('{\n\t"PID" = 94943;\n\t"Label" = "x";\n};') == 94943
    assert host.launchctl_pid('{\n\t"Label" = "x";\n};') is None


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


def test_installed_hop_reports_a_missing_plist(tmp_path: Path) -> None:
    hops = host.installed_hop("com.portal5.omlx", {}, tmp_path)
    assert hops[0].status is Status.FAIL
    assert hops[0].observed == "installed=missing"


def test_installed_hop_compares_process_type_and_env_keys(tmp_path: Path) -> None:
    cfg = {"ProcessType": "Standard", "EnvironmentVariables": {"PATH": "/bin", "HOME": "/h"}}
    (tmp_path / "com.portal5.omlx.plist").write_bytes(
        _plist(ProcessType="Background", EnvironmentVariables={"PATH": "/bin"})
    )
    hops = host.installed_hop("com.portal5.omlx", cfg, tmp_path)
    assert hops[0].status is Status.FAIL  # ProcessType differs
    assert hops[1].status is Status.FAIL  # HOME missing
    assert hops[1].detail == "missing=HOME"


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


def test_revision_hop_fails_without_the_label_and_warns_when_dirty() -> None:
    assert containers.revision_hop("repo", "", "abc123456789", []).status is Status.FAIL
    assert containers.revision_hop("repo", "abc123456789", "abc123456789", []).status is Status.PASS
    dirty = containers.revision_hop("repo", "abc123456789", "abc123456789", ["M portal/x.py"])
    assert dirty.status is Status.WARN
    assert containers.revision_hop("repo", "999123456789", "abc123456789", []).status is Status.FAIL


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
