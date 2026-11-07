"""The longread aggregation diagnostic plan (2026-11-07): why gemma-4-26b-a4b
fails the 128k aggregation tier. 4 arms x 8 t40k/t80k aggregation tasks x 2
repeats, interleaved; one factor changed per arm vs the baseline; arm C pinned
to the Ollama backend through the pipeline eval override (`portal_backend`);
the report's entries-found-vs-expected parser on a fixture. Offline: config,
suite rendering and seat resolution only — no engines are contacted.
"""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import pytest
import yaml

from tests.wfe import campaign, report
from tests.wfe.runner import _build_pipeline
from tests.wfe.suites import build_reading_long_production as gen

REPO = Path(__file__).resolve().parents[3]
PLAN = REPO / "tests/wfe/plans/longread_aggregation_diag_20261107.yaml"
SUITE = REPO / "tests/wfe/suites/reading_long_production.jsonl"
WORKSPACE = "auto-compliance::reading"
GEMMA_TAG = "gemma4:26b-a4b-it-q4_K_M-ctx128k"
QWEN_TAG = "Qwen3.8-27B-oQ4e-mtp"
TASKS = [
    "lr-aggregation-00-t40k",
    "lr-aggregation-01-t80k",
    "lr-aggregation-03-t40k",
    "lr-aggregation-04-t80k",
    "lr-aggregation-06-t40k",
    "lr-aggregation-07-t80k",
    "lr-aggregation-09-t40k",
    "lr-aggregation-10-t80k",
]


@pytest.fixture
def plan() -> dict:
    return yaml.safe_load(PLAN.read_text())


@pytest.fixture
def matrix(monkeypatch):
    """The plan expanded at repeats=2, hermetic against host WFE_* env vars."""
    for var in ("WFE_SAMPLING", "WFE_THINK"):
        monkeypatch.delenv(var, raising=False)
    return campaign.expand_matrix(PLAN, 2)


def _arm_entries(plan: dict) -> dict[str, dict]:
    arms = plan["workloads"][WORKSPACE]["arms"]
    out = {"incumbent": arms["incumbent"]}
    for c in arms["challengers"]:
        out[c["label"]] = c
    return out


def _minus_label(entry: dict) -> dict:
    return {k: v for k, v in entry.items() if k != "label"}


def test_plan_structure(plan):
    wl = plan["workloads"][WORKSPACE]
    assert wl["tool_mode"] == "production"
    assert wl["home"] == "reading_long_production"
    assert wl["discovery"] == []
    assert sorted(wl["home_tasks"]) == TASKS
    assert all("-t40k" in t or "-t80k" in t for t in wl["home_tasks"])
    assert "t112k" not in " ".join(wl["home_tasks"])
    assert plan["repeats"] == 2
    assert plan["arm_order"] == "interleaved"
    entries = _arm_entries(plan)
    assert set(entries) == {"incumbent", "think-on", "ollama-gguf", "qwen38-omlx"}
    assert {e["model"] for e in entries.values()} == {GEMMA_TAG, QWEN_TAG}
    assert entries["incumbent"]["backend"] == "omlx-general"


def test_matrix_is_4_arms_by_8_tasks_at_2_repeats(matrix):
    arms = {r["arm"] for r in matrix}
    assert len(arms) == 4
    assert len(matrix) == 4 * len(TASKS) * 2
    for arm in arms:
        rows = [r for r in matrix if r["arm"] == arm]
        assert {r["task_id"] for r in rows} == set(TASKS)
        assert sorted(r["repeat"] for r in rows) == sorted(list(range(2)) * len(TASKS))
    assert all(r["workspace"] == WORKSPACE and r["is_home"] for r in matrix)


def test_one_factor_changed_per_arm_vs_baseline(plan):
    """B flips think only; C flips the serving backend only; D is the
    different-lineage arm by design, at its card think and card sampling."""
    a = _arm_entries(plan)
    base = _minus_label(a["incumbent"])
    assert _minus_label(a["think-on"]) == {**base, "think": True}
    assert _minus_label(a["ollama-gguf"]) == {**base, "backend": "ollama-general"}
    d = a["qwen38-omlx"]
    assert d["model"] == QWEN_TAG and d["backend"] == "omlx-general"
    assert d["think"] is False


def test_arm_sampling_is_the_vendor_card(plan):
    cards = yaml.safe_load((REPO / "config/model_card_expectations.yaml").read_text())["models"]
    a = _arm_entries(plan)
    gemma_card = cards["gemma4"]["recommended_sampling"]
    for name in ("incumbent", "think-on", "ollama-gguf"):
        s = a[name]["sampling"]
        assert {k: s[k] for k in ("temperature", "top_p", "top_k")} == {
            k: gemma_card[k] for k in ("temperature", "top_p", "top_k")
        }
        assert s["min_p"] == 0.0 and s["repeat_penalty"] == 1.0  # card: no rep penalty
    # "think as its card says" for arm D; sampling = its card instruct profile
    assert cards["qwen3.8"]["harness_policy"]["think"] == "false"
    assert a["qwen38-omlx"]["sampling"] == cards["qwen3.8"]["recommended_sampling"]


def test_arm_c_pins_the_ollama_backend_and_the_seat_registry_agrees(matrix):
    """Arm C's rows carry the pin, the request body names it, and resolving the
    tag AS ollama-general gives the GGUF tag itself — while the unpinned ladder
    (what arm A rides) resolves the SAME tag to the oMLX MLX conversion."""
    c_rows = [r for r in matrix if "ollama-gguf" in r["arm"]]
    assert c_rows and {r["overrides"].get("backend") for r in c_rows} == {"ollama-general"}
    a_rows = [r for r in matrix if "seat-omlx" in r["arm"]]
    assert a_rows and {r["overrides"].get("backend") for r in a_rows} == {"omlx-general"}

    url, payload, _ = _build_pipeline(
        WORKSPACE,
        [{"role": "user", "content": "doc"}],
        "none",
        {},
        None,
        "false",
        False,
        model_override=GEMMA_TAG,
        backend_override="ollama-general",
    )
    assert payload["portal_backend"] == "ollama-general"
    assert urllib.parse.unquote(url.partition("model=")[2]) == GEMMA_TAG

    assert campaign.seat_primary(WORKSPACE, GEMMA_TAG, "ollama-general") == GEMMA_TAG
    mlx_id = "mlx-community--gemma-4-26b-a4b-it-4bit"
    assert campaign.seat_primary(WORKSPACE, GEMMA_TAG, "omlx-general") == mlx_id
    # Why the pin exists at all: unpinned, the priority-10 oMLX alias wins.
    assert campaign.seat_primary(WORKSPACE, GEMMA_TAG) == mlx_id


def test_arm_d_resolves_on_omlx(matrix):
    d_rows = [r for r in matrix if "qwen38-omlx" in r["arm"]]
    assert d_rows and {r["overrides"].get("backend") for r in d_rows} == {"omlx-general"}
    assert campaign.seat_primary(WORKSPACE, QWEN_TAG, "omlx-general") == QWEN_TAG


def test_harness_carries_the_pin_and_think(plan):
    """arm_spec stringifies the overrides; campaign_harness lifts them onto the
    request harness; the pipeline body carries think + the pin."""
    entries = _arm_entries(plan)
    _, _, ov_a = campaign.arm_spec(entries["incumbent"])
    _, _, ov_b = campaign.arm_spec(entries["think-on"])
    assert ov_a["think"] == "false" and ov_b["think"] == "true"
    h = campaign.campaign_harness({}, ov_b)
    assert h["think"] == "true" and h["pipeline_backend"] == "omlx-general"
    url, payload, _ = _build_pipeline(
        WORKSPACE,
        [{"role": "user", "content": "doc"}],
        "none",
        dict(ov_b["sampling"]),
        None,
        "true",
        False,
        model_override=GEMMA_TAG,
        backend_override=ov_b["backend"],
    )
    assert payload["think"] is True
    assert payload["chat_template_kwargs"] == {"enable_thinking": True}
    assert payload["portal_backend"] == "omlx-general"
    assert payload["temperature"] == 1.0 and payload["top_k"] == 64


# ---------------------------------------------------------------- report parser


def _suite_spec(task_id: str) -> dict:
    for line in SUITE.read_text().splitlines():
        t = json.loads(line)
        if t["id"] == task_id:
            return t["doc_spec"]
    raise AssertionError(f"{task_id} not in suite")


def _diag(rows):
    return {d["task_id"]: d for d in report.aggregation_diagnostics(rows)}


def test_diagnostic_parser_on_a_fixture():
    """The expected side is recomputed from the served document; the found side
    is parsed from what the model emitted; a miss carries its position."""
    entries = gen.aggregation_entries(_suite_spec("lr-aggregation-00-t40k"))
    assert len(entries) == 3  # the fixture task's k
    e0, e1, e2 = entries

    def row(text):
        return {
            "run_id": "r",
            "suite": "reading_long_production",
            "arm": "a",
            "task_id": "lr-aggregation-00-t40k",
            "repeat": 0,
            "outcome": "FAIL",
            "final_text": text,
            "transcript": [],
        }

    cites_two = row(f'I counted (entry {e0["id"]}) and entry {e1["id"]}. {{"answer": 12}}')
    d = _diag([cites_two])["lr-aggregation-00-t40k"]
    assert d["found"] == [e0["id"], e1["id"]]
    assert [m["id"] for m in d["missing"]] == [e2["id"]]
    assert 0.0 <= e2["pos_pct"] <= 100.0 and d["extra"] == []

    silent = _diag([row('{"answer": 175}')])["lr-aggregation-00-t40k"]
    assert silent["cited"] == [] and len(silent["missing"]) == 3

    stray = _diag([row(f'entry {e0["id"]}, entry 99999, {{"answer": 3}}')])[
        "lr-aggregation-00-t40k"
    ]
    assert stray["found"] == [e0["id"]] and stray["extra"] == ["99999"]

    # citations surfaced only in the reasoning channel still count
    r = row('{"answer": 287}')
    r["transcript"] = [{"content": "", "reasoning": f"the log says (entry {e1['id']})"}]
    assert _diag([r])["lr-aggregation-00-t40k"]["found"] == [e1["id"]]

    assert _diag([{"task_id": "lr-needle-00-t40k-d10", "suite": "reading_long_production"}]) == {}


def test_expected_entries_match_each_task_key_exactly():
    """The recomputed key: exactly k entries for the asked item, in document
    order, positions ascending and in range."""
    for tid in TASKS:
        spec = _suite_spec(tid)
        entries = gen.aggregation_entries(spec)
        assert len(entries) == spec["k"], tid
        positions = [e["pos_pct"] for e in entries]
        assert positions == sorted(positions), tid
        assert all(0.0 <= p <= 100.0 for p in positions), tid


def test_report_section_renders_positions():
    lines: list[str] = []
    record = {
        "task_id": "lr-aggregation-00-t40k",
        "repeat": 1,
        "arm": "arm@x-1a2b3c4d",
        "outcome": "FAIL",
        "expected": [{"id": "00042", "pos_pct": 51.2}],
        "cited": [],
        "found": [],
        "missing": [{"id": "00042", "pos_pct": 51.2}],
        "extra": [],
    }
    report._sec_aggregation(lines.append, {"aggregation_diagnostics": [record]})
    text = "\n".join(lines)
    assert "found 0/1" in text and "00042@51.2%" in text and "arm@x-1a2b3c4d" in text
