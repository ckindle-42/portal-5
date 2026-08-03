# Upstream issue drafts for jundot/omlx (from Portal 5 Phase-0, 2026-08-02)

Prepared for manual filing (gh authed as ckindle-42). Post with:
`gh issue create -R jundot/omlx --title "<title>" --body-file <file>`

---

## Issue 1 — Grammar-constrained decode livelock on unconstrained→constrained transition (gemma-4-e4b-it-4bit)

**File:** `UPSTREAM_DRAFT_gemma_grammar_livelock.md`

**Title:** Grammar request following an unconstrained request livelocks into whitespace emission (gemma-4-e4b)

**Body:**

oMLX 0.5.4 (Homebrew, --with-grammar + manual xgrammar patch per #1005),
macOS 26.6, M4 Pro 64GB. Model: mlx-community/gemma-4-e4b-it-4bit.

Repro (100%):
1. POST /v1/chat/completions {"model":"gemma-4-e4b-it-4bit","messages":[{"role":"user","content":"hi"}],"max_tokens":1}
2. Then POST same model, stream:true, response_format={"type":"json_schema","json_schema":{"name":"route","schema":{"type":"object","properties":{"workspace":{"type":"string","enum":["auto-coding","auto-research","auto-daily"]},"confidence":{"type":"number"}},"required":["workspace","confidence"],"additionalProperties":false},"strict":true}}

Expected: schema-constrained JSON, e.g. {"workspace":"auto-coding","confidence":0.95}
Actual: output starts {"\n  "workspace": "auto-coding" then emits "\n" until max_tokens (matcher never advances). The NEXT constrained request succeeds (self-recovers).

Same sequence on Qwen3-Coder-30B-A3B-Instruct-4bit and Llama-3.2-3B-Instruct-8bit: unaffected.
Non-streaming gemma request without the prior unconstrained call: works.
Suspect grammar matcher / structural-tag state carried across requests on the VLM-shaped gemma engine.

---

## Issue 2 — brew --with-grammar leaves xgrammar broken (patch_xgrammar did not take)

**File:** `UPSTREAM_DRAFT_brew_grammar_patch.md`

**Title:** `brew reinstall --with-grammar` leaves xgrammar unloadable (RECORD deleted, rpath missing) — follow-up to #1005

**Body:**

oMLX 0.5.4 via `brew tap jundot/omlx && brew install omlx`, then
`brew reinstall omlx --with-grammar` (completed "built in 1m11s", torch 2.13.0 + xgrammar 0.2.3 present in libexec).

Server logs "Structured output requires xgrammar" at engine load; request-time falls back to prompt injection.

Diagnosis: site-packages/xgrammar/libxgrammar_bindings.dylib exists, but
(a) xgrammar-0.2.3.dist-info has NO RECORD file (brew clean deleted it; patch_xgrammar's rewrite did not land), so tvm_ffi's manifest lookup raises RuntimeError("Cannot find library libxgrammar_bindings.dylib");
(b) the dylib lacks an rpath entry for tvm_ffi/lib.

Manual fix that restores it:
  install_name_tool -add_rpath "$SITE/tvm_ffi/lib" "$SITE/xgrammar/libxgrammar_bindings.dylib"
  codesign --force --sign - "$SITE/xgrammar/libxgrammar_bindings.dylib"
  echo "xgrammar/libxgrammar_bindings.dylib,," >> "$SITE/xgrammar-0.2.3.dist-info/RECORD"
After a server restart: "GrammarCompiler initialized" and strict json_schema works on all tested models.

Possibly `brew reinstall` does not run post_install (or the ohai output is lost), so patch_xgrammar never executes on the reinstall path.
