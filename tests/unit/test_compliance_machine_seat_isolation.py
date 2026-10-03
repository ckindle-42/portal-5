"""Compliance machine calls never land in a conversational lane.

The pipeline appends a workspace's ``system_prompt_append`` and offers its
tools to every request addressed to it. The sweep's map_read / reduce and the
batch reader address the reading TAG, which resolves to the first workspace
carrying it; when that was compliance-reading, every strict-JSON map reading
carried its conversational persona and 19 tool schemas (PIPELINE_ALIGNMENT_V1
§12). Every tag or workspace a
compliance machine call addresses must resolve to a compliance workspace with
no persona and no workspace tools.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from portal.platform.inference import model_addressing

_REPO = Path(__file__).resolve().parents[2]


def _machine_addresses() -> list[str]:
    ws = model_addressing.workspaces()
    addresses = [
        ws["compliance-reading"]["model_hint"],  # sweep map_read / reduce, reader.read
        ws["compliance-reading-overflow"]["model_hint"],  # map_read overflow_model
    ]
    council = yaml.safe_load((_REPO / "config/compliance/council.yaml").read_text()) or {}
    addresses += [seat["workspace"] for seat in council.get("seats") or [] if seat.get("workspace")]
    return addresses


@pytest.mark.parametrize("address", _machine_addresses())
def test_machine_address_lands_in_a_bare_compliance_workspace(address: str) -> None:
    workspace_id = model_addressing.workspace_id_for_model(address)
    cfg = model_addressing.workspaces()[workspace_id]
    assert cfg.get("module") == "compliance", workspace_id
    assert not cfg.get("system_prompt_append"), f"{workspace_id} carries a persona"
    assert not cfg.get("tools"), f"{workspace_id} offers workspace tools"


def test_reading_tag_does_not_resolve_to_the_conversational_lane() -> None:
    hint = model_addressing.workspaces()["compliance-reading"]["model_hint"]
    assert model_addressing.workspace_id_for_model(hint) == "compliance-mapping"


def test_reading_seat_cannot_write_and_review_seat_owns_the_write_surface() -> None:
    """A6 (READING_TRUTH_V1 P6): the review-decision and correction tools leave
    the reading seat — the model that reads for an analyst must not be able to
    change the store the next turn reads. compliance_note stays by design
    (dialogue-as-source); compliance_review_list stays (evidence reading)."""
    workspaces = model_addressing.workspaces()
    reading = set(workspaces["compliance-reading"].get("tools") or [])
    review = set(workspaces["compliance-review"].get("tools") or [])
    moved = {"compliance_review_decide", "compliance_review_decide_batch", "compliance_correct"}
    assert not moved & reading, f"reading seat still offers write tools: {moved & reading}"
    assert moved <= review, f"review workspace missing the write surface: {moved - review}"
    assert "compliance_review_list" in review
    assert "compliance_note" in reading
    assert workspaces["compliance-review"].get("module") == "compliance"
