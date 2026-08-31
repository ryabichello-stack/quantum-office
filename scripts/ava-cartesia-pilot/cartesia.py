"""
Cartesia Sonic TTS Pipeline Adapter (AVA pilot).

Implements TTSComponent for Cartesia /tts/bytes → telephony μ-law 8 kHz.

API: https://docs.cartesia.ai/api-reference/tts/bytes
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, AsyncIterator, Callable, Dict, Optional

import aiohttp

from ..audio import pcm16le_to_mulaw, resample_audio
from ..config import AppConfig, CartesiaProviderConfig
from ..logging_config import get_logger
from .base import TTSComponent

logger = get_logger(__name__)

CARTESIA_DEFAULT_PCM_RATE = 16000


class CartesiaTTSAdapter(TTSComponent):
    """Cartesia Sonic → μ-law 8 kHz for Asterisk AudioSocket."""

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

    async def start(self) -> None:
        logger.debug(
            "Cartesia TTS adapter initialized",
            component=self.component_key,
            voice_id=self._provider_config.voice_id,
            model_id=self._provider_config.model_id,
            language=self._provider_config.language,
        )

    async def stop(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def open_call(self, call_id: str, options: Dict[str, Any]) -> None:
        await self._ensure_session()

    async def close_call(self, call_id: str) -> None:
        return

    async def validate_connectivity(self, options: Dict[str, Any]) -> Dict[str, Any]:
        merged = self._compose_options(options or {})
        # Base validator looks for base_url/ws_url in options.
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

        await self._ensure_session()
        merged = self._compose_options(options)

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

        try:
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
        except aiohttp.ClientError as exc:
            logger.error(
                "Cartesia TTS HTTP error",
                call_id=call_id,
                request_id=request_id,
                error=str(exc),
            )
            raise

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
        }

    def _chunk_audio(self, audio: bytes, chunk_ms: int = 20) -> list[bytes]:
        # μ-law: 1 byte/sample @ 8 kHz
        chunk_size = max(1, int(8000 * (chunk_ms / 1000.0)))
        return [audio[i : i + chunk_size] for i in range(0, len(audio), chunk_size) if audio[i : i + chunk_size]]
