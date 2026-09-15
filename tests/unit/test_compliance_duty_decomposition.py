"""Duty decomposition (foundation P3): the logical expression must represent
the text.

These tests pin the shapes the -6 register actually carries for CIP-007-6 R2
plus minimal synthetic duties for each logical form. The historical failures
they guard against: a one-child ALL_OF/ANY_OF claiming decomposition
readiness, an incidental "or" ("a source or sources") manufacturing a
three-way alternative, and modal-free duties losing their modality.
"""

from __future__ import annotations

from portal.modules.compliance.core.obligations import (
    decompose,
    decomposition_defects,
    expression_for,
)

R2_LEADIN = (
    "Each Responsible Entity shall implement one or more documented process(es) "
    "that collectively include each of the applicable requirement parts in "
    "CIP-007-6 Table R2 – Security Patch Management"
)

PART_21 = (
    "A patch management process for tracking, evaluating, and installing cyber "
    "security patches for applicable Cyber Assets. The tracking portion shall "
    "include the identification of a source or sources that the Responsible "
    "Entity tracks for the release of cyber security patches for applicable "
    "Cyber Assets that are updateable and for which a patching source exists."
)
PART_22 = (
    "At least once every 35 calendar days, evaluate security patches for "
    "applicability that have been released since the last evaluation from the "
    "source or sources identified in Part 2.1."
)
PART_23 = (
    "For applicable patches identified in Part 2.2, within 35 calendar days of "
    "the evaluation completion, take one of the following actions: - Apply the "
    "applicable patches; or - Create a dated mitigation plan; or - Revise an "
    "existing mitigation plan. Mitigation plans shall include the Responsible "
    "Entity's planned actions to mitigate the vulnerabilities addressed by "
    "each security patch and a timeframe to complete these mitigations."
)
PART_24 = (
    "For each mitigation plan created or revised in Part 2.3, implement the "
    "plan within the timeframe specified in the plan, unless a revision to the "
    "plan or an extension to the timeframe specified in Part 2.3 is approved "
    "by the CIP Senior Manager or delegate."
)


def _run(node_id: str, text: str, lead_in: str = R2_LEADIN):
    atoms = decompose(node_id, text, lead_in=lead_in)
    expression = expression_for(atoms, text)
    return atoms, expression


def test_part_22_incidental_or_is_not_an_alternative_group():
    """'a source or sources' must not manufacture an ANY_OF — regression for
    the one-child ANY_OF the old keyword scanner produced."""
    atoms, expression = _run("CIP-007-6 R2 Part 2.2", PART_22)
    assert len(atoms) == 1
    assert expression["kind"] == "SINGLE"
    assert expression["kind"] != "ANY_OF"
    assert decomposition_defects(atoms, expression, PART_22) == []


def test_part_22_modal_free_duty_inherits_lead_in_modality():
    atoms, _ = _run("CIP-007-6 R2 Part 2.2", PART_22)
    (atom,) = atoms
    assert atom.modality == "SHALL"
    assert atom.modality_basis == "inherited_lead_in"
    assert atom.interpretation_status == "accepted"
    assert atom.actor == "Each Responsible Entity"
    assert atom.deadline_cadence.lower().startswith("at least once every 35 calendar days")


def test_part_23_alternatives_form_a_three_way_any_of():
    atoms, expression = _run("CIP-007-6 R2 Part 2.3", PART_23)
    assert len(atoms) == 4
    alternatives = [a for a in atoms if a.clause_kind == "alternative"]
    assert len(alternatives) == 3
    assert expression["kind"] == "ALL_OF"
    groups = [c for c in expression["children"] if c["kind"] == "ANY_OF"]
    assert len(groups) == 1 and len(groups[0]["children"]) == 3
    # each alternative carries the head clause's condition and deadline
    for a in alternatives:
        assert a.conditions and a.conditions[0].startswith("For applicable patches")
        assert "35 calendar days" in a.deadline_cadence
        assert "Part 2.2" in a.depends_on
    # the trailing sub-duty is its own explicit-modal atom
    subduty = [a for a in atoms if a.clause_kind == "duty"]
    assert len(subduty) == 1 and subduty[0].modality == "SHALL"
    assert decomposition_defects(atoms, expression, PART_23) == []


def test_part_24_exception_and_dependency_captured():
    atoms, expression = _run("CIP-007-6 R2 Part 2.4", PART_24)
    (atom,) = atoms
    assert expression["kind"] == "SINGLE"
    assert len(atom.exceptions) == 1
    assert "approved by the CIP Senior Manager" in atom.exceptions[0]
    assert "Part 2.3" in atom.depends_on


def test_part_21_conjunctive_sentences_are_all_of():
    atoms, expression = _run("CIP-007-6 R2 Part 2.1", PART_21)
    assert len(atoms) == 2
    assert expression["kind"] == "ALL_OF"
    assert decomposition_defects(atoms, expression, PART_21) == []


def test_every_atom_clause_is_verbatim_and_offset_anchored():
    for part_id, text in (("2.1", PART_21), ("2.2", PART_22), ("2.3", PART_23), ("2.4", PART_24)):
        atoms, expression = _run(f"CIP-007-6 R2 Part {part_id}", text)
        assert decomposition_defects(atoms, expression, text) == [], part_id


def test_and_separated_declared_list_is_all_of_group():
    text = (
        "Each Responsible Entity shall do one of the following: - Review the "
        "plan; and - Approve the plan."
    )
    atoms, expression = _run("CIP-000-1 R9 Part 9.1", text, lead_in="")
    assert len(atoms) == 2
    assert expression["kind"] == "ALL_OF"
    assert len(expression["children"]) == 2


def test_fragment_without_any_modality_stays_proposed():
    text = "Notification of the availability of new cyber security patches."
    atoms, expression = _run("CIP-000-1 R9 Part 9.2", text, lead_in="")
    (atom,) = atoms
    assert atom.modality == ""
    assert atom.interpretation_status == "proposed"
    assert decomposition_defects(atoms, expression, text) == []


def test_empty_text_yields_empty_expression():
    assert decompose("x", "") == []
    assert expression_for([], "") == {"kind": "EMPTY", "children": []}


def test_one_child_container_is_a_named_defect():
    atoms, _ = _run("CIP-007-6 R2 Part 2.2", PART_22)
    forged = {"kind": "ANY_OF", "children": [{"kind": "ATOM", "atom_id": atoms[0].atom_id}]}
    defects = decomposition_defects(atoms, forged, PART_22)
    assert any("one-child" in d for d in defects)


def test_collapsed_alternatives_are_a_named_defect():
    atoms, _ = _run("CIP-007-6 R2 Part 2.3", PART_23)
    alts = [a for a in atoms if a.clause_kind == "alternative"]
    # drop one alternative atom: the declared 3-item list no longer matches
    surviving = [a for a in atoms if a.atom_id != alts[-1].atom_id]
    expression = expression_for(surviving, PART_23)
    defects = decomposition_defects(surviving, expression, PART_23)
    assert any("alternative atoms" in d for d in defects)


def test_unanchored_clause_offsets_are_a_named_defect():
    atoms, expression = _run("CIP-007-6 R2 Part 2.2", PART_22)
    atoms[0].clause_start = -1
    defects = decomposition_defects(atoms, expression, PART_22)
    assert any("offsets" in d for d in defects)


def test_bullet_glyph_variant_declares_the_same_list():
    text = (
        "For applicable patches identified in Part 2.2, take one of the "
        "following actions: • Apply the applicable patches; • Create a dated "
        "mitigation plan; or • Revise an existing mitigation plan."
    )
    atoms, expression = _run("CIP-007-7.1 R2 Part 2.3", text)
    alternatives = [a for a in atoms if a.clause_kind == "alternative"]
    assert len(alternatives) == 3
    # a declared list with no other clause IS the whole expression
    assert expression["kind"] == "ANY_OF"
    assert len(expression["children"]) == 3
