"""Seed upsert: an unchanged Portal preset is not written, a changed field is updated
in place, and a preset Portal did not create is left untouched."""

from __future__ import annotations

import scripts.openwebui_init as owi

DESIRED = {
    "id": "dailydriver",
    "name": "Daily Driver",
    "base_model_id": "auto",
    "meta": {
        "description": "Portal persona: Daily Driver",
        "profile_image_url": "",
        "toolIds": ["server:mcp:portal_code", "server:mcp:portal_documents"],
        "tags": [{"name": "general"}],
    },
    "params": {
        "system": "You are Portal's daily driver — a fast, capable assistant for everyday",
        "model": "auto",
    },
    "access_grants": [],
}


def _live(**over) -> dict:
    row = {
        "id": DESIRED["id"],
        "name": DESIRED["name"],
        "base_model_id": DESIRED["base_model_id"],
        "meta": {
            "description": "Portal persona: Daily Driver",
            "profile_image_url": "/api/v1/files/user-avatar/content",
            "toolIds": ["server:mcp:portal_documents", "server:mcp:portal_code"],
            "tags": [{"name": "general"}],
            "knowledge": [{"id": "user-kb"}],
        },
        "params": {**DESIRED["params"], "temperature": 0.2},
        "access_grants": [],
    }
    row.update(over)
    return row


def test_unchanged_portal_preset_is_not_written():
    actions = dict(owi.persona_seed_actions([DESIRED], {"dailydriver": _live()}, set()))
    assert actions["dailydriver"] == "skip"


def test_changed_system_prompt_is_an_in_place_update():
    live = _live()
    live["params"] = {**live["params"], "system": "stale prompt"}
    actions = dict(owi.persona_seed_actions([DESIRED], {"dailydriver": live}, set()))
    assert actions["dailydriver"] == "update"
    body = owi.preset_write_body(DESIRED, live)
    assert body["params"]["system"] == DESIRED["params"]["system"]
    assert body["params"]["temperature"] == 0.2  # user sampling survives the update
    assert body["meta"]["knowledge"] == [{"id": "user-kb"}]
    assert body["meta"]["profile_image_url"] == "/api/v1/files/user-avatar/content"
    assert "is_active" not in body


def test_foreign_preset_is_not_written():
    live = _live()
    live["meta"] = {**live["meta"], "description": "My own daily driver"}
    live["params"] = {**live["params"], "system": "stale prompt"}
    actions = dict(owi.persona_seed_actions([DESIRED], {"dailydriver": live}, set()))
    assert actions["dailydriver"] == "foreign"


def test_retired_portal_persona_is_reported_and_deleted_only_when_forced():
    stale = _live()
    stale["id"] = "oldpersona"
    kept = dict(owi.persona_seed_actions([DESIRED], {"oldpersona": stale}, set()))
    forced = dict(owi.persona_seed_actions([DESIRED], {"oldpersona": stale}, set(), force=True))
    assert kept["oldpersona"] == "retired"
    assert forced["oldpersona"] == "delete"
    assert kept["dailydriver"] == "create"


def test_workspace_unchanged_skips_and_a_tool_change_updates():
    desired = {
        "id": "auto",
        "name": "Portal Auto",
        "base_model_id": None,
        "meta": {"description": "Portal Auto", "toolIds": ["server:mcp:portal_documents"]},
        "params": {"system": "route", "model": "auto"},
        "access_grants": [],
    }
    live = {
        "id": "auto",
        "name": "Portal Auto",
        "base_model_id": None,
        "meta": {"description": "Portal Auto", "toolIds": ["server:mcp:portal_documents"]},
        "params": {"system": "route", "model": "auto", "temperature": 0.4},
        "access_grants": [],
    }
    assert (
        owi.workspace_seed_action(desired, live, exists=True, force=False, record_readable=True)
        == "skip"
    )
    changed = {
        **live,
        "meta": {**live["meta"], "toolIds": []},
    }
    assert (
        owi.workspace_seed_action(desired, changed, exists=True, force=False, record_readable=True)
        == "update"
    )
    assert (
        owi.workspace_seed_action(desired, live, exists=True, force=True, record_readable=True)
        == "reseed"
    )
