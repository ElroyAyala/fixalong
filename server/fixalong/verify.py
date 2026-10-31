"""The verifier: its own Muse Spark call that decides whether a step passed.

Felix gives the instruction, but he never grades it. The verifier sees the
steps left, each with its pass condition (written before the user acted), what
the user just said, and the photo from when the step started next to the one
from now. It answers with the steps that passed, what decided it, and one
correction when it's "not yet". The user's word is evidence too: they can hear
the water stop, and a headset looking down can't see everything.
"""

import base64
import json
import re

from openai import AsyncOpenAI

from . import config

# For one safety check, which is checked on every photo until it passes.
PROMPT = (
    "You check one safety step of a home repair from headset photos, strictly. The person was "
    'asked to: "{instruction}". It passes only if: {condition}. Their guide last said: '
    '"{asked}" They just said: "{said}". {photos} Judge the result, not the method: if they '
    "got there another way, it passes. Judge only what the photo and their words show. "
    "{unseen} Reply with only JSON: "
    '{{"passed": true or false, "claimed": <true if their words say this specific thing is done '
    "or fine (like 'the lid's good'), or answer yes to the guide asking about it; false for a "
    'question, or words about something else>,"contradicts": <true only if the photo shows '
    "this thing and plainly shows it isn't done, like the lid still on the tank; a photo of "
    "something else, or too dark to tell, never contradicts>, "
    '"seen": "<what you see that decides it, one sentence>", '
    '"correction": "<if not passed: the one thing to do next, in plain everyday words, '
    "describing the part by its look and place. They wear a headset, so say 'look at' or "
    "'show me', never 'photo' or 'camera'>\"}}")

# For the repair steps: every step left, so one report can pass several. The verifier answers
# two plain questions per step and the server decides, since asked for a verdict, it sometimes
# failed a step for what the photo couldn't show, even with the job's proof reported.
STEPS_PROMPT = (
    "You check a home repair's progress from a headset photo and what the person says. The "
    "steps left, in order, each with what shows it worked:\n{steps}\nThey're on {current}.{asked} "
    'They just said: "{said}".{sound} {photos}\n'
    "Answer two plain questions about each step.\n"
    "Reported: did they say they did it or that its result happened (a yes to their guide "
    "asking counts), or does the photo show it done? Their words count: they can hear, feel "
    "and see from angles the photo can't. Judge "
    "results, not methods: getting there another way counts. A later step's result counts for "
    "every step before it, so reporting the last step's result reports them all.\n"
    "Contradicted: does the photo plainly show it is not done, like a part visibly off? "
    "Something out of view, too dark, or that a view from above can't judge, like how much "
    "slack a hanging chain has, is never a contradiction.{tries}\n"
    'Reply with only JSON: {{"reported": ["<step ids>"], "contradicted": ["<step ids>"], '
    '"seen": "<what decides it, from the photo or their words, one sentence>", '
    '"correction": "<if {current} is contradicted: the one thing to fix. If it just isn\'t '
    "reported: a question for them to confirm it, like 'Did you flush it yet? I didn't hear "
    "it.' In plain everyday words; name parts as their headset labels them ({labels}), or by "
    "look and place. Never ask them to show you something awkward to see. They wear a "
    "headset, so never say 'photo' or 'camera'>\"}}")
TRIES = (" They've already heard 'not yet' {misses} times on this step, so give them the "
         "benefit of the doubt.")

BEFORE_AND_NOW = "The first photo is from when the step started; the second is from now."
NOW_ONLY = "The photo is from now."
# What happens when the photo can't show it (too dark, wrong angle, out of view).
STRICT = "If the photo can't show it, it doesn't pass."
WORD_COUNTS = ("If the photo can't show it, their clear statement about this specific thing "
               "counts as a pass (a bare 'done' about something else doesn't); if the photo "
               "shows it isn't done, it doesn't pass.")

# Words that mean "check my work". The verifier only runs on these, so a quick
# "okay" while they're still working doesn't get a premature "not yet".
DONE = re.compile(
    r"\b(done|did (it|that)|i('ve| have) (done|finished)|finished|that'?s it|all set|"
    r"how'?s (that|this|it look)|how about (now|that|this)|(is|does) (that|this|it) look|"
    r"(is )?(that|this) better|can you see (it|that|now)|check (it|that|this|now)|ready|"
    r"got it (on|off|in|out|done)|"
    r"it'?s (on|off|in|out|seated|clipped|fixed|stopped|quiet|working|done|tight|loose)|"
    r"(no|not) (more )?(hiss|hissing|running|sound|noise|water|leak|trickle)|no longer|"
    r"(don'?t|do not|can'?t|cannot) hear|(sound|noise|hiss|hissing|leak|running)( is| has)? gone|"
    r"already (did|done|adjusted|fixed|moved|changed|loosened|tightened|got)|"
    r"(i|we) fix(ed)?|fix(ed)? (it|the)|(it|that) worked|(got|has|some|little|bit of) (some )?(slack|play)|"
    r"stopped|quiet now|silent|works now|working now|fixed|we got it|there (we go|you go|it is)|"
    r"here it is)\b",
    re.IGNORECASE)

_client = AsyncOpenAI(base_url=config.META_BASE_URL, api_key=config.MODEL_API_KEY)


# A yes, for answers to Felix asking "Did you flush it?"
YES = re.compile(r"^\W*(yes|yeah|yep|yup|ya|correct|uh huh|i did|we did|sure did|did it|"
                 r"it is|it does|it did|i have|we have)\b", re.IGNORECASE)


# Asking to check the current thing off themselves, as they can by pinching it on the checklist.
CHECK_OFF = re.compile(r"\b(check (it|that|this) off|mark (it|that|this) (as )?(done|off|complete)|"
                       r"skip (it|that|this)( one| step)?|move on)\b", re.IGNORECASE)


# Closing a caution sign: "got it" and the like once they've looked at it, or any words
# about the sign itself.
ACKNOWLEDGE = re.compile(r"\b(got it|gotcha|understood|noted|will do|copy that|roger|"
                         r"i see (it|that)|okay|ok)\b", re.IGNORECASE)
ABOUT_SIGN = re.compile(r"\b(sign|caution|warning)\b", re.IGNORECASE)


def acknowledges(text: str, looked: bool) -> bool:
    """Whether they acknowledged a caution sign; looked is whether they've looked at it."""
    return bool(ABOUT_SIGN.search(text) or looked and ACKNOWLEDGE.search(text))


def says_done(text: str) -> bool:
    return bool(DONE.search(text))


def affirms(text: str) -> bool:
    return bool(YES.search(text))


def checks_off(text: str) -> bool:
    return bool(CHECK_OFF.search(text))


async def check(instruction: str, condition: str, said: str, now: bytes,
                before: bytes | None = None, word_counts: bool = False, asked: str = "") -> dict:
    """{"passed": bool, "claimed": bool, "contradicts": bool, "seen": str, "correction": str}

    For one safety check. claimed is whether they said it's done, so a question
    like "this lid?" doesn't get a "not yet"; contradicts is whether the photo
    plainly shows it isn't. word_counts lets the person's clear word stand in
    when the photo can't show it, for low-risk checks only. asked is what Felix
    last said, so a "yes" to his question counts.
    """
    prompt = PROMPT.format(instruction=instruction, condition=condition, said=said,
                           asked=asked, photos=BEFORE_AND_NOW if before else NOW_ONLY,
                           unseen=WORD_COUNTS if word_counts else STRICT)
    verdict = parse(await _ask(prompt, [before, now] if before else [now]))
    verdict["passed"] = verdict["passed"] is True
    verdict["claimed"] = verdict.pop("claimed") is True
    verdict["contradicts"] = verdict.pop("contradicts") is True
    return verdict


async def check_steps(steps: list[dict], said: str, now: bytes, before: bytes | None = None,
                      misses: int = 0, sound: str = "", asked: str = "",
                      labels: list[str] = ()) -> dict:
    """{"passed": [step ids, in order], "contradicted": [step ids], "seen": str,
    "correction": str}

    steps are the ones not passed yet, the current one first. misses is how many
    times the current one has already been "not yet". sound is what the mic
    picked up besides speech, like a refill that ran and stopped (see sounds.py).
    asked is what Felix last said, so "yes" to "Did you flush it?" counts.
    labels are the part names in their headset, for the correction to use.

    A step passes when it, or a later step, is reported, unless the photo plainly
    shows it isn't done: then the steps stop passing there.
    """
    listed = "\n".join(f"- {s['id']}: {s['instruction']} Worked if: {s['pass_condition']}"
                       for s in steps)
    prompt = STEPS_PROMPT.format(steps=listed, current=steps[0]["id"], said=said,
                                 asked=f' Their guide last said: "{asked}"' if asked else "",
                                 sound=f" {sound}" if sound else "",
                                 photos=BEFORE_AND_NOW if before else NOW_ONLY,
                                 tries=TRIES.format(misses=misses) if misses else "",
                                 labels=", ".join(labels) or "none yet")
    verdict = parse(await _ask(prompt, [before, now] if before else [now]))
    ids = [s["id"] for s in steps]
    reported = {i for i in _ids(verdict.get("reported")) if i in ids}
    contradicted = {i for i in _ids(verdict.get("contradicted")) if i in ids}
    furthest = max((ids.index(i) for i in reported), default=-1)
    passed = []
    for i in ids[:furthest + 1]:
        if i in contradicted:
            break
        passed.append(i)
    return {"passed": passed, "contradicted": sorted(contradicted, key=ids.index),
            "seen": verdict["seen"], "correction": verdict["correction"]}


def _ids(value) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


async def _ask(prompt: str, photos: list[bytes]) -> str:
    content = [{"type": "input_text", "text": prompt}]
    for jpeg in photos:
        content.append({"type": "input_image",
                        "image_url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()})
    response = await _client.responses.create(
        model=config.META_MODEL,
        reasoning={"effort": config.VERIFY_EFFORT},
        input=[{"role": "user", "content": content}],
    )
    return response.output_text


def parse(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    try:
        verdict = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        verdict = {}
    return {"passed": verdict.get("passed"), "claimed": verdict.get("claimed"),
            "contradicts": verdict.get("contradicts"), "reported": verdict.get("reported"),
            "contradicted": verdict.get("contradicted"),
            "seen": str(verdict.get("seen") or "The verifier's answer couldn't be read."),
            "correction": str(verdict.get("correction") or "")}
