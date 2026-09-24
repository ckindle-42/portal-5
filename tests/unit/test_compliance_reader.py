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

from portal.modules.compliance.core import reader, requirement_scope
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
        assert "NOT IN THIS PACKET" in material

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
        prompt, version, sha = reader.load_prompt()
        lowered = " ".join(prompt.lower().split())
        for forbidden in ("json", "schema", "field", "enum", "step 1", "first,", "format:"):
            assert forbidden not in lowered, forbidden
        assert "prose" in lowered
        # It is a versioned artifact, not a literal: both identifiers exist and
        # the sha is of the body, so an edit cannot pass as the same prompt.
        assert version != "undeclared" and len(sha) == 12

    def test_the_prompt_asks_for_the_work_the_reader_actually_does(self) -> None:
        """PROVE_CIP_007_V1 P1.2. The v1 prompt opened "in front of you" and
        asked for prose. It never said the model had tools, never said the
        opening material was a starting point, and never asked for the
        comparison a posture question needs — so a control contract had to FAIL
        a reading for behaviour the prompt had not requested."""
        prompt, _, _ = reader.load_prompt()
        # wrapping is incidental to prose; the claims are about the sentences
        lowered = " ".join(prompt.lower().split())
        # the tools, named
        for tool in (
            "compliance_requirement",
            "compliance_read",
            "compliance_links",
            "compliance_search",
            "compliance_timeline",
            "compliance_notes",
        ):
            assert tool in prompt, tool
        # references are not text
        assert "references" in lowered and "unread until you read it" in lowered
        # both sides
        assert "at least one operator section" in lowered
        # over-strictness as fact, not as a gap or a question
        assert "exceeding a requirement is permitted" in lowered
        assert "never a gap" in lowered
        # latitude the standard grants and the procedure narrowed
        assert "less latitude than nerc grants" in lowered
        # the GTB, citable but never duty text
        assert "never binding duty text" in lowered
        # declared omissions
        assert "a declared omission is acceptable" in lowered


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

    def test_a_correction_is_filed_against_the_requirement_the_answer_was_about(
        self, store: Repository
    ) -> None:
        """MODULE_COMPLETE_V1 §P3: the bridge. Filed under the answer id alone,
        a correction never reached the next reading of the requirement —
        populations pull notes by REQUIREMENT identity, and the two keys never
        met."""
        payload = self._answer(store)
        note = reader.record_correction(
            store, payload["answer_id"], "The 35 days is a ceiling, not a target."
        )
        # requirement-side address: the note is a population member of the ref
        population = requirement_scope.population(store, "CIP-007-6 R2")
        assert note["section_id"] in population["section_ids"]
        note_entry = population["sections"][note["section_id"]]
        assert note_entry["side"] == "operator_note"
        # answer-side address: the answer names its correction, the correction
        # names the answer, and both remain
        assert note["about_answer"] == payload["answer_id"]
        assert note["addresses"] == {
            "requirement_ref": "CIP-007-6 R2",
            "answer_id": payload["answer_id"],
            "bridged": True,
        }
        (stored,) = reader.answers_for(store, "CIP-007-6 R2")
        assert stored["correction_of"] == note["note_id"]
        assert "outranks it" in stored["standing"]

    def test_a_correction_to_an_answer_without_a_ref_cannot_bridge_and_says_so(
        self, store: Repository
    ) -> None:
        payload = self._answer(store)
        store._conn.execute(
            "UPDATE conversation_answers SET subject_ref = '' WHERE answer_id = ?",
            (payload["answer_id"],),
        )
        note = reader.record_correction(store, payload["answer_id"], "That is not ours.")
        assert note["addresses"]["bridged"] is False
        assert "names no requirement ref" in note["bridge"]
        # still filed, still addressable from the answer
        assert note["subject_ref"] == payload["answer_id"]


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

        def _capture_post(payload, timeout, dialect=None):  # noqa: ANN001, ANN202
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

        def _fake_post(payload, timeout, dialect=None):  # noqa: ANN001, ANN202
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
            lambda payload, timeout, dialect=None: {
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

        def _capture(payload, timeout, dialect=None):  # noqa: ANN001, ANN202
            seen["messages"] = payload["messages"]
            return {"message": {"content": "ok"}, "prompt_eval_count": 10, "eval_count": 2}

        monkeypatch.setattr(reading_transport, "_post", _capture)
        reader.read(
            store,
            "WHAT-IS-THE-QUESTION",
            "CIP-007-6 R2",
            model="stub",
            store=False,
            retain_run=False,
        )
        messages = seen["messages"]
        # WINDOW_AND_SEAT_V1 P1.3: the seed carries no text-bearing regulatory
        # component — the requirement text arrives once, through the recorded
        # bootstrap payloads that follow it, and the seed names what it has
        # NOT seen. The material-and-acquisition prefix still precedes the
        # question.
        assert "## requirement" not in messages[1]["content"]
        tool_names = [str(m.get("tool_name", "")) for m in messages if m.get("role") == "tool"]
        assert tool_names[:2] == ["compliance_requirement", "compliance_links"]
        requirement_payload = next(
            str(m.get("content", ""))
            for m in messages
            if m.get("role") == "tool" and m.get("tool_name") == "compliance_requirement"
        )
        assert '"components"' in requirement_payload
        # the question is the LAST thing said, so the material and the recorded
        # acquisition are a prefix that does not move between turns
        assert messages[-1]["content"].rstrip().endswith("WHAT-IS-THE-QUESTION")
        assert not any("WHAT-IS-THE-QUESTION" in str(m.get("content", "")) for m in messages[:-1])

    def test_two_questions_share_a_byte_identical_prefix(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from portal.modules.compliance.core import reading_transport

        prompts: list[str] = []

        def _capture(payload, timeout, dialect=None):  # noqa: ANN001, ANN202
            prompts.append("".join(str(m.get("content", "")) for m in payload["messages"][:-1]))
            return {"message": {"content": "ok"}, "prompt_eval_count": 10, "eval_count": 2}

        monkeypatch.setattr(reading_transport, "_post", _capture)
        for question in ("first question", "an entirely different second question"):
            reader.read(
                store, question, "CIP-007-6 R2", model="stub", store=False, retain_run=False
            )
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

    def test_a_number_pinned_to_the_wrong_section_is_pointed_at(self, store: Repository) -> None:
        regulatory = _section(store, "35 calendar days")
        note = write_note(store, subject_ref="CIP-007-6 R2", body="We evaluate every 30 days.")
        out = reader.verify_citations(
            store,
            f"The standard requires evaluation every thirty calendar days [{regulatory}], "
            f"which is what we do [{note['section_id']}].",
        )
        assert [m["claim"] for m in out["quantity_review_pointers"]] == ["thirty calendar days"]

    def test_a_number_in_no_source_at_all_is_reported_as_unsupported(
        self, store: Repository
    ) -> None:
        regulatory = _section(store, "35 calendar days")
        out = reader.verify_citations(
            store, f"The standard requires evaluation every ninety days [{regulatory}]."
        )
        assert out["quantities_not_in_cited_text"] == ["ninety days"]
        assert out["quantity_review_pointers"] == []

    def test_a_number_the_cited_section_states_is_not_flagged(self, store: Repository) -> None:
        regulatory = _section(store, "35 calendar days")
        out = reader.verify_citations(
            store, f"The standard requires evaluation every 35 calendar days [{regulatory}]."
        )
        assert out["quantity_review_pointers"] == []

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
        assert out["quantity_review_pointers"] == []
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
            lambda payload, timeout, dialect=None: {
                "message": {"content": "", "thinking": "x" * 6000},
                "prompt_eval_count": 900,
                "eval_count": 1600,
            },
        )
        payload = reader.read(
            store, "q", "CIP-007-6 R2", model="stub", answer_tokens=1600, store=False
        )
        assert payload["failed"] is True
        # A BUDGET verdict, named by the transport after it retried once at
        # double the reasoning allowance — never a substantive answer, and never
        # evidence about reasoning.
        # Reasoning is OFF by default on this call site, so this seat reasoned
        # although it was told not to — the failure says which of the two it
        # was, and either way it is a BUDGET result, never an answer.
        assert "reasoning was OFF for this call" in payload["failure"]
        assert "not a reasoning result and not an answer" in payload["failure"]
        assert payload["applied_settings"]["attempts"][0]["thinking_chars"] == 6000
        assert payload["applied_settings"]["reasoning_allowance"] == 0

    def test_an_answer_that_read_nothing_is_a_failed_reading(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The condition this test used to ACCEPT. A terminal prose answer with
        no tool call was scored as success, so ordinary unsupported prose
        travelled as a sound reading — which is what the live parent-level R2
        run did, and what the loop permitted."""
        from portal.modules.compliance.core import reading_transport

        monkeypatch.setattr(
            reading_transport,
            "_post",
            lambda payload, timeout, dialect=None: {
                "message": {"content": "a real answer"},
                "prompt_eval_count": 900,
                "eval_count": 40,
            },
        )
        payload = reader.read(store, "q", "CIP-007-6 R2", model="stub", store=False)
        assert payload["failed"] is True
        assert "made no tool call" in payload["failure"]
        assert payload["closure_receipt"]["model_tool_calls"] == 0


class TestAcquisitionIsRecordedNotElected:
    """P6.9. The loop used to open with the seed and hope the seat chose to call
    a tool. Measured live on the parent-level R2 question, Qwen3.8 answered in
    prose on the first turn, called nothing, and the loop accepted it — so the
    first acquisition is now RUN and RECORDED before the model speaks."""

    def _seat(self, monkeypatch: pytest.MonkeyPatch, content: str, calls: list | None = None):
        from portal.modules.compliance.core import reading_transport

        turns: list[dict] = []

        def _post(payload, timeout, dialect=None):  # noqa: ANN001, ANN202
            turns.append(payload)
            message = {"content": "" if calls and len(turns) == 1 else content}
            if calls and len(turns) == 1:
                message["tool_calls"] = calls
            return {"message": message, "prompt_eval_count": 900, "eval_count": 40}

        monkeypatch.setattr(reading_transport, "_post", _post)
        return turns

    def test_the_requirement_packet_is_acquired_before_the_model_speaks(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        turns = self._seat(monkeypatch, "an answer")
        payload = reader.read(store, "q", "CIP-007-6 R2", model="stub", store=False)
        roles = [m["role"] for m in turns[0]["messages"]]
        assert roles[:2] == ["system", "user"]
        assert "tool" in roles
        trace = payload["closure_receipt"]["tool_trace"]
        assert [entry["tool"] for entry in trace if entry["derivation"] == "bootstrap"] == list(
            reader.BOOTSTRAP_TOOLS
        )

    def test_the_seed_counts_as_examined(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._seat(monkeypatch, "an answer")
        closure = reader.read(store, "q", "CIP-007-6 R2", model="stub", store=False)[
            "closure_receipt"
        ]
        assert closure["examined"], "material handed over unasked is material that was read"

    def test_following_the_link_list_is_enumerating_not_reading(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`compliance_links` returns edges, not text. Counting its ids as
        examined would let one call mark every linked section read."""
        self._seat(
            monkeypatch,
            "an answer",
            calls=[
                {"function": {"name": "compliance_links", "arguments": {"ref": "CIP-007-6 R2"}}}
            ],
        )
        closure = reader.read(store, "q", "CIP-007-6 R2", model="stub", store=False)[
            "closure_receipt"
        ]
        links = [e for e in closure["tool_trace"] if e["tool"] == "compliance_links"]
        assert links, "the enumeration ran"
        assert not (set(closure["enumerated"]) & set(closure["examined"]))


class TestTheRunIsRetained:
    def _read(self, store: Repository, monkeypatch: pytest.MonkeyPatch, **kwargs) -> dict:
        from portal.modules.compliance.core import reading_transport

        monkeypatch.setattr(
            reading_transport,
            "_post",
            lambda payload, timeout, dialect=None: {
                "message": {"content": "an answer"},
                "prompt_eval_count": 900,
                "eval_count": 40,
            },
        )
        return reader.read(store, "q", "CIP-007-6 R2", model="stub", store=False, **kwargs)

    def test_the_receipt_survives_the_process(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = self._read(store, monkeypatch)
        (run,) = reader.runs_for(store, "CIP-007-6 R2")
        assert run["run_id"] == payload["run_id"]
        assert run["closure"]["stop_reason"] == payload["closure_receipt"]["stop_reason"]
        assert run["tool_trace"] == payload["closure_receipt"]["tool_trace"]

    def test_a_failed_reading_is_retained_not_discarded(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = self._read(store, monkeypatch)
        assert payload["failed"] is True  # it called nothing
        (run,) = reader.runs_for(store, "CIP-007-6 R2")
        assert run["failed"] is True
        assert "made no tool call" in run["failure"]

    def test_the_transcript_is_retained_with_the_tool_messages(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._read(store, monkeypatch)
        (run,) = reader.runs_for(store, "CIP-007-6 R2")
        assert [m["role"] for m in run["messages"]][:2] == ["system", "user"]
        assert any(m["role"] == "tool" for m in run["messages"])

    def test_the_run_can_be_declined(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._read(store, monkeypatch, retain_run=False)
        assert reader.runs_for(store, "CIP-007-6 R2") == []


class TestTurnOrder:
    def test_a_prior_turn_comes_before_the_question_being_asked(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The prior turns were appended AFTER the current question, so on turn
        two the last message in the thread was an old assistant answer and the
        model was replying to its own previous turn."""
        from portal.modules.compliance.core import reading_transport

        seen: list[list[dict]] = []

        def _post(payload, timeout, dialect=None):  # noqa: ANN001, ANN202
            seen.append(payload["messages"])
            return {"message": {"content": "an answer"}, "prompt_eval_count": 9, "eval_count": 4}

        monkeypatch.setattr(reading_transport, "_post", _post)
        for question in ("FIRST-QUESTION", "SECOND-QUESTION"):
            reader.read(
                store, question, "CIP-007-6 R2", model="stub", thread_id="t1", retain_run=False
            )
        contents = [str(m.get("content", "")) for m in seen[-1]]
        joined = "\n".join(contents)
        assert "FIRST-QUESTION" in joined, "the prior turn travels"
        assert joined.index("FIRST-QUESTION") < joined.index("SECOND-QUESTION")
        assert contents[-1].rstrip().endswith("SECOND-QUESTION")


# ── what the live CIP-007-6 acceptance run found ────────────────────────────
#
# TASK_COMPLIANCE_PROVE_CIP_007_V1 §P5. Each of these is a defect the LIVE run
# exposed and no unit test caught, which is the whole reason the task exists:
# "Each of these passed every unit test and failed the moment a model was on the
# other end." They are cases now, so the class cannot return unnoticed.


class TestAnAbsenceClaimIsNotANegativeAnswer:
    """Rung 2, then §P8.4. The analyst asked "does anything narrow that
    choice?"; the model answered "**No.** The operator's procedure preserves
    all three actions" — and the contract read `no` … `procedure` within
    eighty characters as an assertion that evidence was ABSENT. Three live
    Part 2.3 readings, every semantic check passing, all failed for answering
    the question they were asked. The cue regex was first narrowed, then
    REMOVED entirely (WINDOW_AND_SEAT_V1 §P8.4): whether prose asserts an
    absence is a judgment about prose, and a pattern match that makes it is
    the acceptance rubric living inside the product. The closure now fails on
    exactly two facts — no tool call, nothing in scope cited — and never on
    the shape of a sentence."""

    def test_the_closure_has_no_absence_input_left(self) -> None:
        import inspect

        parameters = inspect.signature(reader._closure_failure).parameters
        assert "absence_claim" not in parameters
        assert not hasattr(reader, "_ABSENCE_CLAIM")

    def test_an_absence_flavored_answer_with_in_scope_citations_passes(self) -> None:
        cited = "csection-" + "a" * 20
        # The answer TEXT is not an input to the closure at all — that is the
        # contract. The same facts that once fired the regex now pass: one
        # tool call, one in-scope citation.
        assert reader._closure_failure(model_calls=1, eligible={cited}, cited={cited}) == ""
        assert reader._closure_failure(model_calls=3, eligible={cited}, cited={cited}) == ""

    def test_the_two_facts_still_fail(self) -> None:
        cited = "csection-" + "a" * 20
        no_tool_call = reader._closure_failure(model_calls=0, eligible={cited}, cited={cited})
        assert "without reading" in no_tool_call
        out_of_scope = reader._closure_failure(model_calls=2, eligible={cited}, cited=set())
        assert "cites no section in scope" in out_of_scope


class TestTheLoopRefusesACallThatCannotFit:
    """Rung 0. `DEFAULT_NUM_CTX` was derived at 4.22 chars/token, measured on
    RAW CORPUS TEXT; a real assembled thread runs 2.95–3.06. The loop appends a
    tool result per turn, bounded at 12,000 characters, up to twelve times — so
    the worst thread is ~82,000 tokens, not the ~43,000 the derivation assumed.
    The live `CIP-007-6 R2` cell reached it and died with an Ollama HTTP 500,
    twice, at 1,522 s and 760 s."""

    def test_a_thread_that_would_not_fit_is_refused_with_both_numbers(self) -> None:
        detail = reader._window_exhausted(
            thread_chars=300_000,
            ratio=3.0,
            window=98_304,
            answer_tokens=3072,
            reasoning=4096,
            step=7,
        )
        assert detail
        assert "100000" in detail and "98304" in detail
        assert "after 7 turn(s)" in detail

    def test_a_thread_that_fits_is_not_refused(self) -> None:
        assert (
            reader._window_exhausted(
                thread_chars=30_000,
                ratio=3.0,
                window=98_304,
                answer_tokens=3072,
                reasoning=4096,
                step=1,
            )
            == ""
        )

    def test_the_ratio_is_recalibrated_from_the_runner_not_the_constant(self) -> None:
        """The estimate is seeded from CHARS_PER_TOKEN and replaced by the
        runner's own count, because the constant was measured on other text."""
        assert reader._recalibrate(2.1, 60_000, {"prompt_eval_count": 20_000}) == 3.0
        # no count yet: keep the (conservative) seed rather than invent one
        assert reader._recalibrate(2.1, 60_000, {"prompt_eval_count": 0}) == 2.1
