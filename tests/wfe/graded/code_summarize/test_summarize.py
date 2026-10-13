"""Hidden grader for code-cli-args. The task used to pass on `summarize.py`
existing and containing `def summarize` — a stub scored the same as a working
implementation, so the lane could not separate models."""

from summarize import summarize


def test_sums_per_region():
    rows = [
        {"region": "east", "revenue": 10},
        {"region": "west", "revenue": 5},
        {"region": "east", "revenue": 2.5},
    ]
    assert summarize(rows) == {"east": 12.5, "west": 5.0}


def test_numeric_strings_are_parsed():
    assert summarize([{"region": "a", "revenue": "3.5"}, {"region": "a", "revenue": "1"}]) == {
        "a": 4.5
    }


def test_totals_are_floats():
    out = summarize([{"region": "a", "revenue": 3}])
    assert isinstance(out["a"], float)


def test_missing_revenue_is_ignored():
    rows = [{"region": "a", "revenue": 1}, {"region": "a"}]
    assert summarize(rows) == {"a": 1.0}


def test_unparseable_revenue_is_ignored():
    rows = [{"region": "a", "revenue": "abc"}, {"region": "a", "revenue": 2}]
    assert summarize(rows) == {"a": 2.0}


def test_none_revenue_is_ignored():
    rows = [{"region": "a", "revenue": None}, {"region": "b", "revenue": "4"}]
    assert summarize(rows).get("b") == 4.0 and summarize(rows).get("a", 0.0) == 0.0


def test_empty_input():
    assert summarize([]) == {}
