# Cartesia voice pilot — drop into /root/ava (DO NOT replace default Mango path)

## Goal
A/B listen **Cartesia Sonic** as TTS while **keeping** live inbound on `openai_realtime`.

## Architecture (pilot only)
```
SIP test → AI_CONTEXT=cartesia_pilot
  → pipeline hybrid_cartesia
      STT: local_stt (local_ai_server)
      LLM: openai_llm (gpt-4o-mini)
      TTS: cartesia_tts (Sonic → μ-law 8 kHz)
```

Prod Mango `from-mango` stays on `openai_realtime` / voice `cedar`.

## Prerequisites
1. `CARTESIA_API_KEY` in `/root/ava/.env`
2. Optional: `CARTESIA_VOICE_ID` (Russian-capable voice UUID)
3. `local_ai_server` healthy (already on this host)
4. `OPENAI_API_KEY` present (LLM)

## Offline listen (no call)
```bash
export CARTESIA_API_KEY=...
python3 scripts/cartesia_tts_smoke.py --list-voices
python3 scripts/cartesia_tts_smoke.py --voice-id <uuid>
# → scripts/ava-cartesia-pilot/samples/cartesia_*_8k.wav
```

## Install on AVA host
See `deploy_to_ava.sh` (backs up, copies adapter, patches config/orchestrator,
merges local yaml snippet, adds dialplan `cartesia`, restarts `ai_engine`).

## Test call
From host / SIP test:
```bash
# Dialplan extension (after install):
#   cartesia → AI_CONTEXT=cartesia_pilot → Stasis
asterisk -rx "dialplan show cartesia@from-ai-agent"
# or originate via quantum_sip_test_call targeting extension cartesia
```

## Success criteria
- Greeting plays in Cartesia voice within ~1–2 s of answer
- Russian intelligible on 8 kHz phone path
- Barge-in acceptable
- Mango inbound still openai_realtime (unchanged)

## Rollback
```bash
# restore backups written by deploy_to_ava.sh under /root/ava/backups/cartesia-pilot-*
# remove CARTESIA_* from .env if desired
docker restart ai_engine
asterisk -rx "dialplan reload"
```
