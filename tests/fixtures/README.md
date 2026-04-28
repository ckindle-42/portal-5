# UAT Test Fixtures

Optional fixtures for Portal 5 UAT driver tests. All tests that require a fixture
skip cleanly when the file is absent — no fixture, no test failure.

## Audio

| File | Test | Purpose |
|------|------|---------|
| `sample.wav` | M-01 | Whisper STT round-trip — upload an audio clip and verify transcription is returned correctly. Any WAV file with clear speech works; 10-30 seconds is ideal. |

Place a WAV file at `tests/fixtures/sample.wav` to activate M-01.
Without it, the test SKIPs with `no_audio_fixture` and the full suite still passes.

## Document

| File | Test | Purpose |
|------|------|---------|
| `sample.docx` | A-01 | Document RAG — upload a Word document and query its contents. Any `.docx` with structured text (headings, paragraphs) works. |

## Image

| File | Test | Purpose |
|------|------|---------|
| `sample.png` | Various vision tests | Image-based tests that use the Playwright file-upload path. |

## Knowledge Base

| Path | Test | Purpose |
|------|------|---------|
| `tests/fixtures/knowledge_base/` | A-02 | Persistent collection query — populated through OWUI's Knowledge interface. Files in this directory should be indexed via Admin > Knowledge. |
