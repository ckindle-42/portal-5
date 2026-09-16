"""The compliance model transport — reasoning is a first-class channel.

Native ``/api/chat`` returns ``message.thinking`` separately from
``message.content``, so a reasoning trace never contaminates strict JSON. The
earlier suppression (946196bb) was introduced to stop ``<think>`` leaking into
content and exhausting a 900-token budget; on this endpoint that is solved by
reading the right field and sizing the budget, not by disabling reasoning on a
task that is entirely reasoning.

A model without thinking capability answers HTTP 400. That is detected once per
model and cached, and the call is retried without the flag. A downgrade is
recorded on the response so a trace can never present a non-reasoning answer as
a reasoning one — on the D0-M roster two of the three council seats
(``granite4.1:30b``, ``mistral-small3.2:24b``) take that path on every run, so
the distinction is not hypothetical and must survive into the receipt.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

__all__ = ["DEFAULT_EFFORT", "ChatResult", "chat", "strip_inline_reasoning"]

# The one reasoning knob for every compliance model call.
#
# Measured 2026-09-14 on the byte-exact live case-10 alignment packet, one
# variable, same prompt and model (reports/compliance/THINKING_CONFOUND_V1.md):
#
#     think:false    52.4s      0 thinking chars   A22 SAME, L22 SAME, 35/40
#     think:low     179.5s   5206 thinking chars   A22 SAME, L22 SAME, 35/40
#     think:medium  224.0s   8710 thinking chars   A22 SAME, L22 SAME, 35/40
#     think:true    683.0s  34097 thinking chars   A22 SAME, L22 SAME, 35/40
#
# Four settings, one answer, up to 13x the wall time. `true` is the worst of
# them and not neutral: this roster's template reads
# reasoning_effort|default('xhigh'), so `true` buys the most expensive setting
# the model has. The default therefore stays where production already had it —
# that choice needs no new evidence, whereas raising it does, and none exists.
#
# What the transport changed is that reasoning is now *available, explicit and
# recorded*: a caller passes an effort level per call, a model that cannot
# reason is detected and its downgrade written onto the response. Raising this
# for a given call site is a measurement on that call site, not an assumption
# carried over from this one.
#
# BILATERAL_CORPUS_V1 P6.7 did that measurement for the READING call site — a
# prose answer over a ~27,000-token bilateral neighbourhood, which is a
# different packet answering a different question from the JSON alignment
# verdict above. Qwen3.8-27B, same packet, same question, one variable
# (reports/compliance/seat_probe/20260916T134144Z-effort.json):
#
#     think:false    432.0s      0 thinking chars   4,756-char answer, 7 citations
#     think:low      449.8s  6,382 thinking chars   EMPTY answer, 0 citations
#     think:medium   148.5s  6,258 thinking chars   EMPTY answer, 0 citations
#
# Not "slower for the same answer" as on the alignment packet — NO ANSWER. The
# reasoning trace consumed the entire num_predict budget and the content field
# came back empty. Reasoning stays off here, now for a reason measured here.
DEFAULT_EFFORT: bool | str = False

_ENDPOINT = "http://localhost:11434/api/chat"
_THINK_CAPABLE: dict[str, bool] = {}
_INLINE_THINK = re.compile(r"<think>.*?</think>\s*", re.S | re.I)


class ChatResult(dict[str, Any]):
    """A chat response. ``content`` is the answer; ``thinking`` is the trace."""

    @property
    def content(self) -> str:
        return str(self.get("content", ""))

    @property
    def thinking(self) -> str:
        return str(self.get("thinking", ""))

    @property
    def reasoned(self) -> bool:
        return bool(self.get("reasoned"))


def strip_inline_reasoning(text: str) -> str:
    """Defensive: a non-native template may still emit an inline think block."""
    return _INLINE_THINK.sub("", text).strip()


def _post(payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        _ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        result: dict[str, Any] = json.load(response)
        return result


#: Requested context window, in tokens, for a compliance call.
#:
#: BILATERAL_CORPUS_V1 P6.7. ``options.num_ctx`` was absent from every
#: compliance call site, so Ollama reserved the MODEL'S FULL WINDOW multiplied
#: by ``OLLAMA_NUM_PARALLEL`` for each of them — P5-ROUTER-EVICTION-001, fixed
#: in the router and never applied here. A reading call now states the window it
#: actually needs, which is the size of the assembly plus room to answer.
DEFAULT_NUM_CTX = 32768

#: How long the seat stays resident between turns of one session. A conversation
#: is many calls to one model; paying the load cost on each of them is the
#: difference between a three-second exchange and a ninety-second one.
DEFAULT_KEEP_ALIVE = "30m"


def chat(
    model: str,
    system: str,
    user: str,
    *,
    budget: int = 4096,
    fmt: Any = "json",
    think: bool | str | None = None,
    timeout: int = 900,
    num_ctx: int = DEFAULT_NUM_CTX,
    keep_alive: str = DEFAULT_KEEP_ALIVE,
) -> ChatResult:
    """One judged call. The effort level is explicit; a downgrade is recorded.

    ``think`` is ``True``/``False`` or a reasoning-effort level the server
    passes to the chat template (``"low"``/``"medium"``/``"high"``). The level
    matters: this roster's Qwen3.8 template sets
    ``reasoning_effort|default('xhigh')``, so plain ``True`` buys the most
    expensive setting the model has. ``None`` takes :data:`DEFAULT_EFFORT`,
    whose value is set by measurement — see the comment there.
    """
    if think is None:
        think = DEFAULT_EFFORT
    started = time.time()
    want_think: bool | str = think if isinstance(think, str) else bool(think)
    if not _THINK_CAPABLE.get(model, True):
        want_think = False
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": budget, "num_ctx": num_ctx},
        "keep_alive": keep_alive,
        # Always explicit. Omitting the key is NOT suppression: it leaves the
        # model's own chat template in charge, and a Qwen3/DeepSeek/GLM-Z1
        # template opens <think> by default. Measured on
        # Qwen3.8-27B with this exact packet — omitted vs "think": true produced
        # byte-identical responses (34097 thinking chars, eval_count 7996 both
        # times), i.e. omission reasons. Only `"think": false` actually
        # suppresses, which is what the production transport sent.
        "think": want_think,
    }
    # `format` is omitted, not nulled, when the caller wants prose: a reading
    # answers in prose and a JSON envelope is the schema P6 exists to not have.
    if fmt:
        payload["format"] = fmt

    downgraded = ""
    try:
        body = _post(payload, timeout)
    except urllib.error.HTTPError as exc:
        if not want_think or exc.code != 400:
            raise
        # "does not support thinking" — record it, retry once with the flag
        # explicitly off. Such a model accepts "think": false (that is what the
        # pre-task transport sent to all three seats); it rejects only true.
        _THINK_CAPABLE[model] = False
        downgraded = f"model does not support thinking (HTTP 400): {model}"
        payload["think"] = False
        body = _post(payload, timeout)
        want_think = False
    else:
        if want_think:
            _THINK_CAPABLE[model] = True

    message = body.get("message") or {}
    raw_content = str(message.get("content", "") or "")
    thinking = str(message.get("thinking", "") or "")
    content = strip_inline_reasoning(raw_content) if "<think>" in raw_content else raw_content
    # P6.7: enough to reason about latency afterwards. `_recording_seat_fn`
    # stored {model, raw}, so no run in the module's history has a single
    # recorded duration, token count or load time to argue from.
    return ChatResult(
        content=content,
        thinking=thinking,
        reasoned=bool(want_think),
        downgraded=downgraded,
        elapsed=time.time() - started,
        eval_count=body.get("eval_count", 0),
        prompt_eval_count=body.get("prompt_eval_count", 0),
        eval_duration_s=round(float(body.get("eval_duration", 0) or 0) / 1e9, 3),
        prompt_eval_duration_s=round(float(body.get("prompt_eval_duration", 0) or 0) / 1e9, 3),
        load_duration_s=round(float(body.get("load_duration", 0) or 0) / 1e9, 3),
        total_duration_s=round(float(body.get("total_duration", 0) or 0) / 1e9, 3),
        prompt_bytes=len(system.encode()) + len(user.encode()),
        num_ctx=num_ctx,
        keep_alive=keep_alive,
        reasoning_effort=want_think if isinstance(want_think, str) else str(bool(want_think)),
        model=model,
    )
