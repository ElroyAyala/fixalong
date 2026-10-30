"""Felix's labels: the repair parts in a headset photo, with a point on each.

This is its own Muse Spark call, run alongside the conversation, so naming the
parts never slows Felix's answer. When Felix talks about a part that has no
label yet, a second call finds that one part. Points use Meta's 0-1000 grid:
x runs left to right and y runs top to bottom.
"""

import base64
import json
import re

from openai import AsyncOpenAI

from . import config

PROMPT = (
    "This photo is from a headset camera while someone repairs something at home. "
    "Name the parts that matter for the repair that you can clearly see (at most 6), "
    "using the short everyday names a repair guide would say out loud, like 'flapper', "
    "'fill valve' or 'chain'. Include small parts like a chain when they're visible. "
    "Skip whole fixtures and surroundings, like the tank, the bowl or the wall. For "
    "each part, give one point on the part itself, on a 0-1000 grid where x runs left "
    "to right and y runs top to bottom. If a part already has one of these names, use "
    "it: {known}. If the photo doesn't show a repair, reply []. "
    'Reply with only JSON: [{{"name": "...", "point": [x, y]}}]')

NAMED_PROMPT = (
    "A repair guide just said this to the person wearing the headset that took this "
    'photo: "{reply}" If that asks them to look at, check or touch a specific part '
    "you can see in the photo, give the part's short name and one point on it, on a "
    "0-1000 grid where x runs left to right and y runs top to bottom. If the part "
    "already has one of these names, use it: {known}. If no part in the photo is "
    'meant, reply []. Reply with only JSON: [{{"name": "...", "point": [x, y]}}]')

MAX_PARTS = 6

# Labels Muse Spark sometimes adds anyway that aren't worth pointing at.
SKIP = {"tank", "toilet", "toilet tank", "bowl", "toilet bowl", "wall", "floor", "water"}

_client = AsyncOpenAI(base_url=config.META_BASE_URL, api_key=config.MODEL_API_KEY)


async def find(jpeg: bytes, known: list[str]) -> list[dict]:
    """The repair parts in a photo, as [{"name": str, "x": int, "y": int}].

    known is the names already labeled, so the same part keeps its name.
    """
    return parse(await _ask(PROMPT.format(known=", ".join(known) or "none yet"), jpeg))


async def find_named(jpeg: bytes, reply: str, known: list[str]) -> list[dict]:
    """The part Felix's reply is about, when it has no label yet (like a thin chain)."""
    prompt = NAMED_PROMPT.format(reply=reply, known=", ".join(known) or "none yet")
    return parse(await _ask(prompt, jpeg))[:2]


async def _ask(prompt: str, jpeg: bytes) -> str:
    image = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
    response = await _client.responses.create(
        model=config.META_MODEL,
        reasoning={"effort": "minimal"},  # as accurate as "low" in testing, and faster
        input=[{"role": "user", "content": [{"type": "input_text", "text": prompt},
                                            {"type": "input_image", "image_url": image}]}],
    )
    return response.output_text


def parse(text: str) -> list[dict]:
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        return []
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    found = []
    for item in items if isinstance(items, list) else []:
        try:
            name = str(item["name"]).strip().lower()
            x, y = (round(float(v)) for v in item["point"])
        except (KeyError, TypeError, ValueError):
            continue
        if name and name not in SKIP and 0 <= x <= 1000 and 0 <= y <= 1000 \
                and name not in (p["name"] for p in found):
            found.append({"name": name, "x": x, "y": y})
    return found[:MAX_PARTS]


def mentioned(reply: str, names: list[str]) -> list[str]:
    """The labeled parts Felix's reply talks about, in the order he says them.

    A full name counts ("fill valve"), and so does its last word ("chain" for
    "flush chain") when no other label ends with it.
    """
    text = reply.lower()
    spots = {}
    for name in names:
        hit = re.search(rf"\b{re.escape(name)}\b", text)
        last = name.split()[-1]
        if hit is None and sum(n.split()[-1] == last for n in names) == 1:
            hit = re.search(rf"\b{re.escape(last)}s?\b", text)
        if hit is not None:
            spots[name] = hit.start()
    return sorted(spots, key=spots.get)
