"""Deep-lane (auto-reasoning ?variant=deep) head-to-head: thinking on, deep variant's
sampling + system prompt. One request in flight. Usage: run_deep.py ARM REPEATS OUT"""

import json
import re
import subprocess
import sys
import time
import urllib.request
import zlib
from fractions import Fraction

SYS = "You are a deep reasoning AI. Break down complex problems step-by-step. Show your work. Acknowledge uncertainty. Distinguish between facts and inferences."
SUFFIX = "\n\nEnd your reply with a final line of exactly this form: ANSWER: <answer>"
SAMP = dict(temperature=0.6, top_p=0.95, top_k=20, min_p=0.0, repeat_penalty=1.1)
MAXTOK = 24576
ARMS = {
    "ollama": dict(
        kind="ollama",
        url="http://127.0.0.1:11434/api/chat",
        model="hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k",
    ),
    "prismml": dict(
        kind="v1", url="http://127.0.0.1:11238/v1/chat/completions", model="anchor_v2_pq2"
    ),
    "mtplx": dict(
        kind="v1",
        url="http://127.0.0.1:11241/v1/chat/completions",
        model="Ternary-Bonsai-2-27B-MTPLX-Optimized-Speed",
    ),
}


def post(url, body, timeout=3600):
    req = urllib.request.Request(
        url, json.dumps(body).encode(), {"content-type": "application/json"}
    )
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def swap_mb():
    out = subprocess.run(["sysctl", "vm.swapusage"], capture_output=True, text=True).stdout
    return float(re.search(r"used = ([\d.]+)M", out).group(1))


def norm(s):
    s = s.strip().strip("`*. ").replace(" ", "").upper()
    try:
        return str(Fraction(s))
    except Exception:
        return s


def answer(content):
    m = re.findall(r"ANSWER:\s*(.+)", content or "")
    return m[-1].strip() if m else None


def looped(text):
    tail = (text or "")[-4000:]
    return len(tail) >= 2000 and len(zlib.compress(tail.encode())) / len(tail) < 0.12


arm, repeats, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
a = ARMS[arm]
prompts = json.load(open(sys.argv[4] if len(sys.argv) > 4 else "prompts.json"))
f = open(out, "a")
for r in range(repeats):
    for i, p in enumerate(prompts):
        msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": p["q"] + SUFFIX}]
        seed = 5000 + i * 10 + r
        s0 = swap_mb()
        t0 = time.monotonic()
        err = None
        try:
            if a["kind"] == "ollama":
                d = post(
                    a["url"],
                    {
                        "model": a["model"],
                        "messages": msgs,
                        "stream": False,
                        "think": True,
                        "options": {**SAMP, "num_predict": MAXTOK, "seed": seed},
                    },
                )
                content, reasoning = (
                    d["message"].get("content", ""),
                    d["message"].get("thinking", ""),
                )
                finish, ntok = d.get("done_reason"), d.get("eval_count")
                tps = (
                    d["eval_count"] / (d["eval_duration"] / 1e9) if d.get("eval_duration") else None
                )
            else:
                d = post(
                    a["url"],
                    {
                        "model": a["model"],
                        "messages": msgs,
                        "max_tokens": MAXTOK,
                        "seed": seed,
                        **SAMP,
                        "chat_template_kwargs": {"enable_thinking": True},
                    },
                )
                m = d["choices"][0]["message"]
                content, reasoning = (
                    m.get("content") or "",
                    m.get("reasoning_content") or m.get("reasoning") or "",
                )
                finish, ntok = (
                    d["choices"][0].get("finish_reason"),
                    (d.get("usage") or {}).get("completion_tokens"),
                )
                tps = None
        except Exception as e:
            content = reasoning = ""
            finish = ntok = tps = None
            err = repr(e)[:300]
        wall = time.monotonic() - t0
        if tps is None and ntok:
            tps = ntok / wall
        ans = answer(content)
        row = dict(
            arm=arm,
            id=p["id"],
            repeat=r,
            expected=p["a"],
            answer=ans,
            correct=bool(ans) and norm(ans) == norm(p["a"]),
            finish=finish,
            completion_tokens=ntok,
            reasoning_chars=len(reasoning),
            content_chars=len(content),
            wall_s=round(wall, 1),
            tok_s=round(tps, 2) if tps else None,
            looped=looped(reasoning) or looped(content),
            swap_growth_mb=round(swap_mb() - s0, 1),
            error=err,
            content_tail=(content or "")[-300:],
        )
        f.write(json.dumps(row) + "\n")
        f.flush()
        print(
            f"{arm} r{r} {p['id']} {'OK ' if row['correct'] else 'BAD'} ans={ans!r} fin={finish} tok={ntok} {row['wall_s']}s loop={row['looped']}",
            flush=True,
        )
