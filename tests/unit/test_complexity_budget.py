"""The budget holds ceilings with headroom; prose and god counts are reported (B4).

Raising a ceiling is an operator decision carrying a `reason:`, never an
automatic re-stamp, and `--write-budget` only runs when that reason is given.
"""

import importlib.util
import math
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location(
    "complexity_report", REPO / "scripts" / "complexity_report.py"
)
cr = importlib.util.module_from_spec(_spec)
# Register before exec: dataclass field resolution on 3.10+ looks the module
# up via sys.modules[cls.__module__] and NoneType-errors otherwise.
sys.modules[_spec.name] = cr
_spec.loader.exec_module(cr)


def _census(
    *, data_lines=0, prose=0, god_funcs=0, god_lines=0, unwired=0, identical=0, blob_bytes=0
):
    """A census whose gated and reported totals are exactly the arguments."""
    c = cr.Census()
    c.files.append(cr.FileStats(path="x.py", comment=prose, data_lines=data_lines))
    c.god_funcs = [("x.py", "f", 1, 1)] * god_funcs
    if god_lines:
        c.god_funcs.append(("x.py", "big", god_lines, 1))
    c.unwired = ["s.py"] * unwired
    c.identical = [("a.py", "b.py")] * identical
    c.blobs = [("p.json", blob_bytes)]
    return c


def test_every_metric_is_declared_with_a_reason():
    declared, problems = cr._load_budget()
    assert problems == []
    assert set(declared) == set(cr.GATED_KEYS) | set(cr.REPORTED_KEYS)
    assert all(spec["reason"] for spec in declared.values())


def test_a_total_over_its_ceiling_fails():
    ceiling = cr._load_budget()[0]["data_lines"]["value"]
    assert cr.gate(_census(data_lines=ceiling + 1)) == 1


def test_a_total_exactly_at_its_ceiling_passes():
    ceiling = cr._load_budget()[0]["data_lines"]["value"]
    assert cr.gate(_census(data_lines=ceiling)) == 0


def test_prose_and_god_counts_are_reported_not_gated(capsys):
    declared = cr._load_budget()[0]
    census = _census(
        prose=declared["prose"]["value"] * 10, god_funcs=declared["god_funcs"]["value"] + 50
    )
    assert cr.gate(census) == 0
    assert "reported, not gated" in capsys.readouterr().out


def test_a_ceiling_without_a_reason_is_rejected(tmp_path, monkeypatch, capsys):
    budget = tmp_path / "budget.yaml"
    monkeypatch.setattr(cr, "BUDGET_PATH", budget)
    budget.write_text("ceilings:\n  data_lines:\n    value: 100\n")
    assert cr.gate(_census()) == 1
    assert "reason" in capsys.readouterr().out


def test_deleting_a_metric_fails_instead_of_silencing_the_gate(tmp_path, monkeypatch, capsys):
    budget = tmp_path / "budget.yaml"
    monkeypatch.setattr(cr, "BUDGET_PATH", budget)
    ceilings = {k: {"value": 0, "reason": "test"} for k in cr.GATED_KEYS if k != "data_lines"}
    reported = {k: {"value": 0, "reason": "test"} for k in cr.REPORTED_KEYS}
    budget.write_text(yaml.safe_dump({"ceilings": ceilings, "reported": reported}))
    assert cr.gate(_census()) == 1
    assert "data_lines" in capsys.readouterr().out


def test_write_budget_refuses_without_a_reason():
    budget = REPO / "config" / "complexity_budget.yaml"
    before = budget.read_bytes()
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "complexity_report.py"), "--write-budget"],
        capture_output=True,
        text=True,
        cwd=REPO,
        check=False,
    )
    assert proc.returncode == 2, proc.stderr
    assert "--reason" in proc.stderr
    assert budget.read_bytes() == before


def test_write_budget_records_headroom_and_the_reason(tmp_path, monkeypatch):
    budget = tmp_path / "budget.yaml"
    monkeypatch.setattr(cr, "BUDGET_PATH", budget)
    assert cr.write_budget(_census(data_lines=100, prose=40, unwired=3), "operator: B4 test") == 0
    payload = yaml.safe_load(budget.read_text())
    assert payload["ceilings"]["data_lines"]["value"] == 100 + math.ceil(100 * cr.CEILING_HEADROOM)
    assert payload["ceilings"]["unwired_scripts"]["value"] == 4
    assert payload["reported"]["prose"] == {"value": 40, "reason": "operator: B4 test"}
    assert all(v["reason"] == "operator: B4 test" for v in payload["ceilings"].values())


def test_write_budget_rejects_a_blank_reason(tmp_path, monkeypatch):
    budget = tmp_path / "budget.yaml"
    monkeypatch.setattr(cr, "BUDGET_PATH", budget)
    assert cr.write_budget(_census(), "   ") == 2
    assert not budget.exists()
