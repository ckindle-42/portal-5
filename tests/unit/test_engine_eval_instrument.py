"""Fail-closed contracts for the engine-eval instrument. No network, no engines."""

from __future__ import annotations

import json
from pathlib import Path

from tests.benchmarks import bench_engine_h2h as h
from tests.benchmarks import engine_eval_instrument as instrument
from tests.benchmarks.engine_eval_instrument import (
    HUNT_SEAT,
    _check_memory,
    _check_sources,
    _served_ids,
    assemble_cell,
    completion_text,
    defect_cases,
    golden_evidence,
    grade_preflight,
    judge_cell,
    omlx_server_log,
    parse_footprint,
    parse_ollama_load,
    parse_ollama_plist,
    parse_ollama_show,
    parse_omlx_acceptance,
    parse_omlx_settings,
    parse_pipeline_routes,
    parse_ps_tree,
    parse_vm_stat,
    ps_refreshed,
    reject_engine_log,
    resolve_tokenizer,
    seat_plan,
    self_test,
    served_id_is_filesystem_path,
    stage0,
    tree_rss_gb,
    vm_deltas_gb,
)


def test_self_test_exits_clean() -> None:
    assert self_test() == 0


def test_golden_cell_is_valid() -> None:
    judged = judge_cell(golden_evidence())
    assert judged == {"valid": True, "failures": []}


def test_each_defect_fixture_fails_with_its_needle() -> None:
    for name, evidence, needle in defect_cases():
        judged = judge_cell(evidence)
        assert judged["valid"] is False, name
        assert any(needle in item for item in judged["failures"]), (name, judged["failures"])


def test_missing_evidence_is_invalid() -> None:
    judged = judge_cell(None)
    assert judged["valid"] is False
    assert judged["failures"] == ["instrument: no independent evidence"]


def test_labeled_noise_inside_the_spread_passes() -> None:
    evidence = json.loads(json.dumps(golden_evidence()))
    evidence["noise"]["later_delta_tps"] = 0.4
    evidence["noise"]["labeled_no_difference"] = True
    assert judge_cell(evidence)["valid"] is True


def test_omlx_settings_and_acceptance_parse_the_log_not_the_claim() -> None:
    log = (
        "Applied initial settings for NVIDIA-Nemotron: {'temperature': 1.0, 'mtp_enabled': True}\n"
        "Chat completion: model=NVIDIA-Nemotron, 12 tokens\n"
        "accept=16/18 (88.9%)\n"
    )
    assert parse_omlx_settings(log)["NVIDIA-Nemotron"]["mtp_enabled"] is True
    assert parse_omlx_acceptance(log) == 88.9


def test_ollama_binds_context_forward_and_ignores_template_thinking() -> None:
    log = (
        "llama_context: n_ctx_train = 99999\n"
        "llama_context: n_ctx = 32768\n"
        "n_seq_max = 1\n"
        "chat template, thinking = 0\n"
        "model=hf.co/example/Model:Q4_K_M-ctx32k selected\n"
    )
    bound = parse_ollama_load(log)["hf.co/example/Model:Q4_K_M-ctx32k"]
    assert bound == {"context_tokens": 32768, "parallel_slots": 1}
    assert "thinking" not in bound


def test_memory_parsers_walk_the_tree_and_vm_stat() -> None:
    rows = parse_ps_tree("1 0 100\n10 1 2048\n11 10 4096\n")
    assert tree_rss_gb(rows, 10) == (2048 + 4096) / (1024**2)
    before = parse_vm_stat("page size of 16384 bytes\nPages free: 2000.\nPages wired down: 1000.\n")
    after = parse_vm_stat("page size of 16384 bytes\nPages free: 1000.\nPages wired down: 2000.\n")
    deltas = vm_deltas_gb(before, after)
    assert deltas is not None
    assert deltas["vm_wired_delta_gb"] > 0
    assert deltas["vm_free_delta_gb"] > 0


def test_memory_fixtures_compare_engine_weight_to_wired_without_double_counting() -> None:
    ollama = {
        "tree_walked": True,
        "tree_rss_gb": 23.38,
        "engine_weight_gb": 22.91,
        "engine_weight_source": "GET /api/ps size_vram",
        "vm_wired_delta_gb": 23.08,
        "vm_free_delta_gb": 4.35,
    }
    failures: list[str] = []
    _check_memory(
        {
            "engine": "ollama",
            "expected_model": "daily-moe-model",
            "memory": ollama,
            "residency": {
                "before": {"ollama": {}, "omlx": {}},
                "after": {"ollama": {"daily-moe-model": 22.91 * 1024**3}, "omlx": {}},
            },
        },
        failures,
    )
    assert failures == []

    # The observed -8.57 GB delta is covered below; this is the uncontaminated match case.
    omlx = {
        "tree_walked": True,
        "tree_rss_gb": 9.70,
        "engine_weight_gb": 15.35,
        "engine_weight_source": "GET /v1/models/status actual_size",
        "vm_wired_delta_gb": 15.35,
    }
    failures = []
    _check_memory(
        {
            "engine": "omlx",
            "expected_model": "hunt-model",
            "memory": omlx,
            "residency": {
                "before": {"ollama": {}, "omlx": {}},
                "after": {"ollama": {}, "omlx": {"hunt-model": 15.35 * 1024**3}},
            },
        },
        failures,
    )
    assert failures == []


def test_memory_fails_with_real_omlx_deltas_and_reports_resident_contamination() -> None:
    failures: list[str] = []
    _check_memory(
        {
            "engine": "omlx",
            "expected_model": "hunt-model",
            "memory": {
                "tree_walked": True,
                "tree_rss_gb": 9.70,
                "engine_weight_gb": 15.35,
                "vm_wired_delta_gb": -8.57,
                "vm_free_delta_gb": 11.35,
            },
            "residency": {
                "before": {"ollama": {"task-router": 1}, "omlx": {}},
                "after": {"ollama": {}, "omlx": {"hunt-model": 15.35}},
            },
        },
        failures,
    )
    assert any("contaminated: ollama resident set changed" in item for item in failures)
    assert any("engine weight 15.35GB vs wired delta -8.57GB" in item for item in failures)


def test_residency_checks_candidate_engines_as_well_as_production_engines() -> None:
    failures: list[str] = []
    _check_memory(
        {
            "engine": "rapid-mlx",
            "expected_model": "candidate-model",
            "memory": {
                "tree_walked": True,
                "tree_rss_gb": 1.0,
                "engine_weight_gb": 1.0,
                "vm_wired_delta_gb": 1.0,
            },
            "residency": {
                "before": {"rapid-mlx": {}, "ollama": {}},
                "after": {"rapid-mlx": {"candidate-model": 1}, "ollama": {"other": 1}},
            },
        },
        failures,
    )

    assert any("contaminated: ollama resident set changed" in item for item in failures)


def test_omlx_served_ids_send_the_api_key_and_fail_closed(monkeypatch) -> None:
    monkeypatch.setenv("OMLX_API_KEY", "test-key")
    captured: dict[str, object] = {}

    def fake_http_json(url, payload, headers, timeout):
        captured.update({"url": url, "headers": headers})
        return {"json": {"data": [{"id": "gemma-4-26b-a4b-it-QAT-4bit"}]}}

    monkeypatch.setattr(instrument, "_http_json", fake_http_json)
    assert _served_ids("http://127.0.0.1:8085") == ["gemma-4-26b-a4b-it-QAT-4bit"]
    assert captured["headers"]["Authorization"] == "Bearer test-key"

    def unauthorized(url, payload, headers, timeout):
        raise instrument.urllib.error.HTTPError(url, 401, "unauthorized", {}, None)

    monkeypatch.setattr(instrument, "_http_json", unauthorized)
    served = _served_ids("http://127.0.0.1:8085")
    assert served is None
    assert instrument.grade_preflight("OK", {"ok": True}, served)["verdict"] == "REVIEW"


def test_residency_snapshots_capture_both_engines_and_weight_fields(monkeypatch) -> None:
    def fake_get_json(url, headers):
        if url.endswith("/api/ps"):
            return {
                "models": [
                    {"name": "router", "size_vram": 123},
                    {"name": "nemotron", "size_vram": 456},
                ]
            }
        return {
            "models": [
                {"id": "gemma", "loaded": True, "actual_size": 789},
                {"id": "cold", "loaded": False, "actual_size": 999},
            ]
        }

    monkeypatch.setattr(instrument, "_get_json", fake_get_json)
    snapshots = instrument._resident_snapshots({"engine": "omlx", "base": "http://127.0.0.1:8085"})
    assert snapshots == {"ollama": {"router": 123, "nemotron": 456}, "omlx": {"gemma": 789}}


def test_memory_check_sources_explain_engine_coverage_and_free_delta() -> None:
    ollama = _check_sources({"engine": "ollama"})["memory"].lower()
    omlx = _check_sources({"engine": "omlx"})["memory"].lower()
    assert "size_vram" in ollama and "includes" in ollama and "do not add" in ollama
    assert "actual_size" in omlx and "excludes" in omlx and "do not add" in omlx
    assert "free delta informational" in ollama and "page cache" in ollama
    assert "free delta informational" in omlx and "page cache" in omlx


def test_served_id_rejects_a_path_and_keeps_a_hf_tag() -> None:
    assert served_id_is_filesystem_path("/Volumes/data01/omlx-models/Qwen3.8-27B-4bit")
    assert not served_id_is_filesystem_path("hf.co/example/Model:Q4_K_M-ctx32k")


def test_guard_ceiling_is_optional_and_absolute() -> None:
    ok = h.guard_verdict([{"used_mb": 100.0}, {"used_mb": 900.0}], 2048)
    assert ok["valid"] and ok["swap_growth_mb"] == 800.0
    ceiling = h.guard_verdict([{"used_mb": 100.0}, {"used_mb": 5000.0}], 10000, max_used_mb=4096)
    assert ceiling["valid"] is False
    assert any("ceiling" in reason for reason in ceiling["reasons"])
    under = h.guard_verdict([{"used_mb": 100.0}, {"used_mb": 900.0}], 2048, max_used_mb=4096)
    assert under["valid"] is True


def test_omlx_plain_settings_disable_mtp_and_dflash() -> None:
    settings = h.omlx_settings_for(h.load_config(), "nemotron_35_lightning", "plain")
    assert settings == {"mtp_enabled": False, "dflash_enabled": False}


def _measured(spec: dict) -> dict:
    model = spec["model"]
    header = f"{spec['workspace']};{spec['backend']};{model}"
    return {
        "route_headers": [header, header],
        "pipeline_routes": [
            (spec["workspace"], spec["backend"], model),
            (spec["workspace"], spec["backend"], model),
        ],
        "memory": {
            "tree_walked": True,
            "tree_rss_gb": 2.0,
            "engine_weight_gb": 14.0,
            "engine_weight_source": "fixture",
            "vm_wired_delta_gb": 16.0,
            "vm_free_delta_gb": 16.2,
        },
        "residency": {
            "before": {"ollama": {}, "omlx": {}},
            "after": {
                "ollama": {model: 14 * 1024**3} if spec["engine"] == "ollama" else {},
                "omlx": {model: 14 * 1024**3} if spec["engine"] == "omlx" else {},
            },
        },
        "tokens": {"engine_completion": 32, "tokenizer_completion": 33},
        "noise": {"run_a_tps": 50.0, "run_b_tps": 51.5},
        "swap_samples_mb": [100.0, 300.0],
        "preflight": {"verdict": "OK"},
        "served_model_id": model,
        "launch_argv": ["serve"],
    }


def test_launchd_logs_are_not_per_request_evidence() -> None:
    assert reject_engine_log("/opt/homebrew/var/log/omlx.log")
    assert reject_engine_log("/opt/homebrew/var/log/ollama.log")
    assert reject_engine_log(omlx_server_log()) is None


def test_daily_ollama_sources_can_pass_without_a_log() -> None:
    spec = seat_plan("daily-moe", "ollama")
    model = spec["model"]
    row = {"context_length": 32768, "size": 1, "size_vram": 2, "expires_at": "t0"}
    mid = {**row, "expires_at": "t1"}
    end = {**row, "expires_at": "t2"}
    obs = _measured(spec)
    obs.update(
        {
            "show": parse_ollama_show({"parameters": "num_ctx 32768\n", "template": "hi"}),
            "plist": parse_ollama_plist(
                {
                    "EnvironmentVariables": {
                        "OLLAMA_NUM_PARALLEL": "1",
                        "OLLAMA_KV_CACHE_TYPE": "q8_0",
                        "OLLAMA_FLASH_ATTENTION": "1",
                    }
                }
            ),
            "ps": {model: end},
            "ps_refresh_pairs": [({model: row}, {model: mid}), ({model: mid}, {model: end})],
        }
    )
    evidence = assemble_cell(spec, obs)
    judged = judge_cell(evidence)
    assert judged["valid"] is True, judged
    assert evidence["excluded_claims"]["thinking"]["decision"] == "exclude"
    assert evidence["excluded_claims"]["temperature"]["decision"] == "exclude"
    assert evidence["excluded_claims"]["spec_method"]["decision"] == "exclude"
    assert "pipeline_context_limit" in evidence["excluded_claims"]
    assert evidence["sources"]["kv_dtype"].startswith("com.portal5.ollama.plist")
    evidence["excluded_claims"].pop("thinking")
    missing = judge_cell(evidence)
    assert missing["valid"] is False
    assert any("thinking unverifiable" in item for item in missing["failures"])


def test_ollama_spec_claim_invalidates_without_a_source() -> None:
    spec = seat_plan("daily-moe", "ollama")
    spec["claims"] = {**spec["claims"], "spec_method": "mtp", "drafter_loaded": True}
    spec["mode"] = "spec"
    model = spec["model"]
    row = {"context_length": 32768, "size": 1, "size_vram": 2, "expires_at": "t1"}
    obs = _measured(spec)
    obs.update(
        {
            "show": {"num_ctx": 32768, "template": ""},
            "plist": {"parallel_slots": 1, "kv_dtype": "q8_0", "flash_attention": True},
            "ps": {model: row},
            "ps_refresh_pairs": [
                ({}, {model: row}),
                ({model: row}, {model: {**row, "expires_at": "t2"}}),
            ],
        }
    )
    judged = judge_cell(assemble_cell(spec, obs))
    assert judged["valid"] is False
    assert any("invalidates" in item for item in judged["failures"])


def test_hunt_omlx_is_the_production_baseline() -> None:
    spec = seat_plan(HUNT_SEAT, "omlx")
    assert spec["workspace"] == "hunt-reasoning"
    assert spec["backend"] == "omlx-general"
    assert spec["model"] == "gemma-4-26b-a4b-it-QAT-4bit"
    assert spec["mode"] == "plain"
    model = spec["model"]
    log = (
        f"Applied initial settings for {model}: {{'temperature': 0.0, 'mtp_enabled': False}}\n"
        f"Chat completion: model={model}, 12 tokens\n"
        f"Chat completion: model={model}, 20 tokens\n"
    )
    obs = _measured(spec)
    obs.update(
        {
            "server_log": log,
            "model_settings": {model: {"temperature": 0.0, "vlm_mtp_enabled": False}},
            "global_settings": {"max_concurrent_requests": 8},
            "model_row": {
                "loaded": True,
                "context_tokens": 262144,
                "engine_type": "mlx",
                "actual_size": 16 * 1024**3,
            },
            "total_requests_before": 4,
            "total_requests_after": 6,
        }
    )
    evidence = assemble_cell(spec, obs)
    judged = judge_cell(evidence)
    assert judged["valid"] is True, judged
    assert evidence["readback"]["mtp_enabled"] is False
    assert evidence["readback"]["dflash_enabled"] is False
    assert evidence["readback"]["spec_method"] == "off"
    assert evidence["readback"]["temperature"] == 0.0
    assert evidence["check_sources"]["route"].find("succeeded") > 0
    assert evidence["check_sources"]["memory"].find("actual_size") > 0
    assert stage0(["--engine", "omlx", "--seat", "daily-moe"]) == 2
    try:
        seat_plan("daily-moe", "omlx")
    except KeyError:
        pass
    else:
        raise AssertionError("daily-moe is not an oMLX production seat")


def test_omlx_mtp_acceptance_still_gates_a_spec_cell() -> None:
    spec = seat_plan(HUNT_SEAT, "omlx")
    spec["mode"] = "spec"
    spec["claims"] = {**spec["claims"], "spec_method": "mtp", "temperature": 1.0}
    model = spec["model"]
    log = (
        f"Applied initial settings for {model}: "
        "{'temperature': 1.0, 'top_p': 0.95, 'mtp_enabled': True}\n"
        "MTP path activated for uid=0\n"
        "accept=16/18 (88.9%)\n"
        f"Chat completion: model={model}, 12 tokens\n"
        "MTP path activated for uid=1\n"
        "accept=8/10 (80.0%)\n"
        f"Chat completion: model={model}, 20 tokens\n"
    )
    obs = _measured(spec)
    obs.update(
        {
            "server_log": log,
            "model_settings": {model: {"temperature": 1.0, "mtp_enabled": True}},
            "global_settings": {"max_concurrent_requests": 8},
            "model_row": {"loaded": True, "context_tokens": 262144, "engine_type": "mlx"},
            "total_requests_before": 4,
            "total_requests_after": 6,
        }
    )
    evidence = assemble_cell(spec, obs)
    judged = judge_cell(evidence)
    assert judged["valid"] is True, judged
    assert evidence["readback"]["acceptance"] == 80.0
    na = log.replace("accept=8/10 (80.0%)", "accept=0/0 (n/a)").replace(
        "accept=16/18 (88.9%)", "accept=0/0 (n/a)"
    )
    obs["server_log"] = na
    failed = judge_cell(assemble_cell(spec, obs))
    assert failed["valid"] is False
    assert any("n/a" in item for item in failed["failures"])
    obs["server_log"] = ""
    unloaded = judge_cell(assemble_cell(spec, obs))
    assert any("invalidates" in item for item in unloaded["failures"])


def test_show_parser_ignores_template_text_and_plist_reads_kv(tmp_path: Path) -> None:
    parsed = parse_ollama_show({"parameters": "num_ctx 32768\n", "template": "thinking = 0"})
    assert parsed["num_ctx"] == 32768
    assert "thinking" not in parsed
    assert ps_refreshed(
        {"m": {"expires_at": "a"}}, {"m": {"expires_at": "b"}, "other": {"expires_at": "c"}}
    ) == [
        "m",
        "other",
    ]
    tokenizer = tmp_path / "tokenizer.json"
    tokenizer.write_text("{}", encoding="utf-8")
    assert resolve_tokenizer("omlx", tmp_path, None) == tokenizer
    assert resolve_tokenizer("omlx", str(tmp_path), None) == tokenizer
    assert resolve_tokenizer("ollama", str(tokenizer), None) == tokenizer
    assert resolve_tokenizer("ollama", None, tokenizer) == tokenizer


_FOOTPRINT = """\
======================================================================
llama-server [4242]: 64-bit    Footprint: 620 MB (16384 bytes per page)
======================================================================

  Dirty      Clean  Reclaimable    Regions    Category
    ---        ---          ---        ---    ---
  800 KB        0 B          0 B          2    IOAccelerator
   64 KB        0 B          0 B          1    IOAccelerator
    0 B      23 GB          0 B          4    mapped file
    ---        ---          ---        ---    ---
  620 MB      23 GB          0 B         10    TOTAL

Auxiliary data:
    phys_footprint: 620 MB
    phys_footprint_peak: 640 MB
"""


def test_footprint_parser_reads_the_live_column_shape() -> None:
    parsed = parse_footprint(_FOOTPRINT)
    assert parsed["ioaccelerator_gb"] is not None
    assert parsed["ioaccelerator_gb"] < 0.01
    assert parsed["clean_mapped_gb"] == 23.0
    assert parsed["phys_footprint_gb"] is not None
    assert abs(parsed["phys_footprint_gb"] - (620 / 1024)) < 1e-9


def test_pipeline_routes_use_the_line_every_request_logs() -> None:
    log = (
        "Non-stream routing: workspace=auto-daily backend=ollama-general model=hinted\n"
        "Routing workspace=auto-daily → 2 candidate(s) stream=False\n"
        "Backend ollama-general succeeded for workspace=auto-daily model=real-model\n"
        "Routing workspace=hunt-reasoning → backend=omlx-general "
        "model=gemma-4-26b-a4b-it-QAT-4bit stream=False (1/1 candidates)\n"
    )
    assert parse_pipeline_routes(log) == [("auto-daily", "ollama-general", "real-model")]
    streamed = (
        "Stream routing: workspace=hunt-reasoning backend=omlx-general "
        "model=gemma-4-26b-a4b-it-QAT-4bit (1/1 candidates)\n"
    )
    assert parse_pipeline_routes(streamed) == [
        ("hunt-reasoning", "omlx-general", "gemma-4-26b-a4b-it-QAT-4bit")
    ]


def test_engine_weight_uses_the_engine_field_not_footprint() -> None:
    from tests.benchmarks.engine_eval_instrument import engine_weight_gb

    ollama = {"engine": "ollama", "model": "m"}
    gb, source = engine_weight_gb(ollama, {"ps": {"m": {"size_vram": 1024**3}}})
    assert gb == 1.0
    assert source == "GET /api/ps size_vram"
    omlx = {"engine": "omlx", "model": "g"}
    gb, source = engine_weight_gb(
        omlx,
        {
            "model_row": {"actual_size": 2 * 1024**3},
            "status_after": {"model_memory_used": 9 * 1024**3},
        },
    )
    assert gb == 2.0
    assert source == "GET /v1/models/status actual_size"


def test_completion_text_adds_reasoning_fields() -> None:
    text = completion_text(
        {
            "content": "Here are three planets",
            "reasoning": "The user asks",
            "reasoning_content": "The user asks",
        }
    )
    assert text == "Here are three planets\nThe user asks"


def test_completion_text_includes_tool_name_and_arguments() -> None:
    text = completion_text(
        {
            "content": "OK",
            "tool_calls": [{"function": {"name": "get_weather", "arguments": '{"city":"Boston"}'}}],
        }
    )

    assert text == 'OK\nget_weather\n{"city":"Boston"}'


def test_preflight_grade_and_unknown_seat() -> None:
    ok = grade_preflight("OK", {"ok": True}, "hf.co/example/Model:Q4_K_M")
    assert ok["verdict"] == "OK"
    leaked = grade_preflight("<think>secret", {"ok": True}, "hf.co/example/Model:Q4_K_M")
    assert leaked["verdict"] == "REVIEW"
    assert stage0(["--engine", "ollama", "--seat", "not-a-seat"]) == 2


def test_matrix_records_the_drafter_and_excludes_plain_splash() -> None:
    matrix = Path("docs/ENGINE_EVAL_MATRIX_20261113.md").read_text(encoding="utf-8")
    harness = Path("tests/benchmarks/engine_h2h.yaml").read_text(encoding="utf-8")
    assert "plain Splash cell is excluded" in matrix
    assert "was removed" not in matrix
    assert "daily-moe" in matrix
    assert "Qwen3.8-27B-DFlash2" in harness
    assert "drafter checkpoint was removed" not in harness
    assert "unrunnable" not in harness


def test_compared_claim_without_a_named_source_fails() -> None:
    evidence = golden_evidence()
    evidence["sources"].pop("kv_dtype")
    judged = judge_cell(evidence)
    assert judged["valid"] is False
    assert any("kv_dtype source unnamed" in item for item in judged["failures"])


def test_attach_instrument_rejects_a_row_with_no_evidence(tmp_path) -> None:
    row = {"valid": True}
    h.attach_instrument(row, None)
    assert row["valid"] is False
    assert "no independent evidence" in row["instrument"]["failures"][0]
    path = tmp_path / "cell.json"
    path.write_text(json.dumps(golden_evidence()), encoding="utf-8")
    good = {"valid": True}
    h.attach_instrument(good, str(path))
    assert good["valid"] is True
