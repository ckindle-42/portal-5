"""Granite Switch as a post-hoc verifier over the 183 compliance edges.

Runs inside ~/.portal5/granite-switch/.venv via subprocess so this module
never imports torch. Adapter names and output schemas are the ones shipped
in the checkpoint's io_configs: factuality-detection returns yes/no (yes =
the assistant claim is unsupported by the document), policy-guardrails
returns Yes/No/Ambiguous.
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

    FACT_INSTRUCTION = (
        "<guardian>As a judge agent, your role is to help assess whether the provided "
        "text meets the given judging criteria, utilizing all available information.\n\n"
        "### Criteria: A factually incorrect response occurs when the assistant's message "
        "contains one or more factual claims that are unsupported by, inconsistent with, "
        "or directly contradicted by the information provided in the documents or context.\n\n"
        "### Scoring Schema: If the last assistant's text meets the criteria, return 'yes'; "
        "otherwise, return 'no'. Your answer must be a JSON object with the key \"label\"."
    )
    POL_INSTRUCTION = (
        "<guardian> You are a compliance agent trying to help determine whether a scenario "
        "is compliant with a given policy.\n\n"
        "### Criteria: Policy: A citation must be relevant to standard {std}, not a different "
        "standard, and must substantiate the requirement rather than a reused boilerplate row.\n\n"
        "### Scoring Schema: Does the scenario described in the previous message comply with "
        "the policy? Answer Yes, No, or Ambiguous as a JSON object with the key \"label\"."
    )

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
        req = (e.get("requirement_text") or "")[:2000]
        sec = (e.get("section_text") or "")[:4000]
        std = e.get("standard") or ""
        fact_reply, fact_ms = _gen(
            [
                {"role": "user", "content": f"Document (standard context):\n{sec}"},
                {"role": "assistant", "content": req},
                {"role": "user", "content": FACT_INSTRUCTION},
            ],
            "factuality-detection",
        )
        pol_reply, pol_ms = _gen(
            [
                {"role": "user", "content": f"Citation scenario:\n{sec}\n\nRequirement:\n{req}"},
                {"role": "user", "content": POL_INSTRUCTION.format(std=std)},
            ],
            "policy-guardrails",
        )
        results.append({
            "assertion_id": e.get("assertion_id"),
            "standard": std,
            "gold_verdict": e.get("gold_verdict"),
            "is_boilerplate_pattern": e.get("is_boilerplate_pattern"),
            "is_row_mismatch_pattern": e.get("is_row_mismatch_pattern"),
            "factuality_reply": fact_reply,
            "factuality_ms": fact_ms,
            "policy_reply": pol_reply,
            "policy_ms": pol_ms,
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
    for word in (
        "ambiguous",
        "unsupported",
        "supported",
        "non-compliant",
        "compliant",
        "yes",
        "no",
    ):
        if word in lowered:
            return word
    return "unknown"


def _fact_verdict(reply: str) -> str:
    label = _label(reply)
    if label in ("yes", "unsupported"):
        return "unsupported"
    if label in ("no", "supported"):
        return "supported"
    if label == "ambiguous":
        return "ambiguous"
    return "unknown"


def _policy_verdict(reply: str) -> str:
    label = _label(reply)
    if label in ("no", "non-compliant"):
        return "non-compliant"
    if label in ("yes", "compliant"):
        return "compliant"
    if label == "ambiguous":
        return "ambiguous"
    return "unknown"


def _score(records: list[dict]) -> dict:
    for record in records:
        record["fact_verdict"] = _fact_verdict(record["factuality_reply"])
        record["policy_verdict"] = _policy_verdict(record["policy_reply"])

    boilerplate = [r for r in records if r["is_boilerplate_pattern"]]
    boil_catch = sum(1 for r in boilerplate if r["fact_verdict"] in ("unsupported", "ambiguous"))
    supported = [r for r in records if r["gold_verdict"] == "SUPPORTED"]
    supp_fp = sum(1 for r in supported if r["fact_verdict"] == "unsupported")
    row_mm = [r for r in records if r["is_row_mismatch_pattern"]]
    row_catch = sum(1 for r in row_mm if r["policy_verdict"] == "non-compliant")
    supp_pol_fp = sum(1 for r in supported if r["policy_verdict"] == "non-compliant")

    by_standard: dict[str, dict[str, int]] = {}
    for record in records:
        bucket = by_standard.setdefault(
            record.get("standard") or "?",
            {"n": 0, "boilerplate_caught": 0, "boilerplate_missed": 0, "supported_fp": 0},
        )
        bucket["n"] += 1
        if record["is_boilerplate_pattern"]:
            if record["fact_verdict"] in ("unsupported", "ambiguous"):
                bucket["boilerplate_caught"] += 1
            else:
                bucket["boilerplate_missed"] += 1
        if record["gold_verdict"] == "SUPPORTED" and record["fact_verdict"] == "unsupported":
            bucket["supported_fp"] += 1

    return {
        "n_records": len(records),
        "factuality": {
            "n_boilerplate_target": len(boilerplate),
            "n_boilerplate_caught": boil_catch,
            "boilerplate_catch_rate": (boil_catch / len(boilerplate)) if boilerplate else None,
            "n_supported": len(supported),
            "n_supported_fp": supp_fp,
            "supported_fp_rate": (supp_fp / len(supported)) if supported else None,
        },
        "policy_guardrails": {
            "n_row_mismatch_target": len(row_mm),
            "n_row_mismatch_caught": row_catch,
            "row_mismatch_catch_rate": (row_catch / len(row_mm)) if row_mm else None,
            "n_supported": len(supported),
            "n_supported_fp": supp_pol_fp,
            "supported_fp_rate": (supp_pol_fp / len(supported)) if supported else None,
        },
        "by_standard": by_standard,
    }


def run(n_max: int) -> dict:
    started = time.perf_counter()
    started_at = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    inner_script = "/tmp/_bench_gs_inner.py"
    Path(inner_script).write_text(_INNER)
    env = os.environ.copy()
    env["GS_MODEL_DIR"] = GS_MODEL_DIR

    print(f"  invoking Granite Switch under {GS_PYTHON} on {n_max} edges...")
    completed = subprocess.run(
        [GS_PYTHON, inner_script, EDGES_PATH, str(n_max)],
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
        "adapter_note": (
            "factuality-detection emits yes/no JSON (yes = claim unsupported by the "
            "document). policy-guardrails emits Yes/No/Ambiguous JSON. Mapped onto the "
            "task's supported/unsupported and compliant/non-compliant tables."
        ),
    }


def write_report(receipt: dict, md_path: Path) -> None:
    if receipt.get("status") != "OK":
        md_path.write_text(
            "# Granite Switch compliance probe\n\n"
            f"Status: BLOCKED\n\n```\n{receipt.get('stderr_tail') or receipt.get('reason')}\n```\n"
        )
        return
    scores = receipt["scores"]
    fact = scores["factuality"]
    pol = scores["policy_guardrails"]
    lines = [
        "# Granite Switch compliance probe",
        "",
        f"- Checkpoint: `{receipt['granite_switch_checkpoint']}`",
        f"- Device: `{receipt['device']}`",
        f"- Edges run: {receipt['n_edges_run']}",
        f"- Wall time: {receipt['wall_s']}s",
        f"- Portal HEAD: `{receipt['head_commit']}`",
        "",
        receipt.get("adapter_note", ""),
        "",
        "## Factuality",
        "",
        f"- Boilerplate catch: {fact['n_boilerplate_caught']}/{fact['n_boilerplate_target']}",
        (
            f"- SUPPORTED false positives: {fact['n_supported_fp']}/{fact['n_supported']} "
            f"({(fact['supported_fp_rate'] or 0):.1%})"
        ),
        "",
        "## Policy guardrails",
        "",
        (f"- Row-mismatch catch: {pol['n_row_mismatch_caught']}/{pol['n_row_mismatch_target']}"),
        (
            f"- SUPPORTED false positives: {pol['n_supported_fp']}/{pol['n_supported']} "
            f"({(pol['supported_fp_rate'] or 0):.1%})"
        ),
        "",
        "## Per standard",
        "",
        "| standard | n | boilerplate caught | boilerplate missed | supported FP |",
        "|---|---|---|---|---|",
    ]
    for name, bucket in sorted(scores["by_standard"].items()):
        lines.append(
            f"| {name} | {bucket['n']} | {bucket['boilerplate_caught']} | "
            f"{bucket['boilerplate_missed']} | {bucket['supported_fp']} |"
        )
    caught = [
        r
        for r in receipt["records"]
        if r["is_boilerplate_pattern"] and r["fact_verdict"] in ("unsupported", "ambiguous")
    ][:2]
    disagreed = [
        r
        for r in receipt["records"]
        if r["gold_verdict"] == "SUPPORTED" and r["fact_verdict"] == "unsupported"
    ][:3]
    lines += ["", "## Samples where Granite disagreed with a clean supported reading", ""]
    for record in disagreed:
        lines.append(
            f"- `{record['assertion_id']}` gold={record['gold_verdict']} "
            f"fact={record['fact_verdict']} reply={record['factuality_reply'][:180]}"
        )
    lines += ["", "## Samples where Granite flagged a boilerplate-shaped overclaim", ""]
    for record in caught:
        lines.append(
            f"- `{record['assertion_id']}` gold={record['gold_verdict']} "
            f"fact={record['fact_verdict']} reply={record['factuality_reply'][:180]}"
        )
    lines += [
        "",
        "## Operator gate (P3.G1)",
        "",
        "Ship as a compliance guard only if boilerplate catch is at least 50% and the",
        "SUPPORTED false-positive rate is at most 20%. Retain for tuning if boilerplate",
        "catch is at least 30%. Otherwise reject. This task does not wire the adapter.",
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
    receipt = run(args.n_max)
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_json = Path(args.out or f"tests/benchmarks/results/granite_switch_compliance_{ts}.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(receipt, indent=2))
    md_path = out_json.with_suffix(".md")
    write_report(receipt, md_path)
    print(f"\nWrote {out_json}")
    print(f"Wrote {md_path}")
    if receipt.get("status") == "OK":
        fact = receipt["scores"]["factuality"]
        pol = receipt["scores"]["policy_guardrails"]
        print(
            "factuality boilerplate catch: "
            f"{fact['n_boilerplate_caught']}/{fact['n_boilerplate_target']}"
        )
        print(
            f"factuality SUPPORTED false-positive: {fact['n_supported_fp']}/{fact['n_supported']}"
        )
        print(
            "policy row-mismatch catch: "
            f"{pol['n_row_mismatch_caught']}/{pol['n_row_mismatch_target']}"
        )
        return 0
    print(f"BLOCKED: {(receipt.get('reason') or receipt.get('stderr_tail') or '')[:400]}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
