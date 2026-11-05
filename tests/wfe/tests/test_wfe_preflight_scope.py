"""The tool-surface preflight gates row-building commands only (readiness pass 5, 2026-11-05):
`--status` / `--rescore` carry no --plan, the default workloads.yaml names auto-compliance,
and the gate refused them with exit 4 for a workspace the campaign never touched."""

import sys

import pytest

from tests.wfe import campaign


def _refuse(_plan):
    raise campaign.GateRefused("tool surface preflight: FAIL (test)")


@pytest.mark.parametrize("flag", ["--status", "--verify-complete", "--health"])
def test_read_only_views_skip_the_plan_preflight(monkeypatch, flag):
    monkeypatch.setattr(campaign, "_realuse_tool_preflight", _refuse)
    monkeypatch.setattr(sys, "argv", ["campaign", "--campaign-id", "c", flag])
    _, args = campaign._parse_args()
    assert campaign._is_inspect_only(args)


def test_rescore_runs_before_the_preflight(monkeypatch):
    monkeypatch.setattr(campaign, "_realuse_tool_preflight", _refuse)
    monkeypatch.setattr(campaign, "_cmd_rescore", lambda args: 0)
    monkeypatch.setattr(sys, "argv", ["campaign", "--rescore", "d", "--campaign-id", "c"])
    assert campaign.main() == 0


def test_row_building_commands_are_still_gated(monkeypatch):
    monkeypatch.setattr(campaign, "_realuse_tool_preflight", _refuse)
    monkeypatch.setattr(sys, "argv", ["campaign", "--list-arms"])
    with pytest.raises(campaign.GateRefused):
        campaign.main()
