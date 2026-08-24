"""K.2 -- the analytical path receives a stratified sample, not the last
batch (TASK_BULLY_SCORER_FEED_V1). Seeded: the stage hands >= 50% of the
covered sourcetypes downstream; reverting to `last_batch` reproduces
F.4's `STARVED` verdict."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import bully_full_assembly_run as fa  # noqa: E402

from portal.modules.security.core.bully import live_connect  # noqa: E402
from portal.modules.security.core.bully import score_sample as ss  # noqa: E402
from portal.modules.security.core.bully.connectors import (  # noqa: E402
    QUERY_IN_PLACE_MODE,
    NativeQuery,
    QueryResult,
)
from portal.modules.security.core.bully.full_pipeline import RunContext  # noqa: E402

N_SOURCETYPES = 325
DOMINANT_ST_RECORDS = 5000
THIN_ST_RECORDS = 3


def _fake_list_sourcetypes(_connector, _index):
    out = [("sourcetype-0", DOMINANT_ST_RECORDS)]
    out += [(f"sourcetype-{i}", THIN_ST_RECORDS) for i in range(1, N_SOURCETYPES - 1)]
    out.append(("yum-too_small", 63))
    return out


class _FakeConnector:
    source_id = "lab-splunk-fake"
    mode = QUERY_IN_PLACE_MODE

    def translate(self, intent):
        return NativeQuery(self.source_id, "SPL", {"search": intent.seed.get("spl", "")}, intent)

    def read(self, intent):
        spl = intent.seed.get("spl", "")
        m = re.search(r'sourcetype="([^"]+)"', spl)
        st = m.group(1) if m else "unknown"
        n = DOMINANT_ST_RECORDS if st == "sourcetype-0" else THIN_ST_RECORDS
        n = 63 if st == "yum-too_small" else n
        n = min(n, intent.limit or n)
        records = tuple(
            {
                "_time": 1_700_000_000.0 + i,
                "host": f"host-{i}",
                "fields": {"sourcetype": st, "i": i},
            }
            for i in range(n)
        )
        return QueryResult(self.source_id, self.mode, self.translate(intent), records, 0.0, 0.0)


def _fake_lab_splunk_connector(*, source_id="lab-splunk", index=None):
    return _FakeConnector()


def _run_stream_stage(monkeypatch, per_sourcetype_cap=2000):
    monkeypatch.setattr(fa, "_list_sourcetypes", _fake_list_sourcetypes)
    monkeypatch.setattr(live_connect, "lab_splunk_connector", _fake_lab_splunk_connector)
    stages = fa.build_stages(
        max_records=None,
        batch_size=10_000,
        per_sourcetype_cap=per_sourcetype_cap,
        dry_run_cousins=True,
    )
    stage = next(s for s in stages if s.name == "stream_corpus_sample")
    ctx = RunContext()
    ctx.put("indexes", ("test_index",))
    produced = stage.run(ctx)
    return ctx, produced


def test_scorer_receives_at_least_half_covered_sourcetypes(monkeypatch) -> None:
    ctx, produced = _run_stream_stage(monkeypatch)
    records = ctx.get("records", [])
    seen_sourcetypes = {r["sourcetype"] for r in records}

    assert produced["n_sourcetypes_covered"] == N_SOURCETYPES
    assert len(seen_sourcetypes) >= 0.5 * N_SOURCETYPES
    assert produced["scorer_input_verdict"]["verdict"] == "OK", produced["scorer_input_verdict"]
    assert produced["sample_report"]["sourcetypes_sampled"] == len(seen_sourcetypes)


def test_reverting_to_last_batch_reproduces_starved(monkeypatch) -> None:
    """F.4's exact defect: feeding the scorer only the final loop batch
    reproduces STARVED even though the stream covered every sourcetype."""
    ctx, produced = _run_stream_stage(monkeypatch)

    # Simulate the pre-fix defect: the scorer only ever saw the LAST
    # sourcetype's batch (sorted iteration order -> "yum-too_small" is not
    # last here, but any single sourcetype's batch reproduces the shape).
    last_batch = [r for r in ctx.get("records", []) if r["sourcetype"] == "yum-too_small"]
    last_batch_report = {
        "algorithm_version": "score-sample-v1",
        "sourcetypes_seen": produced["n_sourcetypes_covered"],
        "sourcetypes_sampled": 1,
        "records_seen": produced["n_records_wide_fit"],
        "records_sampled": len(last_batch),
        "per_sourcetype_cap": 200,
        "sample_fraction": len(last_batch) / max(1, produced["n_records_wide_fit"]),
        "truncated_at_max_total": False,
        "largest_sourcetype_share": 1.0,
    }
    verdict = ss.scorer_input_verdict(last_batch_report, produced["n_sourcetypes_covered"])
    assert verdict["verdict"] == "STARVED", verdict
