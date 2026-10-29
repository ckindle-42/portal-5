"""The audio suite: sound under the controls gate, regenerates identically (jsonl), every
gold computed in the generator and absent from the instruction, clips valid and small, the
harness staging each clip into the row's `in/`, the transcribe MCP confining a scoped call to
that namespace, and the plan's arms served by auto-audio's groups at >= 8k windows."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import wave
from pathlib import Path

import pytest
import yaml

from portal.platform.mcp_host import eval_scope as es
from tests.wfe import controls, eval_mode
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.schema import Outcome
from tests.wfe.suites import build_audio_production as gen

REPO = Path(__file__).resolve().parents[3]
SUITE = REPO / "tests/wfe/suites/audio_production.jsonl"
PLAN = REPO / "tests/wfe/plans/audio_decision_v1.yaml"
TASKS = {t["id"]: t for t in map(json.loads, SUITE.read_text().splitlines())}
KINDS = {"fact": 12, "who-said": 12, "number": 12}


def _kind(kind: str) -> list[dict]:
    return [t for t in TASKS.values() if t["kind"] == kind]


def _gold(task: dict):
    return json.loads(task["controls"]["pass"][0]["answer"])["answer"]


def test_the_suite_is_sound_and_balanced():
    assert len(TASKS) == 36 and sum(t["screen"] for t in TASKS.values()) == 12
    for kind, n in KINDS.items():
        assert len(_kind(kind)) == n and sum(t["screen"] for t in _kind(kind)) == 4, kind
        assert all(t["id"].startswith(f"aud-{kind}-") for t in _kind(kind))
    assert controls.check_suite(SUITE) == []
    assert all(controls.schema_failures(t) == [] for t in TASKS.values())


def test_every_task_requires_the_transcription_tool_and_is_graded_on_it():
    for t in TASKS.values():
        assert t["lane"] == "audio" and not t.get("no_tools"), t["id"]
        assert t["requires_tools"] == gen.TOOLS, t["id"]
        assert [c["type"] for c in t["checkers"]] == ["answer_contains", "tool_grounded"], t["id"]


def test_the_controls_pass_and_fail_where_they_must():
    def run(task, answer, calls=None):
        ctx = CheckContext(task=task, final_text=answer, tool_calls=calls or [])
        return apply_checkers(task, ctx).outcome

    for t in TASKS.values():
        good = t["controls"]["pass"][0]
        assert run(t, good["answer"], good["tool_calls"]) == Outcome.PASS, t["id"]
        assert run(t, good["answer"]) == Outcome.FAIL, t["id"]  # answered with no transcription


def test_the_gold_is_not_in_the_instruction():
    for t in TASKS.values():
        assert not re.search(rf"\b{re.escape(str(_gold(t)))}\b", t["instruction"]), t["id"]


def test_number_answers_accept_digits_or_words_and_nothing_else():
    pat = re.compile(gen.number_alt(42))
    assert pat.fullmatch("42") and pat.fullmatch("forty-two") and pat.fullmatch("forty two")
    assert not pat.fullmatch("43") and not pat.fullmatch("forty-three")


def test_every_task_has_a_valid_short_mono_clip():
    for t in TASKS.values():
        (rel,) = t["fixtures"]
        path = REPO / rel
        assert path.parent == REPO / "tests/fixtures/audio" and path.stat().st_size < 700_000
        with wave.open(str(path)) as w:
            assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, gen.RATE)
            assert 3 <= w.getnframes() / gen.RATE <= 20, t["id"]
        assert path.name in t["instruction"]


def test_the_suite_regenerates_identically():
    # The clips are synthesised by macOS `say`, which is not byte-stable: only the spec is pinned.
    assert "".join(json.dumps(t) + "\n" for t in gen.build()) == SUITE.read_text()


def test_the_harness_stages_the_clip_in_the_rows_in_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(eval_mode, "OUTPUT_ROOT", tmp_path / "AI_Output")
    monkeypatch.setattr(eval_mode, "close_data_session", lambda scope: None)
    task = TASKS["aud-fact-00"]
    wsc = {"system_prompt_base": "b", "system_prompt_pipeline": "b+note"}
    row = {"run_id": "auto-audio|m|s|t|r0", "workspace": "auto-audio"}
    _, _, ctx = eval_mode.prepare(True, row, {"campaign_id": "c"}, task, wsc, {})
    staged = ctx["root"] / "in" / Path(task["fixtures"][0]).name
    assert staged.read_bytes() == (REPO / task["fixtures"][0]).read_bytes()
    assert ctx["scope"]["allow"] == ["transcribe_audio", "transcribe_with_speakers"]


# ------------------------------------------------- the transcribe MCP under a scope


@pytest.fixture(scope="module")
def transcribe_module():
    for name in ("mlx_audio", "mlx_audio.stt", "mlx_audio.stt.utils", "mlx_audio.vad"):
        sys.modules.setdefault(name, type(sys)(name))
    sys.modules["mlx_audio.stt.utils"].load = lambda *a, **k: None
    sys.modules["mlx_audio.vad"].load = lambda *a, **k: None
    spec = importlib.util.spec_from_file_location(
        "mlx_transcribe_scoped", REPO / "scripts" / "mlx-transcribe.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def scoped(tmp_path, monkeypatch, transcribe_module):
    monkeypatch.setenv("AI_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    scope = {"campaign": "wfe_" + "a" * 16, "run": "wfe_" + "b" * 16, "allow": []}
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads" / "shared.wav").write_bytes(b"RIFF")  # another user's upload
    in_dir = es.run_root(tmp_path, scope) / "in"
    in_dir.mkdir()
    (in_dir / "clip.wav").write_bytes(b"RIFF")
    token = es.EVAL_SCOPE.set(scope)
    yield transcribe_module, scope, tmp_path
    es.EVAL_SCOPE.reset(token)


def test_a_scoped_call_resolves_only_the_rows_own_clip(scoped):
    mod, scope, root = scoped
    in_dir = es.run_root(root, scope) / "in"
    for arg in ("clip.wav", "/workspace/uploads/clip.wav", "<file_id>", None):
        assert mod._resolve_audio_input(arg) == (in_dir / "clip.wav", "clip.wav"), arg
    path, msg = mod._resolve_audio_input("")
    assert path is None and "file not found" in msg


def test_a_scoped_call_never_falls_back_to_the_shared_uploads(scoped):
    mod, _, _ = scoped
    path, msg = mod._resolve_audio_input("shared.wav")
    assert path is None and "not found" in msg  # no 'most recent upload' fallback


def test_a_scoped_transcript_lands_in_out_with_receipts(scoped):
    mod, scope, root = scoped
    meta = {"duration": 1.0, "language": "en"}
    segments = [{"start": 0, "end": 1, "text": "hi", "speaker": 0}]
    result = mod._persist_transcript(segments, meta, "clip.wav")
    out = es.run_root(root, scope) / "out"
    assert Path(result["json_path"]).parent == out and Path(result["md_path"]).parent == out
    receipts = (es.run_root(root, scope) / ".receipts.jsonl").read_text().splitlines()
    assert len(receipts) >= 2 and all(json.loads(r)["tool"] == "transcribe" for r in receipts)
    assert not (root / "transcripts").exists()  # nothing in the shared workspace


def test_an_unscoped_call_is_unchanged(tmp_path, monkeypatch, transcribe_module):
    monkeypatch.setenv("AI_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads" / "shared.wav").write_bytes(b"RIFF")
    assert es.EVAL_SCOPE.get() is None
    path, _ = transcribe_module._resolve_audio_input(None)
    assert path == tmp_path / "uploads" / "shared.wav"


# ------------------------------------------------------------------------ the plan


def test_the_plan_arms_are_served_by_the_workspaces_groups_and_fit_its_window():
    plan = yaml.safe_load(PLAN.read_text())["workloads"]["auto-audio"]
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]["auto-audio"]
    backends = yaml.safe_load((REPO / "config/backends.yaml").read_text())
    groups = set(backends["workspace_routing"]["auto-audio"])
    served = {
        m["id"]: m
        for b in backends["backends"]
        if b["group"] in groups
        for m in b.get("models") or []
    }
    arms = plan["arms"]
    assert portal["model_hint"] in [arms["incumbent"], *arms["challengers"]]
    assert plan["home"] == "audio_production"
    assert plan["discovery"] == [] and len(arms["challengers"]) == 2
    mode = yaml.safe_load((REPO / "tests/wfe/tool_modes.yaml").read_text())["workspaces"]
    assert mode["auto-audio"]["tool_mode"] == "production"
    assert set(mode["auto-audio"]["allow"]) == set(portal["tools"])
    for tag in [arms["incumbent"], *arms["challengers"]]:
        assert tag in served and served[tag].get("supports_tools") is True, tag
        window = int(re.search(r"ctx(\d+)k", tag).group(1)) * 1024
        assert window >= portal["context_limit"], (tag, window)
