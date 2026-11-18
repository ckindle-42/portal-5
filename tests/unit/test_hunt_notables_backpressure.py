from __future__ import annotations

import pytest

from portal.modules.security.core.hunt.judge import (
    ThrottleBudgetExceededError,
    judge_cell,
)
from portal.modules.security.core.hunt.notables.cards import (
    ModelAnswer,
    SourceCard,
    ask_model,
)
from portal.modules.security.core.hunt.notables.run import (
    _card_failure_counts,
    _check_http_error_rate,
)


def test_a_throttled_request_is_not_a_generic_request_failure():
    class _Throttled:
        def complete(self, **request: object) -> dict[str, object]:
            del request
            raise ThrottleBudgetExceededError("spent")

    answer = ask_model(_Throttled(), "seat", "prompt")
    assert answer.error == "throttled"
    result = judge_cell(_Throttled(), model="seat", prompt="prompt")
    assert result.p_yes is None
    assert result.reason == "throttled"


def test_card_http_errors_are_separate_from_unparsed_and_over_threshold_fails():
    cards = [
        SourceCard(
            index="ix",
            sourcetype="st",
            kind="other",
            roles={},
            understood=False,
            reason="model_http_error",
            fmt="json",
            coverage=0.0,
            fields=(),
            sample={},
            facts={},
            model={},
            cache_key="http",
        ),
        SourceCard(
            index="ix",
            sourcetype="st",
            kind="other",
            roles={},
            understood=False,
            reason="unparseable_answer",
            fmt="json",
            coverage=0.0,
            fields=(),
            sample={},
            facts={},
            model={},
            cache_key="parse",
        ),
    ]
    answers = {
        "http": (ModelAnswer("", 0.0, "", None, "http_error"), 1, False),
        "parse": (ModelAnswer("nonsense", 0.0, "seat", None, None), 1, False),
    }

    assert _card_failure_counts(cards, answers) == (1, 1)
    _check_http_error_rate("cards", 1, 5, "seat", unparsed=1)
    with pytest.raises(RuntimeError, match="model_http_errors=2/5.*unparsed=1"):
        _check_http_error_rate("cards", 2, 5, "seat", unparsed=1)
