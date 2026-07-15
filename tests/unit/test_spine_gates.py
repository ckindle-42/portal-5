"""Ratchet the wiki/router spine's own correctness gates into the pytest CI lane.

These four checks live in scripts/validate_system.py and were only enforced by
(bypassable) pre-commit. Riding tests/unit makes them server-side and unbypassable.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load_validate():
    spec = importlib.util.spec_from_file_location(
        "portal_validate_system", REPO / "scripts" / "validate_system.py"
    )
    mod = importlib.util.module_from_spec(spec)
    # Register before exec: dataclass field resolution on 3.10+ looks the
    # module up via sys.modules[cls.__module__] and NoneType-errors otherwise.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    "fn_name",
    [
        "check_routing_regression",  # AU — served-model baseline
        "check_wiki_core",  # AJ — schema + provenance + import-clean
        "check_wiki_facts_current",  # AW — fact-units vs live config
        "check_doc_currency",  # AK — bound docs vs their sources
    ],
)
def test_spine_gate(fn_name):
    mod = _load_validate()
    status, detail, _subs = getattr(mod, fn_name)()
    assert status == "PASS", f"{fn_name}: {status} — {detail}"
