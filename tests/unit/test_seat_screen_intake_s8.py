"""The s8 intake screen kit: entries parse, seats are real, plans and the bar match."""

from __future__ import annotations

from pathlib import Path

from tests.wfe import campaign

REPO = Path(__file__).resolve().parents[2]

PLANS = REPO / "tests/wfe/plans"


def test_both_fast_seat_plans_expand_to_rows():
    baseline = campaign.expand_matrix(
        PLANS / "s8_fast_incumbent_baseline_20261029.yaml", 1, tier="screen"
    )
    assert baseline and {row["workspace"] for row in baseline} == {"tools-specialist::fast"}
    assert {row["arm_role"] for row in baseline} == {"incumbent"}
    assert {campaign.row_model(row) for row in baseline} == {"gemma4:e4b-it-qat-ctx8k"}
    screen = campaign.expand_matrix(PLANS / "s8_lfm3_fast_screen_20261029.yaml", 1, tier="screen")
    assert screen and {row["workspace"] for row in screen} == {"tools-specialist::fast"}
    assert {row["arm_role"] for row in screen} == {"incumbent", "challenger"}
    assert {campaign.row_model(row) for row in screen} == {
        "gemma4:e4b-it-qat-ctx8k",
        "lfm3:1.7b-qad-q4_0-ctx8k",
        "hf.co/unsloth/NVIDIA-Nemotron-3.5-Bolt-E4B-GGUF:UD-Q4_K_XL-ctx8k",
    }
    assert {row["suite"] for row in baseline + screen} == {"tools_specialist_production"}
    assert {row["tool_mode"] for row in baseline + screen} == {"production"}
