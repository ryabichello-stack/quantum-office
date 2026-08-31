# Changelog

## Unreleased

### Cartesia voice pilot
- Free-talk Cartesia pilot (`cartesia_pilot` / dialplan `cartesia`·`9901`): Denis clone TTS; no knowledge base / tools yet.
- **Low-latency path**: Cartesia Ink Whisper **streaming STT** (RU, silence finalize) + Sonic **websocket TTS** (`pcm_mulaw` 8 kHz); OpenAI only for LLM.
- Disabled `pipeline_filler`: filler↔TTS gating race deafened the bot mid-call.
- Streaming overlap on; TalkDetect barge-in off; short free-talk prompt for turn coherence.
