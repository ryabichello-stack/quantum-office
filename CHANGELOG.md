# Changelog

## Unreleased

### Cartesia voice pilot
- Sales-style Cartesia pilot (`cartesia_pilot`): Denis clone; streaming Ink Whisper STT + Sonic websocket TTS.
- Sales energy prompt + light product pitch; **no «не расслышал» loop** (interpret imperfect STT).
- TTS energy: speed/volume boost + light RU-safe SSML.
- STT: narrow hallucination gate only; silence ~0.65s (ink-whisper: no keyterms).
- Filler off; reused TTS websocket (warm TTFB often ~0.25–0.3s).
