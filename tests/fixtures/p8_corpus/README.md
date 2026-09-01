# P8 diagram-only retrieval corpus (TASK_VL_RUNTIME_LANDING_V4)

The script below regenerates three synthetic PDFs whose diagram content (valve
tags, interlock setpoints, firewall rules, alarm states) appears **only** as a
rendered image on page 2 — never in the page-1 prose. Ground truth for the
"a diagram-only query returns that page" P8 acceptance check.

Real-world companions used in the P8 run (not committed — fetch fresh):
- NIST SP 800-82r3  <https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-82r3.pdf>  (architecture-figure slice, pages ~91-113)
- NERC CIP-005-7    <https://www.nerc.com/pa/Stand/Reliability%20Standards/CIP-005-7.pdf>

Results: `reports/runtime/p8_measurements.json`

```python
"""P8 — build a small PDF corpus where diagram content is NOT in the prose."""
import io
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

OUT = Path("/private/tmp/claude-501/-Users-chris-projects-portal-5/26f8ad8d-f0ef-45cc-9cac-8e0b07c4ead4/scratchpad/p8_corpus")
OUT.mkdir(parents=True, exist_ok=True)

try:
    F = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 22)
    FS = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 16)
except Exception:
    F = FS = ImageFont.load_default()


def pid_diagram() -> Image.Image:
    im = Image.new("RGB", (1400, 1000), "white")
    d = ImageDraw.Draw(im)
    d.text((40, 20), "FIGURE 3-1  Reactor Feed Loop  (P&ID sheet 3 of 7)", font=F, fill="black")
    # tank
    d.rectangle([120, 200, 320, 520], outline="black", width=3)
    d.text((150, 350), "V-204\nSurge Drum", font=FS, fill="black")
    # piping
    d.line([320, 360, 700, 360], fill="black", width=3)
    d.ellipse([690, 330, 750, 390], outline="black", width=3)
    d.text((660, 400), "FV-101", font=FS, fill="black")
    d.text((600, 430), "air-to-open / fail-closed", font=FS, fill="red")
    d.line([750, 360, 1100, 360], fill="black", width=3)
    d.rectangle([1100, 300, 1300, 460], outline="black", width=3)
    d.text((1130, 360), "P-201\nFeed Pump", font=FS, fill="black")
    # instrument bubbles
    d.ellipse([480, 120, 560, 200], outline="black", width=2)
    d.text((495, 150), "FIC\n101", font=FS, fill="black")
    d.line([520, 200, 520, 340], fill="black", width=1)
    d.ellipse([300, 560, 380, 640], outline="black", width=2)
    d.text((315, 590), "LT\n204", font=FS, fill="black")
    d.text((40, 720), "Interlock I-3:  LT-204 HH  ->  close XV-205, trip P-201  (manual reset at local panel)",
           font=FS, fill="black")
    d.text((40, 760), "Setpoint: FIC-101 = 47.5 gpm    Trip: LT-204 = 92%", font=FS, fill="black")
    return im


def zone_diagram() -> Image.Image:
    im = Image.new("RGB", (1400, 900), "white")
    d = ImageDraw.Draw(im)
    d.text((40, 20), "FIGURE 5-2  Electronic Security Perimeter — Plant B", font=F, fill="black")
    d.rectangle([60, 100, 660, 820], outline="blue", width=3)
    d.text((80, 110), "ESP-B  (10.20.0.0/16)", font=FS, fill="blue")
    d.rectangle([100, 180, 400, 360], outline="black", width=2)
    d.text((120, 240), "HMI-B1  10.20.4.11", font=FS, fill="black")
    d.rectangle([100, 420, 400, 600], outline="black", width=2)
    d.text((120, 480), "PLC-B7  10.20.8.30  (rack 0 / slot 2)", font=FS, fill="black")
    d.rectangle([760, 300, 1320, 620], outline="green", width=3)
    d.text((780, 310), "Corporate  (10.99.0.0/16)", font=FS, fill="green")
    d.line([660, 400, 760, 400], fill="red", width=4)
    d.ellipse([690, 360, 740, 410], outline="red", width=3)
    d.text((620, 640), "FW-B  allows: TCP 502 inbound from 10.99.7.5 only; all else deny", font=FS, fill="red")
    return im


def hmi_diagram() -> Image.Image:
    im = Image.new("RGB", (1400, 900), (12, 24, 40))
    d = ImageDraw.Draw(im)
    d.text((40, 20), "FIGURE 7-4  Alarm Summary Page — Unit 2", font=F, fill="white")
    rows = [
        ("07:14:22", "PAH-2201  Discharge pressure HIGH", "UNACK", "red"),
        ("07:15:03", "TAH-2240  Bearing temp HIGH-HIGH", "ACK", "yellow"),
        ("07:16:41", "LAL-2118  Seal pot level LOW", "RTN", "white"),
    ]
    y = 120
    for ts, txt, st, col in rows:
        d.text((60, y), f"{ts}  {txt}", font=FS, fill=col)
        d.text((1180, y), st, font=FS, fill=col)
        y += 60
    d.text((60, 360), "Standing alarms: 1 unacknowledged, 1 acknowledged-active", font=FS, fill="white")
    d.text((60, 400), "Shelved: MAL-2302 (shelved 06:02, expires 14:02)", font=FS, fill="white")
    return im


PROSE = {
    "reactor_feed": (
        "This procedure governs periodic proof testing of safety instrumented functions in the "
        "olefins unit. Testing frequency is derived from the SIL verification calculation and "
        "documented in the safety requirements specification. Each test must be witnessed by a "
        "second qualified technician and the bypass log reviewed by the shift supervisor before "
        "any function is returned to service. Records are retained for the life of the facility. "
        "The maintenance planning group schedules the tests to coincide with unit turnarounds "
        "where possible to minimize the number of online bypasses."
    ),
    "esp_plant_b": (
        "The organization shall maintain documentation of every Electronic Security Perimeter and "
        "review it at least once every fifteen calendar months. Changes to perimeter access "
        "permissions follow the change management process and require approval from the OT security "
        "lead. This section does not enumerate individual assets or addresses; the authoritative "
        "inventory is maintained separately in the asset management system and reconciled quarterly."
    ),
    "alarm_summary": (
        "Alarm rationalization is a continuous improvement activity. The alarm management philosophy "
        "defines priority assignment, the maximum acceptable alarm rate per operator position, and "
        "the process for adding, modifying, or removing a configured alarm. Nuisance alarms "
        "identified in the monthly performance report are entered into the rationalization backlog. "
        "This document describes the governance process only and contains no live alarm data."
    ),
}

specs = [
    ("reactor_feed.pdf", "reactor_feed", pid_diagram()),
    ("esp_plant_b.pdf", "esp_plant_b", zone_diagram()),
    ("alarm_summary.pdf", "alarm_summary", hmi_diagram()),
]

for fname, key, img in specs:
    doc = pymupdf.open()
    # page 1: prose only
    p1 = doc.new_page(width=612, height=792)
    p1.insert_textbox(pymupdf.Rect(54, 72, 558, 720), PROSE[key], fontsize=11, fontname="helv")
    # page 2: the diagram (rendered image), minimal caption
    p2 = doc.new_page(width=612, height=792)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    p2.insert_image(pymupdf.Rect(36, 60, 576, 60 + 540 * img.height / img.width), stream=buf.getvalue())
    p2.insert_textbox(pymupdf.Rect(54, 620, 558, 720), f"See {fname} figure. Details on the drawing.",
                      fontsize=10, fontname="helv")
    doc.save(str(OUT / fname))
    doc.close()
    print("wrote", OUT / fname)
print("corpus at", OUT)
```
