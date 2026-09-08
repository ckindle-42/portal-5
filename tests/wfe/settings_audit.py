#!/usr/bin/env python3
"""WFE settings/design/intent auditor — verifies every workspace incumbent against
its own intent: baked context vs declared, sampling vs lane policy, tool flags,
persona pins, council seats, backend registration. Zero model calls; pure config
+ Ollama metadata. This is the automated layer of 'verify settings, design,
intent, execution' — it catches the glm_coder-128K class of silent regressions.

Usage:
  uv run python -m tests.wfe.settings_audit            # human report
  uv run python -m tests.wfe.settings_audit --json     # machine-readable
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import urllib.request
from pathlib import Path

import yaml

from tests.wfe.runner import card_entry as _card_entry_matched

REPO = Path(__file__).resolve().parents[2]
OLLAMA = "http://localhost:11434"
EXPECTATIONS_PATH = REPO / "config" / "model_card_expectations.yaml"

#: Effective-temperature ceiling per lane, checked against what the pipeline
#: actually serves (see `effective_temperature`). The previous table covered 6
#: of 81 workspaces and — worse — compared only the BAKED tag value, so a
#: workspace that correctly pins a cool temperature over a hot tag was FAILed.
#:
#: `eval` is instrumentation, not a product: every `bench-*` workspace sets its
#: sampling per benchmark (often the model's own native default) to measure the
#: model as it would really run. A deterministic 0.4 ceiling there flagged 33
#: benchmarks that were behaving exactly as intended. It is now non-deterministic
#: at the Ollama default, so a bench is a WARN only when it runs HOTTER than
#: stock — a real "is that deliberate?" question, not a production failure.
LANE_SAMPLING = {
    "compliance": {"temperature": 0.3, "deterministic": True},
    "math": {"temperature": 0.3, "deterministic": True},
    "data": {"temperature": 0.4, "deterministic": True},
    "security": {"temperature": 0.4, "deterministic": True},
    "documents": {"temperature": 0.4, "deterministic": True},
    "coding": {"temperature": 0.5, "deterministic": False},
    "reasoning": {"temperature": 0.5, "deterministic": False},
    "research": {"temperature": 0.5, "deterministic": False},
    "cad": {"temperature": 0.5, "deterministic": False},
    "eval": {"temperature": 0.7, "deterministic": False},
    "general": {"temperature": 0.8, "deterministic": False},
    "media": {"temperature": 0.8, "deterministic": False},
    "image": {"temperature": 0.8, "deterministic": False},
    "video": {"temperature": 0.8, "deterministic": False},
}


def ctx_from_tag(tag: str) -> int | None:
    """Parse the -ctxNk naming convention into a token count."""
    m = re.search(r"-ctx(\d+)k$", tag)
    return int(m.group(1)) * 1024 if m else None


def _post(path: str, payload: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def installed_tags(backends: dict | None = None) -> set[str]:
    """Ollama tags PLUS oMLX backend aliases (oMLX models never appear in /api/tags)."""
    tags: set[str] = set()
    try:
        tags |= {m["name"] for m in _post("/api/tags", {}, timeout=10).get("models", [])}
    except Exception:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=10) as r:
            tags |= {m["name"] for m in json.load(r).get("models", [])}
    for b in (backends or {}).get("backends", []):
        if b.get("type") == "omlx":
            tags |= set(b.get("aliases") or {})
    return tags


def baked_params(tag: str) -> dict:
    params: dict = {}
    with contextlib.suppress(Exception):
        show = _post("/api/show", {"model": tag}, timeout=30)
        for line in (show.get("parameters") or "").splitlines():
            k, _, v = line.strip().partition(" ")
            with contextlib.suppress(ValueError):
                params[k] = float(v) if "." in v else int(v)
    return params


def _v(
    violations: list[dict], workspace: str, kind: str, detail: str, severity: str = "WARN"
) -> None:
    violations.append(
        {"workspace": workspace, "kind": kind, "detail": detail, "severity": severity}
    )


def _audit_context(ws_id, ws, hint, bp, tags, violations) -> None:
    declared_ctx = ws.get("context_limit")
    baked_ctx = bp.get("num_ctx")
    tag_ctx = ctx_from_tag(hint)

    # The previous audit SKIPPED this whole block for any hint matching
    # -ctx\d+k$, i.e. it trusted the tag name for exactly the 31 tags whose
    # names assert a window. The glm-4.7-flash regression was a tag whose NAME
    # promised 128K and whose weights did not. The name is now a claim to verify,
    # not a reason to stop looking.
    if tag_ctx is not None and hint in tags:
        if not baked_ctx:
            _v(
                violations,
                ws_id,
                "ctx_tag_unbacked",
                f"{hint} advertises {tag_ctx} tokens in its tag but bakes NO num_ctx "
                f"(/v1 ignores request-time options.num_ctx — the window is Ollama's default)",
                "FAIL",
            )
        elif baked_ctx != tag_ctx:
            _v(
                violations,
                ws_id,
                "ctx_tag_mismatch",
                f"{hint} advertises {tag_ctx} tokens in its tag but bakes num_ctx={baked_ctx}",
                "FAIL",
            )
    if declared_ctx and hint in tags:
        effective = baked_ctx or (tag_ctx if baked_ctx else None)
        if not effective:
            _v(
                violations,
                ws_id,
                "ctx_not_baked",
                f"context_limit={declared_ctx} declared but {hint} bakes no num_ctx "
                f"(the served window is Ollama's default, not {declared_ctx})",
                "FAIL",
            )
        elif effective < declared_ctx:
            _v(
                violations,
                ws_id,
                "ctx_below_declared",
                f"effective num_ctx={effective} < context_limit={declared_ctx}",
                "FAIL",
            )


def effective_temperature(ws: dict, bp: dict) -> tuple[float | None, str]:
    """The temperature the PIPELINE actually serves, not the one baked in the tag.

    router/validation.py injects the workspace's flat sampling block — or, when
    `think` is set, the matching `think_profiles` entry — into options at request
    time (`_resolve_sampling_values`, setdefault so the caller can still win).
    That override sits on top of whatever the tag bakes, so the served value is:
    think-profile temp -> workspace flat temp -> baked tag temp -> Ollama's 0.7
    default. The previous audit compared only the baked value against lane
    policy, so a workspace that correctly pins temperature 0.2 at the config
    layer over a tag that bakes 0.7 was reported as a FAIL it was not."""
    tp = ws.get("think_profiles") or {}
    tk = ws.get("think")
    prof = tp.get("thinking" if tk else "instruct") if (tp and tk is not None) else {}
    if isinstance(prof, dict) and prof.get("temperature") is not None:
        return float(prof["temperature"]), "think_profile"
    if ws.get("temperature") is not None:
        return float(ws["temperature"]), "workspace config"
    if bp.get("temperature") is not None:
        return float(bp["temperature"]), "baked tag"
    return None, "unset"


def _audit_sampling(ws_id, ws, hint, bp, tags, violations) -> None:
    policy = LANE_SAMPLING.get(str(ws.get("module", "")).lower())
    if not (policy and hint in tags):
        if hint in tags and ws.get("module"):
            _v(
                violations,
                ws_id,
                "lane_no_policy",
                f"module '{ws.get('module')}' has no LANE_SAMPLING entry — sampling unchecked",
            )
        return

    limit = policy["temperature"]
    eff, src = effective_temperature(ws, bp)
    if eff is None:
        if policy["deterministic"]:
            _v(
                violations,
                ws_id,
                "sampling_defaulted",
                f"{ws.get('module')} lane requires <= {limit} but neither the workspace config "
                f"nor {hint} sets a temperature — the pipeline serves Ollama's 0.7 default",
                "FAIL",
            )
    elif eff > limit + 1e-9:
        _v(
            violations,
            ws_id,
            "sampling_hot",
            f"{ws.get('module')} lane limit {limit} but the pipeline serves temperature={eff} "
            f"(from {src})",
            "FAIL" if policy["deterministic"] else "WARN",
        )

    # Defense in depth: the served value is compliant, but the TAG itself is not
    # lane-safe, so any request path that omits the workspace override (a direct
    # /v1 call, a future refactor) would exceed the policy.
    baked = bp.get("temperature")
    if baked is not None and baked > limit + 1e-9 and src != "baked tag":
        _v(
            violations,
            ws_id,
            "sampling_baked_hot",
            f"served temperature {eff} is within the {limit} lane limit, but {hint} bakes "
            f"temperature={baked} — a request that omits the workspace override would exceed it",
        )


def _audit_workspace(
    ws_id: str,
    ws: dict,
    tags: set[str],
    registered: set[str],
    tool_flags: dict[str, bool],
    violations: list[dict],
) -> None:
    hint = ws["model_hint"]

    if hint not in tags:
        _v(
            violations,
            ws_id,
            "hint_absent",
            f"model_hint {hint} not installed (workspace cannot serve)",
            "FAIL",
        )
    if hint not in registered:
        _v(
            violations,
            ws_id,
            "hint_unregistered",
            f"{hint} not registered in any backends.yaml models list",
            "FAIL",
        )

    bp = baked_params(hint) if hint in tags else {}
    _audit_context(ws_id, ws, hint, bp, tags, violations)
    _audit_sampling(ws_id, ws, hint, bp, tags, violations)

    ws_tools = ws.get("tools") or []
    if ws_tools and tool_flags.get(hint) is False:
        _v(
            violations,
            ws_id,
            "tools_unsupported",
            f"workspace declares tools {ws_tools} but backends marks {hint} supports_tools=false",
            "FAIL",
        )

    pin = ws.get("model_pin")
    if pin and pin not in tags:
        _v(violations, ws_id, "pin_absent", f"model_pin={pin} not installed", "FAIL")


_REASONING_TAG_RE = re.compile(
    r"(deepseek-r1|qwen3\.[5-9]|phi4.*reasoning|glm-4\.[67]|glm-z1|gpt-oss|granite4\.[12]"
    r"|magistral|nemotron.*lightning|qwen3-coder-next|Deepwen)",
    re.I,
)


def _is_reasoning_model(hint: str, registry: dict) -> bool:
    """A model that opens a <think> block by default. Card first (its
    harness_policy.think), then a conservative tag pattern for uncarded models."""
    hit = _card_entry_matched(hint, registry)
    if hit and (hit[1].get("harness_policy") or {}).get("think") == "true":
        return True
    return bool(_REASONING_TAG_RE.search(hint))


def _audit_reasoning_fit(ws_id, ws, hint, registry, tags, violations) -> None:
    """A <think> model run with no `think` control (the workspace doesn't set it)
    reasons at its native default. On /v1 the pipeline passes the workspace's
    `think` through, so a workspace that omits it leaves the model's reasoning
    on: on a deterministic lane that defeats the lane's purpose, and on any
    agentic lane the model can spend its whole output budget reasoning and never
    answer (observed: granite4.2 on tools-specialist)."""
    if hint not in tags or ws.get("think") is not None:
        return
    if not _is_reasoning_model(hint, registry):
        return
    module = str(ws.get("module", "")).lower()
    deterministic = LANE_SAMPLING.get(module, {}).get("deterministic")
    _v(
        violations,
        ws_id,
        "reasoning_uncontrolled",
        f"{hint} is a reasoning-family model but the workspace sets no `think` — "
        + (
            f"the {module} lane is deterministic and needs think:false"
            if deterministic
            else "verify the lane's token budget covers reasoning AND an answer"
        ),
        "FAIL" if deterministic else "WARN",
    )


def _audit_personas(tags: set[str], violations: list[dict]) -> int:
    checked = 0
    for pf in (REPO / "config/personas").glob("*.yaml"):
        d = yaml.safe_load(pf.read_text()) or {}
        pins: list[str] = []
        if isinstance(d.get("preferred_models"), list):
            pins += [x for x in d["preferred_models"] if isinstance(x, str)]
        if isinstance(d.get("model_pin"), str):
            pins.append(d["model_pin"])
        if not pins:
            continue
        checked += 1
        for pin in pins:
            if pin not in tags:
                _v(
                    violations,
                    f"persona:{d.get('slug', pf.stem)}",
                    "persona_pin_absent",
                    f"{pin} not installed (silent 404 when resolver reaches this pin)",
                    "FAIL",
                )
    return checked


def _audit_council(
    seats: dict, tags: set[str], registered: set[str], violations: list[dict]
) -> None:
    for sid, model in seats.items():
        if model not in tags:
            _v(
                violations,
                f"compliance-council:{sid}",
                "seat_absent",
                f"council seat model {model} not installed",
                "FAIL",
            )
        elif model not in registered:
            _v(
                violations,
                f"compliance-council:{sid}",
                "seat_unregistered",
                f"council seat model {model} not in backends.yaml",
            )


def _load_expectations() -> dict:
    """family-keyed ground-truth registry; tag-keyed entries take precedence."""
    if not EXPECTATIONS_PATH.exists():
        return {}
    data = yaml.safe_load(EXPECTATIONS_PATH.read_text()) or {}
    return data.get("models", {}) or {}


def _expectations_for(tag: str, registry: dict) -> tuple[str, dict] | None:
    """Longest-match-wins over separator-normalised keys, shared with the runner.

    The previous first-substring-wins scan resolved 28 of 81 production hints to
    the generic 'qwen3' entry — shadowing the specific qwen3.5/3.6/3.8 records —
    and matched NOTHING for granite, because registry keys are hyphenated
    ('granite-4.1') while installed tags are not ('granite4.1'). Dimensions 2
    and 3 were inert for most of the fleet as a result."""
    return _card_entry_matched(tag, registry)


def _template_sha(tag: str) -> str | None:
    import hashlib

    with contextlib.suppress(Exception):
        show = _post("/api/show", {"model": tag}, timeout=30)
        if show.get("template") is not None:
            return hashlib.sha256(show["template"].encode()).hexdigest()[:12]
    return None


def _card_check(tag: str, bp: dict, registry: dict, violations: list[dict], where: str) -> None:
    """Ground-truth layer: baked settings vs model-card expectations + research debt."""
    hit = _expectations_for(tag, registry)
    if hit is None:
        _v(
            violations,
            where,
            "card_no_ground_truth",
            f"{tag}: no model_card_expectations entry — card research owed (WFE-0.6)",
        )
        return
    key, entry = hit
    if entry.get("status") == "research-debt":
        _v(
            violations,
            where,
            "card_research_debt",
            f"{tag}: family '{key}' has no verified card ground truth yet (WFE-0.6)",
        )
        return
    rec = entry.get("recommended_sampling") or {}
    if isinstance(rec, dict) and rec.get("pending_research"):
        _v(
            violations,
            where,
            "card_research_debt",
            f"{tag}: recommended_sampling pending research (WFE-0.6)",
        )
    else:
        for k, want in (rec or {}).items():
            got = bp.get(k)
            if got is None:
                _v(
                    violations,
                    where,
                    "sampling_absent_vs_card",
                    f"{tag} bakes no {k} but the card recommends {k}={want} — the served "
                    f"value is Ollama's default, not the card's",
                )
            elif abs(float(got) - float(want)) > 1e-6:
                _v(
                    violations,
                    where,
                    "sampling_vs_card",
                    f"{tag} bakes {k}={got} but card recommends {k}={want}",
                    "FAIL",
                )
    max_ctx = entry.get("max_context")
    if isinstance(max_ctx, int) and bp.get("num_ctx") and bp["num_ctx"] > max_ctx:
        _v(
            violations,
            where,
            "ctx_over_card_max",
            f"{tag} bakes num_ctx={bp['num_ctx']} > card max {max_ctx}",
            "FAIL",
        )
    known_sha = entry.get("known_good_template_sha")
    if known_sha:
        current = _template_sha(tag)
        if current and current != known_sha:
            _v(
                violations,
                where,
                "template_drift",
                f"{tag} template sha {current} != known-good {known_sha} "
                f"(stock template may be wrong — re-verify against {entry.get('template_source', 'template_source')})",
                "WARN",
            )


def _behavioral_probes(tag: str, violations: list[dict], where: str) -> None:
    """One-call template probes: does the model honor a system instruction, and
    emit clean JSON? These catch broken/out-of-date chat templates that sha
    comparison cannot. Optional (adds ~2 model calls per tag)."""
    opts = {"temperature": 0.0, "num_predict": 20}
    try:
        r = _post(
            "/api/chat",
            {
                "model": tag,
                "stream": False,
                "messages": [
                    {"role": "system", "content": "Always answer the single word: BLUE."},
                    {"role": "user", "content": "What colour is grass? Answer in one word."},
                ],
                "options": opts,
            },
        )
        honored = "blue" in ((r.get("message") or {}).get("content", "") or "").lower()
        if not honored:
            _v(
                violations,
                where,
                "template_system_ignored",
                f"{tag}: system instruction NOT honored — chat template likely wrong/broken for this model",
                "FAIL",
            )
    except Exception as e:
        _v(violations, where, "probe_error", f"{tag}: behavioral probe failed: {e}", "FAIL")
        return
    try:
        r = _post(
            "/api/chat",
            {
                "model": tag,
                "stream": False,
                "format": "json",
                "messages": [
                    {
                        "role": "system",
                        "content": 'Reply with exactly {"ok": true} and nothing else.',
                    },
                    {"role": "user", "content": "go"},
                ],
                "options": {"temperature": 0.0, "num_predict": 40},
            },
        )
        raw = ((r.get("message") or {}).get("content", "") or "").strip()
        if not raw:
            _v(
                violations,
                where,
                "template_json_broken",
                f"{tag}: empty content under format:json — known gpt-oss-class harmony/template conflict",
                "WARN",
            )
    except Exception as e:
        _v(violations, where, "probe_error", f"{tag}: json probe failed: {e}", "WARN")


def run_audit(behavioral: bool = False) -> dict:
    registry = _load_expectations()
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())
    backends = yaml.safe_load((REPO / "config/backends.yaml").read_text())

    registered: set[str] = set()
    tool_flags: dict[str, bool] = {}
    for b in backends.get("backends", []):
        for m in b.get("models") or []:
            if isinstance(m, dict) and m.get("id"):
                registered.add(m["id"])
                tool_flags[m["id"]] = bool(m.get("supports_tools"))

    tags = installed_tags(backends)
    council_path = REPO / "config/compliance/council.yaml"
    seats: dict = {}
    if council_path.exists():
        council = yaml.safe_load(council_path.read_text()) or {}
        seats = {s.get("id"): s.get("model") for s in council.get("seats", [])}

    violations: list[dict] = []
    checked = 0
    for ws_id, ws in portal.get("workspaces", {}).items():
        if not isinstance(ws, dict) or not ws.get("model_hint"):
            continue
        checked += 1
        _audit_workspace(ws_id, ws, tags, registered, tool_flags, violations)
        hint = ws["model_hint"]
        _audit_reasoning_fit(ws_id, ws, hint, registry, tags, violations)
        if hint in tags:
            _card_check(hint, baked_params(hint), registry, violations, ws_id)
            if behavioral:
                _behavioral_probes(hint, violations, ws_id)

    personas_checked = _audit_personas(tags, violations)
    _audit_council(seats, tags, registered, violations)

    fails = [v for v in violations if v["severity"] == "FAIL"]
    return {
        "checked_workspaces": checked,
        "checked_personas": personas_checked,
        "council_seats": seats,
        "violations": violations,
        "fail_count": len(fails),
        "warn_count": len(violations) - len(fails),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--behavioral",
        action="store_true",
        help="add per-model template probes (system-honored + JSON; ~2 calls per tag)",
    )
    args = ap.parse_args()
    report = run_audit(behavioral=args.behavioral)
    if args.json:
        print(json.dumps(report, indent=1))
        return 1 if report["fail_count"] else 0
    print(
        f"WFE settings audit — {report['checked_workspaces']} workspaces, "
        f"{report['checked_personas']} personas with pins, {len(report['council_seats'])} council seats"
    )
    for v in report["violations"]:
        mark = "FAIL" if v["severity"] == "FAIL" else "warn"
        print(f"  [{mark}] {v['workspace']}: {v['kind']} — {v['detail']}")
    print(f"\n{report['fail_count']} FAIL / {report['warn_count']} warn")
    return 1 if report["fail_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
