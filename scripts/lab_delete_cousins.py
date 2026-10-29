#!/usr/bin/env python3
"""Dry-run or remove only the injected corpus cousins from portal5_lab."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx

INDEX = "portal5_lab"
SOURCE = "portal5:corpus:cousin:*"
COUNTS_SEARCH = f'| tstats count where index={INDEX} source="{SOURCE}" by source sourcetype host'
RAW_COUNT_SEARCH = f'search index={INDEX} source="{SOURCE}" | stats count'
DELETE_SEARCH = f'search index={INDEX} source="{SOURCE}" | delete'


def _connection() -> tuple[str, str, str]:
    url = os.environ.get("LAB_SPLUNK_URL", "https://10.0.1.30:8089").rstrip("/")
    user = os.environ.get("LAB_SPLUNK_USER", "admin")
    password = os.environ.get("LAB_SPLUNK_PASSWORD", "")
    if not password:
        raise RuntimeError("LAB_SPLUNK_PASSWORD is required")
    return url, user, password


def rest_request(
    method: str, path: str, *, data: Mapping[str, str] | None = None
) -> dict[str, Any]:
    url, user, password = _connection()
    response = httpx.request(
        method,
        f"{url}/services/{path.lstrip('/')}",
        auth=(user, password),
        data=data,
        params={"output_mode": "json"},
        verify=False,
        timeout=90.0,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Splunk returned an unexpected response for {path}")
    return payload


def export_rows(search: str) -> list[dict[str, Any]]:
    url, user, password = _connection()
    response = httpx.post(
        f"{url}/services/search/jobs/export",
        auth=(user, password),
        data={"search": search, "exec_mode": "oneshot", "output_mode": "json"},
        verify=False,
        timeout=180.0,
    )
    response.raise_for_status()
    rows: list[dict[str, Any]] = []
    for line in response.text.splitlines():
        try:
            result = json.loads(line).get("result")
        except (ValueError, AttributeError):
            continue
        if isinstance(result, dict):
            rows.append(result)
    return rows


def _count(search: str) -> int:
    rows = export_rows(search)
    return int(rows[-1].get("count", 0)) if rows else 0


def cousin_inventory() -> dict[str, Any]:
    rows = export_rows(COUNTS_SEARCH)
    counts = [
        {
            "source": str(row.get("source", "")),
            "sourcetype": str(row.get("sourcetype", "")),
            "host": str(row.get("host", "")),
            "count": int(row.get("count", 0)),
        }
        for row in rows
    ]
    raw_count = _count(RAW_COUNT_SEARCH)
    tstats_count = sum(row["count"] for row in counts)
    return {
        "index": INDEX,
        "source_pattern": SOURCE,
        "raw_count": raw_count,
        "tstats_count": tstats_count,
        "reconciled": raw_count == tstats_count,
        "by_source_sourcetype_host": counts,
    }


def _entry_content(payload: Mapping[str, Any]) -> dict[str, Any]:
    entries = payload.get("entry", [])
    if not isinstance(entries, list) or not entries or not isinstance(entries[0], dict):
        raise RuntimeError("Splunk returned no account or role entry")
    content = entries[0].get("content", {})
    return content if isinstance(content, dict) else {}


def _role_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return sorted({part.strip() for part in value.split(",") if part.strip()})
    if isinstance(value, list):
        return sorted({str(part).strip() for part in value if str(part).strip()})
    return []


def account_roles(username: str = "admin") -> dict[str, list[str]]:
    content = _entry_content(rest_request("GET", f"authentication/users/{quote(username)}"))
    return {
        "roles": _role_list(content.get("roles")),
        "imported_roles": _role_list(content.get("imported_roles")),
    }


def create_delete_role() -> str:
    name = f"p5_temp_delete_{uuid.uuid4().hex[:12]}"
    rest_request(
        "POST",
        "authorization/roles",
        data={"name": name, "capabilities": "can_delete"},
    )
    return name


def add_imported_role(username: str, role: str) -> None:
    current = account_roles(username)
    imported = sorted(set(current["imported_roles"]) | {role})
    rest_request(
        "POST",
        f"authentication/users/{quote(username)}",
        data={"imported_roles": ",".join(imported)},
    )


def remove_imported_role(username: str, role: str) -> None:
    current = account_roles(username)
    imported = [value for value in current["imported_roles"] if value != role]
    rest_request(
        "POST",
        f"authentication/users/{quote(username)}",
        data={"imported_roles": ",".join(imported)},
    )


def delete_role(role: str) -> None:
    rest_request("DELETE", f"authorization/roles/{quote(role)}")


def delete_cousins(username: str = "admin") -> dict[str, Any]:
    before = cousin_inventory()
    if not before["reconciled"]:
        raise RuntimeError("tstats and raw cousin counts do not reconcile")
    initial_roles = account_roles(username)
    if initial_roles["roles"] != ["admin"] or initial_roles["imported_roles"]:
        raise RuntimeError(
            "refusing deletion because the admin account does not have admin-only roles"
        )
    if before["raw_count"] == 0:
        return {
            "before": before,
            "after": before,
            "roles_before": initial_roles,
            "roles_after": initial_roles,
        }

    role: str | None = None
    try:
        role = create_delete_role()
        add_imported_role(username, role)
        export_rows(DELETE_SEARCH)
    finally:
        if role is not None:
            try:
                remove_imported_role(username, role)
            finally:
                delete_role(role)

    after = cousin_inventory()
    final_roles = account_roles(username)
    if after["raw_count"] != 0 or after["tstats_count"] != 0:
        raise RuntimeError("cousin events remain after deletion")
    if final_roles != initial_roles:
        raise RuntimeError("admin account roles were not restored after deletion")
    return {
        "before": before,
        "after": after,
        "roles_before": initial_roles,
        "roles_after": final_roles,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--delete", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        result = {"mode": "DRY-RUN", "inventory": cousin_inventory(), "roles": account_roles()}
    else:
        result = {"mode": "DELETED", **delete_cousins()}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
