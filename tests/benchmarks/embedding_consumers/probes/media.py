"""Media probes: media_alignment, cad_resemblance, unified_recall, audio_recordings.

Artifacts come from ``python -m tests.benchmarks.embedding_consumers.gen_media`` (scratch dir on
data01, which the EG2 service may read) and from stored CAD gauntlet runs. A modality whose
artifacts are missing is reported as a BLOCKED sub-result, never silently dropped.
"""

from __future__ import annotations

import json
import statistics
import tempfile
from pathlib import Path
from typing import Any

import httpx

from portal.platform.embedding.contract import Role, Task

from ..framework import (
    MEASURED,
    REPO_ROOT,
    ProbeContext,
    ProbeResult,
    blocked,
    compare,
    fixture_digest,
    probe,
    recall_at_k,
    top_k_by_cosine,
)
from ._common import DATA, auc_roc, cos, load_fixture

SCRATCH = Path("/Volumes/data01/portal5_scratch_eg2")
MEDIA = SCRATCH / "media"


def _manifest() -> dict[str, list[dict[str, Any]]] | None:
    f = MEDIA / "manifest.json"
    return json.loads(f.read_text()) if f.is_file() else None


def _items(kind: str, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    key = {"images": "image_path", "videos": "video_path", "music": "audio_path"}[kind]
    ok = [r for r in rows if r.get("ok") and r.get("file") and Path(r["file"]).is_file()]
    return [{key: r["file"]} for r in ok], [r["prompt"] for r in ok]


@probe("media_alignment")
async def media_alignment(ctx: ProbeContext) -> ProbeResult:
    man = _manifest()
    if man is None:
        return blocked(
            "media_alignment",
            "media generation out of scope by operator decision (2026-10-07: not needed); no generated artifacts exist. `gen_media` is available if wanted later",
        )
    per: dict[str, Any] = {}
    missing = []
    for kind in ("images", "videos", "music"):
        items, prompts = _items(kind, man.get(kind, []))
        if len(items) < 3:
            missing.append(f"{kind}: {len(items)} usable of {len(man.get(kind, []))}")
            continue
        av = await ctx.client.embed_items(items, task=Task.SEARCH, role=Role.DOCUMENT, dim=768)
        pv = await ctx.client.embed_texts(prompts, task=Task.SEARCH, role=Role.QUERY, dim=768)
        n = len(items)
        sims = [[cos(pv[i], av[j]) for j in range(n)] for i in range(n)]
        r1 = sum(max(range(n), key=lambda j: sims[i][j]) == i for i in range(n)) / n
        true = [sims[i][i] for i in range(n)]
        shuf = [sims[i][j] for i in range(n) for j in range(n) if i != j]
        per[kind] = {
            "n": n,
            "rank1_vs_shuffled": round(r1, 4),
            "chance": round(1 / n, 4),
            "mean_cos_true": round(statistics.mean(true), 4),
            "mean_cos_shuffled": round(statistics.mean(shuf), 4),
            "auc_true_vs_shuffled": auc_roc(true, shuf),
        }
    edits = [
        e
        for e in man.get("edits", [])
        if e.get("ok") and e.get("file") and Path(e["file"]).is_file()
    ]
    edit_res: dict[str, Any] = {"n": len(edits)}
    if edits:
        out = await ctx.client.embed_items([{"image_path": e["file"]} for e in edits], dim=768)
        src = await ctx.client.embed_items([{"image_path": e["source"]} for e in edits], dim=768)
        ins = await ctx.client.embed_texts(
            [e["instruction"] for e in edits], task=Task.SEARCH, role=Role.QUERY, dim=768
        )
        opp = await ctx.client.embed_texts(
            [e["opposite"] for e in edits], task=Task.SEARCH, role=Role.QUERY, dim=768
        )
        edit_res |= {
            "delta_cos(out,instr)-cos(src,instr)": [
                round(cos(o, i) - cos(s, i), 4) for o, s, i in zip(out, src, ins, strict=True)
            ],
            "out_closer_to_instruction_than_opposite": [
                cos(o, i) > cos(o, p) for o, i, p in zip(out, ins, opp, strict=True)
            ],
            "cos_out_vs_src": [round(cos(o, s), 4) for o, s in zip(out, src, strict=True)],
        }
        edit_res["no_op_edits_flagged(cos_out_vs_src>=0.98)"] = sum(
            c >= 0.98 for c in edit_res["cos_out_vs_src"]
        )
    failed = {
        k: [r.get("error") for r in v if not r.get("ok")]
        for k, v in man.items()
        if any(not r.get("ok") for r in v)
    }
    if not per:
        return blocked(
            "media_alignment",
            "; ".join(missing) or "no media artifacts",
            fixture={"manifest": {k: len(v) for k, v in man.items()}},
        )
    mean_r1 = round(statistics.mean(v["rank1_vs_shuffled"] for v in per.values()), 4)
    n_ok = sum(1 for v in man.values() for r in v if r.get("ok"))
    n_all = sum(len(v) for v in man.values())
    return ProbeResult(
        "media_alignment",
        MEASURED,
        {
            "primary": round(n_ok / n_all, 4),
            "metric": "generation success (what acceptance S30/S31/S07 assert: HTTP 200 / job done); it cannot see content, so a no-op or off-prompt artifact passes",
            "failed": failed,
        },
        {
            "primary": mean_r1,
            "metric": "mean rank-1-vs-shuffled across modalities (chance = 1/n)",
            "per_modality": per,
            "edits": edit_res,
            "unusable_modalities": missing,
        },
        "BETTER" if mean_r1 > 0.5 else "INCONCLUSIVE",
        fixture={"manifest": {k: len(v) for k, v in man.items()}, "sha": fixture_digest(man)},
        identity=await ctx.client.version_tag(768),
        notes=[
            "whether the check would have caught the Qwen-Image-2.1 edit failure: see edits['no_op_edits_flagged'] and the out-vs-instruction deltas; acceptance cannot, it passes on HTTP 200"
        ],
    )


# ── cad_resemblance ─────────────────────────────────────────────────────────


@probe("cad_resemblance")
async def cad_resemblance(ctx: ProbeContext) -> ProbeResult:  # noqa: C901, PLR0912, PLR0915
    import glob

    from tests.benchmarks.bench_cad_gauntlet_v2 import TASKS

    prompts = {t["id"]: t["prompt"].split(" Units are millimetres")[0] for t in TASKS}
    cells: list[dict[str, Any]] = []
    for f in sorted(
        glob.glob(str(REPO_ROOT / "tests" / "benchmarks" / "results" / "cad_gauntlet_v2_*.json"))
    ):
        j = json.loads(Path(f).read_text())
        for a in j.get("arms", []):
            for c in a.get("cells", []):
                p = c.get("artifact")
                if (
                    p
                    and Path(p).is_file()
                    and p.endswith((".stl", ".step", ".glb", ".obj"))
                    and c["task"] in prompts
                ):
                    cells.append({**c, "arm": a.get("key"), "run": Path(f).name})
    chosen: list[dict[str, Any]] = []
    for task in prompts:
        ts = [c for c in cells if c["task"] == task and c["verdict"] in ("PASS", "WRONGSIZE")]
        for verdict in ("PASS", "WRONGSIZE"):
            pick = next((c for c in ts if c["verdict"] == verdict), None)
            if pick:
                chosen.append(pick)
    if len(chosen) < 12:
        return blocked(
            "cad_resemblance", f"only {len(chosen)} renderable stored gauntlet artifacts (floor 12)"
        )
    from portal.modules.cad.tools.cad_render_mcp import _render_mesh_to_png

    renders = []
    with tempfile.TemporaryDirectory(dir=str(SCRATCH) if SCRATCH.is_dir() else None) as td:
        for i, c in enumerate(chosen):
            png = Path(td) / f"r{i}.png"
            try:
                note = _render_mesh_to_png(Path(c["artifact"]), png, 512)
            except Exception as e:  # noqa: BLE001
                note = f"render failed: {type(e).__name__}"
            if png.is_file():
                renders.append((c, str(png), note))
        if len(renders) < 12:
            return blocked(
                "cad_resemblance",
                f"only {len(renders)} stored artifacts could be rendered (floor 12)",
            )
        iv = await ctx.client.embed_items([{"image_path": p} for _, p, _ in renders], dim=768)
        task_ids = sorted(prompts)
        tv = dict(
            zip(
                task_ids,
                await ctx.client.embed_texts(
                    [prompts[t] for t in task_ids], task=Task.SEARCH, role=Role.QUERY, dim=768
                ),
                strict=True,
            )
        )
        true, shuf = [], []
        r1 = 0
        for (c, _, _), v in zip(renders, iv, strict=True):
            s = {t: cos(v, tv[t]) for t in task_ids}
            true.append(s[c["task"]])
            shuf += [x for t, x in s.items() if t != c["task"]]
            r1 += max(s, key=lambda t: s[t]) == c["task"]
        passed = [
            cos(v, tv[c["task"]])
            for (c, _, _), v in zip(renders, iv, strict=True)
            if c["verdict"] == "PASS"
        ]
        failed = [
            cos(v, tv[c["task"]])
            for (c, _, _), v in zip(renders, iv, strict=True)
            if c["verdict"] != "PASS"
        ]
    return ProbeResult(
        "cad_resemblance",
        MEASURED,
        {
            "primary": round(len(passed) / len(renders), 4),
            "metric": "sealed spec-derived grader pass rate on the sampled renders (tests/benchmarks/cad_grader.py verdicts stored in the gauntlet JSON); the grader stays authoritative",
        },
        {
            "primary": round(r1 / len(renders), 4),
            "metric": "rank-1-vs-shuffled task (8 distinct tasks)",
            "chance": round(1 / len(task_ids), 4),
            "mean_cos_true": round(statistics.mean(true), 4),
            "mean_cos_shuffled": round(statistics.mean(shuf), 4),
            "auc_pass_vs_nonpass_by_cosine": auc_roc(passed, failed),
            "pass_renders": len(passed),
            "nonpass_renders": len(failed),
        },
        "INCONCLUSIVE",
        fixture={
            "renders": len(renders),
            "tasks": len(task_ids),
            "paths": sorted({Path(c["artifact"]).suffix for c, _, _ in renders}),
            "sha": fixture_digest([c["request_id"] for c, _, _ in renders]),
        },
        identity=await ctx.client.version_tag(768),
        notes=[
            "renders come from stored production-path artifacts (auto-cad build123d/generate_part); resemblance is a WARN-level axis beside the grader, never a replacement",
            f"render path: {renders[0][2]}",
        ],
    )


# ── audio_recordings ────────────────────────────────────────────────────────


async def _tts(text: str, out: Path) -> bool:
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.post(
            "http://localhost:8918/v1/audio/speech", json={"input": text, "voice": "af_heart"}
        )
    if r.status_code != 200 or r.headers.get("content-type", "").startswith("application/json"):
        return False
    out.write_bytes(r.content)
    return True


async def _asr(path: Path) -> str:
    async with httpx.AsyncClient(timeout=600) as c:
        r = await c.post(
            "http://localhost:8924/tools/transcribe_audio", json={"arguments": {"file": str(path)}}
        )
    r.raise_for_status()
    body = r.json()
    for k in ("text", "transcript", "markdown", "md"):
        if isinstance(body.get(k), str) and body[k].strip():
            return body[k]
    raise RuntimeError(f"no transcript in response keys {sorted(body)}")


@probe("audio_recordings")
async def audio_recordings(ctx: ProbeContext) -> ProbeResult:
    if not ctx.live:
        return blocked("audio_recordings", "needs --live (TTS :8918, ASR :8924)")
    rows = load_fixture("audio_recordings.json")["rows"]
    d = MEDIA / "audio_recordings"
    d.mkdir(parents=True, exist_ok=True)
    clips, trans = [], []
    for i, r in enumerate(rows):
        p = d / f"clip_{i:02d}.wav"
        if not p.is_file() and not await _tts(r["text"], p):
            return blocked("audio_recordings", "TTS (:8918) refused or unavailable")
        clips.append(p)
        t = d / f"clip_{i:02d}.txt"
        if not t.is_file():
            t.write_text(await _asr(p))
        trans.append(t.read_text())
    q = [r["query"] for r in rows]
    qv = await ctx.client.embed_texts(q, task=Task.SEARCH, role=Role.QUERY, dim=768)
    nv = await ctx.client.embed_items([{"audio_path": str(p)} for p in clips], dim=768)
    tv = await ctx.client.embed_texts(trans, task=Task.SEARCH, role=Role.DOCUMENT, dim=768)
    ids = [str(i) for i in range(len(rows))]
    gold = [[i] for i in ids]
    nat, tr = dict(zip(ids, nv, strict=True)), dict(zip(ids, tv, strict=True))

    def ranked(index: dict[str, list[float]]) -> list[list[str]]:
        return [top_k_by_cosine(v, index, len(ids)) for v in qv]

    rn, rt = ranked(nat), ranked(tr)

    def rrf(a: list[str], b: list[str], k: int = 60) -> list[str]:
        sc = {i: 1 / (k + a.index(i) + 1) + 1 / (k + b.index(i) + 1) for i in ids}
        return sorted(ids, key=lambda i: -sc[i])

    rf = [rrf(a, b) for a, b in zip(rn, rt, strict=True)]
    # transcript-only lexical FTS-style baseline: query word overlap with the transcript
    from ._common import content_words

    def lex_rank(qq: str) -> list[str]:
        qw = content_words(qq)
        return sorted(ids, key=lambda i: -len(qw & content_words(trans[int(i)])))

    lex = [lex_rank(qq) for qq in q]
    ident = [i for i, r in enumerate(rows) if r["identifier"]]

    def r5(rk: list[list[str]], sel: list[int] | None = None) -> float:
        s = sel if sel is not None else list(range(len(rows)))
        return round(recall_at_k([rk[i] for i in s], [gold[i] for i in s], 5), 4)

    cand = {
        "primary": r5(rf),
        "native_audio_only": r5(rn),
        "rrf_native_plus_transcript": r5(rf),
        "identifier_queries": {
            "n": len(ident),
            "native": r5(rn, ident),
            "transcript_embedding": r5(rt, ident),
            "lexical_transcript": r5(lex, ident),
            "rrf": r5(rf, ident),
        },
    }
    inc = {"primary": r5(rt), "transcript_embedding": r5(rt), "lexical_transcript": r5(lex)}
    wer_note = [(rows[i]["text"], trans[i].strip()[:120]) for i in range(min(3, len(rows)))]
    return ProbeResult(
        "audio_recordings",
        MEASURED,
        inc,
        cand,
        compare(inc["primary"], cand["primary"]),
        fixture={"clips": len(rows), "identifier_clips": len(ident), "sha": fixture_digest(rows)},
        identity=await ctx.client.version_tag(768),
        notes=[
            "clips are TTS (Kokoro via :8918) and transcripts Parakeet (:8924); no operator recordings are available on this host",
            f"sample transcripts: {wer_note}",
        ],
    )


# ── unified_recall ──────────────────────────────────────────────────────────


@probe("unified_recall")
async def unified_recall(ctx: ProbeContext) -> ProbeResult:  # noqa: C901, PLR0912, PLR0915
    man = _manifest()
    if man is None:
        return blocked(
            "unified_recall",
            "media generation out of scope by operator decision (2026-10-07: not needed); no generated artifacts exist",
        )
    media = json.loads((DATA / "media_prompts.json").read_text())["media"]
    corpus_ids: list[str] = []
    items: list[dict[str, Any]] = []
    for kind, tag in (("images", "image"), ("videos", "video"), ("music", "audio")):
        for i, r in enumerate(man.get(kind, [])):
            if r.get("ok") and r.get("file") and Path(r["file"]).is_file():
                corpus_ids.append(f"{tag}:{i}")
                items.append({f"{tag}_path": r["file"]})
    if len(items) < 6:
        return blocked("unified_recall", f"only {len(items)} usable media artifacts")
    mem = load_fixture("memory_recall.json")["memories"]
    vecs = await ctx.client.embed_items(items, dim=768)
    index = dict(zip(corpus_ids, vecs, strict=True))
    mv = await ctx.client.embed_texts(
        list(mem.values()), task=Task.SEARCH, role=Role.DOCUMENT, dim=768
    )
    for k, v in zip(mem, mv, strict=True):
        index[f"memory:{k}"] = v
    from portal.platform.wiki.store import load_all

    units = [u for u in load_all() if u.body][:300]
    uv = await ctx.client.embed_texts(
        [f"{u.title}\n{u.body[:900]}" for u in units], task=Task.SEARCH, role=Role.DOCUMENT, dim=768
    )
    for u, v in zip(units, uv, strict=True):
        index[f"kb:{u.id}"] = v
    results: dict[str, dict[str, Any]] = {}

    def bucket(name: str, ranked: list[list[str]], gold: list[str]) -> None:
        results[name] = {
            "n": len(gold),
            "recall@5": round(recall_at_k(ranked, [[g] for g in gold], 5), 4),
        }

    # text -> media (paraphrased prompts)
    for kind, tag in (("images", "image"), ("videos", "video"), ("music", "audio")):
        pairs = [
            (f"{tag}:{i}", media[kind][i]["paraphrase"])
            for i, r in enumerate(man.get(kind, []))
            if f"{tag}:{i}" in index and i < len(media[kind])
        ]
        if len(pairs) >= 3:
            qv = await ctx.client.embed_texts(
                [p for _, p in pairs], task=Task.SEARCH, role=Role.QUERY, dim=768
            )
            bucket(
                f"text->{tag}", [top_k_by_cosine(v, index, 5) for v in qv], [g for g, _ in pairs]
            )
    # image -> image (a centre-cropped, down-scaled variant of each image)
    from PIL import Image

    var_items, var_gold = [], []
    vdir = MEDIA / "variants"
    vdir.mkdir(exist_ok=True)
    for i, r in enumerate(man.get("images", [])):
        if f"image:{i}" in index:
            im = Image.open(r["file"]).convert("RGB")
            w, h = im.size
            im.crop((w // 8, h // 8, w - w // 8, h - h // 8)).resize((384, 384)).save(
                vdir / f"v{i}.png"
            )
            var_items.append({"image_path": str(vdir / f"v{i}.png")})
            var_gold.append(f"image:{i}")
    if var_items:
        vv = await ctx.client.embed_items(var_items, dim=768)
        bucket(
            "image(variant)->image",
            [
                top_k_by_cosine(v, {k: x for k, x in index.items() if k != g}, 5)
                if False
                else top_k_by_cosine(v, index, 5)
                for v, g in zip(vv, var_gold, strict=True)
            ],
            var_gold,
        )
    # spoken query -> media (TTS of the paraphrase)
    sp_items, sp_gold = [], []
    for kind, tag in (("images", "image"), ("videos", "video"), ("music", "audio")):
        for i in range(min(len(media[kind]), 4)):
            gid = f"{tag}:{i}"
            if gid not in index:
                continue
            p = MEDIA / "variants" / f"speech_{tag}_{i}.wav"
            if not p.is_file() and not await _tts(media[kind][i]["paraphrase"], p):
                continue
            sp_items.append({"audio_path": str(p)})
            sp_gold.append(gid)
    if sp_items:
        sv = await ctx.client.embed_items(sp_items, dim=768)
        bucket("speech->media", [top_k_by_cosine(v, index, 5) for v in sv], sp_gold)
    if not results:
        return blocked("unified_recall", "no query bucket could be built")
    total_n = sum(v["n"] for v in results.values())
    primary = round(sum(v["recall@5"] * v["n"] for v in results.values()) / total_n, 4)
    return ProbeResult(
        "unified_recall",
        MEASURED,
        {
            "primary": None,
            "note": "no unified index exists: generated media is unindexed; memory and KB live in separate spaces",
        },
        {
            "primary": primary,
            "metric": "query-weighted cross-modal recall@5",
            "buckets": results,
            "queries": total_n,
            "index": {"media": len(items), "memories": len(mem), "kb_chunks": len(units)},
        },
        "BETTER" if primary > 0.5 else "INCONCLUSIVE",
        fixture={"queries": total_n, "sha": fixture_digest(list(index))},
        identity=await ctx.client.version_tag(768),
        notes=[
            "shadow index only (in memory); ~/AI_Output documents are not indexed because the generated-media dirs are nearly empty on this host, so the index is the probe's own generated media + 60 memories + 300 wiki units",
            "image(variant)->image queries are a crop+rescale of the same file; the artifact itself is in the index, so this bucket is a self-retrieval sanity check, not a discovery claim",
        ],
    )
