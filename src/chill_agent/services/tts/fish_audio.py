"""Fish Audio TTS adapter."""

from __future__ import annotations

import struct
import wave
from pathlib import Path

import requests
import structlog

from chill_agent.services.tts.base import AudioResult
from chill_agent.utils.retry import with_retry

logger = structlog.get_logger()

FISH_AUDIO_API_URL = "https://api.fish.audio/v1/tts"


def _get_mp3_duration(path: Path) -> float:
    """Estimate MP3 duration by file size (rough). Replaced by pydub if available."""
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_mp3(str(path))
        return len(audio) / 1000.0
    except Exception:
        # Fallback: assume ~128kbps → bytes/16000 ≈ seconds
        size = path.stat().st_size
        return size / 16000.0


class FishAudioTTS:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    @with_retry(attempts=3, backoff=(2.0, 8.0, 30.0))
    def synthesize(self, text: str, voice_id: str, output_path: Path) -> AudioResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "tts_fish_audio_request",
            voice_id=voice_id,
            chars=len(text),
            output=str(output_path),
        )

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "text": text,
            "reference_id": voice_id,
            "format": "mp3",
            "mp3_bitrate": 192,
        }

        response = requests.post(
            FISH_AUDIO_API_URL,
            json=payload,
            headers=headers,
            timeout=120,
            stream=True,
        )
        response.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        duration = _get_mp3_duration(output_path)
        logger.info(
            "tts_fish_audio_done",
            chars=len(text),
            duration_seconds=duration,
            output=str(output_path),
        )

        return AudioResult(
            path=output_path,
            duration_seconds=duration,
            sample_rate=44100,
            chars_synthesized=len(text),
        )
