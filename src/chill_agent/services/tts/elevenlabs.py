"""ElevenLabs TTS adapter (fallback)."""

from __future__ import annotations

from pathlib import Path

import requests
import structlog

from chill_agent.services.tts.base import AudioResult
from chill_agent.utils.retry import with_retry

logger = structlog.get_logger()

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def _get_mp3_duration(path: Path) -> float:
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_mp3(str(path))
        return len(audio) / 1000.0
    except Exception:
        return path.stat().st_size / 16000.0


class ElevenLabsTTS:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    @with_retry(attempts=3, backoff=(2.0, 8.0, 30.0))
    def synthesize(self, text: str, voice_id: str, output_path: Path) -> AudioResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "tts_elevenlabs_request",
            voice_id=voice_id,
            chars=len(text),
        )

        url = ELEVENLABS_API_URL.format(voice_id=voice_id)
        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.8,
                "style": 0.0,
            },
        }

        response = requests.post(url, json=payload, headers=headers, timeout=120, stream=True)
        response.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        duration = _get_mp3_duration(output_path)
        logger.info("tts_elevenlabs_done", chars=len(text), duration_seconds=duration)

        return AudioResult(
            path=output_path,
            duration_seconds=duration,
            sample_rate=44100,
            chars_synthesized=len(text),
        )
