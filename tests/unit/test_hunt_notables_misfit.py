from __future__ import annotations

from portal.modules.security.core.hunt.notables.behaviours import (
    line_shape,
)


def test_line_shape_normalises_values_and_keeps_punctuation() -> None:
    assert line_shape("pid 1234 started") == "aaa 9999 aaaaaaa"
    assert line_shape("bash: 196: Bad file descriptor") == line_shape(
        "bash: 207: Bad file descriptor"
    )
    assert line_shape("bash: 196: Bad file descriptor") != line_shape("bash: 196: Bad gateway")
    assert line_shape("  ") == ""
