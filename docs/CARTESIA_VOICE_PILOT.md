# Cartesia voice pilot — drop into `/root/ava` (DO NOT replace default Mango path)

## Goal
A/B listen **Cartesia Sonic** as TTS while **keeping** live inbound on `openai_realtime`.

Current phase: free conversation (any topic), no knowledge base / no calendar tools.
Script + vault come later.

## Architecture (pilot only)
```
SIP cartesia / 9901 → AI_CONTEXT=cartesia_pilot
  → pipeline hybrid_cartesia
      STT: cartesia_stt (Ink Whisper WS, RU, silence auto-finalize ~0.55s)
      LLM: openai_llm (gpt-4o-mini, streaming overlap, short replies)
      TTS: cartesia_tts (Sonic websocket → pcm_mulaw 8 kHz, Denis)
```

Prod Mango `from-mango` / `garik` stays on `openai_realtime` / voice `cedar`.

## Why not local_stt / OpenAI REST chunks
On this host `local_ai_server` Vosk emits `STT unavailable` → empty transcripts.
Fixed 2.8s OpenAI REST chunks caused both delay and “off-topic” replies.
Pilot now uses **Cartesia streaming STT** (same API key) with silence endpointing.

## Latency / stability notes
Hybrid is still not duplex Realtime, but much closer after streaming STT+TTS:
- STT ends a turn ~0.55s after silence (not a fixed 2.8s buffer + REST round-trip)
- TTS websocket yields first audio ASAP (`pcm_mulaw` @ 8 kHz, no resample wait)
- LLM `aggregation_timeout_sec: 0.45` + `max_tokens: 80`
- `streaming.pipeline_streaming_overlap: true`
- **Do not enable `pipeline_filler`** with Cartesia overlap: filler↔real TTS race left
  `audio_capture_enabled=False` (bot went deaf mid-call; no further STT)
- pipeline TalkDetect barge-in off (echo was cutting replies)

### Known failure mode (2026-08-31)
After “пиво” turn: filler stream end fired late while real `pipeline-tts` gating token
was still active → capture stuck off → ~23s silence until caller hangup.
Also `Task was destroyed but it is pending!` on the overlap playback task.
**Mitigation:** `pipeline_filler_enabled: false` (verified: multi-turn dialog continues).

## Roadmap to feel more “live”
| Priority | Change | Status |
|----------|--------|--------|
| P0 | Keep filler off / safe TTS gating | Done |
| P1 | Cartesia websocket TTS + reused socket | Done (~0.25–0.3s TTFB warm) |
| P1 | Cartesia Ink Whisper streaming STT (RU) | Done |
| P2 | Sales persona + expressive text; speed/volume | Done (RU emotion tags N/A) |
| P2 | Drop garbage single-token STT | Done |
| P3 | Domain script/KB for on-topic sales facts | Next |
| P3 | True duplex / Cartesia S2S when RU-ready | Ceiling |

Honest: “не в попад” is mostly STT noise + weak grounding. Next big win = company script/KB + optional Deepgram Flux when a key is available.

## Prerequisites
1. `CARTESIA_API_KEY` in `/root/ava/.env`
2. `CARTESIA_VOICE_ID` (Denis clone: `631151e9-7ae9-4324-b8e7-c72cb52e6cb1`)
3. Optional stock RU: `CARTESIA_VOICE_STOCK_RU=1e4176b1-3db9-44d6-a601-4fe68b041942` (Sergei)
4. `OPENAI_API_KEY` for LLM (STT/TTS are Cartesia)

## Offline listen (no call)
```bash
export CARTESIA_API_KEY=...
python3 scripts/cartesia_tts_smoke.py --list-voices
python3 scripts/cartesia_tts_smoke.py --voice-id <uuid>
```

## Install on AVA host
`scripts/ava-cartesia-pilot/deploy_to_ava.sh` (backs up, copies adapter, patches
config/orchestrator, merges snippet, dialplan `cartesia`/`9901`, recreates `ai_engine`).

After yaml-only tune:
```bash
# edit /root/ava/config/ai-agent.local.yaml then:
cd /root/ava && docker compose restart ai_engine
```

## How to talk (human)
Softphone dial `9901` does **not** reach Asterisk (Mango cloud). Use:
```bash
asterisk -rx "channel originate PJSIP/<79…>@mango-employee extension cartesia@from-ai-agent"
```

## Success criteria
- Greeting in Denis/Cartesia within ~1–2 s
- Russian dialog on free topics (no tools)
- Fewer mid-phrase STT cuts than 800ms mode
- Mango inbound still openai_realtime

## Rollback
```bash
# restore /root/ava/backups/cartesia-pilot-*
docker compose -f /root/ava/docker-compose.yml restart ai_engine
asterisk -rx "dialplan reload"
```
