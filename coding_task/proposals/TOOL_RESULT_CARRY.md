# Tool Result Carry

The streaming path will append the carry to the final assistant content in `router.streaming._tool_loop_frames`, immediately before the finish chunk. The non-streaming path will append it to each returned assistant message in `non_streaming._apply_non_stream_response`, after answer normalization. Both paths collect only tool calls dispatched during the current request; the Pipeline keeps no cross-request state.

The record is a collapsed `<details><summary>Tool results</summary>…</details>` block. Ordinary carry is emitted only when arguments contain a path, ID, or index, or the JSON result returns identifier fields; each item includes those values and a whitespace-normalized result excerpt. The complete block is capped at 2,048 characters, with individual excerpts bounded so a document result is never copied in full.

`PORTAL_TOOL_RESULT_CARRY` is the single Pipeline process environment switch and defaults to `true`. Each receipt preserves up to eight JSON identifier fields alongside a bounded result excerpt. Setting the switch to `false` disables ordinary carry; mixed owned/client hops still force receipts so Open WebUI receives results for the calls the Pipeline consumed.

On the next turn, Open WebUI or a harness sends its existing `messages` history to `/v1/chat/completions`. `handlers._resolve_request_route` reads that request body and preserves `messages`; the returned assistant content, including the collapsed record, is therefore ordinary history consumed by the next backend request. The Pipeline does not retrieve a separate record or persist conversation state.
