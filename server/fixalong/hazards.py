"""Felix's cautions: hazards to the person or their headset in a headset photo.

This is its own Muse Spark call, run alongside the part labels, so it never
slows Felix's answer. The job type says what to watch for. Each hazard is
flagged once a job, unless it plainly gets worse, so a sign never nags. Points
use Meta's 0-1000 grid, like the labels.
"""

import json
import re

from . import parts

PROMPT = (
    "This photo is from a mixed reality headset worn by someone doing a {job} job at home. "
    "Look for hazards to them or to the headset they're wearing, like {examples}. Only what "
    "the photo plainly shows: most photos have none. Already flagged, so leave these out "
    "unless they've plainly gotten worse: {known}. For each new one, give a short name, one "
    "calm line for a caution sign, at most 8 words, like 'Water nearby. Keep the headset "
    "clear.', and one point on the hazard, on a 0-1000 grid where x runs left to right and y "
    'runs top to bottom. Reply with only JSON: [{{"name": "...", "line": "...", '
    '"point": [x, y]}}]')

MAX_LINE = 60  # one line on a small sign
MAX_FOUND = 2


async def find(jpeg: bytes, job: str, examples: list[str], known: list[str]) -> list[dict]:
    """New hazards in a photo, as [{"name": str, "line": str, "x": int, "y": int}].

    known is the hazards already flagged this job, so each one shows once.
    """
    prompt = PROMPT.format(job=job, examples="; ".join(examples),
                           known="; ".join(known) or "none yet")
    return parse(await parts.ask(prompt, jpeg))


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
            line = str(item["line"]).strip()
            x, y = (round(float(v)) for v in item["point"])
        except (KeyError, TypeError, ValueError):
            continue
        if name and line and len(line) <= MAX_LINE and 0 <= x <= 1000 and 0 <= y <= 1000 \
                and name not in (h["name"] for h in found):
            found.append({"name": name, "line": line, "x": x, "y": y})
    return found[:MAX_FOUND]
