"""Blue-triage loop — poll SIEM, enrich via LLM, produce P1-P4 reports.

Replaces the dead Talon SOC agent with Portal 5's own harness.
No CoPilot coupling — writes to local store only.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

TRIAGE_INTERVAL = int(os.environ.get("LAB_TRIAGE_POLL_INTERVAL", "30"))
SEVERITY_THRESHOLD = int(os.environ.get("LAB_TRIAGE_SEVERITY", "3"))
PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://localhost:9099")
PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "")
BLUETEAM_WORKSPACE = os.environ.get("LAB_BLUETEAM_WORKSPACE", "auto-blueteam")
SPLUNK_URL = os.environ.get("LAB_SPLUNK_URL", "https://portal5-lab-splunk:8089")
SPLUNK_USER = os.environ.get("LAB_SPLUNK_USER", "admin")
SPLUNK_PW = os.environ.get("LAB_SPLUNK_PASSWORD", "")
SPLUNK_INDEX = os.environ.get("LAB_SPLUNK_INDEX", "portal5_lab")


def poll_alerts(max_alerts: int = 10, since_minutes: int = 5) -> list[dict]:
    """Poll Splunk for recent high-severity alerts via SPL."""
    spl = (
        f"search index={SPLUNK_INDEX} earliest=-{since_minutes}m "
        f"| where isnotnull(EventCode) OR isnotnull(status) "
        f"| head {max_alerts}"
    )
    try:
        r = httpx.post(
            f"{SPLUNK_URL}/services/search/jobs/export",
            auth=(SPLUNK_USER, SPLUNK_PW),
            verify=False,
            timeout=30.0,
            data={"search": spl, "exec_mode": "oneshot", "output_mode": "json"},
        )
        alerts = []
        for ln in r.text.splitlines():
            if ln.strip().startswith("{") and '"result"' in ln:
                result = json.loads(ln).get("result", {})
                alerts.append(result)
        return alerts
    except Exception:
        return []


def enrich_alert(alert: dict) -> dict:
    """Enrich a single alert through the pipeline -> auto-blueteam workspace."""
    alert_text = json.dumps(alert, indent=2)[:2000]
    prompt = (
        f"You are a SOC analyst triaging a SIEM alert. Analyze this alert and produce:\n"
        f"1. Severity: P1 (critical) / P2 (high) / P3 (medium) / P4 (low)\n"
        f"2. MITRE ATT&CK technique IDs\n"
        f"3. IOCs (IPs, file paths, tool names, registry keys)\n"
        f"4. Recommended containment actions\n"
        f"5. Confidence: HIGH / MEDIUM / LOW\n\n"
        f"Alert:\n{alert_text}"
    )
    headers = {"Content-Type": "application/json"}
    if PIPELINE_API_KEY:
        headers["Authorization"] = f"Bearer {PIPELINE_API_KEY}"
    try:
        r = httpx.post(
            f"{PIPELINE_URL}/v1/chat/completions",
            headers=headers,
            json={
                "model": BLUETEAM_WORKSPACE,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=120.0,
        )
        data = r.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"alert": alert, "triage": content, "enriched": True}
    except Exception as e:
        return {"alert": alert, "triage": f"[enrichment error: {e}]", "enriched": False}


def report_triage(results: list[dict], output_dir: str | Path | None = None) -> Path:
    """Write triage results to local store (no external DB)."""
    out_dir = Path(output_dir or os.environ.get("LAB_TRIAGE_DIR", "/tmp/blue_triage"))
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_path = out_dir / f"triage_{ts}.json"
    report_path.write_text(json.dumps(results, indent=2, default=str))
    return report_path


def run_triage_loop(
    *,
    max_cycles: int = 1,
    since_minutes: int = 5,
    dry_run: bool = False,
) -> list[dict]:
    """Poll -> enrich -> report loop.  One cycle by default (CLI mode)."""
    all_results = []
    for _cycle in range(max_cycles):
        alerts = poll_alerts(since_minutes=since_minutes)
        if not alerts:
            if dry_run:
                alerts = [{"_dry_run": True, "EventCode": 4769, "host": "dc01"}]
            else:
                time.sleep(TRIAGE_INTERVAL)
                continue
        for alert in alerts:
            result = enrich_alert(alert)
            all_results.append(result)
    if all_results:
        report_path = report_triage(all_results)
        print(f"  [blue-triage] {len(all_results)} alerts triaged → {report_path}")
    return all_results
