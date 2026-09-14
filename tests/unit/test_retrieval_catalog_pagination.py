"""Regress the live acceptance failure once the catalog exceeds ten tables."""

import lancedb
import pyarrow as pa

from portal.modules.compliance.core import review_queue
from portal.platform.retrieval import store


def test_catalog_and_review_queue_beyond_first_page(tmp_path, monkeypatch):
    db = lancedb.connect(tmp_path / "lance")
    monkeypatch.setattr(store, "_db", db)
    schema = pa.schema([pa.field("value", pa.string())])
    # More than the helper's page size tests actual continuation tokens too.
    for index in range(105):
        db.create_table(f"compliance_a{index:03}", schema=schema)
    queue = review_queue._table()
    queue.add(
        [
            review_queue.ReviewItem(
                kind="document_tier", subject_id="kept", proposed_value={}
            ).to_row()
        ]
    )
    text = store.text_table("zz_tail", create=True, prefix="compliance_")
    visual = store.visual_table("zz_tail", create=True, prefix="compliance_")
    assert len(store.table_names(db)) == 108
    assert store.text_table("zz_tail", prefix="compliance_").name == text.name
    assert store.visual_table("zz_tail", prefix="compliance_").name == visual.name
    assert store.text_table("zz_tail", create=True, prefix="compliance_").name == text.name
    assert "zz_tail" in store.list_kbs(prefix="compliance_")
    assert "zz_tail_visual" not in store.list_kbs(prefix="compliance_")
    assert review_queue._table().count_rows() == 1
    assert store.text_table("missing", prefix="compliance_") is None
