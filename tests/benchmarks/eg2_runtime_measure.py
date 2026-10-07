import base64
import io
import json
import statistics
import subprocess
import sys
import time

import httpx

sys.path.insert(0, "/Users/chris/projects/portal-5")
from PIL import Image, ImageDraw

from portal.platform.embedding import contract as ec

EG2 = "http://localhost:8946"
OL = "http://localhost:11434"


def rss(pat):
    out = subprocess.run(["pgrep", "-f", pat], capture_output=True, text=True).stdout.split()
    return (
        max(
            (
                int(
                    subprocess.run(
                        ["ps", "-o", "rss=", "-p", p], capture_output=True, text=True
                    ).stdout.strip()
                    or 0
                )
                for p in out
            ),
            default=0,
        )
        / 1024
    )


texts = [
    f"Substation relay {i} protects feeder {i % 7}; the NERC CIP-007 patch cadence requires review every {30 + i % 5} days."
    for i in range(256)
]


def eg2_text(n):
    r = httpx.post(
        f"{EG2}/embed",
        json={
            "inputs": [{"text": t} for t in texts[:n]],
            "task": "search",
            "role": "document",
            "dim": 768,
        },
        timeout=300,
    )
    r.raise_for_status()
    return r.json()


def ol_text(n, model="embeddinggemma-2:740m-mxfp8", dim=None):
    body = {
        "model": model,
        "input": [ec.format_text(t, ec.Task.SEARCH, ec.Role.DOCUMENT) for t in texts[:n]],
        "keep_alive": "30m",
    }
    r = httpx.post(f"{OL}/api/embed", json=body, timeout=300)
    r.raise_for_status()
    return r.json()["embeddings"]


def tps(fn, n, reps=3):
    fn(n)
    ts = []
    for _ in range(reps):
        t = time.time()
        fn(n)
        ts.append(time.time() - t)
    return n / statistics.median(ts)


res = {}
print(
    "EG2 resp keys:",
    list(eg2_text(2).keys()) if isinstance(eg2_text(2), dict) else type(eg2_text(2)),
)
res["eg2_tps"] = {b: round(tps(eg2_text, b), 1) for b in (8, 32, 64)}
res["ollama_tps"] = {b: round(tps(ol_text, b), 1) for b in (8, 32, 64)}
res["rss_eg2_mb"] = round(rss("eg2-embedding-server.py --port 8946"), 0)
# media
img = Image.new("RGB", (512, 512), "white")
d = ImageDraw.Draw(img)
d.rectangle([100, 100, 400, 400], fill="red")
d.ellipse([200, 200, 300, 300], fill="blue")
b = io.BytesIO()
img.save(b, "PNG")
imgb = base64.b64encode(b.getvalue()).decode()
aud = base64.b64encode(open("/tmp/eg2_m/s1.wav", "rb").read()).decode()


def lat(f, reps=3):
    f()
    ts = []
    for _ in range(reps):
        t = time.time()
        f()
        ts.append(time.time() - t)
    return round(statistics.median(ts), 3)


def eg2_item(k, v):
    r = httpx.post(f"{EG2}/embed_items", json={"items": [{k: v}], "dim": 768}, timeout=300)
    r.raise_for_status()
    return r.json()


def ol_item(k, v):
    r = httpx.post(
        f"{OL}/api/embed",
        json={"model": "embeddinggemma-2:740m-mxfp8", "input": [{k: v}], "keep_alive": "30m"},
        timeout=300,
    )
    r.raise_for_status()
    return r.json()


print("eg2 item keys sample:", json.dumps(eg2_item("image_b64", imgb))[:200])
res["eg2_image_s"] = lat(lambda: eg2_item("image_b64", imgb))
res["eg2_audio_s"] = lat(lambda: eg2_item("audio_b64", aud))
res["ol_image_s"] = lat(lambda: ol_item("image", imgb))
res["ol_audio_s"] = lat(lambda: ol_item("audio", aud))
print(json.dumps(res, indent=1))
json.dump(res, open("/tmp/eg2_m/runtime.json", "w"))
