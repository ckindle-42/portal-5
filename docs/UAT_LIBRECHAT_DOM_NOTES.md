# LibreChat DOM Notes — UAT v1

**LibreChat image:** ghcr.io/danny-avila/librechat:latest (sha256:fcb9958be4431562f7a040389c01aff6368f6051c7f32a28c357d324e2d35e3e)
**LibreChat version:** v0.8.6-rc1 (running) | config: v1.3.11 (librechat.yaml schema version)
**Recon date:** 2026-05-18
**Recon by:** auto (headless Playwright)

## Selectors

### Login
- Email: `input[type="email"], input[name="email"]`
- Password: `input[type="password"]`
- Submit: `button[type="submit"]`
- Post-login readiness: `textarea, [contenteditable='true']` (appears with placeholder "Please select an Agent")

### Endpoint / model picker
- Open: `button[aria-label="Select a model"]` — displays "My Agents" text (model label shown in header bar)
- Select Portal 5 endpoint: The endpoint is the container/source — "Portal 5" is the endpoint name. Models within the endpoint (auto, auto-coding, etc.) appear as options in the list. Click the button, then select the model from the dropdown.
- Select workspace model (e.g. auto-coding): Click `button[aria-label="Select a model"]`, then click the target model row in the dropdown list. Models are listed by their portal workspace slug.

### Preset menu
- Open: `button[aria-label="Presets"]` — icon button in the chat header area
- Filter by text: Not directly filterable in v0.8.6-rc1 — presets appear in a scrollable list
- Click preset row by title `🎭 {name}`: Click the preset button, then locate and click the row by its text content. Each preset appears with the `🎭` emoji prefix as seeded.

### Custom Instructions / promptPrefix UI
- Open settings panel: `button[aria-label="MCP Settings"]` or `button[aria-label="Account Settings"]` — LibreChat v0.8.6-rc1 does NOT expose a per-conversation "Custom Instructions" textarea in the standard UI. The primary mechanism for injecting a system prompt is through Agents (seeded presets).
- System-prompt textarea: NOT available in standard v0.8.6-rc1 chat UI. Presets (Agents) store the system prompt via the Agent Builder (`button[aria-label="Agent Builder"]` in the sidebar).
- Persistence: Per-agent (the prompt is tied to the agent/preset, not the conversation)
- Fallback note: When the preset click path fails, the `_set_custom_instructions` function-raising `_CustomInstructionsNotFound` is expected — persona tests will SKIP with `persona_preset_unreachable`.

### Chat input
- Selector: `textarea` — has placeholder "Please select an Agent" before agent selection, then becomes message-ready
- Submit: Send button click required — `button[aria-label="Send message"]`. Enter alone does NOT send in v0.8.6-rc1.

### Stop button (streaming)
- Selector: `button[aria-label*="Stop"]` (PROVISIONAL — not confirmed during recon; streaming was not observed)
- Disappearance signals stream end: YES (expected LibreChat behavior — stop button visible while generating, gone when complete)

### Assistant message
- Container: `.message-content` (class on the rendered message element)
- Text extraction: `inner_text()` on the `.message-content` element
- Reasoning blocks rendered visibly: LibreChat does NOT inject `<details type="reasoning">` wrappers — thinking content appears inline in the message text. DOM-stable completion detection works without OWUI's API-polling workaround.

### Routed-model readout
- Source: NOT surfaced in the message footer in v0.8.6-rc1 (no model badge or footer text observed on assistant messages)
- Selector: n/a — model name not found in message-level DOM
- Notes: In v0.8.6-rc1, the model used is tracked in the conversation metadata but not rendered in the message. The `get_routed_model()` function will return `""` until a verified selector is found. The operator workflow accepts this limitation — check the conversation's active model via the model picker UI if needed.

### File attachment download
- Container: `a[download], a[href*=".{ext}"], button:has-text("Download")` (PROVISIONAL — not confirmed during recon; no artifact-generating test was run)
- Download trigger: Click the download link — Playwright's `expect_download()` event captures it
- Filename source: `download.suggested_filename` from Playwright download event, or extracted from `/files/` URL in response text

### New chat
- Fresh URL: `/c/new`
- Post-first-message URL: `/c/{conversation_id}` (LibreChat assigns a UUID conversation ID after the first message is sent)

## Open questions / known limitations

1. **Stop button not confirmed during recon.** No streaming response was observed in v0.8.6-rc1 during headless recon. The `wait_for_completion` function uses `button[aria-label*="Stop" i], button[title*="Stop"], button:has-text("Stop")` which covers common LibreChat patterns. If none of these work, fall back to pure DOM-stability detection.

2. **Routed-model display NOT surfaced in v0.8.6-rc1.** The model name does not appear in the assistant message footer or as a badge. `get_routed_model()` returns `""` on this version. This is documented as a known limitation — the model used is still correct (the pipeline routes it), it's just not visible in the LibreChat message UI.

3. **Agent selection required before sending.** LibreChat v0.8.6-rc1 requires selecting an Agent (persona/preset or workspace model) before the textarea becomes message-ready. The `start_new_chat` function handles this by either clicking a preset or selecting a workspace model from the picker.

4. **No per-conversation "Custom Instructions" textarea.** v0.8.6-rc1 does not have the promptPrefix UI. The persona fallback path (select model + paste system prompt) will raise `_CustomInstructionsNotFound`, which triggers SKIP with `persona_preset_unreachable`. Presets must be seeded and available.

5. **Enter does NOT submit.** LibreChat requires clicking `button[aria-label="Send message"]` to send. The `send_prompt` function should click this button rather than pressing Enter.

6. **LibreChat version mismatch.** The running image is v0.8.6-rc1 while `config/librechat/librechat.yaml` declares `version: 1.3.11`. The YAML schema version and runtime version are different concepts, but UI selectors may change across LibreChat releases. Re-run recon when the image is updated.
