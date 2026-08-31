# Cartesia voice pilot — drop into `/root/ava` (DO NOT replace default Mango path)

## Goal
A/B listen **Cartesia Sonic** as TTS while **keeping** live inbound on `openai_realtime`.

Current phase: free conversation + light product pitch. Full script/vault later.

## Architecture (pilot only)
```
SIP cartesia / 9901 → AI_CONTEXT=cartesia_pilot
  → pipeline hybrid_cartesia
      STT: cartesia_stt (Ink Whisper WS, RU, silence ~0.6s; no keyterms — unsupported)
      LLM: openai_llm (gpt-4o-mini, short sales replies, temp ~0.6)
      TTS: cartesia_tts (Sonic websocket → pcm_mulaw 8 kHz, Denis)
```

Prod Mango `from-mango` / `garik` stays on `openai_realtime` / voice `cedar`.

## Why answers go “не в попад”
Usually not the voice — it’s the pipeline:
1. **STT noise** (telephony / echo → «Редактор», «Бугови») → LLM invents a new topic
2. **No script/KB** → model freelances or refuses sales angles
3. **Flat copy** → Sonic has nothing emotional to act (RU emotion tags are EN-only)

Mitigations in pilot: STT garbage gate + hallucination blacklist, domain keyterms,
sales prompt with clarify-if-unclear + light product grounding, TTS speed/volume + light SSML.

## Latency
Hybrid is still not duplex Realtime:
- STT silence finalize ~0.6s; final coalesce ~80ms
- Warm TTS websocket TTFB often ~0.25–0.3s (cold first connect ~1.5s+)
- LLM `aggregation_timeout_sec: 0.28`, `max_tokens: 70`
- **Filler must stay off** (overlap race → mid-call deafness)

## Roadmap to “ideal”
| Priority | Change | Effect |
|----------|--------|--------|
| Now | Sales prompt + energy TTS + STT gate/keyterms | Less drift, more engaged |
| Next | Company script / vault tools on this context | Facts on-thread, real sales |
| Next | Better telephony STT (Deepgram Flux when key exists) | Fewer mishears |
| Ceiling | True duplex / S2S when RU-ready | Garik-like latency |

### What you can tune yourself (yaml)
On prod edit `/root/ava/config/ai-agent.local.yaml` → `contexts.cartesia_pilot.prompt`
and `pipelines.hybrid_cartesia.options`, then:
```bash
cd /root/ava && docker compose restart ai_engine
```

Useful knobs:
- **Emotion / sales tone** → prompt examples + `tts.speed` / `tts.volume` (1.0–1.5 / 1.0–2.0)
- **Less off-topic** → tighter prompt “переспроси”; slightly higher `min_volume`; keep garbage gate
- **Less lag** → lower `max_silence_duration_secs` (don’t go below ~0.45 or you cut mid-phrase)
  and `aggregation_timeout_sec` (~0.2–0.35)

Do **not** enable `pipeline_filler` with Cartesia overlap.

## Prerequisites
1. `CARTESIA_API_KEY` in `/root/ava/.env`
2. `CARTESIA_VOICE_ID` (Denis: `631151e9-7ae9-4324-b8e7-c72cb52e6cb1`)
3. `OPENAI_API_KEY` for LLM

## Install
`scripts/ava-cartesia-pilot/deploy_to_ava.sh`

## How to talk (human)
Softphone `9901` does **not** hit Asterisk. Use:
```bash
asterisk -rx "channel originate PJSIP/<79…>@mango-employee extension cartesia@from-ai-agent"
```
