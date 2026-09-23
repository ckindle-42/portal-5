"""Pure-logic contracts for the engine head-to-head harness
(tests/benchmarks/bench_engine_h2h.py). No network, no engines."""

import pytest

from tests.benchmarks import bench_engine_h2h as h


@pytest.fixture(scope="module")
def cfg():
    return h.load_config()


def test_every_managed_engine_renders_a_plain_command_for_every_model(cfg):
    for eng, e in cfg["engines"].items():
        if e["kind"] != "managed":
            continue
        for model in cfg["models"]:
            argv, _ = h.launch_command(cfg, eng, model, "plain")
            assert not any("{" in a and "}" in a and '"' not in a for a in argv), argv


def test_spec_json_args_survive_rendering(cfg):
    argv, _ = h.launch_command(cfg, "rapid-mlx", "laguna", "spec")
    blob = argv[argv.index("--speculative-config") + 1]
    assert blob.startswith('{"method":"dflash"')
    assert cfg["drafter_root"] in blob


def test_null_spec_cell_refuses(cfg):
    with pytest.raises(SystemExit):
        h.launch_command(cfg, "vllm-mlx", "laguna", "spec")


def test_mlx_serve_plain_disables_all_speculation(cfg):
    argv, _ = h.launch_command(cfg, "mlx-serve", "mimo", "plain")
    assert {"--no-pld", "--no-drafter", "--no-mtp"} <= set(argv)


def test_mlx_lm_runs_from_model_root_with_relative_model(cfg):
    argv, cwd = h.launch_command(cfg, "mlx_lm.server", "vulnllm", "plain")
    assert cwd == cfg["mlx_root"]
    assert argv[argv.index("--model") + 1] == cfg["models"]["vulnllm"]["mlx"]


def test_served_id_is_shared_across_mlx_engines(cfg):
    ids = {h.served_id(cfg, e, "laguna", "plain") for e in cfg["engines"] if e != "ollama"}
    assert ids == {"Laguna-XS.2-4bit"}
    assert h.served_id(cfg, "ollama", "laguna", "plain") == cfg["models"]["laguna"]["ollama"]


def test_think_off_dialects():
    assert h.think_off_fields("ollama") == {"reasoning_effort": "none"}
    assert h.think_off_fields("rapid-mlx") == {"chat_template_kwargs": {"enable_thinking": False}}


def test_parse_swapusage_and_footprint():
    s = h.parse_swapusage("vm.swapusage: total = 20480.00M  used = 19539.38M  free = 940.62M")
    assert s == {"total_mb": 20480.0, "used_mb": 19539.38}
    assert h.parse_footprint("Python [1667]: 64-bit    Footprint: 18 GB (16384 bytes)") == 18.0
    assert h.parse_footprint("x Footprint: 512 MB y") == 0.5
    assert h.parse_footprint("nothing") is None


def test_guard_verdict_swap_growth_and_cpu_split():
    ok = h.guard_verdict([{"used_mb": 100.0}, {"used_mb": 900.0}], 2048)
    assert ok["valid"] and ok["swap_growth_mb"] == 800.0
    grown = h.guard_verdict([{"used_mb": 100.0}, {"used_mb": 3000.0}], 2048)
    assert not grown["valid"]
    split = h.guard_verdict([{"used_mb": 1.0, "gpu_fraction": 0.8}], 2048)
    assert not split["valid"] and "CPU split" in split["reasons"][0]


def test_score_security_vulnerable_and_clean():
    assert h.score_security("CWE-89", "This is CWE-89 SQL injection")["cwe_ok"]
    assert not h.score_security("CWE-89", "This is CWE 79")["cwe_ok"]
    clean = h.score_security(None, "NO VULNERABILITY FOUND — scrypt with a random salt.")
    assert clean["cwe_ok"] and not clean["false_positive"]
    fp = h.score_security(None, "CWE-798 hard-coded parameters")
    assert fp["false_positive"] and not fp["cwe_ok"]


def test_security_summary_counts():
    rows = [
        {"expected_cwe": "CWE-89", "cwe_ok": True, "false_positive": False},
        {"expected_cwe": "CWE-22", "cwe_ok": False, "false_positive": False},
        {"expected_cwe": None, "cwe_ok": False, "false_positive": True},
    ]
    assert h.security_summary(rows) == {
        "cwe_accuracy": 0.5,
        "clean_false_positives": 1,
        "clean_runs": 1,
    }


def test_timing_row_rates():
    r = h.timing_row(0.0, 2.0, 12.0, {"prompt_tokens": 1000, "completion_tokens": 101}, 0, "")
    assert r["ttft_s"] == 2.0 and r["prefill_tps"] == 500.0 and r["decode_tps"] == 10.0


def test_drafter_format_classification():
    assert "z-lab" in h.drafter_format({"dflash_config": {"target_layer_ids": [1]}})
    assert "speculators" in h.drafter_format({"speculators_model_type": "dflash"})
    assert "plain" in h.drafter_format({"model_type": "qwen2"})


def test_security_fixture_has_one_clean_control():
    import json

    fx = json.loads((h.FIXTURES / "security_prompts.json").read_text())
    assert sum(p["expected_cwe"] is None for p in fx["prompts"]) == 1
    assert len(fx["prompts"]) == 6


def test_latest_prefers_valid_rows():
    rows = [
        {"kind": "speed", "model": "m", "engine": "e", "mode": "plain", "valid": True, "n": 1},
        {"kind": "speed", "model": "m", "engine": "e", "mode": "plain", "valid": False, "n": 2},
    ]
    assert h.latest(rows, "speed")[("m", "e", "plain")]["n"] == 1


def test_start_gate_is_absolute_not_fractional():
    assert not h.start_gate_verdict({"used_mb": 10842.0, "total_mb": 12288.0}, 4096)[0]
    assert h.start_gate_verdict({"used_mb": 950.0, "total_mb": 1024.0}, 4096)[0]
    assert h.start_gate_verdict({}, 4096)[0]
