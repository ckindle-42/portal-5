"""The state document is rendered from evidence, never written; --check fails when stale."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from portal.modules.security.core.review_eval import decisions as dc

ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "scripts" / "bully_review_state.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bully_review_state", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _report(corpus: str, arm: str, binding: str) -> dict[str, object]:
    return {
        "stamp": {"commit": "abc123456789", "embedder_id": "emb", "corpus_snapshot": corpus},
        "stamp_digest": f"dig-{arm}",
        "metrics": [
            {
                "name": "recall_at_budget",
                "value": 0.42,
                "n": 50,
                "can_fail": "falls to the random arm",
            }
        ],
        "extra": {"arm": arm, "ledger": {"binding": binding}},
    }


DECISION = dc.parse(
    "---\nid: D-X\nquestion: q\nstage: candidate\narms: [a, b]\nmetric: m\nadopt_if: r\n"
    "anti_goals: [g]\nstatus: PREREGISTERED\n---\n"
)


def test_render_is_deterministic_and_separates_real_from_proxy() -> None:
    state = _load()
    census = {
        "findings": [
            {"id": "D-B", "status": "present", "evidence": "x|y"},
            {"id": "D-A", "status": "absent", "evidence": "z"},
        ],
        "census": {"summary": {"production": {"modules": 9, "lines": 3327}}},
    }
    kwargs: dict[str, Any] = {
        "census": census,
        "decisions": [(DECISION, [])],
        "reports": [
            _report("real:botsv3", "D0", "candidate"),
            _report("proxy:universe", "P0", "unit"),
        ],
        "ownership": {"capabilities": {"funnel": "review.funnel", "intake": "review.intake"}},
    }
    one, two = state.render(**kwargs), state.render(**kwargs)
    assert one == two
    assert one.index("| D-A |") < one.index("| D-B |")  # sorted
    assert "arm `D0`" in one and "arm `P0`" not in one  # proxy runs are not evidence
    assert "Proxy runs (not evidence for any claim): 1" in one
    assert "binding stage: `candidate`" in one and "| funnel | review.funnel |" in one
    assert "x/y" in one  # table pipes in evidence are neutralised


def test_empty_evidence_renders_honestly() -> None:
    state = _load()
    text = state.render(census=None, decisions=[], reports=[], ownership=None)
    for sentence in (
        "No census has been run.",
        "No decision records.",
        "No real-data report exists yet.",
        "No ownership map.",
    ):
        assert sentence in text


def test_render_names_binding_stage_unmeasured_when_no_arm_ran() -> None:
    state = _load()
    doc = _report("real:botsv1", "review_d0", "")
    doc["extra"] = {"arm": "review_d0", "ledger": {"status": "not_measured"}}
    text = state.render(census=None, decisions=[], reports=[doc], ownership=None)
    assert "binding stage: `unmeasured`" in text
    assert "excluded before product execution" in text


def test_check_fails_when_stale_or_a_record_is_invalid(tmp_path: Path) -> None:
    state = _load()
    (tmp_path / "reports" / "bully_review").mkdir(parents=True)
    (tmp_path / "reports" / "bully_review" / "census_1.json").write_text(
        json.dumps({"findings": [], "census": {}}), encoding="utf-8"
    )
    argv = ["--repo", str(tmp_path)]
    sys.argv = ["state", *argv, "--check"]
    assert state.main() == 1  # the document does not exist yet: stale
    sys.argv = ["state", *argv, "--write"]
    assert state.main() == 0
    sys.argv = ["state", *argv, "--check"]
    assert state.main() == 0
    (tmp_path / "docs" / "BULLY_REVIEW_STATE.md").write_text("hand edited\n", encoding="utf-8")
    sys.argv = ["state", *argv, "--check"]
    assert state.main() == 1  # hand edits are detected
