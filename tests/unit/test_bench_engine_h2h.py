"""Pure-logic contracts for the engine head-to-head harness
(tests/benchmarks/bench_engine_h2h.py). No network, no engines."""

from pathlib import Path

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


def test_mlx_launch_uses_model_specific_python_runtime(cfg):
    argv, _ = h.launch_command(cfg, "prismml-mlx", "bonsai_v1_27b", "plain")

    assert argv[0] == str(Path.home() / "src/prismml-mlx/.venv-bonsai/bin/python")


def test_mtplx_serves_its_own_pack_from_mtplx_root_with_fairness_pins(cfg):
    plain, _ = h.launch_command(cfg, "mtplx", "mimo", "plain")
    spec, _ = h.launch_command(cfg, "mtplx", "mimo", "spec")
    pack = "MiMo-V2.6-Qwen-9B-MTPLX-Optimized-Speed"
    for argv in (plain, spec):
        assert argv[argv.index("--model") + 1] == f"{cfg['mtplx_root']}/{pack}"
        assert argv[argv.index("--model-id") + 1] == pack
        assert "--no-stats-footer" in argv
        assert argv[argv.index("--ssd-session-cache") + 1] == "off"
        assert argv[argv.index("--profile") + 1] == "sustained"
        assert argv[argv.index("--tool-prompt-mode") + 1] == "native"
        assert "{spec_args}" not in argv
    assert plain[-1] == "--no-mtp" and "--mtp" not in plain
    assert spec[-1] == "--mtp" and "--no-mtp" not in spec
    assert h.served_id(cfg, "mtplx", "mimo", "spec") == pack


def test_mtplx_only_covers_models_with_a_pack(cfg):
    assert h.model_supports_engine(cfg, "mimo", "mtplx")
    assert not h.model_supports_engine(cfg, "laguna", "mtplx")
    assert not h.model_supports_engine(cfg, "vulnllm", "mtplx")


def test_gguf_path_is_resolved_from_cache_and_spec_args_are_spliced(cfg, monkeypatch):
    monkeypatch.setattr(h, "gguf_path_for", lambda _cfg, _model: "/cache/anchor.gguf")
    argv, _ = h.launch_command(cfg, "prismml-llama", "anchor_v2_mtp_n1", "spec")
    assert argv[argv.index("-m") + 1] == "/cache/anchor.gguf"
    assert argv[-4:] == ["--spec-type", "draft-mtp", "--spec-draft-n-max", "1"]
    assert "{spec_args}" not in argv


def test_spec_command_accepts_converted_local_drafter_override(cfg, tmp_path, monkeypatch):
    drafter = tmp_path / "converted-dspark.gguf"
    drafter.touch()
    monkeypatch.setitem(cfg["models"]["bonsai_v1_27b"], "draft_gguf_override", str(drafter))

    def resolve_cached_file(_gguf, description):
        if description.endswith("drafter"):
            pytest.fail("used cached legacy drafter")
        return "/cache/target.gguf"

    monkeypatch.setattr(h, "cached_hf_file", resolve_cached_file)

    argv, _ = h.launch_command(cfg, "prismml-llama", "bonsai_v1_27b", "spec")

    assert argv[argv.index("-m") + 1] == "/cache/target.gguf"
    assert argv[argv.index("-md") + 1] == str(drafter)


def test_spec_command_rejects_missing_local_drafter_override(cfg, tmp_path, monkeypatch):
    missing = tmp_path / "missing-dspark.gguf"
    monkeypatch.setitem(cfg["models"]["bonsai_v1_27b"], "draft_gguf_override", str(missing))

    with pytest.raises(SystemExit, match="local draft GGUF override is missing"):
        h.launch_command(cfg, "prismml-llama", "bonsai_v1_27b", "spec")


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


def test_ollama_imports_cached_control_gguf_without_vendor_pull(cfg, monkeypatch):
    seen = {}
    model = "qwen3_1_7b_q4"
    monkeypatch.setitem(
        cfg["models"][model],
        "ollama_gguf",
        {"repo": "unsloth/Qwen3-1.7B-GGUF", "file": "Qwen3-1.7B-Q4_K_M.gguf"},
    )
    monkeypatch.setattr(h, "cached_hf_file", lambda _gguf, _label: "/cache/qwen.gguf")

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["modelfile"] = open(argv[-1]).read()

    monkeypatch.setattr(h.subprocess, "run", fake_run)
    created = h.ollama_create_gguf(cfg, model)

    assert created == cfg["models"][model]["ollama"]
    assert "FROM ./file.gguf" in seen["modelfile"]
    assert "PARAMETER num_ctx 16384" in seen["modelfile"]
    assert seen["argv"][:3] == ["ollama", "create", created]


def test_speed_measurement_requires_timings_and_token_usage():
    valid_sample = {
        "ttft_s": 1.0,
        "prompt_tokens": 10,
        "completion_tokens": 2,
        "usage_reported": True,
    }
    valid = {"cold": valid_sample, "decode": [valid_sample], "prefill": [valid_sample]}
    assert h.speed_measurement_errors(valid) == []

    empty_stream = {
        "cold": {
            "ttft_s": None,
            "prompt_tokens": None,
            "completion_tokens": 0,
            "usage_reported": False,
        },
        "decode": [],
        "prefill": [],
    }
    errors = h.speed_measurement_errors(empty_stream)
    assert "cold: missing first-token timing" in errors
    assert "cold: missing reported token usage" in errors
    assert "cold: missing prompt token count" in errors
    assert "cold: missing completion token count" in errors


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


NOVEMBER_TASKS = {
    "gemma4_26b_a4b_qat": "ru-v1-001",
    "qwen38_27b_h2h": "ru-v1-011",
    "nemotron_35_lightning": "ru-v1-001",
    "flint_40b": "ru-v1-011",
}


def test_concurrency_summary_aggregates_tokens_over_wall_and_percentiles():
    samples = [
        {"completion_tokens": 100, "ttft_s": 1.0},
        {"completion_tokens": 100, "ttft_s": 2.0},
        {"completion_tokens": 100, "ttft_s": 3.0},
        {"completion_tokens": 100, "ttft_s": 4.0},
    ]
    row = h.concurrency_summary(samples, 2.0)
    assert row["n"] == 4
    assert row["aggregate_decode_tps"] == 200.0
    assert row["ttft_p50_s"] == 2.5
    assert row["ttft_p95_s"] == 3.85
    one = h.concurrency_summary([{"completion_tokens": 10, "ttft_s": 0.5}], 1.0)
    assert one["aggregate_decode_tps"] == 10.0
    assert one["ttft_p50_s"] == one["ttft_p95_s"] == 0.5
    assert (
        h.concurrency_summary([{"completion_tokens": 10, "ttft_s": 0.5}], 0)["aggregate_decode_tps"]
        is None
    )


def test_vllm_mlx_0_6_pins_batching_and_leaves_disk_cache_off(cfg):
    argv, _ = h.launch_command(cfg, "vllm-mlx", "mimo", "plain")
    assert "vllm-mlx==0.6.0" in argv
    assert "--continuous-batching" in argv
    assert "--ssd-cache-dir" not in argv
    kwargs = argv[argv.index("--default-chat-template-kwargs") + 1]
    assert "enable_thinking" in kwargs and "false" in kwargs


def test_mlxcel_pins_parallel_batch_without_prompt_lookup(cfg):
    argv, _ = h.launch_command(cfg, "mlxcel", "gemma4_26b_a4b_qat", "plain")
    assert argv[argv.index("--parallel") + 1] == "4"
    assert "--kv-unified" in argv
    assert "--prompt-lookup" not in argv
    assert argv[argv.index("--ctx-size") + 1] == "16384"
    with pytest.raises(SystemExit):
        h.launch_command(cfg, "mlxcel", "gemma4_26b_a4b_qat", "spec")


def test_splash_qwen_pins_disk_cache_off_and_local_draft(cfg):
    plain, _ = h.launch_command(cfg, "splash", "qwen38_27b_h2h", "plain")
    spec, _ = h.launch_command(cfg, "splash", "qwen38_27b_h2h", "spec")
    draft = cfg["models"]["qwen38_27b_h2h"]["drafter_dir"]
    for argv in (plain, spec):
        assert argv[argv.index("--max-cache-disk") + 1] == "0"
        assert "--persistent-cache" not in argv
        assert "--language-only" in argv
        assert argv[argv.index("--default-reasoning-effort") + 1] == "none"
        assert argv[argv.index("--draft-model") + 1] == draft
        assert argv[argv.index("--port") + 1] == "11242"
    assert plain == spec
    assert h.served_id(cfg, "splash", "qwen38_27b_h2h", "plain") == "Qwen3.8-27B-4bit"


def test_splash_flint_keeps_256k_and_cannot_force_think_off(cfg):
    argv, _ = h.launch_command(cfg, "splash", "flint_40b", "plain")
    assert argv[argv.index("--model") + 1] == "unsloth/flint-GGUF:UD-Q4_K_XL"
    assert argv[argv.index("--max-context") + 1] == "262144"
    assert "--default-reasoning-effort" not in argv
    assert "--model-dir" not in argv
    assert argv[argv.index("--verify-rows") + 1] == "all"
    assert argv[argv.index("--expert-memory") + 1] == "off"
    assert h.think_off_fields("splash", "flint_40b", cfg) == {}
    assert h.think_off_fields("splash") == {"reasoning_effort": "none"}
    assert "mlx" not in cfg["models"]["flint_40b"]
    assert not h.model_supports_engine(cfg, "flint_40b", "ollama")
    assert not h.model_supports_engine(cfg, "flint_40b", "omlx")


def test_splash_refuses_gemma_and_gemma_spec_is_null(cfg):
    with pytest.raises(SystemExit, match="no splash artifact"):
        h.launch_command(cfg, "splash", "gemma4_26b_a4b_qat", "plain")
    with pytest.raises(SystemExit):
        h.launch_command(cfg, "vllm-mlx", "gemma4_26b_a4b_qat", "spec")


def test_qwen_drafter_dir_is_absolute_and_vllm_spec_is_null(cfg):
    argv, _ = h.launch_command(cfg, "rapid-mlx", "qwen38_27b_h2h", "spec")
    blob = argv[argv.index("--speculative-config") + 1]
    draft = cfg["models"]["qwen38_27b_h2h"]["drafter_dir"]
    assert blob.startswith('{"method":"dflash"')
    assert draft in blob
    qwen_plain, _ = h.launch_command(cfg, "mlx-serve", "qwen38_27b_h2h", "plain")
    assert "--drafter" not in qwen_plain and "--no-drafter" in qwen_plain
    mlx, _ = h.launch_command(cfg, "mlxcel", "qwen38_27b_h2h", "spec")
    assert mlx[mlx.index("--draft-kind") + 1] == "dflash"
    assert draft in mlx
    with pytest.raises(SystemExit):
        h.launch_command(cfg, "vllm-mlx", "qwen38_27b_h2h", "spec")


def test_nemotron_mtp_spec_uses_the_oq4e_dir(cfg):
    plain, _ = h.launch_command(cfg, "mlx-serve", "nemotron_35_lightning", "plain")
    spec, _ = h.launch_command(cfg, "mlx-serve", "nemotron_35_lightning", "spec")
    pack = "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp"
    assert "--no-mtp" in plain and "--mtp" not in plain
    assert "--mtp" in spec and "--no-mtp" not in spec
    assert pack in spec[spec.index("--model") + 1]
    rapid, _ = h.launch_command(cfg, "rapid-mlx", "nemotron_35_lightning", "spec")
    blob = rapid[rapid.index("--speculative-config") + 1]
    assert '"method":"mtp"' in blob
    with pytest.raises(SystemExit):
        h.launch_command(cfg, "mlxcel", "nemotron_35_lightning", "spec")


def test_november_seats_have_one_quality_task(cfg):
    from tests.wfe.campaign import expand_matrix

    for model, task in NOVEMBER_TASKS.items():
        gate = cfg["models"][model]["quality_gate"]
        assert gate["tool_probe"] == "preflight"
        assert gate["wfe_task"] == task
        rows = expand_matrix(h.REPO / gate["wfe_plan"], 1, tier="realuse")
        assert {row["task_id"] for row in rows} == {task}
        assert {row["workspace"] for row in rows} == {gate["wfe_workspace"]}


LANDSCAPE_PINS = {"splash": "1.6.1", "mlx-serve": "26.11.2", "rapid-mlx": "1.0.2"}
VLLM_METAL_SEATS = ("gemma4_26b_a4b_qat", "qwen38_27b_h2h", "nemotron_35_lightning")
MANAGED_ENGINE_KEYS = {"kind", "requires", "port", "plain", "base_spec"}


def test_registry_pins_are_the_landscape_versions(cfg):
    versions = {name: e.get("version") for name, e in cfg["engines"].items()}
    for engine, version in LANDSCAPE_PINS.items():
        assert versions[engine] == version
    assert versions["vllm-metal"] == "0.33.0"


def test_version_bumps_keep_each_engines_fairness_pins(cfg):
    splash, _ = h.launch_command(cfg, "splash", "qwen38_27b_h2h", "spec")
    assert splash[splash.index("--max-cache-disk") + 1] == "0"
    assert "--persistent-cache" not in splash
    assert "--language-only" in splash
    mlx, _ = h.launch_command(cfg, "mlx-serve", "qwen38_27b_h2h", "plain")
    assert {"--no-pld", "--no-drafter", "--no-mtp"} <= set(mlx)
    rapid_plain, _ = h.launch_command(cfg, "rapid-mlx", "qwen38_27b_h2h", "plain")
    assert "--no-telemetry" in rapid_plain and "--no-spec-decode" in rapid_plain
    rapid_spec, _ = h.launch_command(cfg, "rapid-mlx", "qwen38_27b_h2h", "spec")
    assert "--speculative-config" in rapid_spec


def test_every_managed_engine_declares_the_same_schema(cfg):
    managed = {name: e for name, e in cfg["engines"].items() if e["kind"] == "managed"}
    assert "vllm-metal" in managed
    for name, e in managed.items():
        assert set(e) >= MANAGED_ENGINE_KEYS, name
        assert isinstance(e["plain"], list) and isinstance(e["base_spec"], list), name
    ports = [e["port"] for e in cfg["engines"].values() if "port" in e]
    assert len(ports) == len(set(ports))
    assert managed["vllm-metal"]["port"] == 11244
    assert managed["vllm-metal"]["requires"] == "mlx"


def test_vllm_metal_renders_the_documented_plain_argv(cfg):
    argv, cwd = h.launch_command(cfg, "vllm-metal", "qwen38_27b_h2h", "plain")
    assert argv[:2] == ["vllm", "serve"]
    assert cwd is None
    assert argv[argv.index("--port") + 1] == "11244"
    assert argv[argv.index("--gpu-memory-utilization") + 1] == "0.7"
    assert argv[argv.index("--max-model-len") + 1] == "32768"
    assert "--tool-call-parser" not in argv
    assert "--persistent-cache" not in argv


def test_vllm_metal_covers_the_shortlist_seats(cfg):
    for model in VLLM_METAL_SEATS:
        assert h.model_supports_engine(cfg, model, "vllm-metal"), model
        argv, _ = h.launch_command(cfg, "vllm-metal", model, "plain")
        assert argv[2] == f"{cfg['mlx_root']}/{cfg['models'][model]['mlx']}"
    assert h.served_id(cfg, "vllm-metal", "qwen38_27b_h2h", "plain") == "Qwen3.8-27B-4bit"


def test_vllm_metal_spec_cells_stay_null_until_the_model_matrix_is_read(cfg):
    for model in VLLM_METAL_SEATS:
        assert h.spec_entry(cfg, model, "vllm-metal") is None, model
        with pytest.raises(SystemExit, match="no spec path"):
            h.launch_command(cfg, "vllm-metal", model, "spec")


def test_vllm_metal_spec_args_splice_where_the_doc_wrote_spec_json(cfg, monkeypatch):
    blob = '{"method":"mtp","num_speculative_tokens":1}'
    monkeypatch.setitem(
        cfg["models"]["qwen38_27b_h2h"]["spec"],
        "vllm-metal",
        {"method": "mtp", "args": [blob]},
    )
    argv, _ = h.launch_command(cfg, "vllm-metal", "qwen38_27b_h2h", "spec")
    assert "--no-async-scheduling" in argv
    assert argv[argv.index("--speculative-config") + 1] == blob
    assert not any("{" in a and "}" in a and '"' not in a for a in argv)


def test_engine_version_knows_the_new_engine(monkeypatch):
    seen = {}

    def fake_run(argv, timeout=15):
        seen["argv"] = argv
        return "vllm 0.33.0\n"

    monkeypatch.setattr(h, "_run", fake_run)
    assert h.engine_version("vllm-metal") == "vllm 0.33.0"
    assert seen["argv"][0] == "vllm"
