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
    "This photo is from a headset camera while someone {work} at home. "
    "Name the parts that matter for {task} that you can clearly see (at most 6), "
    "using the short everyday names a repair guide would say out loud, like 'flapper', "
    "'fill valve' or 'chain'. Include small parts like a chain when they're visible. "
    "Skip whole fixtures and surroundings, like the tank, the bowl or the wall. For "
    "each part, give one point on the part itself, on a 0-1000 grid where x runs left "
    "to right and y runs top to bottom. If a part already has one of these names, use "
    "it: {known}.{names} If the photo doesn't show {shows}, reply []. "
    'Reply with only JSON: [{{"name": "...", "point": [x, y]}}]')

NAMED_PROMPT = (
    "A repair guide just said this to the person wearing the headset that took this "
    'photo: "{reply}" If that asks them to look at, check or touch a specific part '
    "you can see in the photo, give the part's short name and one point on it, on a "
    "0-1000 grid where x runs left to right and y runs top to bottom. Be as exact as "
    "the guide's words: if they're about a spot on a part, like the flapper's ears, name "
    "that spot ('flapper ear') and point at it, one point for each you can see, not the "
    "whole part. If the same part already has one of these names, use it: {known}. If no "
    'part in the photo is meant, reply []. Reply with only JSON: [{{"name": "...", '
    '"point": [x, y]}}]')

MAX_PARTS = 6

# Asking where something is, like "where's the hex key?" or "I can't find the lid".
WHERE = re.compile(r"\b(where('s| is| are| did| was| were|'d)|can'?t find|cannot find|lost|"
                   r"misplaced)\b", re.IGNORECASE)

# Labels Muse Spark sometimes adds anyway that aren't worth pointing at.
SKIP = {"tank", "toilet", "toilet tank", "bowl", "toilet bowl", "wall", "floor", "water"}

_client = AsyncOpenAI(base_url=config.META_BASE_URL, api_key=config.MODEL_API_KEY)


async def find(jpeg: bytes, known: list[str], work: str = "", names: list[str] = ()) -> list[dict]:
    """The repair parts in a photo, as [{"name": str, "x": int, "y": int}].

    known is the names already labeled, so the same part keeps its name. work is what
    they're doing, for a job that isn't a repair, like building furniture, and names
    are the names that job uses for its parts. With names, tools set down nearby get
    labels too, so they can be found later: asking for that in the toilet's prompt cost
    it the overflow tube in testing, so that prompt stays as it was.
    """
    prompt = PROMPT.format(
        work=work or "repairs something", task="the work" if work else "the repair",
        shows="that work" if work else "a repair",
        known=", ".join(known) or "none yet",
        names=f" This job's parts are usually called: {', '.join(names)}. Include tools and "
              "loose hardware set down nearby too, like the hex key or a hardware bag, so they "
              "can find them later." if names else "")
    return parse(await ask(prompt, jpeg))


async def find_named(jpeg: bytes, reply: str, known: list[str]) -> list[dict]:
    """The part Felix's reply is about, when it has no label yet (like a thin chain)."""
    prompt = NAMED_PROMPT.format(reply=reply, known=", ".join(known) or "none yet")
    return parse(await ask(prompt, jpeg))[:2]


async def ask(prompt: str, jpeg: bytes) -> str:
    """One quick Muse Spark question about a photo; the reply is its text."""
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


def match(part: str, names: list[str]) -> list[str]:
    """The label for a part the job names.

    The last word names the part, so "flapper chain" finds the "chain" label,
    not the "flapper" one.
    """
    part = part.strip().lower()
    if not part:
        return []
    last = part.split()[-1]
    tests = [lambda n: n == part,
             lambda n: n.split()[-1] == last,
             lambda n: re.search(rf"\b{re.escape(n)}\b", part) or re.search(rf"\b{re.escape(part)}\b", n)]
    for test in tests:
        for name in names:
            if test(name):
                return [name]
    return []


def asked_for(said: str, names: list[str]) -> list[str]:
    """The labeled things they asked where to find, like the hex key in "where's the hex
    key?", so the headset points at them even far away."""
    return mentioned(said, names) if WHERE.search(said) else []


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
