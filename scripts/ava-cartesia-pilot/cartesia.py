"""
Cartesia Sonic TTS + Ink Whisper STT adapters (AVA voice pilot).

TTS: WebSocket stream (pcm_mulaw @ 8 kHz) with /tts/bytes fallback.
STT: WebSocket ink-whisper (RU) with silence auto-finalize for natural turns.

API:
  https://docs.cartesia.ai/api-reference/tts/websocket
  https://docs.cartesia.ai/api-reference/stt/websocket
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, Optional
from urllib.parse import urlencode

import aiohttp
import websockets

from ..audio import pcm16le_to_mulaw, resample_audio
from ..config import AppConfig, CartesiaProviderConfig
from ..logging_config import get_logger
from .base import STTComponent, TTSComponent

logger = get_logger(__name__)

CARTESIA_DEFAULT_PCM_RATE = 16000


def _ws_base(http_base: str) -> str:
    base = (http_base or "https://api.cartesia.ai").rstrip("/")
    if base.startswith("https://"):
        return "wss://" + base[len("https://") :]
    if base.startswith("http://"):
        return "ws://" + base[len("http://") :]
    if base.startswith("wss://") or base.startswith("ws://"):
        return base
    return "wss://" + base


def _b64_audio(payload: Dict[str, Any]) -> bytes:
    raw = payload.get("data") or payload.get("audio") or ""
    if isinstance(raw, bytes):
        return raw
    if not raw:
        return b""
    return base64.b64decode(raw)


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------


@dataclass
class _CartesiaSTTSession:
    options: Dict[str, Any]
    websocket: Any = None
    transcript_queue: Optional[asyncio.Queue] = None
    receiver_task: Optional[asyncio.Task] = None
    active: bool = False
    pending_final: str = ""
    flush_task: Optional[asyncio.Task] = None
    emit_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class CartesiaSTTAdapter(STTComponent):
    """Streaming Cartesia Ink Whisper STT (RU) with silence auto-finalize."""

    def __init__(
        self,
        component_key: str,
        app_config: AppConfig,
        provider_config: CartesiaProviderConfig,
        options: Optional[Dict[str, Any]] = None,
    ):
        self.component_key = component_key
        self._app_config = app_config
        self._provider_config = provider_config
        self._pipeline_defaults = options or {}
        self._sessions: Dict[str, _CartesiaSTTSession] = {}

    async def start(self) -> None:
        logger.debug(
            "Cartesia STT adapter initialized",
            component=self.component_key,
            model=getattr(self._provider_config, "stt_model", "ink-whisper"),
        )

    async def stop(self) -> None:
        for call_id in list(self._sessions.keys()):
            await self.close_call(call_id)

    async def open_call(self, call_id: str, options: Dict[str, Any]) -> None:
        merged = self._compose_options(options or {})
        self._sessions[call_id] = _CartesiaSTTSession(options=merged)
        logger.info(
            "Cartesia STT session opened",
            call_id=call_id,
            model=merged.get("model"),
            language=merged.get("language"),
        )

    async def close_call(self, call_id: str) -> None:
        session = self._sessions.pop(call_id, None)
        if not session:
            return
        session.active = False
        if session.flush_task and not session.flush_task.done():
            session.flush_task.cancel()
        if session.websocket is not None:
            try:
                await session.websocket.send("close")
            except Exception:
                pass
            try:
                await session.websocket.close()
            except Exception:
                pass
        if session.receiver_task and not session.receiver_task.done():
            session.receiver_task.cancel()
            try:
                await session.receiver_task
            except Exception:
                pass
        if session.transcript_queue is not None:
            try:
                session.transcript_queue.put_nowait(None)
            except Exception:
                pass
        logger.info("Cartesia STT session closed", call_id=call_id)

    async def validate_connectivity(self, options: Dict[str, Any]) -> Dict[str, Any]:
        merged = self._compose_options(options or {})
        return await super().validate_connectivity(merged)

    async def transcribe(
        self,
        call_id: str,
        audio_pcm16: bytes,
        sample_rate: int,
        options: Dict[str, Any],
    ) -> str:
        # Chunked fallback unused when streaming:true; keep stub for safety.
        return ""

    async def start_stream(self, call_id: str, options: Dict[str, Any]) -> None:
        session = self._sessions.get(call_id)
        if not session:
            raise RuntimeError(f"Cartesia STT session not found for call {call_id}")

        merged = self._compose_options({**session.options, **(options or {})})
        session.options = merged
        api_key = merged.get("api_key") or os.getenv("CARTESIA_API_KEY")
        if not api_key:
            raise RuntimeError("Cartesia STT requires CARTESIA_API_KEY")

        api_version = str(merged.get("api_version") or "2026-08-14")
        query_items: list[tuple[str, str]] = [
            ("model", str(merged.get("model") or "ink-whisper")),
            ("encoding", str(merged.get("encoding") or "pcm_s16le")),
            ("sample_rate", str(int(merged.get("sample_rate") or 16000))),
            ("language", str(merged.get("language") or "ru")),
            ("cartesia_version", api_version),
            (
                "max_silence_duration_secs",
                str(merged.get("max_silence_duration_secs", 0.7)),
            ),
            ("min_volume", str(merged.get("min_volume", 0.035))),
        ]
        keyterms = merged.get("keyterms") or []
        if isinstance(keyterms, str):
            keyterms = [k.strip() for k in keyterms.split(",") if k.strip()]
        # ink-whisper rejects keyterm prompting (HTTP 400). Keep the option for
        # future models, but never send keyterms on ink-whisper.
        model_name = str(merged.get("model") or "ink-whisper").lower()
        if "ink-whisper" in model_name:
            if keyterms:
                logger.info(
                    "Cartesia STT skipping keyterms (unsupported by ink-whisper)",
                    call_id=call_id,
                    keyterm_count=len(keyterms),
                )
            keyterms = []
        for term in keyterms:
            query_items.append(("keyterm", str(term)))
        ws_url = (
            f"{_ws_base(str(merged.get('base_url')))}/stt/websocket?"
            f"{urlencode(query_items)}"
        )

        logger.info(
            "Cartesia STT opening streaming session",
            call_id=call_id,
            model=dict(query_items).get("model"),
            language=dict(query_items).get("language"),
            silence_secs=dict(query_items).get("max_silence_duration_secs"),
            keyterm_count=len(keyterms) if isinstance(keyterms, list) else 0,
        )

        try:
            websocket = await websockets.connect(
                ws_url,
                additional_headers={
                    "X-API-Key": api_key,
                    "Cartesia-Version": api_version,
                },
                max_size=16 * 1024 * 1024,
                ping_interval=20,
                ping_timeout=10,
            )
        except Exception as exc:
            logger.error(
                "Failed to connect to Cartesia STT",
                call_id=call_id,
                error=str(exc),
                exc_info=True,
            )
            raise RuntimeError(f"Cartesia STT connection failed: {exc}") from exc

        session.websocket = websocket
        session.transcript_queue = asyncio.Queue(maxsize=16)
        session.active = True
        session.pending_final = ""
        session.receiver_task = asyncio.create_task(
            self._receive_loop(call_id, session)
        )
        logger.info("Cartesia STT streaming session opened", call_id=call_id)

    async def send_audio(
        self,
        call_id: str,
        audio_pcm16: bytes,
        fmt: str = "pcm16_16k",
    ) -> None:
        session = self._sessions.get(call_id)
        if not session or not session.websocket or not session.active or not audio_pcm16:
            return
        try:
            await session.websocket.send(audio_pcm16)
        except (websockets.ConnectionClosed, websockets.WebSocketException) as exc:
            logger.warning(
                "Cartesia STT websocket closed while sending",
                call_id=call_id,
                error=str(exc),
            )
            session.active = False
        except Exception:
            logger.error(
                "Error sending audio to Cartesia STT",
                call_id=call_id,
                exc_info=True,
            )

    async def iter_results(self, call_id: str) -> AsyncIterator[str]:
        session = self._sessions.get(call_id)
        if not session or not session.transcript_queue:
            return
        while True:
            try:
                transcript = await session.transcript_queue.get()
                if transcript is None:
                    break
                yield transcript
            except asyncio.CancelledError:
                break

    async def stop_stream(self, call_id: str) -> None:
        session = self._sessions.get(call_id)
        if not session or not session.websocket:
            return
        try:
            await session.websocket.send("finalize")
        except Exception:
            pass

    async def _receive_loop(self, call_id: str, session: _CartesiaSTTSession) -> None:
        try:
            async for message in session.websocket:
                if not session.active:
                    break
                if isinstance(message, bytes):
                    continue
                try:
                    data = json.loads(message)
                except (json.JSONDecodeError, TypeError):
                    continue

                msg_type = data.get("type")
                if msg_type == "error":
                    logger.error(
                        "Cartesia STT error event",
                        call_id=call_id,
                        error=str(data)[:400],
                    )
                    continue
                if msg_type != "transcript":
                    continue

                text = data.get("text") or ""
                is_final = bool(data.get("is_final"))
                if not is_final:
                    continue
                if text:
                    session.pending_final += text
                    await self._schedule_flush(call_id, session)
                elif session.pending_final.strip():
                    await self._flush_pending(call_id, session)
        except websockets.ConnectionClosed:
            logger.info("Cartesia STT websocket closed", call_id=call_id)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.error(
                "Cartesia STT receive loop error",
                call_id=call_id,
                exc_info=True,
            )
        finally:
            session.active = False
            if session.pending_final.strip():
                try:
                    await self._flush_pending(call_id, session)
                except Exception:
                    pass
            if session.transcript_queue is not None:
                try:
                    session.transcript_queue.put_nowait(None)
                except Exception:
                    pass

    async def _schedule_flush(
        self, call_id: str, session: _CartesiaSTTSession
    ) -> None:
        # Coalesce rapid final deltas from one utterance before waking the LLM.
        if session.flush_task and not session.flush_task.done():
            session.flush_task.cancel()

        async def _delayed() -> None:
            try:
                # Coalesce finals fast — every 80ms here is end-of-turn latency.
                await asyncio.sleep(0.08)
                await self._flush_pending(call_id, session)
            except asyncio.CancelledError:
                return

        session.flush_task = asyncio.create_task(_delayed())

    async def _flush_pending(
        self, call_id: str, session: _CartesiaSTTSession
    ) -> None:
        async with session.emit_lock:
            text = (session.pending_final or "").strip()
            session.pending_final = ""
            if not text or session.transcript_queue is None:
                return
            if self._is_garbage_transcript(text):
                logger.info(
                    "Cartesia STT dropped low-quality transcript",
                    call_id=call_id,
                    transcript_preview=text[:80],
                )
                return
            logger.info(
                "Cartesia STT transcript received",
                call_id=call_id,
                transcript_preview=text[:80],
            )
            try:
                session.transcript_queue.put_nowait(text)
            except asyncio.QueueFull:
                try:
                    session.transcript_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                await session.transcript_queue.put(text)

    # Narrow Whisper hallucination list only. Imperfect ASR must reach the LLM;
    # a "clarify if unclear" prompt previously caused endless «Не расслышал».
    _STT_HALLUCINATIONS = frozenset(
        {
            "редактор",
            "субтитры",
            "продолжение следует",
            "thanks for watching",
            "thank you for watching",
            "subscribe",
            "подписывайтесь",
        }
    )

    @classmethod
    def _is_garbage_transcript(cls, text: str) -> bool:
        """Drop only clear noise scraps; let imperfect ASR through to the LLM."""
        cleaned = " ".join((text or "").strip().split())
        if not cleaned:
            return True
        low = cleaned.lower().replace("ё", "е")
        if low in {"а", "у", "м", "мм", "ммм", "ээ", "эээ", "эм", "...", "…"}:
            return True
        bare = low.strip(".,!?…:;\"'«» ")
        if bare in cls._STT_HALLUCINATIONS:
            return True
        if "продолжение следует" in bare or "thanks for watching" in bare:
            return True
        tokens = [
            t.strip(".,!?…:;\"'«»")
            for t in cleaned.replace(",", " ").split()
            if t.strip(".,!?…:;\"'«»")
        ]
        if not tokens:
            return True
        short_ok = {
            "да",
            "нет",
            "ок",
            "ладно",
            "привет",
            "пока",
            "спасибо",
            "угу",
            "ага",
            "хорошо",
            "понял",
            "поняла",
            "ясно",
            "стоп",
            "алло",
            "слушай",
            "конечно",
            "отлично",
            "давай",
            "можно",
            "нужно",
            "хочу",
            "деньги",
            "выплаты",
            "карта",
            "сбп",
        }
        if len(tokens) == 1:
            tok = tokens[0].lower().replace("ё", "е")
            if tok in short_ok:
                return False
            if tok in cls._STT_HALLUCINATIONS:
                return True
            letters = sum(ch.isalpha() for ch in tok)
            if letters < 3:
                return True
            # Only drop very short lone noise nouns («Редактор»).
            if len(tok) <= 10:
                return True
            return False
        return False

    def _compose_options(self, runtime_options: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        runtime_options = runtime_options or {}
        pc = self._provider_config
        return {
            "api_key": runtime_options.get(
                "api_key", self._pipeline_defaults.get("api_key", pc.api_key)
            ),
            "base_url": runtime_options.get(
                "base_url", self._pipeline_defaults.get("base_url", pc.base_url)
            ),
            "api_version": runtime_options.get(
                "api_version",
                self._pipeline_defaults.get("api_version", pc.api_version),
            ),
            "model": runtime_options.get(
                "model",
                self._pipeline_defaults.get(
                    "model", getattr(pc, "stt_model", "ink-whisper")
                ),
            ),
            "language": runtime_options.get(
                "language",
                self._pipeline_defaults.get("language", pc.language or "ru"),
            ),
            "encoding": runtime_options.get(
                "encoding", self._pipeline_defaults.get("encoding", "pcm_s16le")
            ),
            "sample_rate": runtime_options.get(
                "sample_rate", self._pipeline_defaults.get("sample_rate", 16000)
            ),
            "max_silence_duration_secs": runtime_options.get(
                "max_silence_duration_secs",
                self._pipeline_defaults.get(
                    "max_silence_duration_secs",
                    getattr(pc, "stt_max_silence_secs", 0.7),
                ),
            ),
            "min_volume": runtime_options.get(
                "min_volume",
                self._pipeline_defaults.get(
                    "min_volume", getattr(pc, "stt_min_volume", 0.035)
                ),
            ),
            "keyterms": runtime_options.get(
                "keyterms", self._pipeline_defaults.get("keyterms", [])
            ),
            "streaming": runtime_options.get(
                "streaming", self._pipeline_defaults.get("streaming", True)
            ),
            "chunk_ms": runtime_options.get(
                "chunk_ms", self._pipeline_defaults.get("chunk_ms", 160)
            ),
        }


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------


class CartesiaTTSAdapter(TTSComponent):
    """Cartesia Sonic → μ-law 8 kHz (WebSocket stream, bytes fallback)."""

    wideband_output_format = {
        "encoding": "linear16",
        "sample_rate": 16000,
        "options": {"encoding": "pcm_s16le", "sample_rate": 16000},
    }

    def __init__(
        self,
        component_key: str,
        app_config: AppConfig,
        provider_config: CartesiaProviderConfig,
        options: Optional[Dict[str, Any]] = None,
        *,
        session_factory: Optional[Callable[[], aiohttp.ClientSession]] = None,
    ):
        self.component_key = component_key
        self._app_config = app_config
        self._provider_config = provider_config
        self._pipeline_defaults = options or {}
        self._session_factory = session_factory
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws_by_call: Dict[str, Any] = {}
        self._ws_lock_by_call: Dict[str, asyncio.Lock] = {}

    async def start(self) -> None:
        logger.debug(
            "Cartesia TTS adapter initialized",
            component=self.component_key,
            voice_id=self._provider_config.voice_id,
            model_id=self._provider_config.model_id,
            language=self._provider_config.language,
        )

    async def stop(self) -> None:
        for call_id in list(self._ws_by_call.keys()):
            await self.close_call(call_id)
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def open_call(self, call_id: str, options: Dict[str, Any]) -> None:
        await self._ensure_session()
        self._ws_lock_by_call[call_id] = asyncio.Lock()

    async def close_call(self, call_id: str) -> None:
        ws = self._ws_by_call.pop(call_id, None)
        self._ws_lock_by_call.pop(call_id, None)
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

    async def validate_connectivity(self, options: Dict[str, Any]) -> Dict[str, Any]:
        merged = self._compose_options(options or {})
        return await super().validate_connectivity(merged)

    async def synthesize(
        self,
        call_id: str,
        text: str,
        options: Dict[str, Any],
    ) -> AsyncIterator[bytes]:
        if not text:
            return
            yield

        merged = self._compose_options(options)
        spoken = self._prepare_spoken_text(text or "")
        transport = str(merged.get("transport") or "websocket").lower()
        if transport in ("websocket", "ws", "stream"):
            try:
                async for chunk in self._synthesize_websocket(call_id, spoken, merged):
                    if chunk:
                        yield chunk
                return
            except Exception as exc:
                logger.warning(
                    "Cartesia TTS websocket failed; falling back to /tts/bytes",
                    call_id=call_id,
                    error=str(exc),
                )

        async for chunk in self._synthesize_bytes(call_id, spoken, merged):
            if chunk:
                yield chunk

    async def _synthesize_websocket(
        self,
        call_id: str,
        text: str,
        merged: Dict[str, Any],
    ) -> AsyncIterator[bytes]:
        api_key = merged.get("api_key") or os.getenv("CARTESIA_API_KEY")
        if not api_key:
            raise RuntimeError("Cartesia TTS requires CARTESIA_API_KEY")

        api_version = str(merged.get("api_version") or "2026-08-14")
        voice_id = str(merged.get("voice_id"))
        model_id = str(merged.get("model_id"))
        language = str(merged.get("language") or "ru")
        request_id = f"cartesia-tts-ws-{uuid.uuid4().hex[:12]}"
        context_id = uuid.uuid4().hex
        ws_url = (
            f"{_ws_base(str(merged.get('base_url')))}/tts/websocket?"
            f"{urlencode({'cartesia_version': api_version})}"
        )

        payload = {
            "model_id": model_id,
            "transcript": text,
            "voice": {"mode": "id", "id": voice_id},
            "language": language,
            "context_id": context_id,
            "continue": False,
            "output_format": {
                "container": "raw",
                "encoding": "pcm_mulaw",
                "sample_rate": 8000,
            },
            "generation_config": self._generation_config(merged),
        }

        logger.info(
            "Cartesia TTS websocket synthesis started",
            call_id=call_id,
            request_id=request_id,
            text_preview=text[:64],
            voice_id=voice_id,
            model_id=model_id,
        )
        started_at = time.perf_counter()
        first_audio_ms: Optional[float] = None
        output_bytes = 0
        chunk_ms = int(merged.get("chunk_size_ms", 20))

        lock = self._ws_lock_by_call.setdefault(call_id, asyncio.Lock())
        async with lock:
            websocket = await self._ensure_tts_ws(
                call_id, ws_url, api_key, api_version
            )
            await websocket.send(json.dumps(payload))
            try:
                while True:
                    raw = await asyncio.wait_for(websocket.recv(), timeout=30)
                    if isinstance(raw, bytes):
                        audio = raw
                        msg_type = "chunk"
                    else:
                        try:
                            msg = json.loads(raw)
                        except (json.JSONDecodeError, TypeError):
                            continue
                        msg_type = msg.get("type")
                        if msg_type == "error":
                            # Drop broken socket so the next turn reconnects.
                            await self._drop_tts_ws(call_id)
                            raise RuntimeError(f"Cartesia TTS WS error: {msg}")
                        if msg_type in ("done", "complete"):
                            break
                        if msg_type != "chunk":
                            continue
                        audio = _b64_audio(msg)

                    if not audio:
                        continue
                    if first_audio_ms is None:
                        first_audio_ms = (time.perf_counter() - started_at) * 1000.0
                        logger.info(
                            "Cartesia TTS websocket first audio",
                            call_id=call_id,
                            request_id=request_id,
                            ttfb_ms=round(first_audio_ms, 2),
                        )
                    output_bytes += len(audio)
                    for piece in self._chunk_audio(audio, chunk_ms):
                        if piece:
                            yield piece
            except (websockets.ConnectionClosed, asyncio.TimeoutError) as exc:
                await self._drop_tts_ws(call_id)
                raise RuntimeError(f"Cartesia TTS WS interrupted: {exc}") from exc

        logger.info(
            "Cartesia TTS websocket synthesis completed",
            call_id=call_id,
            request_id=request_id,
            ttfb_ms=round(first_audio_ms or 0.0, 2),
            latency_ms=round((time.perf_counter() - started_at) * 1000.0, 2),
            output_bytes=output_bytes,
        )

    async def _ensure_tts_ws(
        self,
        call_id: str,
        ws_url: str,
        api_key: str,
        api_version: str,
    ) -> Any:
        existing = self._ws_by_call.get(call_id)
        if existing is not None:
            closed = getattr(existing, "closed", False)
            if not closed:
                return existing
        websocket = await websockets.connect(
            ws_url,
            additional_headers={
                "X-API-Key": api_key,
                "Cartesia-Version": api_version,
            },
            max_size=16 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=10,
            open_timeout=12,
        )
        self._ws_by_call[call_id] = websocket
        logger.info("Cartesia TTS websocket connected", call_id=call_id)
        return websocket

    async def _drop_tts_ws(self, call_id: str) -> None:
        ws = self._ws_by_call.pop(call_id, None)
        if ws is None:
            return
        try:
            await ws.close()
        except Exception:
            pass

    async def _synthesize_bytes(
        self,
        call_id: str,
        text: str,
        merged: Dict[str, Any],
    ) -> AsyncIterator[bytes]:
        await self._ensure_session()
        api_key = merged.get("api_key") or os.getenv("CARTESIA_API_KEY")
        if not api_key:
            raise RuntimeError("Cartesia TTS requires CARTESIA_API_KEY")

        voice_id = str(merged.get("voice_id") or self._provider_config.voice_id)
        model_id = str(merged.get("model_id") or self._provider_config.model_id)
        language = str(merged.get("language") or self._provider_config.language)
        api_version = str(
            merged.get("api_version") or self._provider_config.api_version
        )
        sample_rate = int(
            merged.get("pcm_sample_rate") or self._provider_config.pcm_sample_rate
        )
        base_url = str(merged.get("base_url") or self._provider_config.base_url).rstrip(
            "/"
        )
        url = f"{base_url}/tts/bytes"
        request_id = f"cartesia-tts-{uuid.uuid4().hex[:12]}"

        payload = {
            "model_id": model_id,
            "transcript": text,
            "voice": {"mode": "id", "id": voice_id},
            "language": language,
            "output_format": {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": sample_rate,
            },
            "generation_config": self._generation_config(merged),
        }
        headers = {
            "X-API-Key": api_key,
            "Cartesia-Version": api_version,
            "Content-Type": "application/json",
        }

        logger.info(
            "Cartesia TTS synthesis started",
            call_id=call_id,
            request_id=request_id,
            text_preview=text[:64],
            voice_id=voice_id,
            model_id=model_id,
            language=language,
        )
        started_at = time.perf_counter()

        assert self._session is not None
        async with self._session.post(url, json=payload, headers=headers) as response:
            if response.status >= 400:
                body = await response.text()
                logger.error(
                    "Cartesia TTS synthesis failed",
                    call_id=call_id,
                    request_id=request_id,
                    status=response.status,
                    body=body[:500],
                )
                response.raise_for_status()

            raw_pcm = await response.read()
            latency_ms = (time.perf_counter() - started_at) * 1000.0

            if sample_rate != 8000:
                pcm_8k, _ = resample_audio(raw_pcm, sample_rate, 8000)
            else:
                pcm_8k = raw_pcm
            converted = pcm16le_to_mulaw(pcm_8k)

            logger.info(
                "Cartesia TTS synthesis completed",
                call_id=call_id,
                request_id=request_id,
                latency_ms=round(latency_ms, 2),
                raw_bytes=len(raw_pcm),
                output_bytes=len(converted),
            )

            chunk_ms = int(merged.get("chunk_size_ms", 20))
            for chunk in self._chunk_audio(converted, chunk_ms):
                if chunk:
                    yield chunk

    async def _ensure_session(self) -> None:
        if self._session and not self._session.closed:
            return
        factory = self._session_factory or aiohttp.ClientSession
        self._session = factory()

    def _compose_options(self, runtime_options: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        runtime_options = runtime_options or {}
        return {
            "api_key": runtime_options.get(
                "api_key",
                self._pipeline_defaults.get("api_key", self._provider_config.api_key),
            ),
            "voice_id": runtime_options.get(
                "voice_id",
                self._pipeline_defaults.get("voice_id", self._provider_config.voice_id),
            ),
            "model_id": runtime_options.get(
                "model_id",
                self._pipeline_defaults.get("model_id", self._provider_config.model_id),
            ),
            "language": runtime_options.get(
                "language",
                self._pipeline_defaults.get("language", self._provider_config.language),
            ),
            "base_url": runtime_options.get(
                "base_url",
                self._pipeline_defaults.get("base_url", self._provider_config.base_url),
            ),
            "api_version": runtime_options.get(
                "api_version",
                self._pipeline_defaults.get(
                    "api_version", self._provider_config.api_version
                ),
            ),
            "pcm_sample_rate": runtime_options.get(
                "pcm_sample_rate",
                self._pipeline_defaults.get(
                    "pcm_sample_rate", self._provider_config.pcm_sample_rate
                ),
            ),
            "chunk_size_ms": runtime_options.get(
                "chunk_size_ms", self._pipeline_defaults.get("chunk_size_ms", 20)
            ),
            "transport": runtime_options.get(
                "transport",
                self._pipeline_defaults.get(
                    "transport",
                    getattr(self._provider_config, "tts_transport", "websocket"),
                ),
            ),
            "speed": runtime_options.get(
                "speed",
                self._pipeline_defaults.get(
                    "speed", getattr(self._provider_config, "tts_speed", 1.18)
                ),
            ),
            "volume": runtime_options.get(
                "volume",
                self._pipeline_defaults.get(
                    "volume", getattr(self._provider_config, "tts_volume", 1.4)
                ),
            ),
        }

    @staticmethod
    def _prepare_spoken_text(text: str) -> str:
        """Make RU TTS a bit more 'sales-live' without English emotion tags.

        Cartesia emotion SSML is English-only; for RU we rely on punctuation
        and light speed/volume SSML so Sonic doesn't flatten everything.
        """
        cleaned = " ".join((text or "").strip().split())
        if not cleaned:
            return cleaned
        # Drop accidental English emotion/SSML the LLM might emit.
        if "<emotion" in cleaned.lower() or "</emotion>" in cleaned.lower():
            cleaned = re.sub(r"</?emotion[^>]*>", "", cleaned, flags=re.I)
            cleaned = " ".join(cleaned.split())
        # Mild delivery boost for short sales lines (RU-safe SSML).
        if "<speed" not in cleaned.lower() and "<volume" not in cleaned.lower():
            # Slightly brighter than generation_config alone on clones.
            cleaned = f'<speed ratio="1.05"/><volume ratio="1.08"/> {cleaned}'
        return cleaned

    @staticmethod
    def _generation_config(merged: Dict[str, Any]) -> Dict[str, Any]:
        # Emotion tags are English-only on Cartesia; for RU we lean on expressive
        # transcript + speed/volume so Sonic still sounds engaged.
        cfg: Dict[str, Any] = {}
        try:
            speed = float(merged.get("speed", 1.18))
            cfg["speed"] = max(0.6, min(1.5, speed))
        except (TypeError, ValueError):
            cfg["speed"] = 1.18
        try:
            volume = float(merged.get("volume", 1.4))
            cfg["volume"] = max(0.5, min(2.0, volume))
        except (TypeError, ValueError):
            cfg["volume"] = 1.4
        return cfg

    def _chunk_audio(self, audio: bytes, chunk_ms: int = 20) -> list[bytes]:
        # μ-law: 1 byte/sample @ 8 kHz
        chunk_size = max(1, int(8000 * (chunk_ms / 1000.0)))
        return [
            audio[i : i + chunk_size]
            for i in range(0, len(audio), chunk_size)
            if audio[i : i + chunk_size]
        ]
