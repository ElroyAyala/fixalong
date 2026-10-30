"""Felix's brain for the thin headset loop: a greeting, and describing a photo.

The full agent loop (tools, quest log, safety gates) replaces this later.
"""

import base64

from openai import AsyncOpenAI

from . import config

PERSONA = (
    "You are Felix, a friendly, practical home-repair guide who lives in the "
    "user's mixed reality headset. Everything you say is spoken aloud, so "
    "answer in one or two short sentences: no lists, no markdown, no emoji. "
    "Sound like a handy friend, warm and plain-spoken.")

GREETING = "Hey, I'm Felix. What are we working on today?"

PHOTO_PROMPT = (
    "This photo is from the user's headset camera. Tell them what you see. "
    "If it's something you could help repair, name what kind it is and one "
    "thing to check or do first.")

_client = AsyncOpenAI(base_url=config.META_BASE_URL, api_key=config.MODEL_API_KEY)


async def describe_photo(jpeg: bytes) -> str:
    image = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
    response = await _client.responses.create(
        model=config.META_MODEL,
        reasoning={"effort": "low"},
        input=[
            {"role": "system", "content": PERSONA},
            {"role": "user", "content": [
                {"type": "input_text", "text": PHOTO_PROMPT},
                {"type": "input_image", "image_url": image},
            ]},
        ],
    )
    return response.output_text.strip()
