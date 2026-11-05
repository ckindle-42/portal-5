# MELLUM_SERVING_SETUP — reasoning/content split and tag setup

Lane: `lane/mellum-serving-setup`. Engine: Ollama 0.40.13 (host, `/Volumes/data01/ollama/models`).
Tag under test: `hf.co/JetBrains/Mellum2.1-12B-A2.5B-Thinking-GGUF:Q4_K_M-ctx32k`.
Campaign evidence: `ready_mellum_20261105` (arm `...-ctx32k@card-c7216073`, `auto-coding::fast-repair`,
`predict_limit 16384`).

## Verdict

The reasoning/content split is **not broken for the path the campaign ran**. `ready_mellum_20261105`
used `think: native` with the workspace's `think` unset, so Ollama served its default `think=true`;
in that mode the tag separates reasoning into `message.thinking` and returns clean `message.content`
(direct probe: 739 thinking chars + `"0.35"` content, `done_reason=stop`). The campaign's
"no visible content" turns therefore are **not** the split dropping an answer: the model ended those
turns inside its thinking block, and the pipeline substituted its placeholder.

The tag is still mis-set-up, in two ways that are ours to fix:

1. **`think=false` is broken.** The hf.co import carries Ollama's legacy qwen3 template, whose final
   assistant prefill is `<think>` for **every** think value. The vendor template prefills nothing when
   thinking is on and `<think>\n\n</think>\n\n` when it is off. Measured: `think=false` returns the
   reasoning as `content`, ending with a stranded `</think>` before the answer.
2. **No parser.** With `parser=null`, a `<tool_call>` written before `</think>` is swallowed as
   thinking, and tool calls stay unstructured text. Ollama's `qwen3-thinking` parser explicitly
   recovers a tool call that starts before `</think>` (`model/parsers/qwen3.go`).

The fix is a template repair of the existing tag, in place, plus `PARSER qwen3-thinking`
(`config/ollama_modelfiles/Modelfile.mellum`). It is written but **not applied** — `ollama create`
is the orchestrator's command (below). Do not rerun the Mellum arm until the conformance probe passes.

## 1 — What the tag serves today

`ollama show --modelfile` / `/api/show` (2026-11-05):

```
family mellum, 12.1B, Q4_K_M, capabilities=['completion', 'tools', 'thinking']
parameters: num_ctx 32768; repeat_penalty 1; stop "<|im_start|>"; stop "<|im_end|>";
            temperature 0.6; top_k 20; top_p 0.95
template_source: go_template;  TEMPLATE layer 1506 bytes, sha256:2d54db2b…
thinking: {"values": [true], "default": true}
modelfile: FROM /Volumes/data01/ollama/models/blobs/sha256-ecc4d5b8… (GGUF model layer)
           TEMPLATE """…"""       ← no RENDERER line, no PARSER line
```

Three independent checks agree the template is **not** the vendor template:

- The manifest's template layer is `sha256:2d54db2b9bb29ce7db54fea63a891f5859603813c555b1f88b5e0994652897f9`
  (1,506 bytes), while `tokenizer.chat_template` in the GGUF is the vendor's 4,849-byte
  `chat_template.jinja` (`config/ollama_modelfiles/README.md` table).
- That exact digest is a hard-coded entry in Ollama v0.40.13 `server/model_thinking.go`:
  `"sha256:2d54db2b…": {Values: []any{true}, Default: true}` with the comment
  *"Older Qwen3 template always opens a thinking block"*. It is Ollama's legacy qwen3 template,
  not a Mellum template.
- `/api/show` reports `thinking.values: [true]` — the tag advertises no `false` value, matching
  the legacy entry.

The repo's renderer gate does not refuse this tag: `audit_renderer_gate` and `audit_tags` both
return zero violations (the `mellum` architecture has no native renderer/parser entry in
`config/ollama_modelfiles/renderers.yaml`, and the gate only refuses a known architecture).
Baked stops are clean — `['<|im_start|>', '<|im_end|>']`; there is **no** `<think>` stop to strip
(`_audit_stop_hygiene` passes).

## 2 — Vendor template vs the served template

Pinned vendor source: `JetBrains/Mellum2.1-12B-A2.5B-Thinking` @ `92ddae9`, `chat_template.jinja`
(4,849 bytes). Its generation prompt is:

| think | Vendor prompt tail | Served tag prompt tail |
| --- | --- | --- |
| on (or unset) | `<\|im_start\|>assistant\n` (model emits its own `<think>`) | `<\|im_start\|>assistant\n<think>\n` |
| off (`enable_thinking=false`) | `<\|im_start\|>assistant\n<think>\n\n</think>\n\n` | `<\|im_start\|>assistant\n<think>\n` (identical to on) |

Rendered both ways offline with Go 1.26 `text/template` against the same field shape Ollama passes
(`Messages`, `Tools`, `Think`, `IsThinkSet`); the served tag renders the same tail for `Think=true`
and `Think=false`. That is the whole think-off defect in one line.

The vendor model card (README, "Usage") also prescribes `--reasoning-parser qwen3` and
`--tool-call-parser hermes` under vLLM — i.e. the model is expected to separate reasoning, and the
tool calls use the same `<tool_call>{name, arguments}</tool_call>` body the qwen3 parser accepts.
There is no card statement that the model cannot separate.

## 3 — Direct probe (read-only, `/api/chat`, stream=false)

Prompt: *"A store sells pens at 3 for $1.05. What does one pen cost? Reply with just the price."*
Options: `temperature 0.6, top_p 0.95, top_k 20, num_predict 1024`.

**`think: true`** — `done_reason=stop`, `prompt_eval_count=36`, `eval_count=238`, message keys
`['content', 'role', 'thinking']`:

- `thinking` (739 chars) begins: `"We need to compute cost per pen: 3 pens cost $1.05, so one pen costs $1.05/3 = $0.35…"`
- `content`: `"0.35"`

**`think: false`** — `done_reason=stop`, `prompt_eval_count=36`, `eval_count=133`, message keys
`['content', 'role']` (no `thinking` field):

- `content` (366 chars) ends: `"…I'd output 0.35.\n</think>\n\n0.35"`

So: thinking-on works end-to-end at the engine; thinking-off leaks the reasoning into `content` and
leaves a stray `</think>`, exactly as the template predicts. This is a **serving-setup** defect, not
a model inability to separate.

## 4 — What the campaign rows actually say

`ready_mellum_20261105` has 16 Mellum rows: `12 FAIL, 2 PASS, 2 TRUNCATED`. The per-turn transcript
in `debug/…@card-c7216073.debug.jsonl` (32 turns) shows:

- **14 turns** have `reasoning_chars > 0` and `answer_chars == 0` (reasoning was separated out;
  content was empty). Those are the turns behind the placeholder notes.
- Their `completion_tokens`: `64, 72, 75, 100, 108, 115, 130, 136, 252, 356, 390, 599, 730, 1616`
  — all far below the 16,384 `predict_limit`. **None reached the token cap.**
- All 14 are labelled `finish_reason=length` in the transcript. The pipeline sets that label itself
  whenever the answer was reasoning-only (`router/streaming.py`), regardless of the engine's
  `done_reason`; the row-level `finish_reason` is from the last turn: `11 stop, 5 length`.
- `11/16` rows carry the final `pipeline no-answer placeholder` note; the other FAIL rows fail on
  tool/answer checks. The task's "12/16" is the FAIL+TRUNCATED count, not the placeholder count.

The reported economics anomaly is an accounting artefact, not a second split failure:
`router/trace.py` counts **nonempty stream frames** as `reasoning_tokens` ("These counts are
nonempty stream frames, not tokenizer tokens"). Frame count can exceed `eval_count`; `14/16` rows
show `reasoning_tokens > completion_tokens` for that reason. Compare the incumbent (kat-coder) rows:
the same field ordering appears in its data, so it is not Mellum-specific.

Reading the rows as written, the failure mode is: the model produced a short reasoning burst
(e.g. 110–321 chars on the shortest turns), then ended the turn without visible content or a tool
call. `ru-v1-040` is the extreme: its first turn ended inside thinking while the run logged `29`
dispatched tool calls and `6,767` reasoning frames across both turns. The split did not drop an
answer — there was no answer to drop.

## 5 — Root cause and fix

Root cause is the hf.co import template: Ollama's legacy qwen3 template pre-opens `<think>` for
thinking-on (the vendor does not) and has no think-off branch. That removes the model's own
`<think>` token from the generation, so the protocol it was trained on (emit `<think>`, reason,
emit `</think>`) is only half present; think-off cannot be expressed at all. The missing parser is a
separate, proven loss — see the offline parser check below.

`config/ollama_modelfiles/Modelfile.mellum` (rewritten 2026-11-05) is the vendor-faithful Go
translation, built from the served template so the system/tools and tool-response blocks are
byte-identical to what the tag already sends:

- final prefill: nothing when thinking is on; `<think>\n\n</think>\n\n` when explicitly off;
- assistant `reasoning_content` rendered as the vendor's `<think>\n…\n</think>\n\n` block;
- `PARSER qwen3-thinking` (no `RENDERER`: Ollama ships no mellum renderer, and the qwen3 renderer
  emits a different tool-call body);
- `FROM …:Q4_K_M-ctx32k` so `num_ctx 32768`, the vendor sampling and the two stops are inherited.

Offline template check (Go `text/template`, same values Ollama passes) renders exactly:

```
think=true  → …<|im_start|>assistant\n
think=false → …<|im_start|>assistant\n<think>\n\n</think>\n\n
```

The parser half is verifiable without the live engine. Built Ollama v0.40.13's own
`model/parsers` and `thinking` packages from the tagged source and fed them the candidate streams:

| Parser | Stream | Result |
| --- | --- | --- |
| none (`thinking.Parser`, seeded with `<think>`) | `I should call probe_lookup with CASE-42.\n<tool_call>\n{"name": "probe_lookup", "arguments": {"lookup_id": "CASE-42"}}\n</tool_call>` | `thinking` = the whole string, `content` = `""`, **0 calls** |
| `qwen3-thinking` | same stream | `thinking` = the preamble, `content` = `""`, **1 call** `probe_lookup` / `{"lookup_id":"CASE-42"}` |
| `qwen3-thinking`, think=false | `The answer is 0.35` | `content` = the answer, no thinking |
| `qwen3-thinking`, think=true | `<think>\nLet me compute.\n\n\nThe answer is 0.35` | thinking + content split correctly |

So a tool call written before `</think>` — the shape that produces "reasoning_chars > 0, content
empty, no call" in the campaign — is exactly what `parser=null` loses and `qwen3-thinking` recovers.
That makes the parser part of the fix evidence-based, not a guess.

After the rebuild, `PARSER qwen3-thinking` also keeps the `/api/show` capabilities at
`completion, tools, thinking` (`parserCapabilities` adds both), and the template still contains
`<think>`/`</think>`, so the default `think=true` is preserved.

## 6 — Exact commands (orchestrator; do not run from a worktree)

Run only when no WFE campaign is in flight. `ollama create` reads the base manifest before writing
the new one (`server/create.go` calls `parseFromModel` first), so `FROM <same tag>` is safe.

```bash
cd /Users/chris/projects/portal-5
TAG='hf.co/JetBrains/Mellum2.1-12B-A2.5B-Thinking-GGUF:Q4_K_M-ctx32k'

# 1. snapshot the current Modelfile — this is the rollback
ollama show "$TAG" --modelfile > /tmp/mellum-ctx32k.before.Modelfile

# 2. rebuild the tag in place (same name; no config/backends.yaml change)
ollama create "$TAG" -f config/ollama_modelfiles/Modelfile.mellum

# 3. read back: PARSER qwen3-thinking, template 1547 bytes, num_ctx 32768, stops unchanged
ollama show "$TAG" --modelfile | grep -E '^(FROM|PARSER|RENDERER|PARAMETER)'
curl -s http://127.0.0.1:11434/api/show -d "{\"model\":\"$TAG\"}" | python3 -c '
import json,sys; d=json.load(sys.stdin)
print("template_bytes", len(d.get("template") or ""))
print("params", d.get("parameters"))
print("caps", d.get("capabilities"))'

# 4. conformance probe (think off + on; structured tool call, tool result, final answer)
python3 scripts/ollama_template_conformance_probe.py "$TAG"

# 5. rollback if the probe fails
ollama create "$TAG" -f /tmp/mellum-ctx32k.before.Modelfile
```

Expected: both `think=false` and `think=true` print `tool call and result turn passed`. If
`think=true` fails with `no parsed thinking`, roll back and report — do not ship a half-tested tag.
The think-on path the campaign uses is proven on the current tag, so the rollback is a safe state.

No `config/backends.yaml`, `config/portal.yaml`, persona or port change is needed: the tag name is
unchanged. `apply-params` would recreate a `-ctx32k` tag from the **base** hf.co tag with only
`FROM` + `num_ctx`, i.e. the broken template, so do not delete the repaired tag and re-derive it.

## 7 — Rerun guidance

`ready_mellum_20261105` is valid evidence that the **think-on split** works (the 14 reasoning-only
turns carry `reasoning_chars > 0`, content empty). It is not evidence of a broken split. It is also
not a clean model verdict yet, because the tag was serving a non-vendor template that changes the
model's thinking-block protocol and drops in-thinking tool calls.

Sequence: rebuild + probe (above) → rerun the realuse arm (`tests/wfe/plans/realuse_v1_mellum.yaml`) at the same card sampling and
`think: native` → compare. If reasoning-only turns persist after the probe passes, that is the
model's own behaviour under this task set, not serving; the verdict can then stand.

## 8 — Open

- The rebuild is unverified live; the conformance probe is the gate. The prior probe of the
  prefilled-template + `qwen3-thinking` variant passed think-off and failed think-on, which is why
  this Modelfile also removes the prefill.
- The `PARSER`-less fallback keeps thinking-on working but leaves tool calls as text (the pipeline
  salvages them; the campaign's 29-call row shows that path works). It fails the conformance
  probe's structured-call assertion, so it is not the proposed state.
- `router/streaming.py` relabels a reasoning-only turn as `finish_reason=length` even when the
  engine stopped normally; `router/trace.py` reports stream-frame counts as `reasoning_tokens`.
  Both are measurement caveats, not serving faults — no code change made here. A WFE note that
  says "output truncated at token cap" should not be read as a cap hit for this arm.
