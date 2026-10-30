"""Felix's voice: ElevenLabs text-to-speech, returned as 16-bit mono PCM."""

import httpx

from . import config

_client = httpx.AsyncClient(base_url="https://api.elevenlabs.io/v1", timeout=30)


async def speak(text: str) -> bytes:
    response = await _client.post(
        f"/text-to-speech/{config.FELIX_VOICE_ID}",
        params={"output_format": f"pcm_{config.VOICE_SAMPLE_RATE}"},
        headers={"xi-api-key": config.ELEVENLABS_API_KEY},
        json={"text": text, "model_id": config.ELEVENLABS_MODEL},
    )
    response.raise_for_status()
    return response.content
