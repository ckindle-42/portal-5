# Known Issues & Limitations

This document tracks known limitations in Portal 5. These are items that have been reviewed and deemed acceptable with documentation rather than immediate fixes.

---

## Security

### Multi-User Rate Limiting
- **ID**: P5-ROAD-031
- **Status**: KNOWN LIMITATION
- **Description**: Open WebUI does not have built-in rate limiting configured. In a multi-user environment, a single user could exhaust server resources.
- **Workaround**: Deploy behind a reverse proxy (nginx, Traefik) with rate limiting, or use Open WebUI's admin controls to set per-user quotas.
- **Last Verified**: 2026-03-03

---

## Performance

### Concurrent Request Limit
- **ID**: P5-ROAD-020
- **Status**: DOCUMENTED
- **Description**: The Pipeline uses a semaphore (`MAX_CONCURRENT_REQUESTS=20`) to limit concurrent requests. When exceeded, returns 503 with Retry-After header.
- **Configuration**: Set via `MAX_CONCURRENT_REQUESTS` environment variable
- **Last Verified**: 2026-03-03 (load test with 25 concurrent requests passes - excess requests properly return 503)

---

## Infrastructure

### Telegram Bot History Bounding
- **ID**: P5-ROAD-032
- **Status**: IMPLEMENTED
- **Description**: Telegram bot maintains conversation history with a 20-message sliding window to prevent memory exhaustion.
- **Configuration**: Edit `portal_channels/telegram/bot.py:73` to adjust `if len(history) > 20`
- **Last Verified**: 2026-03-03

---

## External Dependencies

### Fish-Speech TTS
- **Status**: OPTIONAL
- **Description**: Voice cloning requires fish-speech which needs separate host-side installation (not in Docker).
- **Zero-Setup Alternative**: kokoro-onnx is included and works out of the box
- **Documentation**: See `docs/FISH_SPEECH_SETUP.md`
- **Last Verified**: 2026-03-03

### ComfyUI (Image/Video Generation)
- **Status**: HOST-REQUIRED
- **Description**: ComfyUI runs on host (not in Docker) for GPU access
- **Documentation**: See `docs/COMFYUI_SETUP.md`
- **Last Verified**: 2026-03-03

---

## Future Considerations

- Rate limiting at the API gateway level
- Per-user quota enforcement
- Usage analytics dashboard
- Webhook-based event notifications

---

*Last updated: 2026-03-03*
*Part of Portal 5.0.0 release documentation*