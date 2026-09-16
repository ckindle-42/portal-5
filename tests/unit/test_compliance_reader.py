"""The reader's conditions, and the conversation corpus (BILATERAL_CORPUS_V1 P6).

No model is called here. What is tested is everything AROUND the reading: that
the material handed over is complete and labelled, that citations are resolved
and reported with what they are, that a fabricated citation is caught and named,
that an answer is retained and contestable, that it is superseded when its
revision moves, and that an operator note outranks it.

There is deliberately no test asserting what a reading should CONTAIN. A test
that fixed the shape of an answer would be the schema this phase exists to not
build.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from portal.modules.compliance.core import reader
from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit, store_capture
from portal.modules.compliance.core.models import SourceDocument
from portal.modules.compliance.core.notes import write_note
from portal.modules.compliance.core.repository import Repository


def _capture(path: Path, rows: list[tuple[str, str]]) -> CapturedDocument:
    units: list[CapturedUnit] = []
    buf: list[str] = []
    cursor = 0
    for ordinal, (heading, body) in enumerate(rows):
        piece = body + "\n"
        units.append(
            CapturedUnit(
                ordinal=ordinal,
                unit_kind="prose",
                heading_path=heading,
                title=heading,
                page_start=1,
                page_end=1,
                char_start=cursor,
                char_end=cursor + len(piece),
                text=piece,
            )
        )
        buf.append(piece)
        cursor += len(piece)
    return CapturedDocument(
        path=path,
        page_count=1,
        full_text="".join(buf),
        units=units,
        reader_strings=tuple(b for _h, b in rows),
    )


def _document(
    repo: Repository, logical_id: str, jurisdiction: str, kind: str, rows: list[tuple[str, str]]
) -> str:
    repo.upsert_source_document(
        SourceDocument(
            logical_id=logical_id,
            title=logical_id,
            issuer="x",
            source_kind=kind,
            jurisdiction=jurisdiction,
        )
    )
    revision = repo.add_document_revision(logical_id, f"/docs/{logical_id}", logical_id.encode())
    store_capture(repo, revision.revision_id, _capture(Path(f"/docs/{logical_id}"), rows))
    return revision.revision_id


@pytest.fixture
def store(tmp_path: Path) -> Repository:
    repo = Repository(tmp_path / "store.db")
    _document(
        repo,
        "NERC/CIP-007-6",
        "US",
        "regulatory_standard",
        [
            (
                "B. Requirements and Measures",
                "R2. Each Responsible Entity shall implement one or more documented "
                "processes: at least once every 35 calendar days, evaluate security patches.",
            ),
            ("A. Introduction > 6. Background:", "Bulleted items are linked with 'or'."),
            ("Version History", "Version 5 revised to use RBS Template."),
            (
                "Guidelines and Technical Basis > Requirement R2:",
                "The intent is to know, track and mitigate. It is not strictly an "
                '"install every security patch" requirement.',
            ),
        ],
    )
    _document(
        repo,
        "LSPG/patching",
        "internal",
        "procedure",
        [("3 Patching", "The OT team evaluates patches once every 30 calendar days.")],
    )
    yield repo
    repo.close()


def _section(repo: Repository, needle: str) -> str:
    from portal.modules.compliance.core.section_index import build_plan

    for jurisdiction in ("US", "internal"):
        for unit in build_plan(repo, jurisdiction=jurisdiction).units:
            if needle in unit.text:
                return unit.section_id
    raise AssertionError(f"no section containing {needle!r}")


class TestTheMaterialHandedOver:
    def test_every_component_is_rendered_with_its_own_label(self, store: Repository) -> None:
        from portal.modules.compliance.core.reading_assembly import assemble

        context = assemble(store, "CIP-007-6 R2")
        material = reader._render_material(context)
        assert "## requirement" in material
        assert "## technical_basis" in material
        assert "not strictly an" in material

    def test_a_budget_omission_is_stated_to_the_model(self, store: Repository) -> None:
        from portal.modules.compliance.core.reading_assembly import assemble

        context = assemble(store, "CIP-007-6 R2", budget_tokens=1)
        material = reader._render_material(context)
        assert "omitted for budget — you have NOT seen these" in material

    def test_operator_notes_travel_with_the_material(self, store: Repository) -> None:
        from portal.modules.compliance.core.reading_assembly import assemble

        write_note(
            store,
            subject_ref="CIP-007-6 R2",
            body="We chose 30 days deliberately; our change window is monthly.",
            kind="intentional_strictness",
            author="chris",
        )
        context = assemble(store, "CIP-007-6 R2")
        from portal.modules.compliance.core.notes import notes_for

        context["operator_notes"] = notes_for(store, "CIP-007-6 R2")
        material = reader._render_material(context)
        assert "operator notes — the operator's own recorded decisions" in material
        assert "change window is monthly" in material

    def test_the_prompt_imposes_no_output_shape(self) -> None:
        prompt = reader.SYSTEM_PROMPT.lower()
        for forbidden in ("json", "schema", "field", "enum", "step 1", "first,", "format:"):
            assert forbidden not in prompt, forbidden
        assert "prose" in prompt


class TestCitationsAreResolvedAndLabelled:
    def test_a_real_citation_resolves_and_says_what_it_is(self, store: Repository) -> None:
        section_id = _section(store, "35 calendar days")
        out = reader.verify_citations(store, f"The Part requires evaluation [{section_id}].")
        (entry,) = out["citations"]
        assert entry["resolved"] is True
        assert entry["jurisdiction"] == "US"
        assert "regulatory" in entry["resolves_to"]
        assert out["unresolvable"] == []

    def test_the_technical_basis_is_labelled_as_interpretive_not_suppressed(
        self, store: Repository
    ) -> None:
        section_id = _section(store, "not strictly an")
        (entry,) = reader.verify_citations(store, f"[{section_id}]")["citations"]
        assert entry["resolved"] is True
        assert "Technical Basis" in entry["resolves_to"]

    def test_an_operator_section_is_labelled_as_the_operators(self, store: Repository) -> None:
        section_id = _section(store, "once every 30 calendar days")
        (entry,) = reader.verify_citations(store, f"[{section_id}]")["citations"]
        assert entry["jurisdiction"] == "internal"
        assert entry["resolves_to"].startswith("operator document")

    def test_an_operator_note_is_labelled_as_the_operators_own_decision(
        self, store: Repository
    ) -> None:
        note = write_note(
            store, subject_ref="CIP-007-6 R2", body="We chose 30 days.", kind="decision"
        )
        (entry,) = reader.verify_citations(store, f"[{note['section_id']}]")["citations"]
        assert "operator note" in entry["resolves_to"]

    def test_a_fabricated_citation_is_caught_and_named(self, store: Repository) -> None:
        fake = "csection-" + "0" * 20
        out = reader.verify_citations(store, f"as stated in [{fake}]")
        assert out["unresolvable"] == [fake]
        (entry,) = out["citations"]
        assert entry["resolved"] is False
        assert "does not resolve" in entry["detail"]

    def test_a_split_sub_unit_resolves_to_its_parent(self, store: Repository) -> None:
        section_id = _section(store, "35 calendar days")
        (entry,) = reader.verify_citations(store, f"[{section_id}#3]")["citations"]
        assert entry["resolved"] is True

    def test_nothing_is_disqualified(self, store: Repository) -> None:
        section_id = _section(store, "not strictly an")
        out = reader.verify_citations(store, f"[{section_id}]")
        assert "disqualified" in out["note"]
        assert all("eligible" not in str(c) for c in out["citations"])


class TestQuantityClaims:
    def test_a_quantity_present_in_the_cited_text_checks_out(self, store: Repository) -> None:
        section_id = _section(store, "35 calendar days")
        out = reader.verify_citations(store, f"It is every 35 calendar days [{section_id}].")
        assert out["quantities_not_in_cited_text"] == []

    def test_a_quantity_absent_from_the_cited_text_is_named(self, store: Repository) -> None:
        section_id = _section(store, "35 calendar days")
        out = reader.verify_citations(store, f"It is every 90 calendar days [{section_id}].")
        assert out["quantities_not_in_cited_text"] == ["90 calendar days"]


class TestTheConversationIsACorpus:
    def _answer(self, store: Repository, question: str = "What is R2 for?") -> dict:
        from portal.modules.compliance.core.reading_assembly import assemble

        section_id = _section(store, "not strictly an")
        context = assemble(store, "CIP-007-6 R2")
        payload = {
            "question": question,
            "ref": "CIP-007-6 R2",
            "answer": f"It is about knowing and tracking vulnerabilities [{section_id}].",
            "model": "stub-seat",
            "num_ctx": 32768,
            "latency": {"elapsed_s": 4.2, "eval_count": 300, "prompt_bytes": 9000},
            "reasoning_effort": "False",
            "verification": reader.verify_citations(store, f"[{section_id}]"),
        }
        payload["answer_id"] = reader.store_answer(store, payload, context)
        return payload

    def test_an_answer_is_retained_with_its_citations_and_latency(self, store: Repository) -> None:
        payload = self._answer(store)
        (stored,) = reader.answers_for(store, "CIP-007-6 R2")
        assert stored["answer_id"] == payload["answer_id"]
        assert stored["model"] == "stub-seat"
        assert stored["elapsed_s"] == 4.2
        assert stored["eval_count"] == 300
        assert len(stored["citations"]) == 1
        assert stored["citations"][0]["resolved"] == 1

    def test_a_stored_answer_is_never_presented_as_a_fact(self, store: Repository) -> None:
        self._answer(store)
        (stored,) = reader.answers_for(store, "CIP-007-6 R2")
        assert "one analyst's notes" in stored["standing"]

    def test_an_answer_is_retrievable_as_a_derived_source(self, store: Repository) -> None:
        from portal.modules.compliance.core.section_index import build_plan

        self._answer(store)
        plan = build_plan(store, jurisdiction="derived")
        assert plan.kb_id == "conversation"
        assert plan.units, "a stored answer must be projectable like any other source"

    def test_an_operator_note_outranks_a_stored_answer(self, store: Repository) -> None:
        self._answer(store)
        write_note(store, subject_ref="CIP-007-6 R2", body="Actually we decided otherwise.")
        (stored,) = reader.answers_for(store, "CIP-007-6 R2")
        assert "outranks it" in stored["standing"]

    def test_an_answer_is_superseded_when_a_cited_revision_moves(self, store: Repository) -> None:
        payload = self._answer(store)
        revision_id = payload["verification"]["citations"][0]["revision_id"]
        moved = reader.supersede_answers_for_revisions(store, [revision_id])
        assert moved == [payload["answer_id"]]
        (stored,) = reader.answers_for(store, "CIP-007-6 R2")
        assert stored["superseded_at"]
        assert "SUPERSEDED" in stored["standing"]

    def test_a_correction_is_kept_as_a_note_and_both_remain(self, store: Repository) -> None:
        payload = self._answer(store)
        note = reader.record_correction(
            store, payload["answer_id"], "The 35 days is a ceiling, not a target.", author="chris"
        )
        (stored,) = reader.answers_for(store, "CIP-007-6 R2")
        assert stored["correction_of"] == note["note_id"]
        assert stored["answer"]  # the answer is not rewritten


class TestStandingQuestions:
    def test_a_standing_question_is_recorded_and_listed(self, store: Repository) -> None:
        reader.add_standing_question(store, "Are we stricter than we need to be?", "CIP-007-6 R2")
        questions = reader.standing_questions(store, "CIP-007-6 R2")
        assert [q["question"] for q in questions] == ["Are we stricter than we need to be?"]

    def test_recording_the_same_question_twice_is_idempotent(self, store: Repository) -> None:
        reader.add_standing_question(store, "What would an auditor ask for?", "CIP-007-6 R2")
        reader.add_standing_question(store, "What would an auditor ask for?", "CIP-007-6 R2")
        assert len(reader.standing_questions(store, "CIP-007-6 R2")) == 1

    def test_a_question_with_no_subject_applies_everywhere(self, store: Repository) -> None:
        reader.add_standing_question(store, "What changed?")
        assert reader.standing_questions(store, "CIP-007-6 R2")


class TestTheDeletedComparator:
    def test_the_quantity_comparator_is_gone(self) -> None:
        from portal.modules.compliance.core import reading

        assert not hasattr(reading, "_quantity_direction")
        assert "deleted with its cause" in reading._QUANTITY_DIRECTION_DELETED


class TestTheTransportStatesItsWindow:
    def test_num_ctx_and_keep_alive_reach_ollama(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from portal.modules.compliance.core import reading_transport

        seen: dict = {}

        def _capture_post(payload, timeout):  # noqa: ANN001, ANN202
            seen.update(payload)
            return {"message": {"content": "ok"}, "eval_count": 7, "load_duration": 1_000_000_000}

        monkeypatch.setattr(reading_transport, "_post", _capture_post)
        result = reading_transport.chat("m", "sys", "user", num_ctx=24576, keep_alive="5m")
        assert seen["options"]["num_ctx"] == 24576
        assert seen["keep_alive"] == "5m"
        assert result["num_ctx"] == 24576
        assert result["load_duration_s"] == 1.0
        assert result["prompt_bytes"] == len(b"sys") + len(b"user")


class TestTheWindowIsSizedFromMeasurement:
    def test_chars_per_token_errs_high_not_low(self) -> None:
        from portal.modules.compliance.core.reading_assembly import CHARS_PER_TOKEN

        # measured on the live assembly against the runner's own
        # prompt_eval_count: 2.16 chars/token. The constant must be at or below
        # that, because under-estimating chars-per-token means OVER-reserving
        # the window, and the failure that matters is the other direction —
        # a window too small silently truncates the material.
        assert CHARS_PER_TOKEN <= 2.16

    def test_a_context_overflow_is_reported_not_swallowed(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from portal.modules.compliance.core import reading_transport

        def _fake_post(payload, timeout):  # noqa: ANN001, ANN202
            window = payload["options"]["num_ctx"]
            return {
                "message": {"content": "an answer"},
                "prompt_eval_count": window - 10,
                "eval_count": 100,
            }

        monkeypatch.setattr(reading_transport, "_post", _fake_post)
        payload = reader.read(
            store, "q", "CIP-007-6 R2", model="stub", answer_tokens=100, store=False
        )
        fit = payload["context_fit"]
        assert fit["overflowed"] is True
        assert fit["headroom_tokens"] < 0
        assert fit["actual_prompt_tokens"] > 0

    def test_a_comfortable_fit_reports_its_headroom(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from portal.modules.compliance.core import reading_transport

        monkeypatch.setattr(
            reading_transport,
            "_post",
            lambda payload, timeout: {
                "message": {"content": "an answer"},
                "prompt_eval_count": 900,
                "eval_count": 40,
            },
        )
        fit = reader.read(store, "q", "CIP-007-6 R2", model="stub", answer_tokens=100, store=False)[
            "context_fit"
        ]
        assert fit["overflowed"] is False
        assert fit["headroom_tokens"] > 0
        assert fit["chars_per_token_observed"] is not None


class TestPromptOrderIsCacheable:
    def test_the_material_comes_before_the_question(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Every turn ships the same neighbourhood. With the question first the
        prefix differs at token ~20 and the runner re-prefills 30k tokens —
        measured at 281 s per exchange on this corpus. Material first makes the
        prefix byte-identical across turns."""
        from portal.modules.compliance.core import reading_transport

        seen: dict = {}

        def _capture(payload, timeout):  # noqa: ANN001, ANN202
            seen["user"] = payload["messages"][1]["content"]
            return {"message": {"content": "ok"}, "prompt_eval_count": 10, "eval_count": 2}

        monkeypatch.setattr(reading_transport, "_post", _capture)
        reader.read(store, "WHAT-IS-THE-QUESTION", "CIP-007-6 R2", model="stub", store=False)
        user = seen["user"]
        assert user.index("WHAT-IS-THE-QUESTION") > user.index("## requirement")
        assert user.rstrip().endswith("WHAT-IS-THE-QUESTION")

    def test_two_questions_share_a_byte_identical_prefix(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from portal.modules.compliance.core import reading_transport

        prompts: list[str] = []

        def _capture(payload, timeout):  # noqa: ANN001, ANN202
            prompts.append(payload["messages"][1]["content"])
            return {"message": {"content": "ok"}, "prompt_eval_count": 10, "eval_count": 2}

        monkeypatch.setattr(reading_transport, "_post", _capture)
        for question in ("first question", "an entirely different second question"):
            reader.read(store, question, "CIP-007-6 R2", model="stub", store=False)
        shared = len(os.path.commonprefix(prompts))
        assert shared > 0.9 * min(len(p) for p in prompts)


class TestCitationSpelling:
    """A correct citation written with a typographic dash is still a correct
    citation. Found in the P6.8 seat probe: granite4.1 cited nine sections and
    scored zero because it used U+2011."""

    @pytest.mark.parametrize("dash", ["‐", "‑", "‒", "–", "—", "−"])
    def test_a_typographic_dash_still_resolves(self, store: Repository, dash: str) -> None:
        section_id = _section(store, "35 calendar days")
        spelled = section_id.replace("-", dash, 1)
        out = reader.verify_citations(store, f"as required [{spelled}]")
        assert out["unresolvable"] == []
        assert out["citations"][0]["resolved"] is True

    def test_an_ascii_id_is_unaffected(self, store: Repository) -> None:
        section_id = _section(store, "35 calendar days")
        out = reader.verify_citations(store, f"[{section_id}]")
        assert out["citations"][0]["cited_ref"] == section_id


class TestQuantityAttribution:
    """Found by hand in the P6.8 probe, then reproduced here: three of four
    seats wrote "the operator's procedure evaluates every thirty calendar days"
    and cited the section that says thirty-five. The number was real — it came
    from an operator note elsewhere in the packet — so checking against the
    union of everything cited passed all three."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("thirty-five (35) calendar days", ("35", "day")),
            ("thirty calendar days", ("30", "day")),
            ("35 calendar days", ("35", "day")),
            ("three calendar years", ("3", "year")),
            ("ninety days", ("90", "day")),
        ],
    )
    def test_a_compound_number_is_not_read_as_its_own_tail(
        self, text: str, expected: tuple[str, str]
    ) -> None:
        match = reader._QUANTITY_RE.search(text)
        assert match is not None
        assert reader._normalise_quantity(match) == expected

    def test_thirty_five_is_never_read_as_five(self) -> None:
        match = reader._QUANTITY_RE.search("thirty-five calendar days")
        assert reader._normalise_quantity(match)[0] == "35"

    def test_a_number_pinned_to_the_wrong_section_is_flagged(self, store: Repository) -> None:
        regulatory = _section(store, "35 calendar days")
        note = write_note(store, subject_ref="CIP-007-6 R2", body="We evaluate every 30 days.")
        out = reader.verify_citations(
            store,
            f"The standard requires evaluation every thirty calendar days [{regulatory}], "
            f"which is what we do [{note['section_id']}].",
        )
        assert [m["claim"] for m in out["misattributed_quantities"]] == ["thirty calendar days"]

    def test_a_number_in_no_source_at_all_is_reported_as_unsupported(
        self, store: Repository
    ) -> None:
        regulatory = _section(store, "35 calendar days")
        out = reader.verify_citations(
            store, f"The standard requires evaluation every ninety days [{regulatory}]."
        )
        assert out["quantities_not_in_cited_text"] == ["ninety days"]
        assert out["misattributed_quantities"] == []

    def test_a_number_the_cited_section_states_is_not_flagged(self, store: Repository) -> None:
        regulatory = _section(store, "35 calendar days")
        out = reader.verify_citations(
            store, f"The standard requires evaluation every 35 calendar days [{regulatory}]."
        )
        assert out["misattributed_quantities"] == []

    def test_a_parenthesised_spelling_still_counts_as_stated(self) -> None:
        assert reader._quantity_in(
            "35", "day", "At least once every thirty-five (35) calendar days"
        )

    def test_a_claim_with_no_citation_nearby_is_unattributed_not_misattributed(
        self, store: Repository
    ) -> None:
        regulatory = _section(store, "35 calendar days")
        filler = " ".join(["padding"] * 120)
        out = reader.verify_citations(store, f"[{regulatory}] {filler} so it is 90 days.")
        assert out["misattributed_quantities"] == []
        assert any(q["unattributed"] for q in out["quantities"])


class TestAnEmptyAnswerIsAFailure:
    """Measured in P6.7: with reasoning on, the seat spent its whole budget in
    `thinking` and returned zero characters. An empty answer must be reported as
    a failed reading, not returned as a terse one."""

    def test_a_budget_exhausted_by_reasoning_is_named(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from portal.modules.compliance.core import reading_transport

        monkeypatch.setattr(
            reading_transport,
            "_post",
            lambda payload, timeout: {
                "message": {"content": "", "thinking": "x" * 6000},
                "prompt_eval_count": 900,
                "eval_count": 1600,
            },
        )
        payload = reader.read(
            store, "q", "CIP-007-6 R2", model="stub", answer_tokens=1600, store=False
        )
        assert payload["failed"] is True
        assert "whole 1600-token budget" in payload["failure"]
        assert "reasoning" in payload["failure"]

    def test_a_real_answer_is_not_marked_failed(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from portal.modules.compliance.core import reading_transport

        monkeypatch.setattr(
            reading_transport,
            "_post",
            lambda payload, timeout: {
                "message": {"content": "a real answer"},
                "prompt_eval_count": 900,
                "eval_count": 40,
            },
        )
        payload = reader.read(store, "q", "CIP-007-6 R2", model="stub", store=False)
        assert payload["failed"] is False
        assert payload["failure"] == ""
