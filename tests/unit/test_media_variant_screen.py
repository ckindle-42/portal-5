"""Media variant screen: parsing, catalog, plan and render helpers only (no generation)."""

import copy
import importlib
import io
import json
import runpy
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

screen = importlib.import_module("scripts.proofs.media_variant_screen")
install = importlib.import_module("scripts.proofs.media_variant_screen_install")

CATALOG = screen.load_catalog()

# Real `memory_pressure` output shape (macOS 15, 64 GB host), trailing spaces trimmed;
# the parsed line is the last one.
MEMORY_PRESSURE_TEXT = """\
The system has 68719476736 (4194304 pages with a page size of 16384).

Stats:
Pages free: 720448
Pages wired down: 1728862

Swapins: 17782344

System-wide memory free percentage: 56%
"""
SWAPUSAGE_TEXT = "vm.swapusage: total = 15360.00M  used = 14311.25M  free = 1048.75M  (encrypted)"
PS_TEXT = """\
     1     0   100
  1000     1  2000
  1001  1000  3000
  1002  1001   500
  2000     1  9000
"""


def test_catalog_has_one_incumbent_per_medium_and_three_prompts():
    for _medium, spec in CATALOG["media"].items():
        rows = spec["rows"]
        assert sum(1 for r in rows if r["role"] == "incumbent") == 1
        assert len(spec["prompts"]) == 3
        assert len({r["id"] for r in rows}) == len(rows)


def test_cli_rows_carry_prompt_and_output_placeholders():
    for _medium, spec in CATALOG["media"].items():
        for row in spec["rows"]:
            if row.get("kind", "cli") == "cli":
                text = " ".join(row["argv"])
                assert "{prompt}" in text and "{output}" in text, row["id"]


def test_image_and_video_prompts_match_the_doc():
    assert "PORTAL 5" in CATALOG["media"]["image"]["prompts"][0]
    assert "basalt" in CATALOG["media"]["video"]["prompts"][0]
    assert CATALOG["media"]["music"]["prompts"][2]["caption"].startswith("solo nylon-string")


def test_optional_rows_excluded_by_default_and_selectable_by_id():
    rows = CATALOG["media"]["image"]["rows"]
    default_ids = [r["id"] for r in screen.select_rows(rows, None)]
    assert default_ids[0] == "klein4b-q8"
    assert "qwen21-turbo-q4" not in default_ids
    assert [r["id"] for r in screen.select_rows(rows, ["qwen21-turbo-q4"])] == ["qwen21-turbo-q4"]
    with pytest.raises(ValueError):
        screen.select_rows(rows, ["not-a-row"])


def test_tree_rss_sums_descendants_and_tracks_max():
    total, peak = screen.tree_rss(PS_TEXT, 1000)
    assert total == (2000 + 3000 + 500) * 1024
    assert peak == 3000 * 1024


def test_tree_rss_ignores_unrelated_and_missing_roots():
    assert screen.tree_rss(PS_TEXT, 2000) == (9000 * 1024, 9000 * 1024)
    assert screen.tree_rss(PS_TEXT, 424242) == (0, 0)


def test_parse_free_pct_and_swap():
    assert screen.parse_free_pct(MEMORY_PRESSURE_TEXT) == 56.0
    assert screen.parse_free_pct("no line here") is None
    assert screen.parse_swap_gb(SWAPUSAGE_TEXT) == pytest.approx(14311.25 / 1024, abs=1e-3)
    assert screen.parse_swap_gb("used = n/a") is None


def test_parse_output_paths_takes_last_runner_line():
    text = 'noise\nOUTPUT_PATHS: ["/a/one.wav"]\nOUTPUT_PATHS: ["/a/two.wav"]\n'
    assert screen.parse_output_paths(text) == ["/a/two.wav"]
    assert screen.parse_output_paths("OUTPUT_PATHS: [broken") == []
    assert screen.parse_output_paths("") == []


def test_parse_output_paths_ignores_non_path_records():
    text = 'OUTPUT_PATHS: [{"path": "/a/two.wav", "tensor": "large"}]\n'
    assert screen.parse_output_paths(text) == []


def test_plan_image_substitutes_prompt_output_and_candidate_cache(tmp_path):
    row = next(r for r in CATALOG["media"]["image"]["rows"] if r["id"] == "iris-q8")
    plan = screen._plan_prompt(CATALOG, "image", row, 1, tmp_path, tmp_path / "image")
    assert any("A corner bakery at dawn" in part for part in plan.argv)
    assert plan.argv[-1] == str(tmp_path / "image" / "iris-q8-p1.png")
    assert plan.env_add == {"HF_HUB_CACHE": CATALOG["paths"]["hf_cache"]}
    incumbent = next(r for r in CATALOG["media"]["image"]["rows"] if r["role"] == "incumbent")
    assert (
        screen._plan_prompt(CATALOG, "image", incumbent, 1, tmp_path, tmp_path / "image").env_add
        == {}
    )


def test_plan_video_incumbent_uses_portal_installed_cli(tmp_path):
    row = next(r for r in CATALOG["media"]["video"]["rows"] if r["id"] == "ltx25-q4")
    plan = screen._plan_prompt(CATALOG, "video", row, 1, tmp_path, tmp_path / "video")
    assert plan.argv[0] == f"{CATALOG['paths']['video_venv']}/bin/ltx-2-mlx"
    assert "uvx" not in plan.argv
    assert plan.argv[1:3] == ["generate", "--distilled"]
    assert plan.argv[plan.argv.index("--model") + 1] == "dgrauet/ltx-2.5-mlx-q4"
    assert plan.argv[plan.argv.index("--frames") + 1] == "97"
    assert plan.argv[-1] == str(tmp_path / "video" / "ltx25-q4-p1.mp4")


def test_plan_music_spec_and_materialized_runner(tmp_path):
    row = next(r for r in CATALOG["media"]["music"]["rows"] if r["id"] == "ace-turbo2b-lm06")
    plan = screen._plan_prompt(CATALOG, "music", row, 2, tmp_path, tmp_path / "music")
    spec = plan.spec
    assert spec["load_lm"] is True and spec["lm"] == "acestep-5Hz-lm-0.6B"
    assert spec["instrumental"] is False and "Streetlight" in spec["lyrics"]
    assert spec["duration"] == 30.0 and spec["steps"] == 8 and spec["seed"] == 42
    assert plan.argv[2:4] == ["--no-sync", "python"]
    screen._materialize_plan(plan)
    assert json.loads((Path(spec["save_dir"]) / "spec.json").read_text())["caption"].startswith(
        "upbeat"
    )
    runner = tmp_path / "ace_run" / "runner.py"
    assert runner.exists() and "OUTPUT_PATHS: " in runner.read_text()


def test_plan_music_lm_off_row(tmp_path):
    row = next(r for r in CATALOG["media"]["music"]["rows"] if r["id"] == "ace-turbo2b-nolm")
    spec = screen._plan_prompt(CATALOG, "music", row, 1, tmp_path, tmp_path / "music").spec
    assert spec["load_lm"] is False and spec["lm"] is None and spec["instrumental"] is True


def _tiny_catalog(rows):
    return {
        "pins": {},
        "paths": {},
        "media": {
            "image": {"canvas": "c", "criteria": "x", "prompts": ["p"], "rows": rows},
            "video": {
                "canvas": "c",
                "criteria": "x",
                "prompts": ["p"],
                "rows": [
                    {
                        "id": "v",
                        "role": "incumbent",
                        "argv": ["x", "{prompt}", "--output", "{output}"],
                    }
                ],
            },
            "music": {
                "canvas": "c",
                "criteria": "x",
                "prompts": [{"caption": "c", "lyrics": "", "instrumental": True}],
                "gen": {"duration": 1.0, "steps": 1, "seed": 1, "shift": 1.0},
                "rows": [
                    {"id": "m", "role": "incumbent", "kind": "music", "dit": "d", "load_lm": False}
                ],
            },
        },
    }


def test_validate_catalog_rejects_two_incumbents():
    rows = [
        {"id": "a", "role": "incumbent", "argv": ["g", "{prompt}", "{output}"]},
        {"id": "b", "role": "incumbent", "argv": ["g", "{prompt}", "{output}"]},
    ]
    with pytest.raises(ValueError, match="exactly one incumbent"):
        screen._validate_catalog(_tiny_catalog(rows))


def test_validate_catalog_rejects_missing_placeholder_and_bad_music_row():
    rows = [{"id": "a", "role": "incumbent", "argv": ["g", "{prompt}"]}]
    with pytest.raises(ValueError, match="placeholder"):
        screen._validate_catalog(_tiny_catalog(rows))
    music = _tiny_catalog([{"id": "a", "role": "incumbent", "argv": ["g", "{prompt}", "{output}"]}])
    music["media"]["music"]["rows"][0]["load_lm"] = True
    with pytest.raises(ValueError, match="`lm`"):
        screen._validate_catalog(music)


def _receipt(row, role, **kw):
    base = {
        "row": row,
        "role": role,
        "rank": None if role == "incumbent" else 1,
        "prompt_index": 1,
        "prompt": "p",
        "command": ["x"],
        "cwd": ".",
        "env_added": {},
        "wall_s": 10.0,
        "peak_rss_tree_gb": 5.0,
        "peak_rss_max_gb": 4.0,
        "free_floor_pct": 40.0,
        "free_after_pct": 50.0,
        "swap_start_gb": 1.0,
        "swap_peak_gb": 1.5,
        "swap_delta_gb": 0.5,
        "exit_code": 0,
        "status": "ok",
        "outputs": ["out/x.png"],
        "log": "logs/x.log",
        "note": None,
        "expected_peak_gb": None,
        "expected_note": None,
        "stop_reason": None,
    }
    base.update(kw)
    return base


@pytest.mark.parametrize("medium", ["image", "video"])
def test_run_row_creates_outputs_parent_before_running(tmp_path, monkeypatch, medium):
    """Regression (ltx25-q4): each row's output parent must exist before its command runs."""
    cli_row = {"id": "v", "role": "incumbent", "argv": ["x", "{prompt}", "--output", "{output}"]}
    catalog = _tiny_catalog([cli_row])
    seen = {}

    def fake_run_plan(plan, log_path, timeout_s):
        seen["parent"] = plan.output.parent
        return _receipt(plan.row["id"], plan.row.get("role")), False

    monkeypatch.setattr(screen, "_run_plan", fake_run_plan)
    screen._run_row(
        catalog, medium, catalog["media"][medium]["rows"][0], tmp_path, tmp_path / medium, 0
    )
    assert seen["parent"] == tmp_path / medium
    assert (tmp_path / medium).is_dir()


def test_materialize_creates_video_incumbent_output_dir(tmp_path):
    """ltx-2-mlx's ffmpeg cannot create run_dir/video/ itself; the screen must."""
    row = next(r for r in CATALOG["media"]["video"]["rows"] if r["id"] == "ltx25-q4")
    plan = screen._plan_prompt(CATALOG, "video", row, 1, tmp_path, tmp_path / "video")
    assert not plan.output.parent.exists()
    screen._materialize_plan(plan)
    assert plan.output.parent.is_dir()


def test_render_table_lists_rows_and_columns(tmp_path, monkeypatch):
    monkeypatch.setattr(screen, "_host_line", lambda: "test-host")
    results = [_receipt("klein4b-q8", "incumbent"), _receipt("iris-q8", "candidate")]
    text = screen._render_table(CATALOG, "image", results, tmp_path, ["ollama pid=1 1.00 GB"])
    assert "| klein4b-q8 | incumbent |" in text
    assert "| iris-q8 | candidate | 1 |" in text
    assert "peak RSS GB" in text and "free floor %" in text and "swap" in text


def test_render_table_carries_stop_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(screen, "_host_line", lambda: "test-host")
    results = [
        _receipt(
            "qwen21-turbo-q4",
            "candidate",
            rank=None,
            stop_reason="peak 12.40 GB exceeds the 12 GB stop; remaining prompts skipped",
        )
    ]
    text = screen._render_table(CATALOG, "image", results, tmp_path, [])
    assert "stop: peak 12.40 GB exceeds the 12 GB stop" in text


def test_render_judge_pairs_candidate_with_incumbent(tmp_path):
    results = [_receipt("klein4b-q8", "incumbent"), _receipt("iris-q8", "candidate")]
    text = screen._render_judge(CATALOG, "image", results, tmp_path)
    assert "## iris-q8 (rank 1) vs klein4b-q8" in text
    assert "candidate →" in text and "incumbent →" in text


def test_render_judge_reports_video_streams(tmp_path):
    results = [
        _receipt("ltx25-q4", "incumbent", has_video=1, has_audio=1),
        _receipt("fastmetal13", "candidate", has_video=1, has_audio=0),
    ]
    text = screen._render_judge(CATALOG, "video", results, tmp_path)
    assert "streams: candidate v=1 a=0 | incumbent v=1 a=1" in text


def test_status_derivation():
    assert screen._status(None, [], "interrupt") == "interrupt"
    assert screen._status(-9, [], None) == "killed-sig9"
    assert screen._status(1, [], None) == "exit1"
    assert screen._status(0, [], None) == "no-output"
    assert screen._status(0, [Path("x.png")], None) == "ok"


def test_install_pins_and_paths_come_from_the_catalog():
    assert CATALOG["pins"] == install.PINS
    assert install.PATHS["hf_cache"] == Path(CATALOG["paths"]["hf_cache"])
    assert install.PATHS["weights_root"] == Path(CATALOG["paths"]["weights_root"])


def test_hf_size_gb_parses_api_payload(monkeypatch):
    payload = {
        "siblings": [
            {"rfilename": "a.safetensors", "size": 2 * 1024**3},
            {"rfilename": "b.json", "size": 1024**3},
        ]
    }
    monkeypatch.setattr(
        install.urllib.request, "urlopen", lambda url, timeout=30: io.StringIO(json.dumps(payload))
    )
    assert install.hf_size_gb("org/repo") == pytest.approx(3.0)

    def boom(url, timeout=30):
        raise OSError("down")

    monkeypatch.setattr(install.urllib.request, "urlopen", boom)
    assert install.hf_size_gb("org/repo") is None


def test_install_helper_rejects_non_arm64(monkeypatch):
    monkeypatch.setattr(install.platform, "machine", lambda: "x86_64")
    with pytest.raises(SystemExit, match="arm64"):
        install._need_apple_silicon()


def test_maybe_plan_mode_prints_without_running(capsys):
    assert install._maybe(["echo", "hi"], yes=False) == 0
    out = capsys.readouterr().out
    assert "would run: echo hi" in out


def test_music_runner_text_needs_no_substitution():
    text = screen._music_runner_text()
    assert "initialize_service" in text and "OUTPUT_PATHS: " in text
    assert "{prompt}" not in text and "{output}" not in text


def test_music_runner_extracts_path_without_stringifying_tensor(tmp_path, monkeypatch, capsys):
    output_path = tmp_path / "song.wav"
    output_path.write_bytes(b"audio")
    spec = {
        "root": str(tmp_path),
        "save_dir": str(tmp_path),
        "dit": "dit",
        "load_lm": False,
        "lm": None,
        "caption": "caption",
        "lyrics": "",
        "duration": 1.0,
        "steps": 1,
        "seed": 42,
        "shift": 3.0,
        "instrumental": True,
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec))
    runner_path = tmp_path / "runner.py"
    runner_path.write_text(screen._music_runner_text())

    class Tensor:
        def __repr__(self):
            raise AssertionError("tensor was formatted")

    handler = ModuleType("acestep.handler")
    handler.AceStepHandler = type(
        "AceStepHandler",
        (),
        {"initialize_service": lambda self, **kwargs: ("ready", True)},
    )
    inference = ModuleType("acestep.inference")
    inference.GenerationConfig = lambda **kwargs: kwargs
    inference.GenerationParams = lambda **kwargs: kwargs
    inference.generate_music = lambda *args, **kwargs: SimpleNamespace(
        audios=[{"path": str(output_path), "tensor": Tensor()}]
    )
    llm = ModuleType("acestep.llm_inference")
    llm.LLMHandler = type("LLMHandler", (), {})
    package = ModuleType("acestep")
    package.__path__ = []
    for name, module in (
        ("acestep", package),
        ("acestep.handler", handler),
        ("acestep.inference", inference),
        ("acestep.llm_inference", llm),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    old_path = sys.path[:]
    monkeypatch.setattr(sys, "argv", [str(runner_path), "--spec", str(spec_path)])
    try:
        runpy.run_path(str(runner_path), run_name="__main__")
    finally:
        sys.path[:] = old_path
    assert screen.parse_output_paths(capsys.readouterr().out) == [str(output_path)]


def test_catalog_copy_is_deep_enough_for_mutation_tests():
    mutated = copy.deepcopy(CATALOG)
    mutated["media"]["image"]["rows"].pop()
    screen._validate_catalog(CATALOG)  # the shipped catalog still validates


def test_catalog_heartlib_row_is_a_ranked_music_candidate():
    rows = CATALOG["media"]["music"]["rows"]
    row = next(r for r in rows if r["id"] == "heartmula3b")
    assert row["kind"] == "heartlib" and row["role"] == "candidate" and row["rank"] == 3
    assert CATALOG["pins"]["heartlib-mlx"] == "02dd2e22f6a1"
    default_ids = [r["id"] for r in screen.select_rows(rows, None)]
    assert default_ids == ["ace-xl17", "ace-turbo2b-lm06", "ace-turbo2b-nolm", "heartmula3b"]


def test_validate_rejects_heartlib_row_outside_music():
    catalog = _tiny_catalog(
        [{"id": "a", "role": "incumbent", "argv": ["g", "{prompt}", "{output}"]}]
    )
    catalog["media"]["image"]["rows"].append({"id": "h", "role": "candidate", "kind": "heartlib"})
    with pytest.raises(ValueError, match="music-only"):
        screen._validate_catalog(catalog)


def test_plan_heartlib_spec_argv_and_output(tmp_path):
    row = next(r for r in CATALOG["media"]["music"]["rows"] if r["id"] == "heartmula3b")
    plan = screen._plan_prompt(CATALOG, "music", row, 2, tmp_path, tmp_path / "music")
    src = Path(CATALOG["paths"]["heartlib_src"])
    assert plan.argv[0] == str(src / ".venv" / "bin" / "python")
    assert plan.argv[1] == str(tmp_path / "heartlib_run" / "runner.py")
    assert plan.argv[2:] == [
        "--spec",
        str(tmp_path / "heartlib_run" / "heartmula3b-p2" / "spec.json"),
    ]
    assert plan.cwd == src
    assert plan.output == tmp_path / "music" / "heartmula3b-p2.wav"
    assert plan.env_add == {"HF_HUB_CACHE": CATALOG["paths"]["hf_cache"]}
    spec = plan.spec
    assert spec["checkpoint"] == str(Path(CATALOG["paths"]["heartlib_root"]) / "ckpt-mlx")
    assert spec["caption"].startswith("upbeat") and "Streetlight" in spec["lyrics"]
    assert spec["duration"] == 30.0 and spec["seed"] == 42
    assert spec["output"] == str(plan.output)


def test_materialize_heartlib_runner_and_spec(tmp_path):
    row = next(r for r in CATALOG["media"]["music"]["rows"] if r["id"] == "heartmula3b")
    plan = screen._plan_prompt(CATALOG, "music", row, 1, tmp_path, tmp_path / "music")
    screen._materialize_plan(plan)
    runner = tmp_path / "heartlib_run" / "runner.py"
    text = runner.read_text()
    assert "mx.random.seed" in text and "OUTPUT_PATHS: " in text and "generate.py" in text
    assert "{prompt}" not in text and "{output}" not in text
    spec = json.loads((tmp_path / "heartlib_run" / "heartmula3b-p1" / "spec.json").read_text())
    assert spec["lyrics"] == "" and spec["caption"].startswith("sparse acoustic")
    assert plan.output.parent.is_dir()
    assert not (tmp_path / "ace_run").exists()


@pytest.mark.parametrize("prompt_index", [1, 2])
def test_heartlib_runner_seeds_and_delegates_to_generate(
    tmp_path, monkeypatch, capsys, prompt_index
):
    """Generation is mocked: the runner must seed MLX and hand the port's CLI the spec."""
    catalog = copy.deepcopy(CATALOG)
    catalog["paths"]["heartlib_src"] = str(tmp_path / "heartlib-src")
    catalog["paths"]["heartlib_root"] = str(tmp_path / "heartlib-weights")
    row = next(r for r in catalog["media"]["music"]["rows"] if r["id"] == "heartmula3b")
    plan = screen._plan_prompt(catalog, "music", row, prompt_index, tmp_path, tmp_path / "music")
    screen._materialize_plan(plan)
    spec = plan.spec
    generate = Path(spec["src"]) / "generate.py"
    generate.parent.mkdir(parents=True, exist_ok=True)
    generate.write_text("# stub\n")

    seeds: list[int] = []
    mlx = ModuleType("mlx")
    core = ModuleType("mlx.core")
    core.random = SimpleNamespace(seed=seeds.append)
    mlx.core = core
    monkeypatch.setitem(sys.modules, "mlx", mlx)
    monkeypatch.setitem(sys.modules, "mlx.core", core)

    calls: dict = {}
    real_run_path = runpy.run_path

    def fake_generate(path, run_name=None):
        calls["path"] = path
        calls["run_name"] = run_name
        calls["argv"] = list(sys.argv)
        out = Path(sys.argv[sys.argv.index("--output") + 1])
        out.write_bytes(b"audio")

    monkeypatch.setattr(runpy, "run_path", fake_generate)
    runner = str(tmp_path / "heartlib_run" / "runner.py")
    spec_path = str(Path(spec["save_dir"]) / "spec.json")
    monkeypatch.setattr(sys, "argv", [runner, "--spec", spec_path])
    real_run_path(runner, run_name="__main__")

    assert seeds == [42]
    assert calls["path"] == str(Path(spec["src"]) / "generate.py")
    assert calls["run_name"] == "__main__"
    argv = calls["argv"]
    assert argv[argv.index("--tags") + 1] == spec["caption"]
    assert argv[argv.index("--duration") + 1] == "30.0"
    assert argv[argv.index("--checkpoint") + 1] == spec["checkpoint"]
    assert argv[argv.index("--dtype") + 1] == "bfloat16"
    assert argv[argv.index("--output") + 1] == str(plan.output)
    if spec["lyrics"]:
        assert argv[argv.index("--lyrics") + 1] == spec["lyrics"]
    else:
        assert "--lyrics" not in argv
    assert plan.output.exists()
    assert screen.parse_output_paths(capsys.readouterr().out) == [str(plan.output)]
