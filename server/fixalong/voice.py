"""Felix's voice: ElevenLabs text-to-speech, returned as 16-bit mono PCM.

His fillers, a quick "mm-hm" or "let me look" while he thinks, are clips made
ahead of time in the same voice (fillers/), so they play at once.
"""

import random
import wave
from pathlib import Path

import httpx

from . import config

_client = httpx.AsyncClient(base_url="https://api.elevenlabs.io/v1", timeout=30)

FILLERS_DIR = Path(__file__).with_name("fillers")


async def speak(text: str) -> bytes:
    response = await _client.post(
        f"/text-to-speech/{config.FELIX_VOICE_ID}",
        params={"output_format": f"pcm_{config.VOICE_SAMPLE_RATE}"},
        headers={"xi-api-key": config.ELEVENLABS_API_KEY},
        json={"text": text, "model_id": config.ELEVENLABS_MODEL,
              "voice_settings": config.VOICE_SETTINGS},
    )
    response.raise_for_status()
    return response.content


def _load(kind: str) -> list[bytes]:
    clips = []
    for path in sorted((FILLERS_DIR / kind).glob("*.wav")):
        with wave.open(str(path)) as clip:
            if (clip.getframerate(), clip.getnchannels(), clip.getsampwidth()) == \
                    (config.VOICE_SAMPLE_RATE, 1, 2):
                clips.append(clip.readframes(clip.getnframes()))
    return clips


# look: he's about to check your work ("Let me look"); plain: anything else ("Mm-hm").
_fillers = {kind: _load(kind) for kind in ("plain", "look")}
_last_filler = b""


def filler(kind: str) -> bytes:
    """A filler clip of that kind, never the one he just used. Empty if there are none."""
    global _last_filler
    clips = _fillers.get(kind) or []
    choices = [c for c in clips if c is not _last_filler] or clips
    _last_filler = random.choice(choices) if choices else b""
    return _last_filler
