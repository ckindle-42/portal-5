# tests/fixtures

Test fixtures for portal5_uat_driver.py and the acceptance suite.

## Audio

`sample.wav` — Whisper STT round-trip fixture for test M-01. Generated locally;
not committed. To regenerate on macOS:

```bash
say -o /tmp/sample.aiff "The quick brown fox jumps over the lazy dog at the Portal acceptance test."
afconvert -f WAVE -d LEI16@16000 /tmp/sample.aiff tests/fixtures/sample.wav
rm /tmp/sample.aiff
```

Format: 16-bit signed-LE PCM @ 16 kHz mono (Whisper's preferred input — no resample needed).
Content must include at least one of: `portal`, `five`, `acceptance`, `quick`, `brown`, `fox`
(see portal5_uat_driver.py M-01 assertion list).

## Other fixtures

- `sample.docx`, `sample.pdf`, `sample.pptx`, `sample.xlsx`, `sample.png` — document-reading
  and vision fixtures, committed to the repo.
- `coding_scenarios.yaml`, `compliance_scenarios.yaml` — multi-turn scenario specs.
- `knowledge_base/` — RAG ingestion test data.
