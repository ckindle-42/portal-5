"""Fail-closed contracts for the engine-eval instrument. No network, no engines."""

from __future__ import annotations

import json

from tests.benchmarks import bench_engine_h2h as h
from tests.benchmarks.engine_eval_instrument import (
    defect_cases,
    golden_evidence,
    judge_cell,
    parse_ollama_load,
    parse_omlx_acceptance,
    parse_omlx_settings,
    parse_ps_tree,
    parse_vm_stat,
    self_test,
    served_id_is_filesystem_path,
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
