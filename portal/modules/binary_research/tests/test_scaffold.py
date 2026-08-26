"""Session-based intake — start, answer, scaffold write (no live model, stubbed)."""

import json
from pathlib import Path

from portal.modules.binary_research.harness import scaffold as s
from portal.modules.binary_research.harness.llm import LLMConfig


def test_parse_json_plain():
    assert s._parse_json('{"done": true}', {}) == {"done": True}


def test_parse_json_fenced():
    assert s._parse_json('```json\n{"goal":"x"}\n```', {}) == {"goal": "x"}


def test_parse_json_embedded():
    assert s._parse_json('here: {"goal":"y"} done', {}).get("goal") == "y"


def test_parse_json_garbage_returns_default():
    assert s._parse_json("not json", {"goal": "d"}) == {"goal": "d"}


def test_start_writes_opening_question(tmp_path: Path):
    out = s.start(tmp_path)
    assert out["state"] == "asking"
    assert out["question"]  # opening question set
    st = json.loads((tmp_path / ".brh" / "intake.json").read_text())
    assert st["opening_asked"] is True


def test_answer_asks_next_when_model_wants_more(tmp_path: Path, monkeypatch):
    s.start(tmp_path)
    monkeypatch.setattr(
        s, "_next_step", lambda cfg, turns: {"done": False, "next_question": "Which arch?"}
    )
    out = s.answer(LLMConfig(), tmp_path, "a firmware blob")
    assert out["state"] == "asking"
    assert out["question"] == "Which arch?"
    st = json.loads((tmp_path / ".brh" / "intake.json").read_text())
    assert st["turns"][0]["a"] == "a firmware blob"


def test_answer_scaffolds_when_model_done(tmp_path: Path, monkeypatch):
    s.start(tmp_path)
    plan = {
        "goal": "Reconstruct payload",
        "hypotheses": ["embeds a token"],
        "checks": ["token recovered"],
        "verifiers": [{"name": "token", "description": "token in 03_model.md"}],
    }
    monkeypatch.setattr(
        s, "_next_step", lambda cfg, turns: {"done": True, "next_question": None, "plan": plan}
    )
    out = s.answer(LLMConfig(), tmp_path, "find the token")
    assert out["state"] == "ready"
    assert (tmp_path / "GOAL.txt").read_text().strip() == "Reconstruct payload"
    assert (tmp_path / "verifiers" / "token.sh").exists()
    st = json.loads((tmp_path / ".brh" / "intake.json").read_text())
    assert st["scaffold_written"] is True


def test_answer_forces_done_after_max(tmp_path: Path, monkeypatch):
    s.start(tmp_path)
    # Model always wants more, but the cap forces a scaffold.
    monkeypatch.setattr(
        s, "_next_step", lambda cfg, turns: {"done": False, "next_question": "again?"}
    )
    out = {}
    for i in range(s._MAX_QUESTIONS + 1):
        out = s.answer(LLMConfig(), tmp_path, f"answer {i}")
    assert out["state"] == "ready"


def test_apply_plan_writes_structure(tmp_path: Path):
    plan = s.ScaffoldPlan(
        goal="G",
        hypotheses=["h1"],
        checks=["c1"],
        verifiers=[{"name": "v one", "description": "d"}],
    )
    s.apply_plan(tmp_path, plan)
    assert (tmp_path / "GOAL.txt").read_text().strip() == "G"
    assert "h1" in (tmp_path / "01_hypotheses.md").read_text()
    stubs = list((tmp_path / "verifiers").glob("*.sh"))
    assert len(stubs) == 1 and stubs[0].stat().st_mode & 0o111
