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

__all__ = [
    "DEFAULT_ANSWER_BUDGET",
    "DEFAULT_EFFORT",
    "DEFAULT_NUM_CTX",
    "DEFAULT_REASONING_ALLOWANCE",
    "DEFAULT_TEMPERATURE",
    "ChatResult",
    "ContextCeilingError",
    "applied_context_length",
    "chat",
    "seat_ceiling",
    "strip_inline_reasoning",
]

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
    """A chat response, including the raw message needed for tool loops."""

    @property
    def content(self) -> str:
        return str(self.get("content", ""))

    @property
    def thinking(self) -> str:
        return str(self.get("thinking", ""))

    @property
    def reasoned(self) -> bool:
        return bool(self.get("reasoned"))

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        calls = self.get("tool_calls") or []
        return calls if isinstance(calls, list) else []

    @property
    def raw_message(self) -> dict[str, Any]:
        message = self.get("raw_message") or {}
        return message if isinstance(message, dict) else {}


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


#: What the model is allowed to spend on the ANSWER, in tokens.
DEFAULT_ANSWER_BUDGET = 3072

#: What a reasoning trace may spend ON TOP of the answer budget, when reasoning
#: is requested. It is never shared with the answer.
#:
#: ``num_predict`` covers thinking AND content on this endpoint, so a single
#: budget makes the two compete and the trace wins — measured on the reading
#: call site, where 1,600 tokens produced 6,382 characters of reasoning and an
#: EMPTY answer. Sizing the allowance separately is what the transport's own
#: docstring said the fix was. The figure is measured, not assumed: the
#: heaviest recorded trace on this seat is 34,097 characters, which at the
#: 4.22 chars/token observed on this material (P0.4, 140,000 chars ->
#: 33,142 prompt tokens) is ~8,080 tokens; 4,096 covers the "low"/"medium"
#: traces (6,382 and 6,258 chars, ~1,500 tokens) with room, and the automatic
#: retry doubles it once when it does not.
DEFAULT_REASONING_ALLOWANCE = 4096

#: Sampling for every compliance call, named so an auditor can see it.
#:
#: This was an unnamed ``0.0`` literal inside the payload, which is why
#: ``LANE_SAMPLING["compliance"]`` and the transport could disagree without
#: anything noticing. They do not in fact disagree: the lane value is a
#: CEILING (``settings_audit`` fails a lane when the served temperature is
#: ABOVE it) and 0.0 is under 0.3. Greedy decoding is what makes three runs of
#: one acceptance case comparable, so the transport keeps 0.0 and now says so.
DEFAULT_TEMPERATURE = 0.0

#: Requested context window, in tokens, for a compliance call.
#:
#: BILATERAL_CORPUS_V1 P6.7 gave every call an explicit ``num_ctx`` — Ollama had
#: been reserving the model's full window times ``OLLAMA_NUM_PARALLEL`` for each
#: of them (P5-ROUTER-EVICTION-001). It set the figure to 32,768, which is
#: EXACTLY what the seat tag bakes, leaving zero margin.
#:
#: Two things were measured on Ollama 0.34.0 before changing it
#: (reports/compliance/SETTINGS_PREFLIGHT_V1.md):
#:
#: * A baked ``num_ctx`` is a DEFAULT, not a ceiling. ``/api/chat`` honours a
#:   larger request-time ``options.num_ctx``: the same 140,000-character prompt
#:   that failed at 32,768 succeeded at 65,536, ``/api/ps`` reported
#:   ``context_length: 65536``, and all 33,142 prompt tokens were evaluated.
#:   (This is the native endpoint. ``/v1`` does ignore request-time options,
#:   which is why the tag exists at all.)
#: * The runner does NOT truncate from the front. An oversized prompt is HTTP
#:   400 ``exceed_context_size_error`` carrying ``n_prompt_tokens`` and
#:   ``n_ctx``. So the danger is a killed reading, not a fluent answer over
#:   silently cut material — and that error is now caught and named rather than
#:   escaping as a bare ``HTTPError``.
#:
#: The figure is sized for the worst case this call site can build, not for the
#: seed: a 12,000-character assembly, two bootstrap tool payloads and up to
#: twelve model-elected tool results, each bounded at 12,000 characters
#: (~43,000 tokens at the observed ratio), plus the answer budget and the
#: reasoning allowance. 65,536 holds that with roughly 15,000 tokens of margin
#: and keeps the 27B seat at 19.2 GB resident.
DEFAULT_NUM_CTX = 65536

_SHOW_ENDPOINT = "http://localhost:11434/api/show"
_PS_ENDPOINT = "http://localhost:11434/api/ps"
_CEILING: dict[str, int] = {}


class ContextCeilingError(RuntimeError):
    """A window was requested that the seat cannot serve.

    Raised BEFORE the call when the request exceeds the model's trained
    context, and raised FROM the runner's own 400 when the assembled prompt
    exceeds the window that was requested. Either way the number that was
    exceeded and the number that exceeded it are both in the message: the one
    thing this must never be is a silent clamp.
    """


def seat_ceiling(model: str) -> int:
    """The largest ``num_ctx`` this tag can serve — its TRAINED context.

    Read from ``/api/show`` ``model_info``'s ``*.context_length``, not from the
    ``-ctxNk`` tag suffix and not from the baked ``num_ctx``: both of those are
    defaults the request may exceed, and the trained length is the one that
    cannot be. Cached per tag; an unreadable one returns 0, which disables the
    pre-flight check rather than inventing a ceiling.
    """
    if model in _CEILING:
        return _CEILING[model]
    ceiling = 0
    try:
        request = urllib.request.Request(
            _SHOW_ENDPOINT,
            data=json.dumps({"model": model}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            info = (json.load(response) or {}).get("model_info") or {}
        ceiling = max(
            (int(value) for key, value in info.items() if key.endswith(".context_length")),
            default=0,
        )
    except Exception:  # noqa: BLE001 - an unreadable ceiling disables the check, never guesses
        ceiling = 0
    _CEILING[model] = ceiling
    return ceiling


def applied_context_length(model: str) -> int:
    """The window the runner ACTUALLY loaded, from ``/api/ps``.

    The requested ``num_ctx`` is a request. This is the applied value, and it is
    the only place the two can be compared, so every acceptance row records this
    one rather than the number it asked for.
    """
    try:
        with urllib.request.urlopen(_PS_ENDPOINT, timeout=10) as response:  # noqa: S310
            models = (json.load(response) or {}).get("models") or []
    except Exception:  # noqa: BLE001 - an unreadable runner is reported as unknown
        return 0
    for entry in models:
        if entry.get("name") == model or entry.get("model") == model:
            return int(entry.get("context_length") or 0)
    return 0


#: How long the seat stays resident between turns of one session. A conversation
#: is many calls to one model; paying the load cost on each of them is the
#: difference between a three-second exchange and a ninety-second one.
DEFAULT_KEEP_ALIVE = "30m"


def _exceeds_context(exc: urllib.error.HTTPError) -> dict[str, Any] | None:
    """The runner's own oversized-prompt report, parsed.

    Ollama 0.34.0 answers an oversized prompt with HTTP 400
    ``exceed_context_size_error`` carrying ``n_prompt_tokens`` and ``n_ctx``. It
    does NOT truncate from the front, so this is the failure mode that actually
    exists, and it arrives as an exception that would otherwise kill a reading
    with a bare ``HTTPError``.
    """
    try:
        body = json.loads(exc.read().decode())
    except Exception:  # noqa: BLE001 - an unparseable body is not this error
        return None
    inner = body.get("error")
    if isinstance(inner, str):
        try:
            inner = json.loads(inner)
        except Exception:  # noqa: BLE001
            return None
    detail = (inner or {}).get("error") if isinstance(inner, dict) else None
    if isinstance(detail, dict) and detail.get("type") == "exceed_context_size_error":
        return detail
    return None


def _unpack(raw: dict[str, Any]) -> tuple[str, str]:
    """Content and reasoning, read from the two fields the native endpoint keeps
    apart, with a defensive strip for a template that still inlines its block."""
    message = raw.get("message") or {}
    raw_content = str(message.get("content", "") or "")
    return (
        strip_inline_reasoning(raw_content) if "<think>" in raw_content else raw_content,
        str(message.get("thinking", "") or ""),
    )


def _attempt(body: dict[str, Any], answer_budget: int, allowance: int) -> dict[str, Any]:
    content, thinking = _unpack(body)
    return {
        "answer_budget": answer_budget,
        "reasoning_allowance": allowance,
        "thinking_chars": len(thinking),
        "answer_chars": len(content),
        "eval_count": body.get("eval_count", 0),
    }


def _post_judged(
    model: str,
    build: Any,
    allowance: int,
    want_think: bool | str,
    timeout: int,
) -> tuple[dict[str, Any], bool | str, str]:
    """One POST, with the two HTTP 400s this endpoint actually returns told apart.

    ``exceed_context_size_error`` is a window that could not hold the prompt and
    becomes a named :class:`ContextCeilingError`; the other 400 is "does not
    support thinking", which is cached and retried once with the flag off. They
    used to be one branch, so an oversized prompt on a reasoning model was
    retried as a non-reasoning call and then failed again with a bare
    ``HTTPError``.
    """
    try:
        body = _post(build(allowance, want_think), timeout)
    except urllib.error.HTTPError as exc:
        if exc.code != 400:
            raise
        overflow = _exceeds_context(exc)
        if overflow:
            raise ContextCeilingError(
                f"{model}: the assembled prompt is {overflow.get('n_prompt_tokens')} tokens "
                f"and the requested window is {overflow.get('n_ctx')} — the runner refused "
                "it rather than truncating"
            ) from exc
        if not want_think:
            raise
        _THINK_CAPABLE[model] = False
        return (
            _post(build(allowance, False), timeout),
            False,
            f"model does not support thinking (HTTP 400): {model}",
        )
    if want_think:
        _THINK_CAPABLE[model] = True
    return body, want_think, ""


def chat(
    model: str,
    system: str = "",
    user: str = "",
    *,
    messages: list[dict[str, Any]] | None = None,
    tools: list[dict[str, Any]] | None = None,
    budget: int | None = None,
    answer_budget: int | None = None,
    reasoning_allowance: int = DEFAULT_REASONING_ALLOWANCE,
    fmt: Any = "json",
    think: bool | str | None = None,
    timeout: int = 900,
    num_ctx: int = DEFAULT_NUM_CTX,
    temperature: float = DEFAULT_TEMPERATURE,
    keep_alive: str = DEFAULT_KEEP_ALIVE,
) -> ChatResult:
    """One judged call. The effort level is explicit; a downgrade is recorded.

    ``think`` is ``True``/``False`` or a reasoning-effort level the server
    passes to the chat template (``"low"``/``"medium"``/``"high"``). The level
    matters: this roster's Qwen3.8 template sets
    ``reasoning_effort|default('xhigh')``, so plain ``True`` buys the most
    expensive setting the model has. ``None`` takes :data:`DEFAULT_EFFORT`,
    whose value is set by measurement — see the comment there.

    **The answer and the reasoning trace have separate allowances.**
    ``num_predict`` covers both on this endpoint, so one number made them
    compete and the trace won: the reading call site returned an EMPTY answer
    after spending its whole budget inside ``thinking``. ``num_predict`` is now
    ``answer_budget + reasoning_allowance`` when reasoning is on and
    ``answer_budget`` when it is off, so turning reasoning on cannot shrink the
    answer. ``budget`` remains an alias for ``answer_budget`` so no existing
    call site changes behaviour.

    A reasoning trace that still leaves the answer empty is a BUDGET ERROR, not
    an answer: it retries once at double the allowance, records both attempts,
    and reports ``stop_reason="budget_exhausted_in_reasoning"`` if the second
    attempt is empty too. It is never returned as a substantive answer and
    never as evidence about reasoning.
    """
    if think is None:
        think = DEFAULT_EFFORT
    if answer_budget is None:
        answer_budget = DEFAULT_ANSWER_BUDGET if budget is None else int(budget)
    started = time.time()
    want_think: bool | str = think if isinstance(think, str) else bool(think)
    if not _THINK_CAPABLE.get(model, True):
        want_think = False

    ceiling = seat_ceiling(model)
    if ceiling and num_ctx > ceiling:
        # Stated, never clamped. A window silently reduced to the trained length
        # is a reading that believes it holds material it does not.
        raise ContextCeilingError(
            f"{model}: num_ctx={num_ctx} exceeds the seat's trained context ({ceiling}); "
            "reduce the window or choose a seat that can hold the material"
        )

    sent_messages = (
        messages
        if messages is not None
        else [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )

    def build(allowance: int, thinking: bool | str) -> dict[str, Any]:
        predict = answer_budget + (allowance if thinking else 0)
        payload: dict[str, Any] = {
            "model": model,
            "messages": sent_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": predict,
                "num_ctx": num_ctx,
            },
            "keep_alive": keep_alive,
            # Always explicit. Omitting the key is NOT suppression: it leaves the
            # model's own chat template in charge, and a Qwen3/DeepSeek/GLM-Z1
            # template opens <think> by default. Measured on
            # Qwen3.8-27B with this exact packet — omitted vs "think": true produced
            # byte-identical responses (34097 thinking chars, eval_count 7996 both
            # times), i.e. omission reasons. Only `"think": false` actually
            # suppresses, which is what the production transport sent.
            "think": thinking,
        }
        # `format` is omitted, not nulled, when the caller wants prose: a reading
        # answers in prose and a JSON envelope is the schema P6 exists to not have.
        if fmt:
            payload["format"] = fmt
        if tools is not None:
            payload["tools"] = tools
        return payload

    allowance = reasoning_allowance
    body, want_think, downgraded = _post_judged(model, build, allowance, want_think, timeout)

    content, thinking = _unpack(body)
    attempts = [_attempt(body, answer_budget, allowance if want_think else 0)]
    stop_reason = ""
    if want_think and not content.strip() and thinking:
        # One retry at double the allowance. The answer budget is untouched:
        # what was starved was the trace's room, not the answer's.
        allowance *= 2
        body = _post(build(allowance, want_think), timeout)
        content, thinking = _unpack(body)
        attempts.append(_attempt(body, answer_budget, allowance))
        if not content.strip():
            stop_reason = "budget_exhausted_in_reasoning"

    message = body.get("message") or {}
    prompt_bytes = sum(len(str(entry.get("content", "")).encode()) for entry in sent_messages)
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
        prompt_bytes=prompt_bytes,
        num_ctx=num_ctx,
        num_ctx_applied=applied_context_length(model),
        seat_ceiling=ceiling,
        temperature=temperature,
        answer_budget=answer_budget,
        reasoning_allowance=allowance if want_think else 0,
        num_predict=answer_budget + (allowance if want_think else 0),
        attempts=attempts,
        stop_reason=stop_reason,
        keep_alive=keep_alive,
        reasoning_effort=want_think if isinstance(want_think, str) else str(bool(want_think)),
        model=model,
        tool_calls=message.get("tool_calls") or [],
        raw_message=message,
    )
