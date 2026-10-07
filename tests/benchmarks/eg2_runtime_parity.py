"""Parity of Ollama embeddinggemma-2 vs the :8946 service. Inputs (texts.txt: one sentence
per line from canonical units; a1..a5.wav TTS clips) live in /tmp/eg2_m — see RUNTIME.md."""

import base64
import io
import json
import math
import random
import statistics
import sys

import httpx

sys.path.insert(0, "/Users/chris/projects/portal-5")
from PIL import Image, ImageDraw

from portal.platform.embedding import contract as ec

EG2 = "http://localhost:8946"
OL = "http://localhost:11434"


def cos(a, b):
    return sum(x * y for x, y in zip(a, b, strict=False)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    )


texts = [ln.strip() for ln in open("/tmp/eg2_m/texts.txt") if ln.strip()][:80]


def eg2_texts(ts, role):
    return httpx.post(
        f"{EG2}/embed",
        json={"inputs": [{"text": t} for t in ts], "task": "search", "role": role, "dim": 768},
        timeout=300,
    ).json()["embeddings"]


def ol_texts(ts, role, model):
    body = {
        "model": model,
        "input": [ec.format_text(t, ec.Task.SEARCH, ec.Role(role)) for t in ts],
        "keep_alive": "30m",
    }
    return httpx.post(f"{OL}/api/embed", json=body, timeout=300).json()["embeddings"]


out = {}
for model in ("embeddinggemma-2:740m-mxfp8",):
    for role in ("document", "query"):
        e = eg2_texts(texts, role)
        o = ol_texts(texts, role, model)
        c = [cos(a, b) for a, b in zip(e, o, strict=False)]
        out[f"{model}|text-{role}"] = {
            "n": len(c),
            "mean": round(statistics.mean(c), 4),
            "min": round(min(c), 4),
        }
    # rank parity: query->doc ranking agreement
    qe = eg2_texts(texts[:20], "query")
    de = eg2_texts(texts, "document")
    qo = ol_texts(texts[:20], "query", model)
    do = ol_texts(texts, "document", model)
    agree = 0
    for a, b in zip(qe, qo, strict=False):
        ra = max(range(len(de)), key=lambda i: cos(a, de[i]))
        rb = max(range(len(do)), key=lambda i: cos(b, do[i]))
        agree += ra == rb
    out[f"{model}|top1-agreement"] = f"{agree}/20"
    # images
    random.seed(1)
    ims = []
    for k in range(12):
        im = Image.new(
            "RGB",
            (384, 384),
            (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)),
        )
        d = ImageDraw.Draw(im)
        for _ in range(4):
            d.rectangle(
                [
                    random.randint(0, 200),
                    random.randint(0, 200),
                    random.randint(200, 380),
                    random.randint(200, 380),
                ],
                fill=tuple(random.randint(0, 255) for _ in range(3)),
            )
        d.text((20, 20), f"fig {k}", fill="black")
        b = io.BytesIO()
        im.save(b, "PNG")
        ims.append(base64.b64encode(b.getvalue()).decode())
    ce = []
    for b64 in ims:
        e = httpx.post(
            f"{EG2}/embed_items", json={"items": [{"image_b64": b64}], "dim": 768}, timeout=300
        ).json()["embeddings"][0]
        o = httpx.post(
            f"{OL}/api/embed",
            json={"model": model, "input": [{"image": b64}], "keep_alive": "30m"},
            timeout=300,
        ).json()["embeddings"][0]
        ce.append(cos(e, o))
    out[f"{model}|image"] = {
        "n": len(ce),
        "mean": round(statistics.mean(ce), 4),
        "min": round(min(ce), 4),
    }
    ca = []
    for i in range(1, 6):
        b64 = base64.b64encode(open(f"/tmp/eg2_m/a{i}.wav", "rb").read()).decode()
        e = httpx.post(
            f"{EG2}/embed_items", json={"items": [{"audio_b64": b64}], "dim": 768}, timeout=300
        ).json()["embeddings"][0]
        o = httpx.post(
            f"{OL}/api/embed",
            json={"model": model, "input": [{"audio": b64}], "keep_alive": "30m"},
            timeout=300,
        ).json()["embeddings"][0]
        ca.append(cos(e, o))
    out[f"{model}|audio"] = {
        "n": len(ca),
        "mean": round(statistics.mean(ca), 4),
        "min": round(min(ca), 4),
    }
    # MRL dims
    e = eg2_texts(texts[:20], "document")
    o = ol_texts(texts[:20], "document", model)
    for d in (512, 256, 128):

        def tr(v, d=d):
            t = v[:d]
            n = math.sqrt(sum(x * x for x in t))
            return [x / n for x in t]

        out[f"{model}|text-doc-dim{d}"] = {
            "mean": round(statistics.mean(cos(tr(a), tr(b)) for a, b in zip(e, o, strict=False)), 4)
        }
print(json.dumps(out, indent=1))
json.dump(out, open("/tmp/eg2_m/parity.json", "w"))
