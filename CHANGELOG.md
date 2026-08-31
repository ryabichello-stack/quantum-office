# Changelog

## Unreleased

### Cartesia voice pilot
- Free-talk Cartesia pilot (`cartesia_pilot` / dialplan `cartesia`·`9901`): Denis clone TTS, OpenAI STT+LLM (local Vosk STT broken on host).
- Tuned for conversation: longer STT chunks, short LLM replies, streaming overlap/filler, softer barge-in; no knowledge base / tools yet.
