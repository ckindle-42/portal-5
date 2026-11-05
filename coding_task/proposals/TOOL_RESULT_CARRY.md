# Tool Result Carry

The streaming path will append the carry to the final assistant content in `router.streaming._tool_loop_frames`, immediately before the finish chunk. The non-streaming path will append it to each returned assistant message in `non_streaming._apply_non_stream_response`, after answer normalization. Both paths collect only tool calls dispatched during the current request; the Pipeline keeps no cross-request state.

The record is a collapsed `<details><summary>Tool results</summary>…</details>` block. Each item contains the tool name, arguments whose keys identify paths or IDs, and a whitespace-normalized result excerpt. The complete block is capped at 2,048 characters, with individual excerpts bounded so a document result is never copied in full. This is enough for several short tool receipts while bounding the extra prompt history on later turns.

`PORTAL_TOOL_RESULT_CARRY` is the single Pipeline process environment switch. It defaults to `false`; setting it to `true` enables the record. When disabled, response content is unchanged.

On the next turn, Open WebUI or a harness sends its existing `messages` history to `/v1/chat/completions`. `handlers._resolve_request_route` reads that request body and preserves `messages`; the returned assistant content, including the collapsed record, is therefore ordinary history consumed by the next backend request. The Pipeline does not retrieve a separate record or persist conversation state.
