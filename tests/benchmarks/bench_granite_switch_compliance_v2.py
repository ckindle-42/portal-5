"""Granite Switch as a post-hoc verifier over the 183 compliance edges — v2.

v1 (tests/benchmarks/bench_granite_switch_compliance.py) had two real setup
flaws, found on operator review:

1. It wrote its own instruction text for factuality-detection instead of the
   checkpoint's shipped template
   (~/.portal5/granite-switch/granite-switch-4.1-3b-preview/io_configs/), and
   truncated section_text to 4000 chars for no reason — the checkpoint's
   max_position_embeddings is 131072.
2. It ran the "row mismatch" edges through the policy-guardrails adapter
   (org-policy compliance judging) asking whether a citation came from the
   wrong *standard* — but none of the 8 row-mismatch gold edges are about
   that. They're empty/bare/irrelevant citations and one REFERENCES-vs-
   IMPLEMENTS mismatch — i.e. "does this citation satisfy the requirement,"
   which is exactly what the checkpoint's requirement-check adapter is built
   for (io_configs/requirement-check/io.yaml). policy-guardrails was the
   wrong adapter for this question; it was never going to score above zero.

v2 uses the shipped io.yaml instruction text verbatim for both
factuality-detection and requirement-check, runs requirement-check over all
183 edges (not just the mistagged 8), and adds a same-corpus comparison arm
against the seated Ollama compliance model so accuracy and wall-clock are
both reported against what's actually in production.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import textwrap
import time
from pathlib import Path

GS_VENV = os.environ.get("GS_VENV", os.path.expanduser("~/.portal5/granite-switch/.venv"))
GS_MODEL_DIR = os.environ.get(
    "GS_MODEL_DIR",
    os.path.expanduser("~/.portal5/granite-switch/granite-switch-4.1-3b-preview"),
)
GS_PYTHON = os.path.join(GS_VENV, "bin", "python")
EDGES_PATH = "tests/benchmarks/fixtures/compliance_edges_183.json"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get(
    "OLLAMA_COMPLIANCE_MODEL", "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k"
)

# Verbatim from ~/.portal5/granite-switch/granite-switch-4.1-3b-preview/io_configs/.
FACT_INSTRUCTION = textwrap.dedent(
    """
    <guardian>As a judge agent, your role is to help assess whether the provided text meets the given judging criteria, utilizing all available information, including conversations, documents, and tools.

    ### Criteria: A factually incorrect response occurs when the assistant's message contains one or more factual claims that are unsupported by, inconsistent with, or directly contradicted by the information provided in the documents or context. This includes situations where the assistant: introduces details not grounded in the context, misstates or distorts facts contained within the context, misinterprets the meaning or implications of the context, supplies erroneous or conflicting information relative to the context. Even if only a small portion of the response contains such inaccuracies, the overall message is considered factually incorrect.

    ### Scoring Schema: If the last assistant's text meets the criteria, return 'yes'; otherwise, return 'no'.
    """
).strip()

REQUIREMENT_CHECK_TEMPLATE = (
    "<requirements>: {requirement}\n"
    "Please verify if the assistant's generation satisfies the user's requirements or not and "
    'reply with a binary label accordingly. Respond with a json {{"score": "yes"}} if the '
    'constraints are satisfied or respond with {{"score": "no"}} if the constraints are not '
    "satisfied."
)

_INNER = textwrap.dedent(
    r"""
    import json, sys, time, os
    import granite_switch.hf  # registers GraniteSwitchForCausalLM with transformers
    from transformers import AutoTokenizer, AutoModelForCausalLM
    import torch

    model_dir = os.environ["GS_MODEL_DIR"]
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    dtype = torch.float16 if device != "cpu" else torch.float32

    tok = AutoTokenizer.from_pretrained(model_dir)
    mdl = AutoModelForCausalLM.from_pretrained(model_dir, dtype=dtype).to(device).eval()

    edges = json.load(open(sys.argv[1]))
    n_max = int(sys.argv[2]) if len(sys.argv) > 2 else len(edges)
    edges = edges[:n_max]

    FACT_INSTRUCTION = sys.argv[3]
    REQUIREMENT_CHECK_TEMPLATE = sys.argv[4]

    def _gen(messages, adapter):
        prompt = tok.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, adapter_name=adapter,
        )
        t0 = time.perf_counter()
        ids = tok(prompt, return_tensors="pt").to(device)
        with torch.no_grad():
            out = mdl.generate(**ids, max_new_tokens=24, do_sample=False)
        reply = tok.decode(out[0, ids.input_ids.shape[1]:], skip_special_tokens=True).strip()
        return reply, round((time.perf_counter() - t0) * 1000)

    results = []
    for i, e in enumerate(edges):
        # No truncation — checkpoint context is 131072 tokens, longest
        # section_text in this corpus is ~14.5k chars.
        req = e.get("requirement_text") or ""
        sec = e.get("section_text") or ""
        cited = " ".join(e.get("cited_sentences") or [])

        fact_reply, fact_ms = _gen(
            [
                {"role": "user", "content": f"Document (standard context):\n{sec}"},
                {"role": "assistant", "content": req},
                {"role": "user", "content": FACT_INSTRUCTION},
            ],
            "factuality-detection",
        )

        # requirement-check: does the CITED material (the "generation" being
        # checked) actually satisfy the requirement. Empty citation is fed
        # through as an empty generation, which the adapter should fail.
        rc_reply, rc_ms = _gen(
            [
                {"role": "user", "content": "Provide the citation text that implements this requirement."},
                {"role": "assistant", "content": cited},
                {"role": "user", "content": REQUIREMENT_CHECK_TEMPLATE.format(requirement=req)},
            ],
            "requirement-check",
        )

        results.append({
            "assertion_id": e.get("assertion_id"),
            "standard": e.get("standard") or "",
            "gold_verdict": e.get("gold_verdict"),
            "is_boilerplate_pattern": e.get("is_boilerplate_pattern"),
            "is_row_mismatch_pattern": e.get("is_row_mismatch_pattern"),
            "factuality_reply": fact_reply,
            "factuality_ms": fact_ms,
            "requirement_check_reply": rc_reply,
            "requirement_check_ms": rc_ms,
        })
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(edges)} done", flush=True)

    print(json.dumps({"device": device, "results": results}))
    """
)


def _label(reply: str) -> str:
    text = reply.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            payload = json.loads(text[start : end + 1])
            for key in ("label", "score"):
                if key in payload:
                    return str(payload[key]).strip().lower()
        except json.JSONDecodeError:
            pass
    lowered = text.lower()
    for word in ("yes", "no"):
        if word in lowered:
            return word
    return "unknown"


def _fact_verdict(reply: str) -> str:
    label = _label(reply)
    return {"yes": "unsupported", "no": "supported"}.get(label, "unknown")


def _rc_verdict(reply: str) -> str:
    label = _label(reply)
    return {"yes": "supported", "no": "unsupported"}.get(label, "unknown")


def _gold_bucket(gold: str) -> str:
    return "supported" if gold == "SUPPORTED" else "unsupported"


def _score(records: list[dict]) -> dict:
    for r in records:
        r["fact_verdict"] = _fact_verdict(r["factuality_reply"])
        r["rc_verdict"] = _rc_verdict(r["requirement_check_reply"])
        r["gold_bucket"] = _gold_bucket(r["gold_verdict"])

    def _confusion(pred_key: str) -> dict:
        supported_gold = [r for r in records if r["gold_bucket"] == "supported"]
        unsupported_gold = [r for r in records if r["gold_bucket"] == "unsupported"]
        tp = sum(
            1 for r in unsupported_gold if r[pred_key] == "unsupported"
        )  # caught a real defect
        fn = len(unsupported_gold) - tp
        fp = sum(1 for r in supported_gold if r[pred_key] == "unsupported")  # false alarm
        tn = len(supported_gold) - fp
        return {
            "n_supported_gold": len(supported_gold),
            "n_unsupported_gold": len(unsupported_gold),
            "defect_catch_rate": round(tp / len(unsupported_gold), 3) if unsupported_gold else None,
            "supported_false_positive_rate": round(fp / len(supported_gold), 3)
            if supported_gold
            else None,
            "tp": tp,
            "fn": fn,
            "fp": fp,
            "tn": tn,
        }

    boilerplate = [r for r in records if r["is_boilerplate_pattern"]]
    row_mm = [r for r in records if r["is_row_mismatch_pattern"]]

    return {
        "n_records": len(records),
        "factuality_detection": _confusion("fact_verdict"),
        "requirement_check": _confusion("rc_verdict"),
        "requirement_check_boilerplate_catch": {
            "n": len(boilerplate),
            "caught": sum(1 for r in boilerplate if r["rc_verdict"] == "unsupported"),
        },
        "requirement_check_row_mismatch_catch": {
            "n": len(row_mm),
            "caught": sum(1 for r in row_mm if r["rc_verdict"] == "unsupported"),
        },
    }


def run_granite(n_max: int) -> dict:
    started = time.perf_counter()
    started_at = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    inner_script = "/tmp/_bench_gs_inner_v2.py"
    Path(inner_script).write_text(_INNER)
    env = os.environ.copy()
    env["GS_MODEL_DIR"] = GS_MODEL_DIR

    print(f"  invoking Granite Switch under {GS_PYTHON} on {n_max} edges...")
    completed = subprocess.run(
        [
            GS_PYTHON,
            inner_script,
            EDGES_PATH,
            str(n_max),
            FACT_INSTRUCTION,
            REQUIREMENT_CHECK_TEMPLATE,
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=int(os.environ.get("GS_TIMEOUT", "7200")),
    )
    if completed.returncode != 0:
        return {
            "started_at_utc": started_at,
            "head_commit": head,
            "status": "BLOCKED",
            "returncode": completed.returncode,
            "stderr_tail": completed.stderr[-2000:],
            "wall_s": round(time.perf_counter() - started, 1),
        }
    lines = [ln for ln in completed.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines:
        return {
            "started_at_utc": started_at,
            "head_commit": head,
            "status": "BLOCKED",
            "reason": "inner produced no JSON",
            "stdout_tail": completed.stdout[-2000:],
            "wall_s": round(time.perf_counter() - started, 1),
        }
    payload = json.loads(lines[-1])
    records = payload["results"]
    return {
        "started_at_utc": started_at,
        "head_commit": head,
        "granite_switch_checkpoint": GS_MODEL_DIR,
        "device": payload["device"],
        "n_edges_run": len(records),
        "scores": _score(records),
        "records": records,
        "status": "OK",
        "wall_s": round(time.perf_counter() - started, 1),
    }


OLLAMA_JUDGE_PROMPT = (
    "You are a compliance auditor. Below is a requirement and a document section "
    "that is cited as evidence the requirement is met.\n\n"
    "Requirement:\n{req}\n\n"
    "Cited text:\n{cited}\n\n"
    "Does the cited text actually substantiate (implement, describe compliance with) "
    "the requirement? Answer with exactly one word: yes or no."
)


def run_ollama(n_max: int) -> dict:
    import httpx

    edges = json.loads(Path(EDGES_PATH).read_text())[:n_max]
    started_at = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    t0 = time.perf_counter()
    records = []
    with httpx.Client(timeout=120.0) as client:
        for e in edges:
            cited = " ".join(e.get("cited_sentences") or []) or "(no citation given)"
            prompt = OLLAMA_JUDGE_PROMPT.format(req=e.get("requirement_text") or "", cited=cited)
            t_item = time.perf_counter()
            resp = client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0.0, "num_predict": 8},
                },
            )
            resp.raise_for_status()
            reply = resp.json().get("response", "")
            ms = round((time.perf_counter() - t_item) * 1000)
            lowered = reply.strip().lower()
            verdict = (
                "supported"
                if "yes" in lowered
                else ("unsupported" if "no" in lowered else "unknown")
            )
            records.append(
                {
                    "assertion_id": e.get("assertion_id"),
                    "gold_verdict": e.get("gold_verdict"),
                    "gold_bucket": _gold_bucket(e.get("gold_verdict")),
                    "reply": reply,
                    "verdict": verdict,
                    "ms": ms,
                }
            )
    supported_gold = [r for r in records if r["gold_bucket"] == "supported"]
    unsupported_gold = [r for r in records if r["gold_bucket"] == "unsupported"]
    tp = sum(1 for r in unsupported_gold if r["verdict"] == "unsupported")
    fp = sum(1 for r in supported_gold if r["verdict"] == "unsupported")
    return {
        "started_at_utc": started_at,
        "model": OLLAMA_MODEL,
        "n_edges_run": len(records),
        "wall_s": round(time.perf_counter() - t0, 1),
        "mean_ms_per_edge": round(sum(r["ms"] for r in records) / len(records), 1)
        if records
        else None,
        "scores": {
            "n_supported_gold": len(supported_gold),
            "n_unsupported_gold": len(unsupported_gold),
            "defect_catch_rate": round(tp / len(unsupported_gold), 3) if unsupported_gold else None,
            "supported_false_positive_rate": round(fp / len(supported_gold), 3)
            if supported_gold
            else None,
        },
        "records": records,
    }


def write_report(gs: dict, ol: dict, md_path: Path) -> None:
    lines = ["# Granite Switch v2 — corrected adapter/prompt vs seated Ollama compliance model", ""]
    if gs.get("status") != "OK":
        lines += [
            "## Granite Switch",
            "",
            f"Status: BLOCKED — {gs.get('stderr_tail') or gs.get('reason')}",
            "",
        ]
    else:
        s = gs["scores"]
        fd, rc = s["factuality_detection"], s["requirement_check"]
        lines += [
            "## Granite Switch (checkpoint templates, no truncation)",
            "",
            f"- Checkpoint: `{gs['granite_switch_checkpoint']}` on `{gs['device']}`",
            f"- Edges run: {gs['n_edges_run']}, wall time: {gs['wall_s']}s "
            f"({round(gs['wall_s'] / gs['n_edges_run'], 2)}s/edge, both adapters combined)",
            "",
            "### factuality-detection (checkpoint's own instruction, full text)",
            f"- Defect catch (gold UNSUPPORTED/WRONG_RELATION correctly flagged): "
            f"{fd['tp']}/{fd['n_unsupported_gold']} ({(fd['defect_catch_rate'] or 0):.1%})",
            f"- SUPPORTED false positives: {fd['fp']}/{fd['n_supported_gold']} "
            f"({(fd['supported_false_positive_rate'] or 0):.1%})",
            "",
            "### requirement-check (correct adapter for citation-satisfies-requirement)",
            f"- Defect catch: {rc['tp']}/{rc['n_unsupported_gold']} ({(rc['defect_catch_rate'] or 0):.1%})",
            f"- SUPPORTED false positives: {rc['fp']}/{rc['n_supported_gold']} "
            f"({(rc['supported_false_positive_rate'] or 0):.1%})",
            f"- Row-mismatch subset catch (the 8 edges v1 mis-tested with policy-guardrails): "
            f"{s['requirement_check_row_mismatch_catch']['caught']}/{s['requirement_check_row_mismatch_catch']['n']}",
            f"- Boilerplate subset catch: "
            f"{s['requirement_check_boilerplate_catch']['caught']}/{s['requirement_check_boilerplate_catch']['n']}",
            "",
        ]
    lines += [
        "## Seated Ollama compliance model (same corpus, same judgment question)",
        "",
        f"- Model: `{ol['model']}`",
        f"- Edges run: {ol['n_edges_run']}, wall time: {ol['wall_s']}s "
        f"({ol['mean_ms_per_edge']}ms/edge)",
        f"- Defect catch: {ol['scores']['defect_catch_rate']:.1%}"
        if ol["scores"]["defect_catch_rate"] is not None
        else "- Defect catch: n/a",
        f"- SUPPORTED false positives: {ol['scores']['supported_false_positive_rate']:.1%}"
        if ol["scores"]["supported_false_positive_rate"] is not None
        else "- SUPPORTED false positives: n/a",
        "",
        "## Operator gate (P3.G1, corrected)",
        "",
        "Compare requirement-check's defect catch / false-positive numbers against the",
        "seated Ollama model's, on both accuracy and wall-clock. This task does not wire",
        "either into the compliance module.",
        "",
        "Operator decision: PENDING",
        "",
    ]
    md_path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-max", type=int, default=183)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    gs = run_granite(args.n_max)
    ol = run_ollama(args.n_max)

    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_json = Path(args.out or f"tests/benchmarks/results/granite_switch_compliance_v2_{ts}.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps({"granite_switch": gs, "ollama": ol}, indent=2))
    md_path = out_json.with_suffix(".md")
    write_report(gs, ol, md_path)
    print(f"\nWrote {out_json}")
    print(f"Wrote {md_path}")
    return 0 if gs.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
