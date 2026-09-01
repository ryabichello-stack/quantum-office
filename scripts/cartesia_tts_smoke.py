#!/usr/bin/env python3
"""Generate Russian Cartesia Sonic samples (WAV 8 kHz mono) for listening tests.

Usage:
  export CARTESIA_API_KEY=...
  python3 scripts/cartesia_tts_smoke.py
  python3 scripts/cartesia_tts_smoke.py --list-voices
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = os.getenv("CARTESIA_API_BASE", "https://api.cartesia.ai").rstrip("/")
API_VERSION = os.getenv("CARTESIA_API_VERSION", "2026-08-14")
DEFAULT_MODEL = os.getenv("CARTESIA_MODEL_ID", "sonic-3")
DEFAULT_VOICE = os.getenv(
    "CARTESIA_VOICE_ID", "f786b574-daa5-4673-aa0c-cbe3e8534c02"
)
DEFAULT_LANG = os.getenv("CARTESIA_LANGUAGE", "ru")

SAMPLES = [
    (
        "greeting",
        "Здравствуйте! Это Quantum Labs. Мы помогаем бизнесу с выплатами "
        "на карты и по СБП и со сложными платёжными сценариями.",
    ),
    (
        "qualify",
        "Подскажите, чем занимается ваша организация и какие выплаты "
        "вы делаете физлицам — зарплата, самозанятые или иное?",
    ),
    (
        "cta",
        "Могу предложить короткий созвон с экспертом на пятнадцать минут. "
        "Какой день и время вам удобны?",
    ),
]


def _headers(api_key: str) -> dict[str, str]:
    return {
        "X-API-Key": api_key,
        "Cartesia-Version": API_VERSION,
        "Content-Type": "application/json",
    }


def _request(method: str, path: str, api_key: str, body: dict | None = None) -> bytes:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        method=method,
        headers=_headers(api_key),
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"Cartesia HTTP {exc.code}: {err}") from exc


def list_voices(api_key: str, language: str | None = None) -> list[dict]:
    raw = _request("GET", "/voices", api_key)
    payload = json.loads(raw.decode("utf-8") or "{}")
    voices = payload.get("data") or payload.get("voices") or payload
    if not isinstance(voices, list):
        return []
    if language:
        lang = language.lower()
        filtered = []
        for v in voices:
            langs = v.get("language") or v.get("languages") or []
            if isinstance(langs, str):
                langs = [langs]
            if any(str(x).lower().startswith(lang) for x in langs) or lang in str(
                v.get("name", "")
            ).lower():
                filtered.append(v)
        return filtered or voices[:20]
    return voices


def synthesize(
    api_key: str,
    text: str,
    *,
    voice_id: str,
    model_id: str,
    language: str,
    sample_rate: int = 16000,
) -> bytes:
    body = {
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
    return _request("POST", "/tts/bytes", api_key, body)


def pcm16_downsample_to_8k(pcm: bytes, source_rate: int) -> bytes:
    if source_rate == 8000:
        return pcm
    if source_rate % 8000 != 0:
        raise ValueError(f"unsupported source_rate={source_rate}")
    factor = source_rate // 8000
    samples = memoryview(pcm).cast("h")
    out = bytearray()
    for i in range(0, len(samples), factor):
        out += struct.pack("<h", samples[i])
    return bytes(out)


def write_wav(path: Path, pcm16le: bytes, sample_rate: int = 8000) -> None:
    n = len(pcm16le)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + n,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sample_rate,
        sample_rate * 2,
        2,
        16,
        b"data",
        n,
    )
    path.write_bytes(header + pcm16le)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-voices", action="store_true")
    parser.add_argument("--voice-id", default=DEFAULT_VOICE)
    parser.add_argument("--model-id", default=DEFAULT_MODEL)
    parser.add_argument("--language", default=DEFAULT_LANG)
    parser.add_argument(
        "--out-dir",
        default=str(Path("scripts/ava-cartesia-pilot/samples")),
    )
    args = parser.parse_args()

    api_key = (os.getenv("CARTESIA_API_KEY") or "").strip()
    if not api_key:
        print("CARTESIA_API_KEY is not set", file=sys.stderr)
        return 2

    if args.list_voices:
        voices = list_voices(api_key, language=args.language)
        for v in voices[:40]:
            vid = v.get("id") or v.get("voice_id")
            name = v.get("name") or ""
            langs = v.get("language") or v.get("languages") or ""
            print(f"{vid}\t{name}\t{langs}")
        return 0

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for slug, text in SAMPLES:
        pcm16 = synthesize(
            api_key,
            text,
            voice_id=args.voice_id,
            model_id=args.model_id,
            language=args.language,
            sample_rate=16000,
        )
        pcm8 = pcm16_downsample_to_8k(pcm16, 16000)
        path = out_dir / f"cartesia_{slug}_8k.wav"
        write_wav(path, pcm8, 8000)
        print(f"wrote {path} ({len(pcm8)} bytes pcm)")
    print("done — listen to 8 kHz WAVs (phone-like)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
