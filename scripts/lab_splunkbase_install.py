#!/usr/bin/env python3
"""Install the Splunkbase apps/add-ons the BOTS datasets need for field extraction.

BOTS ships raw events; the *field aliases and CIM normalization* live in
Splunkbase add-ons listed in each dataset's README. Without them the data is
still fully searchable, but sourcetype-specific fields (Sysmon, Windows TA,
Stream, Suricata, CIM datamodels) do not extract, so the published BOTS hunt
searches match nothing.

Splunkbase downloads are auth-gated — the app *pages* are public but the
download endpoint returns 401 — so this needs a splunk.com account.
``SPLUNKBASE_USERNAME`` / ``SPLUNKBASE_PASSWORD`` live in ``.env`` (gitignored,
placeholders in ``.env.example``); they are install-time only and no runtime
path reads them::

    set -a; . ./.env; set +a
    docker cp scripts/lab_splunkbase_install.py splunk:/tmp/
    docker exec -u splunk -e SPLUNKBASE_USERNAME -e SPLUNKBASE_PASSWORD \\
        splunk /opt/splunk/bin/python3 /tmp/lab_splunkbase_install.py

Idempotent and additive-only: an app whose directory already exists is skipped,
nothing is deleted, and a delisted app is reported rather than fatal. Apps load
at splunkd startup, so restart Splunk afterwards. Extraction is search-time, so
add-ons installed after the data still apply to it retroactively.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

SPLUNK_HOME = os.environ.get("SPLUNK_HOME", "/opt/splunk")
APPS_DIR = os.path.join(SPLUNK_HOME, "etc", "apps")
BASE = "https://splunkbase.splunk.com"

# Union of every Splunkbase app id referenced by the BOTS v1/v2/v3 READMEs.
# Note 2760 (TA-Suricata) is delisted and superseded by 4242 (TA for Suricata).
BOTS_APP_IDS: tuple[int, ...] = (
    742,  # Splunk Add-on for Microsoft Windows
    833,  # Splunk Add-on for Unix and Linux
    1493,  # Splunk Add-on for Bro IDS
    1620,  # Splunk Add-on for Cisco ASA
    1621,  # Splunk Common Information Model (CIM)
    1710,  # Splunk Add-on for Tenable
    1809,  # Splunk App / Add-on for Stream
    1876,  # Splunk Add-on for AWS
    1914,  # Splunk Add-On for Microsoft Sysmon
    1922,  # Base64
    2655,  # DecryptCommands
    2734,  # URL Toolbox
    2757,  # Palo Alto Networks Add-on for Splunk
    2772,  # Splunk Add-on for Symantec Endpoint Protection
    2846,  # Fortinet Fortigate Add-on for Splunk
    2875,  # Collectd App for Splunk Enterprise
    2968,  # Cisco Networks Add-on
    2992,  # Cisco NVM
    3110,  # Splunk Add-on for Microsoft Cloud Services
    3172,  # SSL Certificate Checker
    3185,  # Splunk Add-on for NGINX
    3186,  # Splunk Add-on for Apache Web Server
    3278,  # Splunk Add-on for ISC BIND
    3435,  # Splunk Security Essentials
    3446,  # TA-VirusTotalActions
    3449,  # Splunk Add-on for Amazon Kinesis Firehose
    3626,  # JellyFisher
    3720,  # Microsoft Office 365 Reporting Add-on
    3736,  # Code42 App For Splunk
    3746,  # Code42ForSplunk Technology Add-On
    3749,  # SA-Investigator
    3757,  # Microsoft Azure AD Reporting Add-on
    3786,  # Microsoft Cloud App for Splunk
    3790,  # AWS GuardDuty
    3902,  # OSquery App for Splunk
    4055,  # Splunk Add-on for Microsoft Office 365
    4242,  # TA for Suricata (supersedes delisted 2760)
)


def curl(args: list[str], timeout: int = 900) -> str:
    return subprocess.run(
        ["curl", "-sL", "--max-time", str(timeout), *args],
        check=False,
        capture_output=True,
        text=True,
    ).stdout


def login(username: str, password: str) -> str:
    """Splunkbase session token. Basic auth returns 'Bad Request' on the current
    endpoint — it wants the credentials as POST form fields."""
    body = curl(
        ["-d", f"username={username}&password={password}", f"{BASE}/api/account:login/"], 60
    )
    if "<id>" not in body:
        raise SystemExit(f"[FAIL] Splunkbase auth failed: {body[:200]}")
    return body.split("<id>", 1)[1].split("</id>", 1)[0].strip()


def latest_release(app_id: int, token: str) -> str | None:
    raw = curl(["-H", f"X-Auth-Token: {token}", f"{BASE}/api/v1/app/{app_id}/release/"], 60)
    try:
        doc = json.loads(raw)
    except ValueError:
        return None
    releases = doc if isinstance(doc, list) else doc.get("results", [])
    return releases[0].get("name") if releases else None


def archive_root(path: str) -> str | None:
    """Top-level directory inside the tarball = the installed app dir name."""
    out = subprocess.run(["tar", "-tzf", path], check=False, capture_output=True, text=True).stdout
    first = out.splitlines()[0] if out.strip() else ""
    return first.split("/", 1)[0] or None


def install(app_id: int, token: str, workdir: str) -> tuple[str, str]:
    version = latest_release(app_id, token)
    if not version:
        return "FAIL", f"app {app_id}: no release listed (delisted?)"
    archive = os.path.join(workdir, f"app{app_id}.tgz")
    curl(
        [
            "-H",
            f"X-Auth-Token: {token}",
            "-o",
            archive,
            f"{BASE}/app/{app_id}/release/{version}/download/",
        ]
    )
    if not os.path.exists(archive) or os.path.getsize(archive) < 1024:
        return "FAIL", f"app {app_id} v{version}: download empty/denied"
    root = archive_root(archive)
    if not root:
        return "FAIL", f"app {app_id} v{version}: not a readable tar.gz"
    if os.path.isdir(os.path.join(APPS_DIR, root)):
        os.remove(archive)
        return "SKIP", f"{root} (v{version}) already installed"
    rc = subprocess.run(["tar", "-xzf", archive, "-C", APPS_DIR], check=False).returncode
    os.remove(archive)
    if rc != 0:
        return "FAIL", f"app {app_id} v{version}: tar rc={rc}"
    return "OK", f"{root} v{version}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--app", type=int, action="append", help="app id (repeatable); default: all BOTS apps"
    )
    args = ap.parse_args()

    username = os.environ.get("SPLUNKBASE_USERNAME")
    password = os.environ.get("SPLUNKBASE_PASSWORD")
    if not (username and password):
        print("[FAIL] set SPLUNKBASE_USERNAME and SPLUNKBASE_PASSWORD")
        return 2
    if not os.path.isdir(APPS_DIR):
        print(f"[FAIL] {APPS_DIR} not found — run on the Splunk host, or set SPLUNK_HOME")
        return 2

    token = login(username, password)
    print(f"authenticated to Splunkbase; installing into {APPS_DIR}\n")

    results: dict[str, list[str]] = {"OK": [], "SKIP": [], "FAIL": []}
    with tempfile.TemporaryDirectory(dir=SPLUNK_HOME + "/var") as workdir:
        for app_id in args.app or BOTS_APP_IDS:
            status, detail = install(app_id, token, workdir)
            results[status].append(detail)
            print(f"  [{status:<4}] {detail}", flush=True)

    print(
        f"\ninstalled {len(results['OK'])}, skipped {len(results['SKIP'])}, failed {len(results['FAIL'])}"
    )
    if results["FAIL"]:
        print("failures (delisted apps are expected, not fatal):")
        for detail in results["FAIL"]:
            print(f"  - {detail}")
    print("\nRestart splunkd to load newly installed apps.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
