"""Code-and-feed security probes: binary_similarity, vuln_severity, ics_advisories."""

from __future__ import annotations

import glob
import json
import math
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

from portal.platform.embedding.contract import Task

from ..framework import (
    MEASURED,
    REPO_ROOT,
    ProbeContext,
    ProbeResult,
    blocked,
    compare,
    fixture_digest,
    macro_f1,
    probe,
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


def _nvd_sample(per_class: int = 60) -> list[dict[str, Any]]:
    cache = SCRATCH / "nvd_sample.json"
    if cache.is_file():
        return json.loads(cache.read_text())
    by: dict[str, list[dict[str, Any]]] = {"LOW": [], "MEDIUM": [], "HIGH": [], "CRITICAL": []}
    windows = [
        ("2024-01-01T00:00:00.000", "2024-04-29T00:00:00.000"),
        ("2024-09-01T00:00:00.000", "2024-12-29T00:00:00.000"),
        ("2025-03-01T00:00:00.000", "2025-06-28T00:00:00.000"),
    ]
    with httpx.Client(timeout=120) as c:
        for a, b in windows:
            r = c.get(NVD, params={"pubStartDate": a, "pubEndDate": b, "resultsPerPage": 2000})
            r.raise_for_status()
            for v in r.json().get("vulnerabilities", []):
                cve = v["cve"]
                desc = next(
                    (d["value"] for d in cve.get("descriptions", []) if d["lang"] == "en"), ""
                )
                m = (cve.get("metrics", {}).get("cvssMetricV31") or [{}])[0].get("cvssData", {})
                sev = m.get("baseSeverity")
                if sev in by and len(desc) > 40:
                    by[sev].append({"id": cve["id"], "desc": desc, "severity": sev})
    import random

    rng = random.Random(7)
    out = []
    for rows in by.values():
        rng.shuffle(rows)
        out += rows[:per_class]
    SCRATCH.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out))
    return out


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


def _softmax_lr(
    x: Any, y: Any, k: int, epochs: int = 400, lr: float = 0.5, l2: float = 1e-3
) -> Any:
    import numpy as np

    w = np.zeros((x.shape[1], k), dtype=np.float64)
    onehot = np.eye(k)[y]
    for _ in range(epochs):
        z = x @ w
        z -= z.max(1, keepdims=True)
        p = np.exp(z)
        p /= p.sum(1, keepdims=True)
        w -= lr * (x.T @ (p - onehot) / len(x) + l2 * w)
    return w


@probe("vuln_severity")
async def vuln_severity(ctx: ProbeContext) -> ProbeResult:
    import numpy as np

    try:
        rows = _nvd_sample()
    except Exception as e:  # noqa: BLE001
        return blocked("vuln_severity", f"NVD fetch failed: {type(e).__name__}: {e}")
    if len(rows) < 200:
        return blocked("vuln_severity", f"only {len(rows)} labelled CVEs obtained (floor 200)")
    labels = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    y = np.array([labels.index(r["severity"]) for r in rows])
    rng = np.random.default_rng(11)
    idx = rng.permutation(len(rows))
    cut = int(0.6 * len(rows))
    tr, te = idx[:cut], idx[cut:]
    vec = np.asarray(
        await ctx.client.embed_texts(
            [r["desc"][:1500] for r in rows], task=Task.CLASSIFICATION, dim=768
        ),
        dtype=np.float64,
    )
    w = _softmax_lr(vec[tr], y[tr], 4)
    pred_eg2 = (vec[te] @ w).argmax(1)
    py = Path("/Users/chris/.portal5/eg2-venv/bin/python3")
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "in.json").write_text(json.dumps([rows[i] for i in te]))
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
    gold = [labels[i] for i in y[te]]
    inc = macro_f1(pred_inc, gold)
    cand = macro_f1([labels[i] for i in pred_eg2], gold)
    acc = lambda p: round(sum(a == b for a, b in zip(p, gold, strict=True)) / len(gold), 4)  # noqa: E731
    return ProbeResult(
        "vuln_severity",
        MEASURED,
        {
            "primary": round(inc, 4),
            "accuracy": acc(pred_inc),
            "model": "CIRCL/vulnerability-severity-classification-roberta-base",
        },
        {
            "primary": round(cand, 4),
            "accuracy": acc([labels[i] for i in pred_eg2]),
            "head": "softmax regression on EG2 CLASSIFICATION 768d, trained on a disjoint 60% split",
            "train": len(tr),
            "test": len(te),
        },
        compare(inc, cand),
        fixture={
            "cves": len(rows),
            "per_class": dict(Counter(r["severity"] for r in rows)),
            "sha": fixture_digest([r["id"] for r in rows]),
        },
        identity=await ctx.client.version_tag(768),
        notes=[
            "labels = NVD CVSS v3.1 baseSeverity (stratified, 3 NVD publication windows); the fine-tuned RoBERTa was trained on CVE data that may overlap this sample, which favours the incumbent"
        ],
    )


# ── ics_advisories ──────────────────────────────────────────────────────────


@probe("ics_advisories")
async def ics_advisories(ctx: ProbeContext) -> ProbeResult:
    pcaps = sorted(
        glob.glob(
            str(
                REPO_ROOT
                / "portal"
                / "modules"
                / "security"
                / "core"
                / "results"
                / "captures"
                / "pcap"
                / "*.pcap"
            )
        )
    )
    from portal.modules.icsot.tools.icsot_mcp import asset_inventory

    tried, ics_hits, products = 0, 0, 0
    for p in pcaps[:40]:
        inv = asset_inventory(p, max_packets=2000)
        tried += 1
        assets = inv.get("assets") or inv.get("hosts") or []
        for a in assets if isinstance(assets, list) else assets.values():
            protos = set(a.get("protocols", [])) if isinstance(a, dict) else set()
            ics_hits += bool(
                protos
                & {
                    "modbus",
                    "dnp3",
                    "s7comm",
                    "enip",
                    "bacnet",
                    "Modbus",
                    "DNP3",
                    "S7comm",
                    "EtherNet/IP",
                    "BACnet",
                }
            )
            products += bool(isinstance(a, dict) and (a.get("vendor") or a.get("product")))
    return blocked(
        "ics_advisories",
        f"asset_inventory emits only host/protocol/role hints (no vendor or product string field); {tried} lab pcaps tried, "
        f"{ics_hits} ICS-protocol assets, {products} with a product string. The only pcaps on this host are IT attack-episode captures",
        fixture={"pcaps_tried": tried},
    )
