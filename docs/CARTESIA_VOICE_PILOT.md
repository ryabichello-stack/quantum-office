# Cartesia voice pilot — drop into `/root/ava` (DO NOT replace default Mango path)

## Goal
A/B listen **Cartesia Sonic** as TTS while **keeping** live inbound on `openai_realtime`.

Current phase: free conversation (any topic), no knowledge base / no calendar tools.
Script + vault come later.

## Architecture (pilot only)
```
SIP cartesia / 9901 → AI_CONTEXT=cartesia_pilot
  → pipeline hybrid_cartesia
      STT: openai_stt (gpt-4o-mini-transcribe, ~2.8s chunks)
      LLM: openai_llm (gpt-4o-mini, streaming overlap)
      TTS: cartesia_tts (Sonic → μ-law 8 kHz, voice Denis by default)
```

Prod Mango `from-mango` / `garik` stays on `openai_realtime` / voice `cedar`.

## Why not local_stt
On this host `local_ai_server` Vosk emits `STT unavailable` → empty transcripts.
Pilot uses OpenAI REST STT until local STT is fixed.

## Latency notes
Hybrid STT→LLM→TTS is slower than Realtime. Mitigations in pilot:
- utterance-sized STT chunks (`chunk_ms: 2800`) instead of 800ms scrapes
- LLM `aggregation_timeout_sec: 0.9` + short `max_tokens`
- engine `streaming.pipeline_streaming_overlap` + optional filler phrases
- softer / disabled pipeline TalkDetect barge-in (echo was cutting replies)

## Prerequisites
1. `CARTESIA_API_KEY` in `/root/ava/.env`
2. `CARTESIA_VOICE_ID` (Denis clone: `631151e9-7ae9-4324-b8e7-c72cb52e6cb1`)
3. Optional stock RU: `CARTESIA_VOICE_STOCK_RU=1e4176b1-3db9-44d6-a601-4fe68b041942` (Sergei)
4. `OPENAI_API_KEY` for STT + LLM

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
