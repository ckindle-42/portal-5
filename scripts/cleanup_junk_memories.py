"""One-shot cleanup of junk/templated memory rows (Jarvis R5).

Earlier test tasks wrote memories carrying unfilled template placeholders
(``{line_count}``, ``<output_of_previous_step>``). This lists those rows (dry-run by
default) and, with ``--apply``, deletes them from the live memory store. It matches
across all user ids because the junk was written by scoped test runs as well as the
operator. The orchestrator runs it against the live store; it is not wired into the
stack.
"""

from __future__ import annotations

import argparse
from typing import Any

from portal.platform.memory import graph_memory


def junk_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The rows whose text carries an unfilled template placeholder."""
    return [row for row in rows if graph_memory.unfilled_placeholder(str(row.get("text") or ""))]


def collect_junk(limit: int) -> list[dict[str, Any]]:
    rows = graph_memory._memory_table().search().limit(limit).to_list()
    slim = [
        {"id": r["id"], "user_id": r.get("user_id", ""), "text": r.get("text", "")} for r in rows
    ]
    return junk_rows(slim)


def apply_deletes(rows: list[dict[str, Any]]) -> int:
    """Delete only the matched junk ids (memory row + its relations), across users."""
    deleted = 0
    for row in rows:
        mid = str(row["id"])
        if "'" in mid or "\\" in mid:
            continue
        graph_memory._memory_table().delete(f"id = '{mid}'")
        graph_memory._relations().delete(f"source_memory_id = '{mid}'")
        deleted += 1
    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="delete the matched rows")
    parser.add_argument("--limit", type=int, default=100_000, help="max rows to scan")
    args = parser.parse_args()
    rows = collect_junk(args.limit)
    for row in rows:
        print(f"{row['id']}  user={row['user_id']}  {row['text'][:160]}")
    if not rows:
        print("no junk memory rows found")
        return
    if args.apply:
        deleted = apply_deletes(rows)
        print(f"deleted {deleted} junk memory row(s)")
    else:
        print(f"{len(rows)} junk row(s) matched; dry-run only — re-run with --apply to delete")


if __name__ == "__main__":
    main()
