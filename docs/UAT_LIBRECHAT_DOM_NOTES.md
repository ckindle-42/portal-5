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
- Open: `#presets-button` (ID), fallback `button[aria-label=" Presets"]` (note: leading space in aria-label) — icon button in the chat header area
- Filter by text: Not directly filterable in v0.8.6-rc1 — presets appear in a scrollable list
- Click preset row by title `🎭 {name}`: Click the preset button, then locate and click the row by its text content via `get_by_text(title, exact=False)`. Each preset appears with the `🎭` emoji prefix as seeded.

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
- Source: **Pipeline logs** (`docker logs portal5-pipeline`) — not the DOM
- Selector: n/a — by design, no DOM scraping for this field
- Notes:
  - LibreChat v0.8.6-rc1 does NOT surface the backend model name (e.g.
    `gemma-4-26b-a4b-it-4bit`) anywhere in the message UI: not in footers,
    tooltips, badges, or data attributes. The model picker shows the
    selected agent (workspace slug like `auto`) but not which physical
    model the pipeline routed the request to.
  - The pipeline already emits the routing decision as a log line on every
    request:
    `Routing workspace=auto → backend=mlx-apple-silicon model=mlx-community/Dolphin-0/Flushi-4bit stream=True (1/7 candidates)`
  - The UAT driver reads this directly via `_get_backend_from_pipeline_logs(slug)`
    in `tests/portal5_uat_driver.py` (existing helper, unchanged). The
    LibreChat path in `_fe_get_routed_model` calls it; there is no DOM
    path. Verifying the routed model is therefore frontend-independent.
  - **Do not re-introduce DOM scraping for this field.** If a future
    LibreChat release adds a model badge in the UI, the pipeline-log path
    still wins (it sees the *actual* model after fallback cascades, not the
    *selected* model the UI advertises).

### File attachment download
- Container: `a[download], a[href*=".{ext}"], button:has-text("Download")` (PROVISIONAL — not confirmed during recon; no artifact-generating test was run)
- Download trigger: Click the download link — Playwright's `expect_download()` event captures it
- Filename source: `download.suggested_filename` from Playwright download event, or extracted from `/files/` URL in response text

### New chat
- Fresh URL: `/c/new`
- Post-first-message URL: `/c/{conversation_id}` (LibreChat assigns a UUID conversation ID after the first message is sent)

## Open questions / known limitations

1. **Stop button not confirmed during recon.** No streaming response was observed in v0.8.6-rc1 during headless recon. The `wait_for_completion` function uses `button[aria-label*="Stop" i], button[title*="Stop"], button:has-text("Stop")` which covers common LibreChat patterns. If none of these work, fall back to pure DOM-stability detection.

2. **Routed-model is read from pipeline logs, not the DOM (architectural decision).** LibreChat v0.8.6-rc1 does not display the backend model in its UI; the pipeline emits the routing decision in its container logs, and the UAT driver reads it from there via `_get_backend_from_pipeline_logs(slug)`. This is frontend-independent and is the right source even when a UI display is available — the pipeline log records the actual routed model after fallback cascades, which the UI cannot. See § Routed-model readout above. The LibreChat `get_routed_model()` DOM helper that existed in the initial track has been removed.

3. **Agent selection required before sending.** LibreChat v0.8.6-rc1 requires selecting an Agent (persona/preset or workspace model) before the textarea becomes message-ready. The `start_new_chat` function handles this by either clicking a preset or selecting a workspace model from the picker.

4. **No per-conversation "Custom Instructions" textarea.** v0.8.6-rc1 does not have the promptPrefix UI. The persona fallback path (select model + paste system prompt) will raise `_CustomInstructionsNotFound`, which triggers SKIP with `persona_preset_unreachable`. Presets must be seeded and available.

5. **Enter does NOT submit.** LibreChat requires clicking `button[aria-label="Send message"]` to send. The `send_prompt` function should click this button rather than pressing Enter.

6. **LibreChat version mismatch.** The running image is v0.8.6-rc1 while `config/librechat/librechat.yaml` declares `version: 1.3.11`. The YAML schema version and runtime version are different concepts, but UI selectors may change across LibreChat releases. Re-run recon when the image is updated.

## MCPSelect dropdown (per-conversation tool attachment)

### When this matters

This dropdown is the **only** mechanism for attaching MCP servers to a
non-Agent conversation in LibreChat 0.8.x. Until 2026-05-20, the UAT driver
did not click it, which is why every tool-requiring test FAILed on LibreChat
(`M-01`, `T-04`, `T-05`, `T-08`, `T-11`, `WS-08–11`, `P-D*`/`P-N*` docs
personas, etc.). See `TASK_LIBRECHAT_UAT_MCP_ENABLEMENT_V1.md` for the fix.

### Visibility prerequisites (config side)

Both must be in `config/librechat/librechat.yaml`:

1. `interface.mcpServers.placeholder: "MCP Servers"` — renders the dropdown
   label.
2. `chatMenu: true` on each server in `mcpServers` — keeps the server visible
   in the dropdown (default true; we set it explicitly).

These come from `scripts/frontend_seeder/adapters/librechat.py` and are written
on every `./launch.sh up-librechat`. Do NOT hand-edit the YAML.

### Selectors (verified on v0.8.6-rc1, calibrated 2026-05-20)

| Element | Selector (in order of preference) |
|---|---|
| Dropdown button | `[data-testid="mcp-select"]` → `button:has-text("MCP Servers")` (verified) |
| Popover container | `[data-radix-popper-content-wrapper]` (Radix popover — scoped search root) |
| Popover row (server) | `get_by_text(key, exact=True)` on the popover container, with `scroll_into_view_if_needed` |
| Already-selected indicator | None observed — click is idempotent (toggling back off is harmless for UAT purposes) |
| Close dropdown | Click `textarea` (composer) or press `Escape` |

**IMPORTANT:** The third original selector `button[aria-label*="MCP" i]` was REMOVED. It matched
`button[aria-label="MCP Settings"]` (the account/profile menu), opening the user account
dropdown instead of the MCPSelect popover. The "MCP Servers" button itself has `aria-label=""`
and `data-testid=""` — only `button:has-text("MCP Servers")` matches it reliably.

**Row structure:** Rows in the MCPSelect popover are plain `div` elements — no ARIA `role="menuitem"`,
`role="option"`, or `role="listitem"`. The server name (exactly the YAML key, e.g. `portal-memory`)
is the row's visible text. The list scrolls; `portal-mlx_transcribe` is below the initial fold.

The `{key}` placeholder is the librechat.yaml key — `portal-documents`,
`portal-mlx_transcribe`, etc. The driver translates `requires_tool:
portal_documents` → `portal-documents` automatically.

### What the driver does

`tests/frontends/librechat.py::select_mcp_servers` opens the dropdown, clicks
each server row in `requires_tool`, and closes. It is called from
`start_new_chat(page, model, title, requires_tool=...)`. The OWUI shim accepts
the same kwarg and ignores it (OWUI uses workspace-level toolIds seeding).

### Phase 0.5 calibration is mandatory after this change

The MCPSelect click is new browser interaction. Re-run Phase 0.5 calibration
on the next LibreChat UAT run before committing to a full 7-9 hour phased
sweep. Expected after fix: M-01 PASS, T-04/T-05/T-08/T-11 PASS, TR-01 PASS.

### Failure modes to watch for

| Symptom | Likely cause | Fix |
|---|---|---|
| `[librechat-mcp] MCPSelect dropdown not found` log line in every test | `interface.mcpServers` block missing from generated YAML | Task 1 not applied; re-run seeder |
| `WARN: server row not found for portal-X` | Row label doesn't match `{key}` — LibreChat UI may show display name | Add the display name as a candidate in `select_mcp_servers` row_selectors |
| Tool calls happen on first message but fail on the second (multi-turn) | Selection cleared between turns by `/c/new` navigation | This task's `start_new_chat` is per-chat — multi-turn within one chat should keep state |
| LibreChat conversation log shows `tools: []` despite picker click | Dropdown click landed but row click didn't — re-check selectors | Phase 0.5 |

## Audio upload (TR-01 golden path)

`TR-01` does not click a file-picker in the LibreChat UI. The driver pre-stages
`tests/fixtures/sample_two_speakers.wav` into `${AI_OUTPUT_DIR}/uploads/` via
`shutil.copy2`, then calls `_staged.touch()` to guarantee the newest mtime. The
`mlx-transcribe` MCP's `_latest_audio_upload` picks it up when the persona
calls `transcribe_with_speakers` with no `file` argument.

This mirrors OWUI's M-01 (the OWUI driver has no `set_input_files` call
anywhere either) and exercises the production code path the
`transcriptanalyst` persona uses. A future task can add real UI uploads
symmetrically across both frontends — that work is out of scope here.
