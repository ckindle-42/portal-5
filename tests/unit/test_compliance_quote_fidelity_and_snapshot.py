"""P6R - near-verbatim quotes are named, and every rep reads the same store."""

from __future__ import annotations

import importlib.util
import pathlib
import sqlite3
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
TRUTH = REPO / "scripts" / "compliance" / "truth"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, TRUTH / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


qf = _load("quote_fidelity")
ss = _load("store_snapshot")

SOURCE = (
    "Remote users connect through the Intermediate System. The vendor portal does not "
    "directly access any BES Cyber System, and every session is logged for 90 days."
)


def test_the_b0_meaning_reversal_is_near_verbatim():
    hit = qf.near_verbatim(
        "The vendor portal does car directly access any BES Cyber System", SOURCE
    )
    assert hit is not None and hit.distance == 3


def test_verbatim_quotes_and_paraphrases_are_not_near_verbatim():
    assert qf.near_verbatim("does not directly access any BES Cyber System", SOURCE) is None
    assert (
        qf.near_verbatim(
            "the portal never touches BES systems and logs are kept three months", SOURCE
        )
        is None
    )
    assert qf.near_verbatim("logged for", SOURCE) is None


def test_the_fold_and_budget_are_the_callers():
    assert qf.near_verbatim("THE VENDOR PORTAL DOES NOT DIRECTLY ACCESS", SOURCE) is None
    assert (
        qf.near_verbatim("The vendor portal does car directly access", SOURCE, budget=lambda s: 2)
        is None
    )


def test_levenshtein_is_bounded():
    assert qf.levenshtein("kitten", "sitting", 10) == 3
    assert qf.levenshtein("a" * 50, "b" * 50, 5) == 6


def _db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE notes(id INTEGER PRIMARY KEY, body TEXT)")
    conn.execute("CREATE TABLE edges(src TEXT, dst TEXT, status TEXT)")
    conn.executemany(
        "INSERT INTO edges VALUES (?,?,?)", [("R2 Part 2.2", "isection-1", "proposed")]
    )
    conn.commit()
    conn.close()


def test_restore_undoes_a_reps_write_even_with_a_connection_open(tmp_path):
    db, snap = tmp_path / "store.db", tmp_path / "snap.db"
    _db(db)
    pinned = ss.snapshot(db, snap)
    reader = sqlite3.connect(db)
    writer = sqlite3.connect(db)
    writer.execute("INSERT INTO notes(body) VALUES ('a note written by the model in rep 1')")
    writer.execute("UPDATE edges SET status = 'approved'")
    writer.commit()
    writer.close()
    assert ss.digest(db)["sha256"] != pinned["sha256"]
    result = ss.restore(snap, db)
    assert result["restored"] is True
    assert reader.execute("SELECT count(*) FROM notes").fetchone()[0] == 0
    assert reader.execute("SELECT status FROM edges").fetchone()[0] == "proposed"
    reader.close()


def test_digest_ignores_page_layout(tmp_path):
    db = tmp_path / "store.db"
    _db(db)
    before = ss.digest(db)["sha256"]
    conn = sqlite3.connect(db)
    conn.execute("VACUUM")
    conn.close()
    assert ss.digest(db)["sha256"] == before


def test_snapshot_refuses_the_public_tree(tmp_path):
    db = tmp_path / "store.db"
    _db(db)
    assert (
        ss.main(
            ["snapshot", "--db", str(db), "--out", str(REPO / "reports" / "compliance" / "s.db")]
        )
        == 2
    )
