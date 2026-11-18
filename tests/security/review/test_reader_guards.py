from __future__ import annotations

import pytest

from portal.modules.security.core.review.reader import assert_prompt_label_free
from portal.modules.security.core.review.wall import WallViolation


def test_prompt_label_guard_catches_seeded_identifier() -> None:
    with pytest.raises(WallViolation, match="label identifier"):
        assert_prompt_label_free("event payload contains attack_id=T1110")
