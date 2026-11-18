"""Technical basis reaches every requirement it exists for, and no reading runs truncated.

Covers ``requirement_anchor.requirements_named`` / ``anchor_rationale_document``
(a separate Technical Rationale placed by its own headings),
``reading_assembly``'s fixed body dropping a TR once it travels per requirement,
``materialize_regulatory_corpus.capture_registered``'s hash guard, and
``sweep.window_fit`` (Ollama truncates an oversized prompt silently).
"""

from __future__ import annotations

from portal.modules.compliance.core.requirement_anchor import (
    attachment_targets_named,
    requirements_named,
)
from portal.modules.compliance.core.sweep import window_fit


def test_headings_name_requirements_and_attachment_sections() -> None:
    assert requirements_named("Rationale for Requirement R4") == ({"R4"}, None)
    assert requirements_named("General Considerations for Requirements R1 and R2")[0] == {
        "R1",
        "R2",
    }
    assert requirements_named("Rational for Requirement 1 and Requirement 2")[0] == {"R1", "R2"}
    assert requirements_named("Attachment 1 Section 6 Part 6.3 - Detecting") == (set(), ("1", "6"))
    # a standard's name is not a requirement, and a heading without the word places nothing
    assert requirements_named("Technical Rationale for Reliability Standard CIP-010-3") == (
        set(),
        None,
    )
    assert requirements_named("Preface") == (set(), None)


def test_window_fit_refuses_what_ollama_would_truncate() -> None:
    # CIP-003-8 R1: 155,333 bytes, counted at 16,387 tokens after silent truncation
    assert window_fit(155_333, 32_768, 3_072)["fits"] is False
    assert window_fit(155_333, 65_536, 3_072)["fits"] is True
    # CIP-007-6 R5 Part 5.1: 90,894 bytes, 25,160 real tokens — fits
    assert window_fit(90_894, 32_768, 3_072)["fits"] is True


def test_attachment_grammars_are_parsed_not_guessed() -> None:
    assert attachment_targets_named("Requirement R2, Attachment 1, Section 3 - ESPs") == {
        "attachment": "1",
        "section": "3",
        "part": None,
        "impact": None,
    }
    assert attachment_targets_named("Attachment 1, Criterion 2.1")["part"] == "2.1"
    assert attachment_targets_named("Medium Impact Rating (M)") == {
        "attachment": "1",
        "section": "2",
        "part": None,
        "impact": "medium impact rating",
    }
    assert attachment_targets_named("Requirement R2, Attachment 1")["attachment"] == "1"
    # no attachment named → this route stays out of it
    assert attachment_targets_named("Guidelines and Technical Basis")["attachment"] is None
    assert (
        attachment_targets_named("Requirement R2: identify BES Cyber Systems")["attachment"] is None
    )
