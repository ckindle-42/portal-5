from __future__ import annotations

import pytest

from portal.modules.compliance.core.determination import AtomResult, DeterminationContractError


def test_v01_dataclass_contract_rejects_invalid_results():
    with pytest.raises(DeterminationContractError):
        AtomResult("TEST-ATOM", "UNRESOLVED")
    with pytest.raises(DeterminationContractError):
        AtomResult("TEST-ATOM", "ABSENT")
    with pytest.raises(DeterminationContractError):
        AtomResult("TEST-ATOM", "SUPPORTED", governing_anchor_ids=["g"])
