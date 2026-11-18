from __future__ import annotations

from portal.modules.security.core.hunt.notables.knowledge import (
    statement_has_content,
)


def test_statement_has_content_rejects_a_statement_that_is_only_roles_and_masks() -> None:
    assert statement_has_content("to * * * * * *") is False
    assert statement_has_content("actor *") is False
    assert statement_has_content("program sudo") is True
    assert statement_has_content("actor 0 did USER_START") is True
