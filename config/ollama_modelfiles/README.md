# Ollama chat-template conformance

The HF references are pinned to the commits read for this review:

- Flint `chat_template.jinja`: [RecursiveSI/flint at `2a247be0c0aec895ccb0ac7ca92229ec6df37288`](https://huggingface.co/RecursiveSI/flint/blob/2a247be0c0aec895ccb0ac7ca92229ec6df37288/chat_template.jinja)
- Mellum `chat_template.jinja`: [JetBrains/Mellum2.1-12B-A2.5B-Thinking at `92ddae9fc7665e9f801d141d2e5a6b2caf2460c4`](https://huggingface.co/JetBrains/Mellum2.1-12B-A2.5B-Thinking/blob/92ddae9fc7665e9f801d141d2e5a6b2caf2460c4/chat_template.jinja)
- LFM2.5 `chat_template.jinja`: [LiquidAI/LFM2.5-24B-A2B at `3fcfdbfa1a1b6d8166846a6323e69f1e1254440d`](https://huggingface.co/LiquidAI/LFM2.5-24B-A2B/blob/3fcfdbfa1a1b6d8166846a6323e69f1e1254440d/chat_template.jinja)

Each vendor template is byte-for-byte equal to `tokenizer.chat_template` in the local GGUF model layer. The local model-layer digests came from the Ollama manifests, and the GGUF reader stopped after metadata; it did not read tensor data or load a model.

| Model | Local GGUF model layer | Effective Ollama template/config | Difference and defect |
| --- | --- | --- | --- |
| Flint | `hf.co/unsloth/flint-GGUF:UD-Q4_K_XL`, `sha256:63c2ecc461ca545134b670c660e76fa20f47240f8d39b6510bfd21c4dd6e072f`; vendor and embedded template are 2,328 bytes and identical | No manifest template layer; config has `renderer=null`, `parser=null`, so Ollama uses the GGUF template | Tool definitions use `<tools>` JSON, assistant calls use `<tool_call>name<arg_key>…<arg_value>…`, and results use `<|observation|><tool_response>`. The HF template has no think-off branch. The format is correct, but the imported tag lacks the native `flint` renderer/parser that turn calls into structured tool calls and restore tool turns. |
| Mellum | `hf.co/JetBrains/Mellum2.1-12B-A2.5B-Thinking-GGUF:Q4_K_M`, `sha256:ecc4d5b8107fc219e23c494b2d107552137637b6c6002ee713e0ba8af7fa2755`; vendor and embedded template are 4,849 bytes and identical | Manifest template layer `sha256:2d54db2b9bb29ce7db54fea63a891f5859603813c555b1f88b5e0994652897f9` (1,506 bytes); config has `renderer=null`, `parser=null` | The effective Go template already sends `<tools>` definitions, JSON `{name, arguments}` calls, and `<tool_response>` user turns. Its final assistant prefill always ends with `<think>`, even for explicit `Think=false`, and there is no parser to extract reasoning or JSON tool calls. The Modelfile closes an empty think block for explicit off and adds Ollama's compatible `qwen3-thinking` parser. |
| LFM2.5 HF | `hf.co/unsloth/LFM2.5-24B-A2B-GGUF:UD-Q4_K_XL`, `sha256:a235d23638cc5549cb1ff61da7522c8a7e97f056f27093462a1e56f35aba91d8`; vendor and embedded template are 5,443 bytes and identical | Manifest template layer `sha256:a776233427f34f27db3c6e090de4523a0785a9c286e17a6b869a026dd83971d7` (197 bytes); config has `renderer=null`, `parser=null` | The effective template only renders `.Prompt` as a user message and `.Response` as an assistant response. It has no tool definitions, tool-call history, tool-result turns, reasoning tags, or think switch. The `lfm2-thinking` renderer/parser pair supplies the LFM2 tool and think protocol. |
| LFM2.5 Ollama library | No matching local model layer was present on this Mac | The read-only public registry manifest for `lfm2.5:24b-a2b-q4_K_M` has no template layer and its config has `renderer=null`, `parser=null` | The `Modelfile.lfm2.5-library` applies the same native LFM2.5 renderer/parser repair to the P40 tag. Its GGUF header was not read because that tag's model blob is not installed in this local store. |

Ollama v0.40.13's existing renderer/parser implementations are used here: [Flint renderer](https://github.com/ollama/ollama/blob/v0.40.13/model/renderers/flint.go), [Flint parser](https://github.com/ollama/ollama/blob/v0.40.13/model/parsers/flint.go), [LFM2 renderer](https://github.com/ollama/ollama/blob/v0.40.13/model/renderers/lfm2.go), [LFM2 parser](https://github.com/ollama/ollama/blob/v0.40.13/model/parsers/lfm2.go), and [Qwen3 parser](https://github.com/ollama/ollama/blob/v0.40.13/model/parsers/qwen3.go). The Qwen3 parser accepts `<tool_call>` JSON objects and `<think>`; its matching native renderer does not match Mellum's JSON call body, so the Mellum Modelfile retains its tag's template instead of selecting a Qwen renderer. The [Ollama prompt path](https://github.com/ollama/ollama/blob/v0.40.13/server/prompt.go) uses a native renderer when one is set, otherwise the model's template.

For Mellum the template edit is limited to the last assistant prefill: when `Think` is explicitly false, it emits `<think></think>`; when thinking is true or unset, it retains the existing `<think>` prefix. Ollama v0.40.13 passes `Think` and `IsThinkSet` to Go templates.

Build each derived model with `ollama create <name> -f <Modelfile>`, then run `python3 scripts/ollama_template_conformance_probe.py <name>`. The probe makes two sequential `/api/chat` rounds for each think setting, checks the structured tool call, returns a fixed tool result, and checks the final answer. It was not run in this worktree because the live-engine prohibition applies.

The Mac GGUFs establish setup differences for the HF tags. The P40 library tag's public registry metadata establishes its missing renderer/parser, but a local P40 GGUF-header comparison and live smoke remain open.

## Live verification (orchestrator, 2026-10-29, Ollama 0.40.13 on the Mac)

`scripts/ollama_template_conformance_probe.py` (tool call → tool result → final answer, think off and on):

| Derived tag | Result |
| --- | --- |
| Flint + `RENDERER flint` / `PARSER flint` | PASS both think modes. Applied in place to `hf.co/unsloth/flint-GGUF:UD-Q4_K_XL-ctx256k` (num_ctx 262144 kept). The s8_flint_screen_20261029 result (5/7 BUDGET_EXHAUSTED) was this setup gap and must be re-run. |
| LFM2.5 + `lfm2-thinking` | FAIL: think=false still leaks reasoning — LFM2.5 always thinks (the intake's listed risk). Not applied. |
| Mellum + `PARSER qwen3-thinking` | think=false PASS; think=true returned no parsed thinking. Not applied; fast-repair declares no think flag. |
