#!/usr/bin/env python3
"""Idle warm WITH paced mic keepalive, then kick-only on answer.

REFUSES unless AVA_LIVE_WARM_COST_OK=1 — this opens a paid Live session.
"""
import asyncio, audioop, base64, json, os, time
import websockets
LIVE_WS_URL = "wss://api.openai.com/v1/live/sessions"
GREETING = "Здравствуйте, проверка задержки."
TARGET = 1.5

async def main():
    if str(os.environ.get("AVA_LIVE_WARM_COST_OK", "0")).strip().lower() not in (
        "1", "true", "yes", "on",
    ):
        raise SystemExit(
            "REFUSED: set AVA_LIVE_WARM_COST_OK=1 explicitly "
            "(this probe opens a paid OpenAI Live session)"
        )
    api_key = os.environ["OPENAI_API_KEY"]
    proxy = (os.environ.get("AVA_OPENAI_PROXY") or "").strip() or None
    kw = dict(additional_headers={"Authorization": f"Bearer {api_key}"}, max_size=8*1024*1024, open_timeout=20)
    if proxy:
        kw["proxy"] = proxy
    results = []
    for i in (1, 2, 3):
        ws = await websockets.connect(LIVE_WS_URL, **kw)
        started = asyncio.Event()
        energy_s = None
        t_kick = None
        stop_mic = asyncio.Event()

        async def recv():
            nonlocal energy_s
            async for raw in ws:
                ev = json.loads(raw)
                et = ev.get("type")
                if et == "session.started":
                    started.set()
                elif et == "session.output_audio.delta" and t_kick:
                    raw_b = base64.b64decode(ev.get("delta") or "")
                    try:
                        rms = audioop.rms(audioop.ulaw2lin(raw_b, 2), 2)
                    except Exception:
                        rms = 0
                    if rms >= 50 and energy_s is None:
                        energy_s = time.time() - t_kick
                        return

        async def mic_loop():
            sil = audioop.lin2ulaw(b"\x00\x00" * 160, 2)
            b64 = base64.b64encode(sil).decode()
            while not stop_mic.is_set():
                try:
                    await ws.send(json.dumps({"type":"session.input_audio.append","audio": b64}))
                except Exception:
                    return
                await asyncio.sleep(0.02)

        rt = asyncio.create_task(recv())
        await ws.send(json.dumps({
            "type":"session.start","event_id":f"warm-{i}",
            "session":{
                "model":"gpt-live-1",
                "instructions":"Ты телефонный ассистент. Когда получишь kick — сразу скажи приветствие по-русски.",
                "audio":{"format":{"type":"audio/pcmu","rate":8000},"output":{"voice":"cedar"}},
                "delegation":{"type":"responses","responses":{"model":"gpt-4.1-mini","tool_choice":"none","parallel_tool_calls":False,"tools":[]}},
            },
        }))
        await asyncio.wait_for(started.wait(), timeout=8)
        mt = asyncio.create_task(mic_loop())
        # idle warm 3s with mic keepalive
        await asyncio.sleep(3.0)
        t_kick = time.time()
        await ws.send(json.dumps({"type":"session.instructions.append","event_id":f"i-{i}","delegation_id":None,"content":"Speak first immediately. Say exactly: "+GREETING}))
        await ws.send(json.dumps({"type":"session.commentary.append","event_id":f"c-{i}","delegation_id":None,"content":"Begin speaking now. Say exactly: "+GREETING}))
        try:
            await asyncio.wait_for(rt, timeout=3.0)
        except asyncio.TimeoutError:
            pass
        stop_mic.set()
        mt.cancel()
        ok = energy_s is not None and energy_s <= TARGET
        print(f"call{i}: kick_to_audio={energy_s} {'PASS' if ok else 'FAIL'}")
        results.append(ok)
        try:
            await ws.close()
        except Exception:
            pass
        await asyncio.sleep(0.3)
    print("RESULTS", results)
    return 0 if all(results) else 1

raise SystemExit(asyncio.run(main()))
