"""Code-and-feed security probes: binary_similarity, vuln_severity, ics_advisories."""

from __future__ import annotations

import json
import math
import re
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

from portal.platform.embedding.contract import Role, Task

from ..framework import (
    MEASURED,
    ProbeContext,
    ProbeResult,
    blocked,
    compare,
    fixture_digest,
    macro_f1,
    mrr,
    probe,
    recall_at_k,
    top_k_by_cosine,
)
from ._common import DATA, retrieval_ab

_HEX = re.compile(r"#?-?0x[0-9a-f]+|\b\d+\b")


def _functions(obj: Path) -> dict[str, str]:
    """name -> normalised disassembly (addresses/immediates/branch targets masked, names stripped)."""
    syms = subprocess.run(
        ["nm", "-n", str(obj)], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    starts = sorted(
        (int(ln.split()[0], 16), ln.split()[-1].lstrip("_")) for ln in syms if " T " in ln
    )
    dis = subprocess.run(
        ["objdump", "-d", "--no-show-raw-insn", str(obj)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    insns: list[tuple[int, str]] = []
    for ln in dis.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\s+(.*)", ln)
        if m:
            body = m.group(2).split(";")[0].strip()
            insns.append((int(m.group(1), 16), _HEX.sub("N", re.sub(r"<[^>]*>", "", body))))
    out = {}
    for i, (a, name) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else 10**12
        out[name] = "\n".join(t for addr, t in insns if a <= addr < end)
    return out


def _bag_cos(a: str, b: str) -> float:
    ca, cb = Counter(a.split()), Counter(b.split())
    dot = sum(ca[k] * cb[k] for k in ca)
    return dot / (
        math.sqrt(sum(v * v for v in ca.values())) * math.sqrt(sum(v * v for v in cb.values())) or 1
    )


@probe("binary_similarity")
async def binary_similarity(ctx: ProbeContext) -> ProbeResult:
    src = DATA / "binary_similarity.c"
    with tempfile.TemporaryDirectory() as td:
        objs = {}
        for lvl in ("O0", "O2"):
            o = Path(td) / f"{lvl}.o"
            r = subprocess.run(
                ["cc", "-arch", "arm64", f"-{lvl}", "-c", str(src), "-o", str(o)],
                capture_output=True,
                text=True,
            )
            if r.returncode:
                return blocked("binary_similarity", f"cc failed: {r.stderr[:200]}")
            objs[lvl] = _functions(o)
    names = sorted(set(objs["O0"]) & set(objs["O2"]))
    if len(names) < 20:
        return blocked("binary_similarity", f"only {len(names)} comparable functions")
    res: dict[str, Any] = {}
    for q_lvl, d_lvl in (("O0", "O2"), ("O2", "O0")):
        q = [objs[q_lvl][n] for n in names]
        inc_rank = [
            sorted(names, key=lambda m, qi=qi: -_bag_cos(qi, objs[d_lvl][m]))[:10] for qi in q
        ]
        res[f"{q_lvl}->{d_lvl}"] = await retrieval_ab(
            ctx,
            q,
            [[n] for n in names],
            names,
            [objs[d_lvl][n] for n in names],
            task=Task.CODE_RETRIEVAL,
            incumbent_rank=inc_rank.__getitem__,
        )
    cand5 = sum(v["candidate"]["recall@5"] for v in res.values()) / len(res)
    inc5 = sum(v["incumbent"]["recall@5"] for v in res.values()) / len(res)
    return ProbeResult(
        "binary_similarity",
        MEASURED,
        {
            "primary": round(inc5, 4),
            "note": "no similarity search exists; value is a mnemonic bag-of-tokens cosine reference",
            **{k: v["incumbent"] for k, v in res.items()},
        },
        {"primary": round(cand5, 4), **{k: v["candidate"] for k, v in res.items()}},
        compare(inc5, cand5),
        fixture={"functions": len(names), "sha": fixture_digest(objs["O2"]), "arch": "arm64"},
        identity=await ctx.client.version_tag(768),
        notes=[
            "arm64 objdump disassembly (addresses, immediates, symbols masked) stands in for decompiler pseudocode: the binresearch module's Ghidra path needs its 7 GB container and the examples ship no function pairs; matched across -O0/-O2 of the same source"
        ],
    )


# ── vuln_severity ───────────────────────────────────────────────────────────

NVD = "https://services.nvd.nist.gov/rest/json/cves/2.0"
SCRATCH = Path("/Volumes/data01/portal5_scratch_eg2")


#: The incumbent's local snapshot and the date its training data ends (HF commit date). The test
#: window starts after it, so neither arm has seen a test CVE. A different local revision blocks the
#: probe until this pin is updated.
CIRCL_REVISION = "321fe6288a43d3a231bc0c06b92be733f97e611f"
CIRCL_TRAINED_THROUGH = "2026-08-28"
CIRCL_CACHE = Path(
    "/Volumes/data01/hf-cache/models--CIRCL--vulnerability-severity-classification-roberta-base"
)
#: Recency-matched to the incumbent: the EG2 head trains on CVEs published in the months right
#: before CIRCL_TRAINED_THROUGH, so neither arm's training data is further from the test window than
#: the other's. Training on 2024-2025 instead handed the candidate a 1-2 year distribution shift the
#: continuously-retrained incumbent does not carry.
TRAIN_WINDOWS = [
    ("2026-03-01T00:00:00.000", "2026-06-01T00:00:00.000"),
    ("2026-06-01T00:00:00.000", "2026-08-28T00:00:00.000"),
]
TEST_WINDOW = ("2026-08-29T00:00:00.000", "2026-10-06T00:00:00.000")
_LABELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def _nvd_window(c: httpx.Client, a: str, b: str, max_pages: int = 3) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in range(max_pages):
        r = c.get(
            NVD,
            params={
                "pubStartDate": a,
                "pubEndDate": b,
                "resultsPerPage": 2000,
                "startIndex": page * 2000,
            },
        )
        r.raise_for_status()
        body = r.json()
        for v in body.get("vulnerabilities", []):
            cve = v["cve"]
            desc = next((d["value"] for d in cve.get("descriptions", []) if d["lang"] == "en"), "")
            m = (cve.get("metrics", {}).get("cvssMetricV31") or [{}])[0].get("cvssData", {})
            sev = m.get("baseSeverity")
            if sev in _LABELS and len(desc) > 40:
                out.append({"id": cve["id"], "desc": desc, "severity": sev})
        if (page + 1) * 2000 >= int(body.get("totalResults", 0)):
            break
        time.sleep(7)  # unauthenticated NVD rate limit: 5 requests / 30 s
    return out


def _nvd_split(per_class_train: int = 300, per_class_test: int = 60) -> tuple[list, list]:
    cache = SCRATCH / f"nvd_split_{CIRCL_TRAINED_THROUGH}_recency.json"
    if cache.is_file():
        d = json.loads(cache.read_text())
        return d["train"], d["test"]
    import random

    rng = random.Random(7)

    def stratify(rows: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
        by: dict[str, list[dict[str, Any]]] = {k: [] for k in _LABELS}
        for r in rows:
            by[r["severity"]].append(r)
        out = []
        for v in by.values():
            rng.shuffle(v)
            out += v[:n]
        return out

    with httpx.Client(timeout=180) as c:
        pool: list[dict[str, Any]] = []
        for a, b in TRAIN_WINDOWS:
            pool += _nvd_window(c, a, b)
            time.sleep(7)
        test_pool = _nvd_window(c, *TEST_WINDOW, max_pages=10)
    train, test = stratify(pool, per_class_train), stratify(test_pool, per_class_test)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"train": train, "test": test}))
    return train, test


_ROBERTA = """
import json, sys
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
name = "CIRCL/vulnerability-severity-classification-roberta-base"
tok = AutoTokenizer.from_pretrained(name); mod = AutoModelForSequenceClassification.from_pretrained(name).eval()
labels = ["low", "medium", "high", "critical"]
rows = json.load(open(sys.argv[1])); out = []
for r in rows:
    x = tok(r["desc"], return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        out.append(labels[int(mod(**x).logits.argmax(-1))].upper())
json.dump(out, open(sys.argv[2], "w"))
"""


@probe("vuln_severity")
async def vuln_severity(ctx: ProbeContext) -> ProbeResult:
    import numpy as np
    from sklearn.linear_model import LogisticRegressionCV
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    ref = CIRCL_CACHE / "refs" / "main"
    if ref.is_file() and ref.read_text().strip() != CIRCL_REVISION:
        return blocked(
            "vuln_severity",
            f"local CIRCL revision {ref.read_text().strip()[:12]} != pinned {CIRCL_REVISION[:12]}; "
            "update CIRCL_REVISION/CIRCL_TRAINED_THROUGH so the test window stays post-training",
        )
    try:
        train, test = _nvd_split()
    except Exception as e:  # noqa: BLE001
        return blocked("vuln_severity", f"NVD fetch failed: {type(e).__name__}: {e}")
    per_test = Counter(r["severity"] for r in test)
    if len(test) < 80 or min(per_test.get(k, 0) for k in _LABELS) < 10:
        return blocked("vuln_severity", f"post-training test window too thin: {dict(per_test)}")
    texts = [r["desc"][:1500] for r in (*train, *test)]
    vec = np.asarray(
        await ctx.client.embed_texts(texts, task=Task.CLASSIFICATION, dim=768), dtype=np.float64
    )
    xtr, xte = vec[: len(train)], vec[len(train) :]
    ytr = np.array([_LABELS.index(r["severity"]) for r in train])
    head = make_pipeline(
        StandardScaler(), LogisticRegressionCV(Cs=[0.01, 0.1, 1.0, 10.0], cv=5, max_iter=5000)
    ).fit(xtr, ytr)
    pred_eg2 = [_LABELS[i] for i in head.predict(xte)]
    py = Path("/Users/chris/.portal5/eg2-venv/bin/python3")
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "in.json").write_text(json.dumps(test))
        script = Path(td) / "rb.py"
        script.write_text(_ROBERTA)
        r = subprocess.run(
            [str(py), str(script), str(Path(td) / "in.json"), str(Path(td) / "out.json")],
            capture_output=True,
            text=True,
            env={"HF_HUB_OFFLINE": "1", "PATH": "/usr/bin:/bin", "HOME": str(Path.home())},
        )
        if r.returncode:
            return blocked("vuln_severity", f"incumbent RoBERTa could not run: {r.stderr[-200:]}")
        pred_inc = json.loads((Path(td) / "out.json").read_text())
    gold = [r["severity"] for r in test]
    inc = macro_f1(pred_inc, gold)
    cand = macro_f1(pred_eg2, gold)
    acc = lambda p: round(sum(a == b for a, b in zip(p, gold, strict=True)) / len(gold), 4)  # noqa: E731
    return ProbeResult(
        "vuln_severity",
        MEASURED,
        {
            "primary": round(inc, 4),
            "accuracy": acc(pred_inc),
            "model": "CIRCL/vulnerability-severity-classification-roberta-base",
            "revision": CIRCL_REVISION[:12],
        },
        {
            "primary": round(cand, 4),
            "accuracy": acc(pred_eg2),
            "head": "standardized logistic regression (C by 5-fold CV) on EG2 CLASSIFICATION 768d",
            "train": len(train),
            "test": len(test),
        },
        compare(inc, cand),
        fixture={
            "train_per_class": dict(Counter(r["severity"] for r in train)),
            "test_per_class": dict(per_test),
            "test_window": TEST_WINDOW,
            "sha": fixture_digest([r["id"] for r in (*train, *test)]),
        },
        identity=await ctx.client.version_tag(768),
        notes=[
            f"test CVEs published after the incumbent's training data ends ({CIRCL_TRAINED_THROUGH}), so neither arm has seen them; EG2 head trained on 2024-2025 NVD CVEs",
            "labels = NVD cvssMetricV31 baseSeverity (primary or CNA score); the incumbent was fine-tuned on ~600k CVEs, the EG2 head on the train split only",
            "train window is recency-matched to the incumbent's cutoff so neither arm eats a distribution shift the other does not",
        ],
    )


# ── ics_advisories ──────────────────────────────────────────────────────────


ICS_FEED = "https://www.cisa.gov/cybersecurity-advisories/ics-advisories.xml"
#: The feed `vulnintel_mcp.ics_advisories` pulls. Verified 404 on 2026-10-07 (see probe notes).
ICS_FEED_INCUMBENT = "https://www.cisa.gov/cybersecurity-advisories/all.json"


def _ics_feed() -> list[dict[str, str]]:
    """Live CISA ICS advisories (titles are ``<vendor> <product>``), cached for reproducibility."""
    import xml.etree.ElementTree as ET

    cache = SCRATCH / "cisa_ics_advisories.json"
    if cache.is_file():
        return json.loads(cache.read_text())
    with httpx.Client(timeout=120, follow_redirects=True) as c:
        r = c.get(ICS_FEED)
        r.raise_for_status()
        xml = r.text
    rows = []
    for it in ET.fromstring(xml).findall(".//item"):
        link = (it.findtext("link") or "").strip()
        title = (it.findtext("title") or "").strip()
        desc = re.sub(r"<[^>]+>", " ", (it.findtext("description") or "").strip())
        desc = re.sub(r"\s+", " ", desc).replace("View CSAF", "").strip()
        rows.append({"id": link.rstrip("/").split("/")[-1], "title": title, "desc": desc})
    SCRATCH.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(rows, indent=1))
    return rows


def _strip_identity(text: str, title: str) -> str:
    """Remove the vendor/product tokens from an advisory's own summary, so a query built from it
    carries only the functional description — what an asset inventory emitting protocol/role hints
    gives you, and the case the incumbent's vendor-substring match cannot serve."""
    out = text
    for tok in sorted(set(re.findall(r"[A-Za-z0-9][\w.-]+", title)), key=len, reverse=True):
        if len(tok) > 2:
            out = re.sub(re.escape(tok), " ", out, flags=re.I)
    return re.sub(r"\s+", " ", out).strip()


@probe("ics_advisories")
async def ics_advisories(ctx: ProbeContext) -> ProbeResult:
    """Advisory<->asset product matching on the live CISA ICS feed.

    Incumbent: ``vulnintel_mcp.ics_advisories``'s filter, ``vendor.lower() in title.lower()``.
    Candidate: EG2 SEARCH over the advisory text. Two mechanically derived query forms:
    ``product_string`` (the title verbatim — the case substring matching is built for) and
    ``description_only`` (the advisory's own summary with every vendor/product token removed — the
    case an asset inventory without a product field actually produces).
    """
    if not ctx.live:
        return blocked("ics_advisories", "needs --live (CISA feed + EG2 :8946)")
    try:
        rows = _ics_feed()
    except Exception as e:  # noqa: BLE001
        return blocked("ics_advisories", f"CISA ICS feed fetch failed: {type(e).__name__}: {e}")
    rows = [r for r in rows if r["id"] and r["title"] and len(r["desc"]) > 80]
    if len(rows) < 20:
        return blocked("ics_advisories", f"only {len(rows)} usable advisories in the feed")
    ids = [r["id"] for r in rows]
    docs_text = [f"{r['title']}: {r['desc'][:1200]}" for r in rows]
    forms = {
        "product_string": [r["title"] for r in rows],
        "description_only": [_strip_identity(r["desc"][:600], r["title"]) for r in rows],
    }

    # incumbent: the production substring filter, scored as a ranking (matches first, feed order)
    def substring_rank(query: str) -> list[str]:
        q = query.lower()
        hits = [
            r["id"] for r in rows if any(w in r["title"].lower() for w in q.split() if len(w) > 3)
        ]
        return hits + [i for i in ids if i not in hits]

    dv = await ctx.client.embed_texts(docs_text, task=Task.SEARCH, role=Role.DOCUMENT, dim=768)
    docs = dict(zip(ids, dv, strict=True))
    out: dict[str, Any] = {}
    for form, queries in forms.items():
        usable = [(q, i) for q, i in zip(queries, ids, strict=True) if len(q.split()) >= 3]
        qs = [q for q, _ in usable]
        gold = [[i] for _, i in usable]
        qv = await ctx.client.embed_texts(qs, task=Task.SEARCH, role=Role.QUERY, dim=768)
        cand = [top_k_by_cosine(v, docs, 5) for v in qv]
        inc = [substring_rank(q)[:5] for q in qs]
        out[form] = {
            "queries": len(qs),
            "incumbent": {
                "recall@1": round(recall_at_k(inc, gold, 1), 4),
                "recall@5": round(recall_at_k(inc, gold, 5), 4),
                "mrr": round(mrr(inc, gold), 4),
            },
            "candidate": {
                "recall@1": round(recall_at_k(cand, gold, 1), 4),
                "recall@5": round(recall_at_k(cand, gold, 5), 4),
                "mrr": round(mrr(cand, gold), 4),
            },
        }
    inc_p = round(sum(v["incumbent"]["recall@5"] for v in out.values()) / len(out), 4)
    cand_p = round(sum(v["candidate"]["recall@5"] for v in out.values()) / len(out), 4)
    return ProbeResult(
        "ics_advisories",
        MEASURED,
        {"primary": inc_p, **{k: v["incumbent"] for k, v in out.items()}},
        {"primary": cand_p, **{k: v["candidate"] for k, v in out.items()}},
        compare(inc_p, cand_p),
        fixture={
            "advisories": len(rows),
            "corpus": "live CISA ICS advisory feed (RSS caps at 30 most recent)",
            "sha": fixture_digest(ids),
        },
        identity=await ctx.client.version_tag(768),
        notes=[
            "primary = mean recall@5 over both query forms; corpus is only 30 advisories (the feed's cap), so treat absolute values as indicative and the product_string/description_only SPLIT as the finding",
            "DEFECT FOUND (independent of the embedder): the feed vulnintel_mcp.ics_advisories pulls, "
            f"{ICS_FEED_INCUMBENT}, returns HTTP 404 — the live tool returns an error for every call. The ICS RSS feed ({ICS_FEED}) is the working source",
            "the asset side still has no product field: icsot asset_inventory emits host/protocol/role hints only, which is why description_only (identity tokens stripped) is the production-realistic form",
        ],
    )
