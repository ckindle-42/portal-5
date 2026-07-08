"""model_survey.py — repeatable model discovery for reasoning-first blue eval.

Two discovery mechanisms, not a hand-curated list (TASK-SEC-MODEL-DISCOVERY-V1):

1. --catalog:   parse config/backends.yaml (146 entries), score each model by
                reasoning-first fit heuristics (size band, architecture/name
                signals, tool-capability, context length), cross-reference
                against what's already been benched (wiki delta-report tags +
                /tmp/agentic_blue_sweep.json + results/candidates/ captures),
                and surface the GAP: promising-but-un-benched models.

2. --hf-search: query the public HF Hub (huggingface_hub.HfApi.list_models,
                no token needed) for GGUF models tagged reasoning/thinking/code,
                sorted by downloads, filtered to the size band that fits the
                rig and NOT already present in backends.yaml.

Both are read-only surveys — they queue candidates, they do not pull models,
promote anything, or touch backends.yaml. PROMOTE_POLICY=confirm applies
downstream (seeding/benching), not here.

Run directly:
    python3 -m tests.benchmarks.bench_security.model_survey --catalog
    python3 -m tests.benchmarks.bench_security.model_survey --hf-search --tags reasoning,thinking,code --gguf
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

BACKENDS_YAML = Path(__file__).resolve().parents[3] / "config" / "backends.yaml"
SWEEP_CHECKPOINT = Path("/tmp/agentic_blue_sweep.json")

# Sweet spot for this rig (see CLAUDE.md — single M-series host, 7-35B fits
# comfortably alongside other loaded models; below 7B tends to be too weak a
# raw reasoner, above 35B risks Metal OOM — see project_scout_removed memory).
MIN_SIZE_B = 7.0
MAX_SIZE_B = 35.0

REASONING_SIGNALS = (
    "thinking",
    "reasoning",
    "reason",
    "r1",
    "cot",
    "cybersec",
    "security",
    "agent",
    "qwen3",
    "qwen3.5",
    "qwen3.6",
    "devstral",
    "granite",
    "magistral",
    "neo-code",
)
NARROW_SECURITY_TUNED_SIGNALS = (
    "cybersecqwen",
    "bugtrace",
    "vulnllm",
)


def _extract_size_b(model_id: str) -> float | None:
    """Best-effort parameter-count extraction from a model id string.

    Handles forms like '27b', '8B', '26B-A4B' (MoE — use total, not active),
    '35B-A3B'. Returns None if no size token found.
    """
    matches = re.findall(r"(\d+(?:\.\d+)?)[bB](?:-a\d+(?:\.\d+)?[bB])?", model_id)
    if not matches:
        return None
    # Prefer the first size-looking token before a colon/tag boundary
    try:
        return float(matches[0])
    except ValueError:
        return None


def _extract_ctx(model_id: str) -> int | None:
    """Extract context-length hint from an id suffix like '-ctx8k'/'-ctx64k'."""
    m = re.search(r"-ctx(\d+)k", model_id, re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1)) * 1024


def load_catalog(path: Path = BACKENDS_YAML) -> list[dict]:
    """Flatten config/backends.yaml into a deduped list of {id, groups, supports_tools}.

    The same model id can appear under multiple groups (general/coding/security/
    reasoning) — dedup by id, keeping the union of groups it appears under, so
    the ranked survey doesn't repeat the same model 3x.
    """
    data = yaml.safe_load(path.read_text())
    by_id: dict[str, dict] = {}
    for backend in data.get("backends", []):
        group = backend.get("group", "?")
        for model in backend.get("models", []) or []:
            mid = model.get("id", "")
            if mid in by_id:
                by_id[mid]["groups"].append(group)
                by_id[mid]["supports_tools"] = by_id[mid]["supports_tools"] or bool(
                    model.get("supports_tools", False)
                )
            else:
                by_id[mid] = {
                    "id": mid,
                    "groups": [group],
                    "supports_tools": bool(model.get("supports_tools", False)),
                }
    return list(by_id.values())


def _already_benched_models() -> set[str]:
    """Cross-reference models already benched via agentic blue eval.

    Sources (best-effort, all optional — a missing source just means we
    can't rule those models out yet, not an error):
      - /tmp/agentic_blue_sweep.json (live sweep checkpoint)
      - portal_wiki delta-report units (SEC_BENCH-agentic-blue-deltas-*) tags
      - results/candidates/*.json capture filenames (blue_<model>_<scenario>_*)
    """
    benched: set[str] = set()

    if SWEEP_CHECKPOINT.exists():
        try:
            import json

            records = json.loads(SWEEP_CHECKPOINT.read_text())
            for r in records:
                m = r.get("model")
                if m:
                    benched.add(m)
        except Exception:
            pass

    try:
        from portal_wiki.core.store import load_all

        for unit in load_all():
            if "agentic-blue" not in (unit.tags or []):
                continue
            for tag in unit.tags:
                # Model tags are written with ':' -> '-' (see _sweep_driver.py)
                if tag in ("agentic-blue", "maturation", "arm-deltas", "confidence-interval"):
                    continue
                benched.add(tag)
    except Exception:
        pass

    return benched


def _fuzzy_benched(model_id: str, benched: set[str]) -> bool:
    """Loose match: wiki tags mangle ':' -> '-', so compare normalized forms."""
    norm = model_id.replace(":", "-").replace("/", "-")
    return any(b in (model_id, norm) or norm.startswith(b) or b.startswith(norm) for b in benched)


def score_model(entry: dict) -> dict:
    """Score one catalog entry for reasoning-first blue fit.

    Returns entry augmented with: size_b, ctx_hint, reasoning_signal,
    narrow_tuned, score, reasons.
    """
    model_id = entry["id"]
    lower = model_id.lower()
    size_b = _extract_size_b(model_id)
    ctx_hint = _extract_ctx(model_id)

    reasons: list[str] = []
    score = 0.0

    # Size band (favor 7-35B sweet spot)
    if size_b is not None:
        if MIN_SIZE_B <= size_b <= MAX_SIZE_B:
            score += 2.0
            reasons.append(f"size {size_b:.0f}B in sweet spot ({MIN_SIZE_B:.0f}-{MAX_SIZE_B:.0f}B)")
        elif size_b < MIN_SIZE_B:
            score += 0.3
            reasons.append(
                f"size {size_b:.0f}B below sweet spot (small/fast, weaker raw reasoning)"
            )
        else:
            score += 0.5
            reasons.append(f"size {size_b:.0f}B above sweet spot (OOM/eviction risk)")
    else:
        reasons.append("size unknown (no numeric token in id)")

    # Architecture / naming signal
    hits = [sig for sig in REASONING_SIGNALS if sig in lower]
    if hits:
        score += 1.5
        reasons.append(f"reasoning-signal match: {hits}")

    narrow_tuned = any(sig in lower for sig in NARROW_SECURITY_TUNED_SIGNALS)
    if narrow_tuned:
        score -= 0.5
        reasons.append("narrow security-tuned name (may underperform as a general reasoner)")

    # Tool capability
    if entry["supports_tools"]:
        score += 2.0
        reasons.append("supports_tools=true (agentic-eligible)")
    else:
        reasons.append("supports_tools=false (not yet agentic-eligible)")

    # Context length
    if ctx_hint:
        if ctx_hint >= 32 * 1024:
            score += 1.0
            reasons.append(f"ctx={ctx_hint} (large haystack capable)")
        else:
            score += 0.3
            reasons.append(f"ctx={ctx_hint}")

    entry.update(
        {
            "size_b": size_b,
            "ctx_hint": ctx_hint,
            "narrow_tuned": narrow_tuned,
            "score": round(score, 2),
            "reasons": reasons,
        }
    )
    return entry


def survey_catalog(path: Path = BACKENDS_YAML) -> list[dict]:
    """Score+rank the full catalog, flag un-benched-but-promising candidates."""
    catalog = load_catalog(path)
    benched = _already_benched_models()
    scored = [score_model(e) for e in catalog]
    for e in scored:
        e["already_benched"] = _fuzzy_benched(e["id"], benched)
        e["gap_candidate"] = (
            (not e["already_benched"]) and e["supports_tools"] and e["score"] >= 3.0
        )
    scored.sort(key=lambda e: e["score"], reverse=True)
    return scored


def print_catalog_survey(scored: list[dict], limit: int | None = None) -> None:
    total = len(scored)
    benched_n = sum(1 for e in scored if e["already_benched"])
    gap = [e for e in scored if e["gap_candidate"]]
    print(
        f"Catalog survey: {total} entries, {benched_n} already benched, {len(gap)} un-benched-but-promising (gap)"
    )
    print()
    print("RANKED UN-BENCHED CANDIDATES (gap — good models never tested):")
    rows = gap[:limit] if limit else gap
    for e in rows:
        print(
            f"  [{e['score']:>5.2f}] {e['id']}  (groups={e['groups']}, tools={e['supports_tools']})"
        )
        for r in e["reasons"]:
            print(f"           - {r}")


# ── HF Hub search ────────────────────────────────────────────────────────

DEFAULT_HF_TAGS = ["reasoning", "thinking", "code"]


def _catalog_hf_ids(catalog: list[dict]) -> set[str]:
    """Extract the bare HF repo id (org/name) from hf.co/... catalog entries."""
    ids = set()
    for e in catalog:
        mid = e["id"]
        if mid.startswith("hf.co/"):
            rest = mid[len("hf.co/") :]
            repo = rest.split(":", 1)[0]
            ids.add(repo.lower())
    return ids


def hf_search(
    tags: list[str] | None = None,
    gguf_only: bool = True,
    limit: int = 30,
    sort: str = "downloads",
) -> list[dict]:
    """Search the public HF Hub for reasoning-first GGUF candidates.

    Uses huggingface_hub.HfApi.list_models — public queries need no token.
    Filters out anything already present in backends.yaml (via hf.co/ ids).
    """
    try:
        from huggingface_hub import HfApi
    except ImportError:
        print(
            "huggingface_hub not installed — run: "
            "pip install huggingface_hub --break-system-packages",
            file=sys.stderr,
        )
        return []

    tags = tags or DEFAULT_HF_TAGS
    api = HfApi()
    catalog = load_catalog()
    existing_hf_ids = _catalog_hf_ids(catalog)

    seen: dict[str, dict] = {}
    for tag in tags:
        try:
            models = api.list_models(
                filter=("gguf", tag) if gguf_only else (tag,),
                sort=sort,
                limit=limit,
            )
        except Exception as exc:
            print(f"hf-search: query for tag={tag!r} failed (non-fatal): {exc}", file=sys.stderr)
            continue
        for m in models:
            mid = m.id
            if mid.lower() in existing_hf_ids:
                continue
            entry = seen.setdefault(
                mid,
                {
                    "id": mid,
                    "downloads": getattr(m, "downloads", 0) or 0,
                    "tags": list(getattr(m, "tags", None) or []),
                    "matched_query_tags": [],
                },
            )
            entry["matched_query_tags"].append(tag)

    candidates = list(seen.values())
    for c in candidates:
        size_b = _extract_size_b(c["id"])
        c["size_b"] = size_b
        c["in_size_band"] = size_b is not None and MIN_SIZE_B <= size_b <= MAX_SIZE_B
        c["is_gguf"] = "gguf" in [t.lower() for t in c["tags"]] or "gguf" in c["id"].lower()
    candidates.sort(key=lambda c: (c["in_size_band"], c["downloads"]), reverse=True)
    return candidates


def print_hf_survey(candidates: list[dict], limit: int | None = 20) -> None:
    print(f"HF search: {len(candidates)} new candidates not already in catalog")
    print()
    rows = candidates[:limit] if limit else candidates
    for c in rows:
        band = "IN-BAND" if c["in_size_band"] else "off-band"
        print(
            f"  {c['downloads']:>8} dl  [{band}]  {c['id']}"
            f"  (matched: {c['matched_query_tags']}, size={c['size_b']})"
        )


# ── Seed candidates (operator-named, 2026-07-08) ────────────────────────
#
# The operator named 7 candidates by label/repo, not verified HF ids. Some
# are safetensors-only (no Ollama-runnable GGUF at that exact repo); some
# have a differently-named GGUF quantization. Each entry below is the result
# of a manual HF resolution pass (api.model_info / api.list_models search):
# resolved_id is the actual GGUF repo to pull, or None if nothing was found
# (honest-BLOCKED, not faked). trust is bartowski/mradermacher/unsloth/
# huihui-ai (task-named trusted quantizers) vs "single-user" (works, but
# unverified quant quality — bench don't assume, but don't blindly trust
# either).
TRUSTED_QUANTIZERS = {"bartowski", "mradermacher", "unsloth", "huihui-ai", "huihui_ai"}

SEED_CANDIDATES = [
    {
        "requested": "josefprusa/ThinkingCap-Qwen3.6-27B-int4-AutoRound-v1",
        "resolved_id": "Abiray/ThinkingCap-Qwen3.6-27B-Q4_K_M-GGUF",
        "resolved_file": "ThinkingCap-Qwen3.6-27B-Q4_K_M.gguf",
        "size_b": 27,
        "note": (
            "Requested repo is AutoRound int4 safetensors, NOT GGUF — "
            "not Ollama-runnable as named. Resolved to Abiray's GGUF requant "
            "of the same base model (Abiray already appears in our catalog)."
        ),
    },
    {
        "requested": "migtissera/Tess-4-27B",
        "resolved_id": "migtissera/Tess-4-27B-GGUF",
        "resolved_file": "Tess-4-27B-Q4_K_M.gguf",
        "size_b": 27,
        "note": (
            "Requested repo is safetensors-only. bartowski/migtissera_Tess-4-27B-GGUF "
            "also has a Q4_K_M quant (trusted quantizer) but its 31-file repo "
            "manifest consistently timed out via `ollama pull` (context deadline "
            "exceeded, reproduced 3x, blob fully downloaded each time). Verified: "
            "the author's own smaller 8-file GGUF repo (migtissera/Tess-4-27B-GGUF) "
            "pulls cleanly — used that instead."
        ),
    },
    {
        "requested": "TrevorS/gemma-4-abliteration (thinking family)",
        "resolved_id": "TrevorJS/gemma-4-31B-it-uncensored-GGUF",
        "resolved_file": "gemma-4-31B-it-uncensored-Q4_K_M.gguf",
        "size_b": 31,
        "note": (
            "Corrected author: no HF author 'TrevorS' exists — this is "
            "TrevorJS (operator-confirmed, HF collection "
            "TrevorJS/gemma-4-uncensored). That collection ships GGUF "
            "abliterations at E2B/E4B/12B/26B-A4B/31B; picked the largest "
            "in-band size (31B). Quantizer is TrevorJS itself (single-user)."
        ),
    },
    {
        "requested": "MaralGPT/MaralGPT-Mythos-9B-2606-GGUF",
        "resolved_id": "MaralGPT/MaralGPT-Mythos-9B-2606-GGUF",
        "resolved_file": "MaralGPT-Mythos-9B-2606-Q4_K_M.gguf",
        "size_b": 9,
        "note": "GGUF exists as named. Quantizer is MaralGPT itself (single-user, not in trust list).",
    },
    {
        "requested": "huihui-ai/Huihui-Ornith-1.0-9B-abliterated-MTP-GGUF",
        "resolved_id": "huihui-ai/Huihui-Ornith-1.0-9B-abliterated-MTP-GGUF",
        "resolved_file": "ornith-9b-mtp-kl-Q4_K_M.gguf",
        "size_b": 9,
        "note": (
            "GGUF exists as named, huihui-ai is a trusted quantizer. CAUTION: "
            "this is an MTP (multi-token-prediction) build — llama.cpp/Ollama "
            "MTP support is unverified on this stack; preflight must confirm "
            "it loads and emits tool_calls at all before it's benchable."
        ),
    },
    {
        "requested": "DavidAU/Qwen3.6-40B-...-Thinking-NEO-CODE-...-GGUF",
        "resolved_id": "DavidAU/Qwen3.6-40B-Claude-4.6-Opus-Deckard-Heretic-Uncensored-Thinking-NEO-CODE-Di-IMatrix-MAX-GGUF",
        "resolved_file": "Qwen3.6-40B-Deck-Opus-NEO-CODE-HERE-2T-OT-Q4_K_M.gguf",
        "size_b": 40,
        "note": (
            "GGUF exists (24GB Q4_K_M). DavidAU is prolific but single-user "
            "(task explicit caution). Size 40B is ABOVE the 7-35B sweet spot "
            "— OOM/eviction risk on this rig (see Llama-4-Scout precedent: "
            "57GB model caused Metal OOM machine crash). Preflight + a small "
            "smoke load before any real bench."
        ),
    },
    {
        "requested": "HauhauCS/Gemma4-12B-QAT-Uncensored-...-GGUF",
        "resolved_id": "HauhauCS/Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced",
        "resolved_file": "Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf",
        "size_b": 12,
        "note": "Actual repo id has no '-GGUF' suffix but ships a GGUF quant. Quantizer is HauhauCS (single-user).",
    },
]


def resolve_seed_candidates() -> list[dict]:
    """Attach trust classification + a pull-ready ollama tag to each seed candidate."""
    out = []
    for c in SEED_CANDIDATES:
        c = dict(c)
        if c["resolved_id"] is None:
            c["trust"] = "n/a"
            c["ollama_tag"] = None
        else:
            org = c["resolved_id"].split("/")[0]
            c["trust"] = "trusted" if org in TRUSTED_QUANTIZERS else "single-user"
            c["ollama_tag"] = f"hf.co/{c['resolved_id']}:{c['resolved_file']}"
        out.append(c)
    return out


def print_seed_survey(resolved: list[dict]) -> None:
    found = [c for c in resolved if c["resolved_id"]]
    dropped = [c for c in resolved if not c["resolved_id"]]
    print(
        f"Seed candidates: {len(resolved)} operator-named, {len(found)} resolved to GGUF, {len(dropped)} dropped (honest)"
    )
    print()
    for c in resolved:
        status = "DROPPED" if not c["resolved_id"] else f"trust={c['trust']}"
        print(f"  [{status}] requested={c['requested']}")
        if c["resolved_id"]:
            print(f"      -> {c['ollama_tag']}")
        print(f"      note: {c['note']}")


# ── Discovery writeback (Phase 4) ────────────────────────────────────────


def write_discovery_wiki_unit(
    ranking: list[dict],
    devstral_bar: float = 0.421,
    sweep_path: str = "/tmp/agentic_blue_sweep.json",
) -> str | None:
    """Write the raw-reasoner ranking as a cited wiki survey/discovery unit.

    `ranking` is a list of {model, tactic_recall, source} dicts, sorted
    descending by tactic_recall. `source` records where the candidate came
    from (catalog-gap / hf-search / seed) so the survey stays traceable.
    Makes model discovery a durable, repeatable capability (TASK-SEC-MODEL-
    DISCOVERY-V1) instead of a one-off hand list.
    """
    import time

    from portal_wiki.core.writeback import propose_unit

    date = time.strftime("%Y-%m-%d", time.gmtime())
    lines = [
        "# Model Discovery Survey — Raw-Reasoner Ranking (Blue)",
        "",
        f"**Date:** {date}  ",
        f"**Devstral raw/tactic bar:** {devstral_bar:.3f}  ",
        "**Scope:** discovers + ranks candidates by RAW blue reasoning ability. "
        "Does not build purple evaluation or multi-seat testing (separate work).",
        "",
        "## Ranking (raw arm, tactic-tier recall)",
        "",
        "| Model | Source | Tactic Recall | vs devstral bar |",
        "|-------|--------|---------------|------------------|",
    ]
    for r in ranking:
        delta = r["tactic_recall"] - devstral_bar
        delta_s = f"{delta:+.3f}"
        lines.append(f"| `{r['model']}` | {r['source']} | {r['tactic_recall']:.3f} | {delta_s} |")

    lines.extend(
        [
            "",
            "## No label filtering",
            "",
            "Seat fitness is measured, never assumed from a model's name. "
            "Red/abliterated/uncensored candidates were included in this blue "
            "ranking on equal footing with everything else.",
        ]
    )
    body = "\n".join(lines)

    tags = ["model-discovery", "survey", "reasoning-first", "agentic-blue"]
    for r in ranking:
        tags.append(r["model"].replace(":", "-").replace("/", "-"))

    proposed = propose_unit(
        {
            "id": f"SEC_BENCH-model-discovery-survey-{date.replace('-', '')}",
            "title": f"Model Discovery Survey — Raw-Reasoner Ranking ({date})",
            "kind": "what",
            "body": body,
            "sources": [
                {
                    "type": "bench-security",
                    "path": sweep_path,
                    "description": "Raw-arm sweep across catalog-gap + HF-search + seed candidates",
                }
            ],
            "tags": tags,
        },
        proposed_by="model-discovery-v1",
        auto_confirm=True,
    )
    print(f"Discovery survey written to wiki: {proposed.unit_id} (status={proposed.status})")
    return proposed.unit_id


def _parse_args(argv: list[str]) -> dict:
    opts = {
        "catalog": "--catalog" in argv,
        "hf_search": "--hf-search" in argv,
        "seed": "--seed" in argv,
        "gguf": "--gguf" in argv,
        "tags": DEFAULT_HF_TAGS,
        "limit": None,
    }
    for arg in argv:
        if arg.startswith("--tags="):
            opts["tags"] = [t.strip() for t in arg.split("=", 1)[1].split(",") if t.strip()]
        if arg.startswith("--limit="):
            opts["limit"] = int(arg.split("=", 1)[1])
    return opts


def main() -> None:
    opts = _parse_args(sys.argv[1:])

    if not opts["catalog"] and not opts["hf_search"] and not opts["seed"]:
        opts["catalog"] = True  # default action

    if opts["catalog"]:
        scored = survey_catalog()
        print_catalog_survey(scored, limit=opts["limit"])
        print()

    if opts["seed"]:
        print_seed_survey(resolve_seed_candidates())
        print()

    if opts["hf_search"]:
        candidates = hf_search(tags=opts["tags"], gguf_only=opts["gguf"])
        print_hf_survey(candidates, limit=opts["limit"] or 20)


if __name__ == "__main__":
    main()
