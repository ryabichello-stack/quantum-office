# Changelog

## Unreleased

### Cartesia voice pilot
- Sales-style Cartesia pilot (`cartesia_pilot`): Denis clone; streaming Ink Whisper STT + Sonic websocket TTS.
- Engaged salesperson prompt + expressive punctuation; TTS speed/volume (RU emotion tags unsupported by Cartesia).
- STT quality gate drops lone noise tokens that derailed context; silence finalize ~0.7s.
- Filler off; reused TTS websocket (warm TTFB often ~0.25–0.3s).
