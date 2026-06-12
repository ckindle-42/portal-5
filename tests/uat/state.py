"""Portal 5 UAT — mutable per-run state (TASK_UAT_MODULARIZE_V1 phase A).

All cross-module access is attribute-form (``state._ROUTING_LOG`` etc.) so
rebinding (e.g. ``state._run_folder_id = ...``) is visible everywhere and
monkeypatch-safe. Never ``from tests.uat.state import <name>``.
"""

# Routing telemetry — appended per test, written to UAT_RESULTS.md at end of run.
# Each entry: {test_id, name, section, workspace, intended, actual, matched, tier_mismatch}
_ROUTING_LOG: list[dict] = []

# Chat IDs created in the current run. Populated by owui_create_chat() so that
# the post-run archival step can move all chats to a dated UAT subfolder.
_run_chat_ids: list[str] = []

# Archival state: set at run start, used by the SIGINT handler to archive on interrupt.
_run_folder_id: str | None = None   # UAT/{date} folder ID, resolved before first test
_archive_token: str | None = None   # OWUI token for use in signal handler
