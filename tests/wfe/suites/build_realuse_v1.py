"""Build deterministic fixtures and the runnable realuse_v1 suite."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

from tests.wfe.suites._publish import publish_bytes, publish_text

ROOT = Path(__file__).resolve().parents[3]
DRAFT = ROOT / "coding_task" / "realuse_v1.draft.jsonl"
OUT = Path(__file__).with_name("realuse_v1.jsonl")
ARTIFACTS = Path(__file__).with_name("realuse_v1")
FIXTURE_PREFIX = Path("tests/wfe/suites/realuse_v1/fixtures")

TEXTS = {
    ("ru-v1-002", "trip_notes.txt"): """Trip notes — Colorado drive

Weather: A snow advisory is expected on I-70 westbound Tuesday and Wednesday. Pack tire chains and check road conditions before leaving.

Restaurants: Boulder — The Kitchen; Vail — Sweet Basil; Grand Junction — Bin 707.
""",
    ("ru-v1-003", "management_notes.md"): """# Management notes

Weekly one-to-ones should be 30 minutes maximum. Reading note: *The Making of a Manager* recommends a blocker-first approach. No page number was recorded.
""",
    ("ru-v1-009", "calendar_notes.md"): """# Sprint review calendar

Meeting: Thursday at 2pm. No conflicts are noted. Backup plan: reschedule to Friday if the client call runs long.
""",
    ("ru-v1-009", "prep_script.py"): """from pathlib import Path

config_path = Path("/workspace/uploads/config.json")
if config_path.is_file() and "mode" in config_path.read_text(encoding="utf-8"):
    print("READY")
else:
    print(f"ERROR: missing file or mode: {config_path}")
""",
    ("ru-v1-005", "process_customers.py"): """import time

import pandas as pd

INPUT_PATH = "customers_20k.csv"


def normalize_customer(row):
    row = row.copy()
    row["name_copy"] = row["name"]
    row["email_copy"] = row["email"]
    row["name"] = row["name"].strip().title()
    row["email"] = row["email"].strip().lower()
    return row


def main():
    started = time.time()
    data = pd.read_csv(INPUT_PATH)
    data["region_copy"] = data["region"]
    data["status_copy"] = data["status"]
    print(f"loaded {len(data)} rows")
    data = data.apply(normalize_customer, axis=1)
    for start in range(0, len(data), 100):
        end = min(start + 100, len(data))
        print(f"processed {end} of {len(data)} rows")
    print(data["region"].value_counts())
    print(data["tier"].value_counts())
    print(data["status"].value_counts())
    print(f"elapsed: {time.time() - started:.2f}s")
    print(f"output rows: {len(data)}")
    region_counts = data.groupby("region").size()
    for region, count in region_counts.items():
        print(f"{region}: {count}")
    active_count = (data["status"] == "active").sum()
    inactive_count = (data["status"] == "inactive").sum()
    print(f"active: {active_count}")
    print(f"inactive: {inactive_count}")
    tier_counts = data.groupby("tier")["id"].count()
    print(tier_counts)
    copied_columns = data[["name_copy", "email_copy"]]
    print(copied_columns.head())
    print(data[["id", "name", "region", "status"]].tail())
    return data


if __name__ == "__main__":
    main()
""",
    ("ru-v1-010", "report.txt"): """1. Monday intake was stable.
2. urgent: replace the west relay.
3. The east team cleared routine work.
4. Review the maintenance calendar.
5. urgent: confirm the backup operator.
6. A priority item remains with finance.
7. No other escalations were opened.
8. Parts arrive on Thursday.
9. The night shift confirmed coverage.
10. Close the report after sign-off.
""",
    ("ru-v1-012", "src/app.py"): """from flask import Flask

app = Flask(__name__)


@app.get("/")
def home():
    return {"message": "service is running"}
""",
    ("ru-v1-012", "data.json"): '{"status":"ok","value":42}\n',
    ("ru-v1-013", "email_sample.txt"): """From: alice@example.com
Subject: Meeting Tomorrow
To: team@example.com

Body: Please bring the revised schedule to tomorrow's planning meeting.
""",
    ("ru-v1-014", "src/auth.py"): """API_KEY = "sk-test-000000000000000000000000"


def find_user(cursor, username):
    query = f"SELECT * FROM users WHERE username = '{username}'"
    cursor.execute(query)
    return cursor.fetchone()


def password_matches(expected, supplied):
    return expected == supplied


def authenticate(cursor, username, supplied):
    if not username.strip():
        return False
    user = find_user(cursor, username.strip())
    if user is None:
        return False
    stored_password = user["password"]
    return password_matches(stored_password, supplied)


def lookup_role(cursor, username):
    query = f"SELECT role FROM users WHERE username = '{username}'"
    cursor.execute(query)
    row = cursor.fetchone()
    return "guest" if row is None else row["role"]
""",
    ("ru-v1-016", "src/app.py"): """from flask import Flask

app = Flask(__name__)
CACHE = []


@app.get("/health")
def health():
    return {"status": "ok", "cached_requests": len(CACHE)}


@app.get("/items")
def items():
    request_id = len(CACHE) + 1
    request_path = "/items"
    request_label = f"{request_path}-{request_id}"
    cached_before = len(CACHE)
    CACHE.append(request_label)
    count = len(CACHE)
    return {"items": _read_lines(), "requests_seen": count, "cached_before": cached_before}


def _read_lines():
    path = "data.txt"
    if not path.endswith(".txt"):
        return []
    try:
        return _read_file(path)
    except OSError:
        return []


def _read_file(path):
    if not path:
        return ""
    file_mode = "r"
    text_encoding = "utf-8"
    source_name = "data.txt"
    if not source_name.endswith(".txt"):
        return ""
    path = source_name
    handle = open(path, mode=file_mode, encoding=text_encoding)
    content = handle.read()
    return content.splitlines()
""",
    ("ru-v1-017", "project_notes.md"): """# Q3 project status

Milestone 3 is delayed by one week. A revised timeline is needed by Friday.
""",
    ("ru-v1-020", "event_notes.txt"): """Team event Q3 budget:
- Venue: $800
- Food: $450
- Decorations: $120
- Contingency buffer: 10%
""",
    ("ru-v1-021", "kb/hybrid_policy.md"): """# Internal hybrid policy

The regular schedule is in-office Monday through Wednesday. This note defines no core-hour policy and mentions no equipment stipend.
""",
    ("ru-v1-024", "source_a.md"): """# Transparency-first regulation

This perspective prioritizes transparency and disclosure requirements. Enforcement is a secondary concern once organizations publish clear, comparable information.
""",
    ("ru-v1-024", "source_b.md"): """# Enforcement-first industry view

This perspective prioritizes enforceable penalties. Transparency without enforcement is ineffective because organizations can disclose problems without correcting them.

Neither source discusses international coordination.
""",
    ("ru-v1-028", "nerc_cip_007_v6.md"): """# Synthetic compliance reference: CIP-007 v6 excerpt

This training fixture is fictional and is not an official standard.

## Access control
Multi-factor authentication is required for access to critical systems.

## Audit frequency
Access reviews must occur at least annually.

## Coverage note
This excerpt does not describe third-party vendor access.
""",
    ("ru-v1-028", "compliance_policy_internal.md"): """# Internal access policy

Multi-factor authentication is required for all systems, including systems outside the critical-system boundary. Access audits are performed quarterly.

The policy does not define vendor access controls.
""",
    ("ru-v1-030", "cloud_policy_notes.md"): """# Cloud policy notes

New projects should use GCP. Existing AWS infrastructure stays in place. The budget cap for new cloud spend is $15k per month.
""",
    ("ru-v1-030", "memory_seed.md"): """# Team memory note

The team prefers AWS because of existing relationships and support contracts.
""",
    ("ru-v1-032", "week_plan_notes.txt"): """Tuesday: 9am–12pm focus block.
Wednesday: travel; leave by 8am.
Friday: half-day ends at 1pm.
""",
    ("ru-v1-011", "src/calc.py"): """def _validate_n(n):
    if not isinstance(n, int):
        raise TypeError("n must be an integer")
    if n < 0:
        raise ValueError("n must be non-negative")
    return n


def sum_to_n(n):
    "Return the sum of the positive integers through n."
    n = _validate_n(n)
    if n == 0:
        return 0
    total = 0
    for value in range(1, n):
        total += value
    return total
""",
    ("ru-v1-011", "tests/test_calc.py"): """from calc import sum_to_n


def test_sum_to_n_includes_n():
    assert sum_to_n(5) == 15
""",
    ("ru-v1-031", "src/auth.py"): """def password_matches(expected, supplied):
    return secrets.compare_digest(expected, supplied.lower())  # noqa: F821
""",
    ("ru-v1-031", "tests/unit/test_auth.py"): """from auth import password_matches


def test_password_matches_exact_text():
    assert password_matches("Portal5", "Portal5")


def test_password_comparison_is_case_sensitive():
    assert not password_matches("Portal5", "portal5")
""",
}

TREE_FILES = {
    ("ru-v1-015", "workspace/tree"): {
        "workspace/tree/main.py": "from config import load_config\n\n\ndef main():\n    return load_config()\n",
        "workspace/tree/config.py": 'def load_config():\n    return {"mode": "safe"}\n',
        "workspace/tree/worker.py": 'def run_job(job):\n    return {"job": job, "status": "queued"}\n',
        "workspace/tree/tests/test_main.py": 'from main import main\n\n\ndef test_main():\n    assert main()["mode"] == "safe"\n',
        "workspace/tree/tests/test_worker.py": 'from worker import run_job\n\n\ndef test_worker():\n    assert run_job(4)["status"] == "queued"\n',
    },
    ("ru-v1-034", "src/repo"): {
        "src/repo/entry_point.py": 'import json\n\n\ndef main(path="config.json"):\n    with open(path, encoding="utf-8") as handle:\n        return json.load(handle)\n',
        "src/repo/config_reader.py": 'import json\n\n\ndef read_config(path):\n    try:\n        with open(path, encoding="utf-8") as handle:\n            return json.load(handle)\n    except FileNotFoundError:\n        return {}\n',
        "src/repo/helper_a.py": "def format_name(value):\n    return str(value).strip().title()\n",
        "src/repo/helper_b.py": 'import json\n\n\ndef load_settings(path):\n    with open(path, encoding="utf-8") as handle:\n        return json.load(handle)\n',
    },
}

PDFS = {
    ("ru-v1-001", "final_invoice.pdf"): [
        [
            "FINAL INVOICE",
            "Contractor: Northfield Kitchen Co.",
            "Project: Kitchen remodel",
            "Note: Completion was delayed by 3 days.",
            "Line items",
            "Labor                         $2,400.00",
            "Materials                       $890.00",
            "Misc supplies                   $340.00",
            "Permit                          $180.00",
            "Cleanup                         $210.00",
            "Subtotal                      $4,020.00",
        ]
    ],
    ("ru-v1-004", "remote_work_policy_2025.pdf"): [
        [
            "Remote Work Policy 2025",
            "Page 1 of 6",
            "Hybrid schedule",
            "In-office days: Tuesday, Wednesday, Thursday.",
            "Remote days: Monday and Friday.",
        ],
        [
            "Remote Work Policy 2025",
            "Page 2 of 6",
            "Core hours",
            "Core collaboration hours are 10am to 2pm Eastern Time.",
        ],
        [
            "Remote Work Policy 2025",
            "Page 3 of 6",
            "Equipment stipend",
            "The annual equipment stipend increases from $300 to $500.",
        ],
        [
            "Remote Work Policy 2025",
            "Page 4 of 6",
            "Scheduling",
            "Managers coordinate team coverage for the in-office days.",
        ],
        [
            "Remote Work Policy 2025",
            "Page 5 of 6",
            "Workspace",
            "Employees keep issued equipment secure and report damage promptly.",
        ],
        [
            "Remote Work Policy 2025",
            "Page 6 of 6",
            "Effective date",
            "The updated schedule begins January 6, 2025.",
        ],
    ],
    ("ru-v1-009", "agenda.pdf"): [
        [
            "Agenda - Product Sprint Review",
            "Time: 2pm",
            "Topics: Q3 metrics; roadmap update; hiring freeze status.",
        ]
    ],
    ("ru-v1-018", "contract_draft.pdf"): [
        [
            "CONTRACT DRAFT",
            "1. Scope: supplier will deliver the agreed project materials.",
            "2. Payment: milestone-based payment, net-30 after invoice receipt.",
            "3. Termination: either party may terminate for cause; cause is undefined.",
            "4. Liability: each party is responsible for its obligations under this agreement.",
            "5. Governing law: the agreement is governed by the law of the selected venue.",
        ]
    ],
    ("ru-v1-023", "remote_commute_2025.pdf"): [
        [
            "Synthetic 2025 Remote Commute Study",
            "Average commute saved: 55 minutes per workday.",
            "The reported 2022 comparison was 72 minutes per workday.",
            "The decrease is likely related to partial return to the office.",
        ]
    ],
    ("ru-v1-029", "regulatory_update_2025.pdf"): [
        [
            "Synthetic 2025 Regulatory Update",
            "Applies to: energy-sector operators.",
            "New requirement: automated audit logging for critical system access changes.",
            "Compliance deadline: 2026-03-31.",
        ]
    ],
}

PDF_MARKERS = {
    ("ru-v1-001", "final_invoice.pdf"): (
        "Labor",
        "$2,400.00",
        "Materials",
        "$890.00",
        "Misc supplies",
        "$340.00",
        "Permit",
        "$180.00",
        "Cleanup",
        "$210.00",
        "$4,020.00",
        "3 days",
    ),
    ("ru-v1-004", "remote_work_policy_2025.pdf"): (
        "Page 6 of 6",
        "Tuesday, Wednesday, Thursday",
        "Monday and Friday",
        "10am to 2pm Eastern Time",
        "$300 to $500",
    ),
    ("ru-v1-009", "agenda.pdf"): ("Q3 metrics", "roadmap update", "hiring freeze status"),
    ("ru-v1-018", "contract_draft.pdf"): (
        "1. Scope",
        "2. Payment",
        "net-30",
        "3. Termination",
        "undefined",
        "4. Liability",
        "5. Governing law",
    ),
    ("ru-v1-023", "remote_commute_2025.pdf"): ("55 minutes", "72 minutes", "partial return"),
    ("ru-v1-029", "regulatory_update_2025.pdf"): (
        "automated audit logging",
        "critical system access changes",
        "2026-03-31",
        "energy-sector operators",
    ),
}

TEXT_MARKERS = {
    ("ru-v1-002", "trip_notes.txt"): (
        "I-70 westbound",
        "Tuesday and Wednesday",
        "tire chains",
        "The Kitchen",
        "Sweet Basil",
        "Bin 707",
    ),
    ("ru-v1-003", "management_notes.md"): (
        "30 minutes maximum",
        "The Making of a Manager",
        "blocker-first",
        "No page number",
    ),
    ("ru-v1-009", "calendar_notes.md"): ("Thursday at 2pm", "No conflicts", "Friday"),
    ("ru-v1-010", "report.txt"): ("urgent", "priority"),
    ("ru-v1-012", "src/app.py"): ("Flask", '@app.get("/")', "service is running"),
    ("ru-v1-012", "data.json"): ('"status":"ok"', '"value":42'),
    ("ru-v1-013", "email_sample.txt"): (
        "From: alice@example.com",
        "Subject: Meeting Tomorrow",
        "Body:",
    ),
    ("ru-v1-014", "src/auth.py"): (
        "API_KEY",
        "sk-test-",
        'f"SELECT * FROM users',
        "expected == supplied",
    ),
    ("ru-v1-016", "src/app.py"): ("CACHE = []", "CACHE.append", "open(path, mode="),
    ("ru-v1-017", "project_notes.md"): ("Milestone 3", "one week", "Friday"),
    ("ru-v1-020", "event_notes.txt"): ("$800", "$450", "$120", "10%"),
    ("ru-v1-021", "kb/hybrid_policy.md"): (
        "Monday through Wednesday",
        "no core-hour policy",
        "no equipment stipend",
    ),
    ("ru-v1-024", "source_a.md"): ("transparency", "disclosure", "secondary concern"),
    ("ru-v1-024", "source_b.md"): (
        "enforceable penalties",
        "ineffective",
        "international coordination",
    ),
    ("ru-v1-028", "nerc_cip_007_v6.md"): (
        "Multi-factor authentication",
        "annually",
        "third-party vendor access",
        "fictional",
    ),
    ("ru-v1-028", "compliance_policy_internal.md"): (
        "all systems",
        "quarterly",
        "vendor access controls",
    ),
    ("ru-v1-030", "cloud_policy_notes.md"): ("GCP", "Existing AWS", "$15k per month"),
    ("ru-v1-030", "memory_seed.md"): ("prefers AWS", "support contracts"),
    ("ru-v1-032", "week_plan_notes.txt"): (
        "Tuesday",
        "9am–12pm",
        "Wednesday",
        "8am",
        "Friday",
        "1pm",
    ),
}

CSV_HEADERS = {
    "customers_20k.csv": ["id", "name", "email", "region", "sign_date", "tier", "status"],
    "team_output_q3.csv": ["person", "project", *[f"week_{n}" for n in range(1, 14)]],
    "customer_feedback.csv": ["response_id", "rating", "product_line", "region"],
    "internal_ai_survey.csv": [
        "response_id",
        "adopted",
        "use_case_responded",
        "customer_support",
        "content_creation",
        "analysis",
        "barrier_responded",
        "barrier_cost",
        "barrier_lack_expertise",
    ],
}

REFERENCE_FIXES = {
    "ru-v1-011": ("calc.py", "test_calc.py", (("range(1, n)", "range(1, n + 1)"),)),
    "ru-v1-031": (
        "auth.py",
        "test_auth.py",
        (
            ("def password_matches", "import secrets\n\n\ndef password_matches"),
            ("expected, supplied.lower()", "expected, supplied"),
        ),
    ),
}


def _csv_bytes(header: list[str], rows: list[list[object]]) -> bytes:
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows([header, *rows])
    return output.getvalue().encode("utf-8")


def _customer_rows() -> list[list[object]]:
    regions = ("north", "south", "east", "west")
    tiers = ("standard", "silver", "gold", "enterprise")
    statuses = ("active", "active", "active", "inactive")
    start = date(2024, 1, 1)
    return [
        [
            10000 + i,
            f"Customer {i + 1:05d}",
            f"customer{i + 1:05d}@example.test",
            regions[i % 4],
            (start + timedelta(days=i % 900)).isoformat(),
            tiers[i % 4],
            statuses[i % 4],
        ]
        for i in range(20000)
    ]


def _team_rows() -> list[list[object]]:
    rows = []
    for i in range(12):
        values = [10] * 13
        values[6] = 0 if i % 3 == 2 else 9
        rows.append([f"Person {i + 1:02d}", ("App", "Infra", "Design")[i % 3], *values])
    return rows


def _feedback_rows() -> list[list[object]]:
    distributions = {
        "north": (5, 25, 45, 35, 15),
        "south": (2, 8, 30, 50, 35),
        "east": (3, 12, 35, 45, 30),
        "west": (1, 6, 28, 50, 40),
    }
    positions: dict[str, dict[str, list[int]]] = {}
    for i in range(500):
        product = "ABCD"[(i // 4) % 4]
        region = ("north", "south", "east", "west")[i % 4]
        positions.setdefault(region, {letter: [] for letter in "ABCD"})[product].append(i)
    ratings = [0] * 500
    for region, counts in distributions.items():
        low = [rating for rating, count in ((1, counts[0]), (2, counts[1])) for _ in range(count)]
        candidates = positions[region]["C"]
        for index, rating in zip(candidates, low, strict=False):
            ratings[index] = rating
        remaining = [index for product in "ABD" for index in positions[region][product]]
        remaining.extend(index for index in candidates if ratings[index] == 0)
        high = [
            rating
            for rating, count in ((3, counts[2]), (4, counts[3]), (5, counts[4]))
            for _ in range(count)
        ]
        for index, rating in zip(remaining, high, strict=True):
            ratings[index] = rating
    return [
        [i + 1, ratings[i], "ABCD"[(i // 4) % 4], ("north", "south", "east", "west")[i % 4]]
        for i in range(500)
    ]


def _survey_rows() -> list[list[object]]:
    rows = []
    for i in range(50):
        rows.append(
            [
                f"R{i + 1:03d}",
                "yes" if i < 14 else "no",
                "yes" if i < 40 else "no",
                "yes" if i < 24 else "no" if i < 40 else "na",
                "yes" if i < 8 else "no" if i < 40 else "na",
                "yes" if i < 6 else "no" if i < 40 else "na",
                "yes" if i < 40 else "no",
                "yes" if i < 16 else "no" if i < 40 else "na",
                "yes" if i < 14 else "no" if i < 40 else "na",
            ]
        )
    return rows


def _table_bytes(name: str) -> bytes:
    rows = {
        "customers_20k.csv": _customer_rows,
        "team_output_q3.csv": _team_rows,
        "customer_feedback.csv": _feedback_rows,
        "internal_ai_survey.csv": _survey_rows,
    }[name]()
    return _csv_bytes(CSV_HEADERS[name], rows)


def _pdf_bytes(pages: list[list[str]]) -> bytes:
    objects = [b"<</Type/Catalog/Pages 2 0 R>>"]
    page_ids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(f"<</Type/Pages/Kids[{page_ids}]/Count {len(pages)}>>".encode())
    font_id = 3 + 2 * len(pages)
    for index, lines in enumerate(pages):
        stream_id = 4 + 2 * index
        commands = ["BT /F1 12 Tf 54 740 Td 16 TL"]
        for line in lines:
            safe = line.encode("cp1252", errors="replace").decode("cp1252")
            escaped = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f"({escaped}) Tj T*")
        commands.append("ET")
        stream = " ".join(commands).encode("cp1252", errors="replace")
        objects.append(
            f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents {stream_id} 0 R/Resources<</Font<</F1 {font_id} 0 R>>>>>>".encode()
        )
        objects.append(f"<</Length {len(stream)}>>\nstream\n".encode() + stream + b"\nendstream")
    objects.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica/Encoding/WinAnsiEncoding>>")
    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for object_id, body in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    output.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets))
    output.extend(
        f"trailer\n<</Size {len(objects) + 1}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


def _font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _jpeg(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=92, subsampling=0, optimize=False, progressive=False)
    return output.getvalue()


def _invoice_image() -> bytes:
    image = Image.new("RGB", (640, 420), "white")
    draw = ImageDraw.Draw(image)
    regular, large = _font(24), _font(34)
    draw.rectangle((18, 18, 622, 402), outline=(70, 80, 90), width=3)
    draw.text((42, 38), "INVOICE", fill=(20, 35, 55), font=large)
    draw.text((42, 105), "Vendor: Acme Supply", fill=(20, 20, 20), font=regular)
    draw.text((42, 158), "Date:", fill=(20, 20, 20), font=regular)
    draw.text((145, 158), "2026-10-23", fill=(20, 20, 20), font=regular)
    draw.text((42, 235), "Hardware and field supplies", fill=(30, 30, 30), font=regular)
    draw.line((42, 290, 598, 290), fill=(70, 80, 90), width=2)
    draw.text((42, 315), "TOTAL: $1,240.00", fill=(10, 25, 45), font=large)
    crop = image.crop((140, 150, 320, 194)).filter(ImageFilter.GaussianBlur(radius=7))
    image.paste(crop, (140, 150))
    return _jpeg(image)


def _office_sign_image() -> bytes:
    image = Image.new("RGB", (760, 420), (220, 231, 238))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 760, 230), fill=(211, 226, 234))
    for x in (28, 190, 540, 710):
        draw.rectangle((x, 25, x + 20, 230), fill=(178, 202, 215))
    draw.rectangle((48, 250, 712, 391), fill=(14, 39, 76), outline=(8, 24, 48), width=5)
    draw.ellipse((74, 280, 126, 332), fill=(55, 151, 213))
    font = _font(32)
    prefix = "Portal 5 "
    dash_x = 158 + int(font.getlength(prefix)) + 2
    draw.text((158, 274), prefix, fill="white", font=font)
    draw.line((dash_x, 293, dash_x + 13, 293), fill="white", width=3)
    draw.text((dash_x + 24, 274), "Open Source", fill="white", font=font)
    draw.text((158, 324), "Intelligence Layer", fill="white", font=font)
    return _jpeg(image)


def _team_image() -> bytes:
    image = Image.new("RGB", (760, 390), (238, 240, 242))
    draw = ImageDraw.Draw(image)
    colors = ((48, 95, 150), (72, 125, 92), (148, 83, 72), (113, 87, 146), (65, 119, 139))
    for index, color in enumerate(colors):
        x = 56 + index * 142
        draw.ellipse((x + 35, 42, x + 91, 98), fill=(220, 187, 157), outline=(80, 70, 65), width=2)
        draw.rectangle((x + 18, 104, x + 108, 300), fill=color)
        draw.line((x + 18, 155, x + 2, 247), fill=color, width=15)
        draw.line((x + 108, 155, x + 124, 247), fill=color, width=15)
        draw.line((x + 42, 300, x + 35, 365), fill=(45, 48, 54), width=18)
        draw.line((x + 84, 300, x + 91, 365), fill=(45, 48, 54), width=18)
        if index < 4:
            draw.rectangle(
                (x + 66, 143, x + 84, 162), fill=(255, 224, 92), outline=(35, 45, 50), width=1
            )
    return _jpeg(image)


def _dashboard_image() -> bytes:
    image = Image.new("RGB", (760, 440), (247, 248, 250))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 759, 68), fill=(179, 36, 42))
    draw.text((28, 20), "ALERT", fill="white", font=_font(32))
    draw.text((176, 26), "SYNTHETIC STATUS TEXT", fill=(255, 224, 224), font=_font(16))
    draw.rectangle((24, 100, 238, 396), outline=(125, 137, 150), width=2)
    draw.line(
        (50, 337, 83, 278, 117, 302, 150, 210, 186, 239, 214, 160), fill=(39, 107, 178), width=6
    )
    draw.rectangle((273, 100, 487, 396), outline=(125, 137, 150), width=2)
    for x, height, color in (
        (302, 95, (71, 128, 180)),
        (344, 152, (89, 150, 116)),
        (386, 122, (133, 112, 175)),
        (428, 206, (84, 146, 170)),
    ):
        draw.rectangle((x, 370 - height, x + 25, 370), fill=color)
    draw.ellipse((542, 166, 728, 352), fill=(62, 119, 173))
    draw.pieslice((542, 166, 728, 352), 270, 52, fill=(205, 143, 63))
    draw.pieslice((542, 166, 728, 352), 52, 160, fill=(94, 151, 112))
    draw.pieslice((542, 166, 728, 352), 160, 270, fill=(142, 109, 166))
    return _jpeg(image)


def _image_bytes(task_id: str, name: str) -> bytes:
    return {
        ("ru-v1-019", "invoice_scan.jpg"): _invoice_image,
        ("ru-v1-025", "office_sign.jpg"): _office_sign_image,
        ("ru-v1-026", "team_photo.jpg"): _team_image,
        ("ru-v1-033", "dashboard_screenshot.jpg"): _dashboard_image,
    }[(task_id, name)]()


def _meeting_notes() -> str:
    notes = (
        (
            "Meeting 01 — Q3 planning kickoff",
            "Launch target is September. The group reviewed the release scope, staffing assumptions, customer readiness, and the sequence of decisions needed before the end of August. Product will confirm the feature list, engineering will estimate the remaining integration work, and marketing will prepare a first announcement draft. The team agreed to keep the launch checklist short and assign one owner to every open item. Risks include late design feedback, incomplete support documentation, and dependencies on the reporting dashboard. Each lead will post a written update before the next weekly review. The date remains a target until the readiness review is complete.",
        ),
        (
            "Meeting 02 — Budget review",
            "Finance announced a budget freeze for discretionary purchases through the end of Q3. Existing commitments remain funded, but new equipment and contractor requests need director approval. The team reviewed travel, testing, and launch support costs and found no urgent exception. The freeze may affect the timing of external design help, so the project lead will identify work that can move in-house. Finance will publish the revised forecast by Friday. The September launch target from the kickoff remains on the planning board, subject to the readiness review. Owners should flag any required spend before committing funds.",
        ),
        (
            "Meeting 03 — Release timeline",
            "The launch target is October, following a review of integration testing and the remaining accessibility work. Engineering needs two additional weeks to complete end-to-end checks, and support asked for time to rehearse the escalation path. Product will update the milestone tracker and circulate a revised schedule. Marketing should hold public announcements until the readiness review confirms the date. This timeline differs from the September target discussed at kickoff. The team did not record a final decision reconciling those dates, so the project lead will bring both schedules to the next steering meeting. The budget freeze remains in effect.",
        ),
        (
            "Meeting 04 — Marketing alignment",
            "Marketing needs agreement on the launch message and audience by August. The team reviewed the draft announcement, customer examples, and the internal FAQ. Product will confirm terminology and remove features that are not in the release scope. Support will provide the known-issues summary, while design checks that the screenshots match the current build. The September target from the kickoff is still listed in one planning document, while the October target from the timeline review appears in another. The group requested one schedule of record before outreach begins. Marketing alignment is needed by August so that review and translation can finish on time.",
        ),
    )
    filler = "Owners will record decisions in the tracker and bring unresolved questions to the next review."
    blocks = []
    for heading, body in notes:
        words = body.split()
        while len(words) < 200:
            words.extend(filler.split()[: 200 - len(words)])
        blocks.append(f"{heading}\n{' '.join(words[:200])}")
    return "\n\n".join(blocks) + "\n"


def _fixture_bytes(task_id: str, name: str) -> dict[str, bytes]:
    key = (task_id, name)
    if key in TEXTS:
        return {name: TEXTS[key].encode("utf-8")}
    if key in PDFS:
        return {name: _pdf_bytes(PDFS[key])}
    if name.endswith(".csv"):
        return {name: _table_bytes(name)}
    if name.endswith(".jpg"):
        return {name: _image_bytes(task_id, name)}
    if key in TREE_FILES:
        return {path: content.encode("utf-8") for path, content in TREE_FILES[key].items()}
    if task_id == "ru-v1-006" and name == "meeting_notes_01-04.txt":
        return {name: _meeting_notes().encode("utf-8")}
    raise ValueError(f"no fixture generator for {task_id}:{name}")


def _read_draft(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _records(tasks: list[dict]) -> tuple[dict[str, bytes], str]:
    records: dict[str, bytes] = {}
    suite = []
    for task in tasks:
        row = dict(task)
        references = []
        for fixture in task.get("fixtures", []):
            name = fixture["name"]
            for relative, content in sorted(_fixture_bytes(task["id"], name).items()):
                path = (FIXTURE_PREFIX / task["id"] / relative).as_posix()
                if path in records:
                    raise ValueError(f"duplicate fixture path: {path}")
                records[path] = content
                references.append(path)
        row["fixtures"] = references
        suite.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return records, "\n".join(suite) + "\n"


def build(
    artifact_dir: Path = ARTIFACTS,
    output_path: Path = OUT,
    draft_path: Path = DRAFT,
) -> int:
    tasks = _read_draft(draft_path)
    records, suite_text = _records(tasks)
    fixture_root = artifact_dir / "fixtures"
    for relative, content in records.items():
        path = fixture_root / Path(relative).relative_to(FIXTURE_PREFIX)
        path.parent.mkdir(parents=True, exist_ok=True)
        publish_bytes(path, content)
    manifest = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {path}\n" for path, data in sorted(records.items())
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    publish_text(artifact_dir / "manifest.sha256", manifest)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    publish_text(output_path, suite_text)
    return len(records)


def _check_csv(task_id: str, name: str, data: bytes) -> None:
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8"))))
    expected_rows = {
        "customers_20k.csv": 20000,
        "team_output_q3.csv": 12,
        "customer_feedback.csv": 500,
        "internal_ai_survey.csv": 50,
    }[name]
    assert len(rows) == expected_rows
    assert list(rows[0]) == CSV_HEADERS[name]
    if name == "team_output_q3.csv":
        week_totals = [sum(int(row[f"week_{week}"]) for row in rows) for week in range(1, 14)]
        assert week_totals[6] * 10 == week_totals[5] * 6
        assert all(int(row["week_7"]) == 0 for row in rows if row["project"] == "Design")
    if name == "customer_feedback.csv":
        averages = {
            region: sum(int(row["rating"]) for row in rows if row["region"] == region)
            / sum(row["region"] == region for row in rows)
            for region in ("north", "south", "east", "west")
        }
        low = {
            product: sum(int(row["rating"]) <= 2 for row in rows if row["product_line"] == product)
            for product in "ABCD"
        }
        assert round(averages["north"], 1) == 3.2
        assert averages["north"] < min(averages[region] for region in ("south", "east", "west"))
        assert low["C"] > max(low[product] for product in "ABD")
    if name == "internal_ai_survey.csv":
        assert sum(row["adopted"] == "yes" for row in rows) == 14
        use_case_rows = [row for row in rows if row["use_case_responded"] == "yes"]
        barrier_rows = [row for row in rows if row["barrier_responded"] == "yes"]
        assert len(use_case_rows) == len(barrier_rows) == 40
        assert sum(row["customer_support"] == "yes" for row in use_case_rows) == 24
        assert sum(row["content_creation"] == "yes" for row in use_case_rows) == 8
        assert sum(row["analysis"] == "yes" for row in use_case_rows) == 6
        assert sum(row["barrier_cost"] == "yes" for row in barrier_rows) == 16
        assert sum(row["barrier_lack_expertise"] == "yes" for row in barrier_rows) == 14
    if task_id == "ru-v1-005":
        assert rows[0]["id"] == "10000" and rows[-1]["id"] == "29999"


def _check_image(task_id: str, name: str, data: bytes) -> None:
    with Image.open(io.BytesIO(data)) as image:
        assert image.format == "JPEG"
        sizes = {
            "invoice_scan.jpg": (640, 420),
            "office_sign.jpg": (760, 420),
            "team_photo.jpg": (760, 390),
            "dashboard_screenshot.jpg": (760, 440),
        }
        assert image.size == sizes[name]
        rgb = image.convert("RGB")
        if name == "invoice_scan.jpg":
            assert sum(ImageStat.Stat(rgb.crop((300, 310, 520, 360))).mean) > 200
            assert max(ImageStat.Stat(rgb.crop((140, 150, 320, 194))).stddev) < 70
        elif name == "office_sign.jpg":
            font = _font(32)
            dash_x = 158 + int(font.getlength("Portal 5 ")) + 2
            red, green, blue = rgb.getpixel((dash_x + 6, 293))
            assert red > 210 and green > 210 and blue > 210
        elif name == "team_photo.jpg":
            pixels = [rgb.getpixel((56 + i * 142 + 60, 200)) for i in range(5)]
            assert len(pixels) == 5 and len(set(pixels)) == 5
            badge_pixels = [rgb.getpixel((56 + i * 142 + 75, 152)) for i in range(4)]
            assert all(
                red > 180 and green > 150 and blue < 180 for red, green, blue in badge_pixels
            )
        elif name == "dashboard_screenshot.jpg":
            red, green, blue = rgb.getpixel((50, 40))
            assert red > 130 and green < 70 and blue < 80


def _check_pdf(task_id: str, name: str, data: bytes) -> None:
    import pdfplumber

    assert data.startswith(b"%PDF-1.4")
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        assert len(pdf.pages) == len(PDFS[(task_id, name)])
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert all(marker in text for marker in PDF_MARKERS[(task_id, name)])
    if task_id == "ru-v1-004":
        assert "international" not in text.lower()


def _check_bug_repos(records: dict[str, bytes]) -> None:
    for task_id, (source_name, test_name, fixes) in REFERENCE_FIXES.items():
        prefix = f"{FIXTURE_PREFIX.as_posix()}/{task_id}/"
        source = next(
            data
            for path, data in records.items()
            if path.startswith(prefix) and path.endswith("/" + source_name)
        )
        test = next(
            data
            for path, data in records.items()
            if path.startswith(prefix) and path.endswith("/" + test_name)
        )
        with tempfile.TemporaryDirectory(prefix=f"{task_id}-") as directory:
            sandbox = Path(directory)
            source_path = sandbox / source_name
            test_path = sandbox / test_name
            source_path.write_bytes(source)
            test_path.write_bytes(test)
            before = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", test_name],
                cwd=sandbox,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert before.returncode != 0, f"{task_id} must fail before the reference fix"
            fixed = source.decode("utf-8")
            for old, new in fixes:
                assert fixed.count(old) == 1
                fixed = fixed.replace(old, new)
            source_path.write_text(fixed, encoding="utf-8")
            after = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", test_name],
                cwd=sandbox,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert after.returncode == 0, (
                f"{task_id} failed after its reference fix: {after.stdout}{after.stderr}"
            )


def self_check(
    artifact_dir: Path = ARTIFACTS,
    output_path: Path = OUT,
    draft_path: Path = DRAFT,
) -> int:
    tasks = _read_draft(draft_path)
    records, suite_text = _records(tasks)
    fixture_root = artifact_dir / "fixtures"
    manifest_lines = []
    for relative, expected in sorted(records.items()):
        path = fixture_root / Path(relative).relative_to(FIXTURE_PREFIX)
        actual = path.read_bytes()
        assert actual == expected, f"fixture differs from declarative spec: {path}"
        manifest_lines.append(f"{hashlib.sha256(actual).hexdigest()}  {relative}\n")
        name = Path(relative).name
        path_parts = Path(relative).parts
        task_id = path_parts[path_parts.index("fixtures") + 1]
        if name.endswith(".csv"):
            _check_csv(task_id, name, actual)
        elif name.endswith(".pdf"):
            _check_pdf(task_id, name, actual)
        elif name.endswith(".jpg"):
            _check_image(task_id, name, actual)
        else:
            text = actual.decode("utf-8")
            assert text.strip()
            for marker in TEXT_MARKERS.get((task_id, name), ()):
                assert marker in text, f"missing {marker!r} in {relative}"
            if task_id == "ru-v1-010":
                assert len(text.splitlines()) == 10
                assert text.lower().count("urgent") == 2 and text.lower().count("priority") == 1
            if task_id == "ru-v1-005" and name == "process_customers.py":
                assert len(text.splitlines()) == 48
                assert (
                    ".apply(" in text
                    and "pd.read_csv" in text
                    and "range(0, len(data), 100)" in text
                )
            if task_id == "ru-v1-011" and name == "calc.py":
                assert text.splitlines()[14].strip() == "for value in range(1, n):"
            if task_id == "ru-v1-014" and name == "auth.py":
                assert len(text.splitlines()) == 28
            if task_id == "ru-v1-016" and name == "app.py":
                lines = text.splitlines()
                assert len(lines) == 44
                assert lines[17].strip() == "CACHE.append(request_label)"
                assert lines[41].strip().startswith("handle = open(path")
            if task_id == "ru-v1-006" and name == "meeting_notes_01-04.txt":
                blocks = text.rstrip().split("\n\n")
                assert len(blocks) == 4 and all(
                    len(block.split("\n", 1)[1].split()) == 200 for block in blocks
                )
                assert "September" in blocks[0] and "October" in blocks[2]
    assert (artifact_dir / "manifest.sha256").read_text(encoding="utf-8") == "".join(manifest_lines)
    assert output_path.read_text(encoding="utf-8") == suite_text
    assert len(tasks) == 35 and len(records) >= 40
    _check_bug_repos(records)
    return len(records)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="verify the published suite and fixtures"
    )
    parser.add_argument("--self-check", action="store_true", help="build and verify all fixtures")
    args = parser.parse_args()
    if not args.check:
        count = build()
        if not args.self_check:
            print(f"built {count} fixture files and {OUT}")
            return
    count = self_check()
    print(f"self-check passed for {count} fixture files")


if __name__ == "__main__":
    main()
