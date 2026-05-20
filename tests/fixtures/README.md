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

## sample_two_speakers.wav

- **Purpose:** drives `TR-01` (LibreChat / OWUI parity, diarized transcription
  → Word doc chain).
- **Format:** WAV, 16 kHz, mono, ≤30 seconds, ≤500 KB.
- **Speakers:** 2 distinct voices, alternating turns.
- **Content:** any English sentences; the test asserts on speaker tokens and
  the presence of a `.docx` artifact, not on transcribed text. Avoid profanity
  and PII — the file is committed.

### Regenerating

Three viable recipes; pick whichever has the right tools on hand. Then verify
diarization separates the speakers via the smoke command at the bottom.

**piper + sox** (most reproducible):

    echo "Hello, this is the first speaker. We are testing diarization." | \
      piper --model en_US-amy-medium --output_file /tmp/s1.wav
    echo "Yes, this is the second speaker, responding." | \
      piper --model en_US-ryan-high --output_file /tmp/s2.wav
    echo "First speaker, one more line to confirm." | \
      piper --model en_US-amy-medium --output_file /tmp/s3.wav
    sox /tmp/s1.wav /tmp/s2.wav /tmp/s3.wav -r 16000 -c 1 sample_two_speakers.wav

**coqui-tts** (VCTK speaker bank):

    tts --text "First line."  --speaker_idx 0 --model_name tts_models/en/vctk/vits --out_path /tmp/s1.wav
    tts --text "Second line." --speaker_idx 1 --model_name tts_models/en/vctk/vits --out_path /tmp/s2.wav
    sox /tmp/s1.wav /tmp/s2.wav -r 16000 -c 1 sample_two_speakers.wav

**Recording**: trim, downmix, downsample:

    sox raw.wav -r 16000 -c 1 sample_two_speakers.wav

**macOS say + ffmpeg** (committed version was generated this way):

    say -o /tmp/s1.aiff -v Daniel "Hello, this is the first speaker..."
    say -o /tmp/s2.aiff -v Samantha "Yes, and this is the second speaker..."
    say -o /tmp/s3.aiff -v Daniel "First speaker again..."
    ffmpeg -i /tmp/s1.aiff -ar 16000 -ac 1 /tmp/s1_16k.wav
    ffmpeg -i /tmp/s2.aiff -ar 16000 -ac 1 /tmp/s2_16k.wav
    ffmpeg -i /tmp/s3.aiff -ar 16000 -ac 1 /tmp/s3_16k.wav
    ffmpeg -i "concat:/tmp/s1_16k.wav|/tmp/s2_16k.wav|/tmp/s3_16k.wav" -c copy sample_two_speakers.wav

### Diarization smoke-check (mandatory before commit)

    cp sample_two_speakers.wav ~/AI_Output/uploads/
    curl -F file=@sample_two_speakers.wav \
      http://localhost:8924/v1/audio/transcribe-with-speakers | jq .speaker_count

`speaker_count` must be ≥ 2. If it is 1, increase the voice contrast or
lengthen the file.
