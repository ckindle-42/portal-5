# SETTINGS_PREFLIGHT_V1 — the settings the transport requests, proven applied

**Task:** `TASK_COMPLIANCE_PROVE_CIP_007_V1` §P0 · **Base:** `0db04c6f`
**Runner:** Ollama 0.34.0, host-native · **Measured:** 2026-09-17
**Machine:** M4 Pro, 64 GiB · **Measurements:** `SETTINGS_PREFLIGHT_V1.json`

Reproduce:

```bash
uv run python -m tests.wfe.settings_audit --json                      # fleet, no model calls
uv run python -m tests.wfe.settings_audit --tag <tag> --behavioral    # one seat, 7 calls
uv run python -m tests.wfe.compliance_preflight --json                # the request path
uv run python -m tests.wfe.compliance_preflight --survey              # populations only
```

---

## Verdict — GO on all three candidate seats

| seat | template sha | baked `num_ctx` | tools | think | applied `num_ctx` | go |
| --- | --- | --- | --- | --- | --- | --- |
| `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` (incumbent) | `701ba13a085c` | 32768 | rendered | honored | 65536 | **GO** |
| `glm-4.7-flash:Q4_K_M-ctx64k` | `b507b9c2f6ca` | 65536 | rendered | honored | 65536 | **GO** |
| `qwen3.6:27b-q4_K_M` | `b507b9c2f6ca` | *none* | rendered | honored | 65536 | **GO** |

No relevant FAIL remains in the fleet audit for the compliance lane or any
candidate seat.

---

## §P0.1 — the audit that already existed

`tests/wfe/settings_audit.py` had **zero references** from the compliance
reading path. Run against the fleet it reported 88 violations, 12 FAIL, of which
7 touch this run:

| severity | workspace | kind | detail |
| --- | --- | --- | --- |
| FAIL | `auto-compliance` | `sampling_hot` | lane limit 0.3, pipeline serves 0.5 |
| FAIL | `compliance-reading` | `sampling_hot` | lane limit 0.3, pipeline serves 0.5 |
| FAIL | `persona:qwen38coder-dflash` | `persona_pin_absent` | `Qwen3.8-27B-4bit` not installed |
| WARN | `auto-compliance` | `card_research_debt` | family `qwen3.8` has no verified card ground truth |
| WARN | `compliance-reading` | `card_research_debt` | as above |
| WARN | `bench-qwen38-27b` | `card_research_debt` | as above, bare tag |
| WARN | `compliance-council:mistral` | `seat_unregistered` | council seat not in `backends.yaml` |

The two `sampling_hot` FAILs are fixed below. `persona_pin_absent` is an oMLX
pin on a coding persona, not a compliance seat and not on this run's path: it is
**carried as an open fleet FAIL**, named here rather than fixed, because nothing
in the reading path resolves it. The four WARNs are carried.

### A defect in the audit's own probe, found by running it

The pre-existing `template_system_ignored` probe FAILed the incumbent seat. It
was wrong, and the reason matters because it is this task's §0.4 in miniature:

```
think omitted  -> thinking 86 chars, content '',     FAIL reported
think: false   -> thinking  0 chars, content 'BLUE', correct
```

The probe sent `num_predict: 20` and **omitted** `think`. Omitting the key is
not suppression — it leaves the chat template in charge, and a Qwen3-family
template opens `<think>` by default. The trace ate the whole 20-token budget and
the probe read the empty `content` as a broken template. Both template probes
now send `think: false` explicitly; reasoning is measured by its own probe. This
was failing correct templates fleet-wide on every reasoning-family tag.

---

## §P0.2 — declared against actual, settled

### Context ceiling — the premise was wrong, and the measurement is better news

The task assumed a baked `num_ctx` is a ceiling, that a larger request is a
silent no-op, and that an oversized prompt is truncated from the front. All
three were measured on the incumbent seat and none holds on Ollama 0.34.0 via
native `/api/chat`:

| measurement | result |
| --- | --- |
| 140,000-char prompt, `num_ctx: 32768` (= the baked value) | **HTTP 400** `exceed_context_size_error`, `n_prompt_tokens: 33142`, `n_ctx: 32768` |
| same prompt, `num_ctx: 65536` (above the baked value) | OK, `prompt_eval_count: 33142`, correct answer |
| `/api/ps` after that call | `context_length: 65536`, `size_vram` 19.2 GB |

So: a baked `num_ctx` is a **default**, the request overrides it upward, and the
runner **refuses rather than truncates**. The danger was never a fluent answer
over silently cut material — it was a killed reading and an unhandled
`HTTPError`. `qwen3.6:27b-q4_K_M`, which bakes no `num_ctx` at all, also served
the requested 65536, confirming the same. (The `-ctxNk` tags still earn their
place: `/v1`, which the pipeline uses, does ignore request-time options.)

`DEFAULT_NUM_CTX` moves **32768 → 65536**, derived rather than picked: the worst
case this loop can build is a 12,000-char assembly, two bootstrap tool payloads
and up to twelve model-elected tool results at 12,000 chars each — about 43,000
tokens at the observed ratio — plus the 3,072-token answer budget and the
4,096-token reasoning allowance. Against the largest real case it leaves 41,778
tokens of margin. The seat's true ceiling is its **trained** context, 262,144,
read from `/api/show`; `reading_transport.seat_ceiling()` now reads it, a
request above it is a `ContextCeilingError` **before** the call, and the
runner's own 400 is caught and re-raised as the same named error carrying both
numbers. Nothing is clamped silently.

`reader.read()` also sized its window from the FIRST turn's prefix only, while
the loop appends a tool result per turn — the smallest thread the reading will
ever have. The window now floors at `DEFAULT_NUM_CTX`.

### chars per token — over-counting, not under-counting

`reading_assembly.CHARS_PER_TOKEN = 2.1`. Observed on the real first-turn
thread: **3.15** (incumbent and `qwen3.6`), **3.41** (`glm-4.7-flash`), and 4.22
on raw corpus text without the tool schemas. The constant therefore reserves
roughly 1.5× the window it needs. That is the **safe** direction and it is left
alone deliberately — the number that reserves a window must never be optimistic.
The §P0.4 observed ratio is what sizing decisions use.

### Two tags, one model

Both exist and both stay; nothing is deleted.

| tag | bakes | used by |
| --- | --- | --- |
| `…Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` | `num_ctx 32768` | `auto-compliance`, `compliance-reading` |
| `…Qwen3.8-27B-GGUF:Q4_K_M` | nothing | `bench-qwen38-27b` (module `eval`) |

`config/portal.yaml` already names exactly one of them for the compliance lane —
the `-ctx32k` tag — and that is the one the lane keeps. The bare tag's existence
and its single consumer are recorded here.

### Temperature — three values, and the one that was actually wrong

| layer | value | verdict |
| --- | --- | --- |
| `LANE_SAMPLING["compliance"]` | 0.3, deterministic | a **ceiling**, not a target — kept |
| `reading_transport` payload | 0.0 | inside the ceiling; was an unnamed literal — **now `DEFAULT_TEMPERATURE`**, and recorded on every result |
| `portal.yaml` compliance workspaces | 0.5 | **above** the ceiling — this was the wrong one, now **0.3** |

The declared policy and the transport never disagreed in substance; the audit
could not see the transport's value at all, because it was an anonymous literal
inside a dict. It is a named constant and travels on every `ChatResult`.

---

## §P0.3 — the two probes the audit was missing

Both added to `tests/wfe/settings_audit._behavioral_probes`, in the shared
harness, so the next consumer inherits them. `--tag <tag>` probes one seat
instead of sweeping every workspace incumbent.

**`template_tools_ignored`** sends a real `tools` array and a question only a
tool call can answer. Prose with no `tool_calls` is a FAIL. This promotes the P6
gate's `tool_trace=[]` from a mystery to a measurement: a template that drops
`tools` produces exactly the trace of a model choosing not to call anything, and
no prompt can repair it.

**`template_think_ignored`** sends `think: true` then `think: false`. Honored
means `message.thinking` non-empty then empty. A tag answering HTTP 400 is
recorded as REFUSED (the `_THINK_CAPABLE` downgrade), never confused with one
that silently ignores the flag.

Results — all three candidate seats render tools and honor think:

| seat | `tool_calls` returned | thinking chars (`true` / `false`) | verdict |
| --- | --- | --- | --- |
| Qwen3.8-27B ctx32k | yes, `get_vault_code` | 48 / 0 | honored |
| glm-4.7-flash ctx64k | yes, `get_vault_code` | 404 / 0 | honored |
| qwen3.6:27b | yes, `get_vault_code` | 425 / 0 | honored |

**This settles a registration contradiction.** `glm-4.7-flash:Q4_K_M` and
`:Q4_K_M-ctx64k` were `supports_tools: false` under `ollama-general` and `true`
under `ollama-coding`/`ollama-security`; `qwen3.6:27b-q4_K_M` and its `-ctx16k`
tag likewise. One model cannot both render a tools array and not render one, and
nothing in the module ever produced that field. The probe does, and the four
`ollama-general` entries are corrected to `true` with the measurement recorded
beside them.

`qwen3.6:35b-a3b-q4_K_M`, which the task names as registered both ways, is
registered `true` in both of its groups and is **not installed**. It cannot be
probed and is not a candidate seat.

---

## §P0.4 — applied versus requested, one real call per seat

One call each, carrying the first-turn thread for the largest CIP-007-6
population (`CIP-007-6 R5`, 43 regulatory + 14 operator sections, 31,335 chars
of section text, 52,244 chars of assembled thread).

| checked | Qwen3.8-27B ctx32k | glm-4.7-flash ctx64k | qwen3.6:27b |
| --- | --- | --- | --- |
| `num_ctx` requested | 65536 | 65536 | 65536 |
| `num_ctx` applied (`/api/ps`) | **65536** | **65536** | **65536** |
| seat ceiling (trained) | 262144 | 202752 | 262144 |
| `prompt_eval_count` | 16590 | 15339 | 16582 |
| headroom (`ctx − prompt − eval`) | 48191 | 49697 | 48193 |
| margin over material+answer+reasoning | 41778 | 43029 | 41786 |
| chars/token observed | 3.15 | 3.41 | 3.15 |
| tools rendered in the real call | 14 `compliance_read` | 17 `compliance_read` | 7 `compliance_read` + `compliance_notes` |
| think honored | yes | yes | yes |
| temperature applied | 0.0 | 0.0 | 0.0 |
| latency | 226.8 s | 111.1 s | 228.2 s |

No seat's prompt is at its ceiling; no headroom is ≤ 0; no baked value overrode
a requested one without being recorded. `glm-4.7-flash` is roughly **twice as
fast** as the incumbent on identical material.

The first-turn tool calls are worth naming on their own: under the v1 prompt a
live parent-level run answered in prose and called **nothing**. Under the v2
prompt every seat's first act is to go and read.

---

## §P0.5 — the campaign pin

Recorded in `SETTINGS_PREFLIGHT_V1.json`, per seat: template sha, baked params,
applied `num_ctx`, applied temperature, think verdict, observed chars-per-token,
Ollama version, `/api/ps` (including `context_length` and `size_vram`) and free
memory at the time of the call.

**If a template sha changes mid-campaign, abort and restart.** The shas above
are the pin. `validate_system` check `HH` (§P6.1) fails when the seat's live sha
differs from the one an acceptance run recorded.

---

## §P0.6 — go / no-go

For the seat in use (`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k`):

- audit shows **no relevant FAIL** — the two `sampling_hot` FAILs are fixed, the
  probe defect that produced the third is fixed;
- the tools probe **passes**;
- the think verdict is **recorded** (honored);
- the applied ceiling holds the largest case's material (16,590) plus the
  reasoning allowance (4,096) plus the answer budget (3,072) with **41,778
  tokens of margin**.

**GO.**

## Carried forward

- `persona:qwen38coder-dflash` pins `Qwen3.8-27B-4bit`, an oMLX alias that is
  not installed — an open fleet FAIL outside this run's path.
- `qwen3.8` family has no `model_card_expectations` ground truth (WARN ×3).
- `compliance-council:mistral` seat is not in `backends.yaml` (WARN).
- Every operator edge in the CIP-007-6 population is `proposed`; none is
  `approved`. Acceptance does not depend on approvals, by design.
