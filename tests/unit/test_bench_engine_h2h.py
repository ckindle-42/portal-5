"""Pure-logic contracts for the engine head-to-head harness
(tests/benchmarks/bench_engine_h2h.py). No network, no engines."""

import pytest

from tests.benchmarks import bench_engine_h2h as h


@pytest.fixture(scope="module")
def cfg():
    return h.load_config()


def test_wait_ready_fails_fast_when_managed_child_exits(monkeypatch):
    class ExitedProcess:
        def poll(self):
            return 1

    def unavailable(*_args, **_kwargs):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(h, "http_json", unavailable)
    monkeypatch.setattr(h.time, "sleep", lambda _seconds: pytest.fail("waited for dead child"))
    with pytest.raises(SystemExit, match=r"process exited during startup \(exit 1\)"):
        h.wait_ready("http://127.0.0.1:11240", 900, ExitedProcess())


def test_every_managed_engine_renders_a_plain_command_for_every_model(cfg):
    for eng, e in cfg["engines"].items():
        if e["kind"] != "managed":
            continue
        for model in cfg["models"]:
            if not h.model_supports_engine(cfg, model, eng) or e.get("requires") == "gguf":
                continue
            argv, _ = h.launch_command(cfg, eng, model, "plain")
            assert not any("{" in a and "}" in a and '"' not in a for a in argv), argv


def test_gguf_path_is_resolved_from_cache_and_spec_args_are_spliced(cfg, monkeypatch):
    monkeypatch.setattr(h, "gguf_path_for", lambda _cfg, _model: "/cache/anchor.gguf")
    argv, _ = h.launch_command(cfg, "prismml-llama", "anchor_v2_mtp_n1", "spec")
    assert argv[argv.index("-m") + 1] == "/cache/anchor.gguf"
    assert argv[-4:] == ["--spec-type", "draft-mtp", "--spec-draft-n-max", "1"]
    assert "{spec_args}" not in argv


def test_gguf_engine_rejects_missing_local_cache_artifact(cfg, monkeypatch):
    monkeypatch.setattr(
        h, "gguf_path_for", lambda _cfg, _model: (_ for _ in ()).throw(SystemExit("missing"))
    )
    with pytest.raises(SystemExit, match="missing"):
        h.launch_command(cfg, "prismml-llama", "anchor_v2_pq2", "plain")


def test_mlx_template_check_uses_model_base_repo_when_available(cfg, monkeypatch):
    seen = {}

    def fake_source(repo):
        seen["repo"] = repo
        return "same template"

    monkeypatch.setattr(h, "local_template", lambda _path: "same template")
    monkeypatch.setattr(h, "source_template", fake_source)
    result = h.template_check(cfg, "prismml-mlx", "ternary_v1_8b", "plain")
    assert seen["repo"] == cfg["models"]["ternary_v1_8b"]["base_repo"]
    assert result["ok"]


def test_ollama_control_creation_uses_vendor_tag_and_registered_context(cfg, monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["modelfile"] = open(argv[-1]).read()

    monkeypatch.setattr(h.subprocess, "run", fake_run)
    created = h.ollama_create_derived(cfg, "qwen38_27b_q4")
    assert created == cfg["models"]["qwen38_27b_q4"]["ollama"]
    assert "FROM hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M" in seen["modelfile"]
    assert "PARAMETER num_ctx 32768" in seen["modelfile"]
    assert seen["argv"][:3] == ["ollama", "create", created]


def test_bonsai_quality_fixture_is_frozen_with_expected_category_counts():
    import json

    fx = json.loads(h.QUALITY_FIXTURE.read_text())
    counts = {
        category: sum(row["category"] == category for row in fx["items"])
        for category in {row["category"] for row in fx["items"]}
    }
    assert counts == {
        "arithmetic": 8,
        "logic": 6,
        "python": 8,
        "factual": 8,
        "instruction": 6,
        "summary": 4,
        "long_context": 3,
    }
    assert len(fx["long_context"].splitlines()) == 601


def test_quality_long_context_scope_uses_base_model_for_anchor_aliases(cfg):
    import json

    fx = json.loads(h.QUALITY_FIXTURE.read_text())
    anchor = h.quality_items(cfg, "anchor_v2_mtp_n1", fx)
    small = h.quality_items(cfg, "ternary_v1_8b", fx)
    assert sum(item["category"] == "long_context" for item in anchor) == 3
    assert not any(item["category"] == "long_context" for item in small)


def test_bonsai_quality_scorers_use_exact_checks_and_hidden_tests():
    assert h.score_quality({"category": "arithmetic", "expected": "444"}, "444.")["ok"]
    item = {
        "category": "instruction",
        "checks": {"json": {"equals": {"status": "ready", "count": 3}}},
    }
    assert h.score_quality(item, '{"status":"ready","count":3}')["ok"]
    code = {
        "category": "python",
        "test_source": "def test_it():\n    from solution import is_even\n    assert is_even(4)\n    assert not is_even(3)\n",
    }
    assert h.score_quality(code, "```python\ndef is_even(n):\n    return n % 2 == 0\n```")["ok"]


def test_phase_one_sanity_checks_reject_wrong_answers_and_accept_expected_outputs():
    assert (
        h.score_compatibility_sanity("france", "Paris is the capital of France.")["status"] == "OK"
    )
    assert (
        h.score_compatibility_sanity("france", "ParÃs is the capital of France.")["status"]
        == "GARBAGE"
    )
    assert h.score_compatibility_sanity("france", "Paris Paris Paris Paris.")["status"] == "GARBAGE"
    assert (
        h.score_compatibility_sanity("sort", "1, 3, 7, 11, 19, 23, 42, 56, 70, 88")["status"]
        == "OK"
    )
    assert h.score_compatibility_sanity("sort", "42 7 19 3 88 1 56 23 11 70")["status"] == "GARBAGE"


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
    engines = {"omlx", "mlx-serve", "rapid-mlx", "vllm-mlx", "mlx_lm.server"}
    ids = {h.served_id(cfg, e, "laguna", "plain") for e in engines}
    assert ids == {"Laguna-XS.2-4bit"}
    assert h.served_id(cfg, "ollama", "laguna", "plain") == cfg["models"]["laguna"]["ollama"]


def test_think_off_dialects():
    assert h.think_off_fields("ollama") == {"think": False, "reasoning_effort": "none"}
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
