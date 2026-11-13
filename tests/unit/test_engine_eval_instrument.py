"""Fail-closed contracts for the engine-eval instrument. No network, no engines."""

from __future__ import annotations

import json
from pathlib import Path

from tests.benchmarks import bench_engine_h2h as h
from tests.benchmarks.engine_eval_instrument import (
    assemble_cell,
    defect_cases,
    golden_evidence,
    grade_preflight,
    judge_cell,
    omlx_server_log,
    parse_ollama_load,
    parse_ollama_plist,
    parse_ollama_show,
    parse_omlx_acceptance,
    parse_omlx_settings,
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
            "metal_wired_gb": 14.0,
            "vm_wired_delta_gb": 16.0,
            "vm_free_delta_gb": 16.2,
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


def test_daily_omlx_sources_come_from_server_log_and_status() -> None:
    spec = seat_plan("daily-moe", "omlx")
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
            "model_settings": {
                model: {"temperature": 1.0, "mtp_enabled": True, "turboquant_kv_enabled": False}
            },
            "global_settings": {"max_concurrent_requests": 8},
            "model_row": {"loaded": True, "context_tokens": 262144, "engine_type": "mlx"},
            "total_requests_before": 4,
            "total_requests_after": 6,
        }
    )
    evidence = assemble_cell(spec, obs)
    judged = judge_cell(evidence)
    assert judged["valid"] is True, judged
    assert evidence["readback"]["spec_method"] == "mtp"
    assert evidence["readback"]["acceptance"] == 80.0
    assert evidence["sources"]["spec_method"].startswith("server.log")
    assert evidence["excluded_claims"]["kv_dtype"]["decision"] == "exclude"
    assert evidence["excluded_claims"]["drafter_loaded"]["decision"] == "exclude"
    assert evidence["check_sources"]["route"].find("total_requests") > 0
    na = log.replace("accept=8/10 (80.0%)", "accept=0/0 (n/a)").replace(
        "accept=16/18 (88.9%)", "accept=0/0 (n/a)"
    )
    obs["server_log"] = na
    failed = judge_cell(assemble_cell(spec, obs))
    assert failed["valid"] is False
    assert any("n/a" in item for item in failed["failures"])


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
    assert resolve_tokenizer("ollama", tmp_path, None) is None
    assert resolve_tokenizer("ollama", None, tokenizer) == tokenizer


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
