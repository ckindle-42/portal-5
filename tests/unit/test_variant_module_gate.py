"""A variant's own module gates that variant; the engine stays up."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from portal.platform.inference.config import (
    WorkspaceSpec,
)


def test_unknown_variant_module_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown module"):
        WorkspaceSpec.model_validate(
            {
                "name": "Media",
                "description": "bad variant module",
                "module": "media",
                "variants": {"bad": {"module": "not-a-module"}},
            }
        )
