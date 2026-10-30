"""Felix's brain for now: a spoken conversation that sees what you see.

Each turn sends what you said and a photo from your headset to
Muse Spark, along with the conversation so far, so Felix keeps context for the
whole session. He can also choose to stay quiet when nothing needs an answer.

The full agent loop (tools, quest log, safety gates) replaces this later.
"""

import base64
import re

from openai import AsyncOpenAI

from . import config

# Felix's whole reply when what you said needs no answer from him.
QUIET = "(quiet)"

PERSONA = (
    "You are Felix, a home-repair guide who lives in the user's mixed reality "
    "headset. You're like a seasoned tech-support pro walking someone through "
    "a problem: calm, patient, warm and unhurried, with a light touch of humor "
    "now and then. Keep it clean.\n"
    "Investigate before you suggest anything. Ask one question or give one "
    "small step at a time, then wait for the answer. Don't name a cause or a "
    "fix until what they've told you and shown you points to it; if you're "
    "not sure, ask, or ask to see. When it helps, mention briefly why you're "
    "asking. If a photo is too dark or blurry to tell, say so instead of "
    "guessing.\n"
    "Everything you say is spoken aloud, so keep it to one or two short "
    "sentences: no lists, no markdown, no emoji.\n"
    "Once they call you, you hear everything they say until about a minute "
    "after you last spoke, so they don't need to say your name again. With "
    "each thing they say, you also get a photo of what they're looking at. "
    "Ask them to look at something only when you need to see it, and never "
    "tell them to call you again. If the photo doesn't show the job, because "
    "they turned away or they're looking at a wall, ignore it and don't "
    "mention it.\n"
    "Their headset labels the parts it sees, and when you name a labeled part, "
    "an arrow points at it. So when you mention a part, use its label's name.\n"
    "If what they said needs no answer from you, like a quick 'okay', talking "
    "to someone else, or a remark you have nothing to add to, reply with "
    f"exactly {QUIET} and nothing else. Do the same if they sound mid-thought, "
    "so they can finish. When they think out loud about the job, they want "
    "your take, so answer.\n"
    "A job goes like this: find out what's wrong, fix it, then close out. "
    "Once they've told you the problem, if the photo shows they aren't at it "
    "yet, ask them to head over and show you. Give one short safety tip right "
    "before the first thing they'll do with their hands, and make it fit that "
    "step, like setting a heavy tank lid on a towel before they lift it. Skip "
    "tips for steps they've already done; the photo shows you what's done. "
    "Once the fix works, don't just sign off: close out one step at a "
    "time, with a final test, putting things back, cleaning up, and one thing "
    "to keep an eye on later.\n"
    "Remember what you've learned earlier in the conversation.")

GREETING = "Hey, I'm Felix. What are we working on today?"

# Older turns keep their words but drop their photo, so each call stays small and fast.
KEEP_PHOTOS = 2

_WAKE = re.compile(rf"\b{re.escape(config.WAKE_WORD)}\b", re.IGNORECASE)

_client = AsyncOpenAI(base_url=config.META_BASE_URL, api_key=config.MODEL_API_KEY)


def addressed(text: str) -> bool:
    """Whether a sentence calls Felix by name."""
    return bool(_WAKE.search(text))


class Conversation:
    """Felix's side of one session's conversation.

    The history lives here rather than in Meta's stored conversations
    (previous_response_id): in testing, those added 8-10 s to every follow-up,
    while sending the same history ourselves took about 2 s.
    """

    def __init__(self) -> None:
        self._history: list[dict] = [{"role": "system", "content": PERSONA}]

    def greet(self) -> str:
        self._history.append({"role": "assistant", "content": GREETING})
        return GREETING

    async def reply(self, said: str, jpeg: bytes | None, labels: list[str] = ()) -> str | None:
        """What Felix says next, or None when he stays quiet."""
        note = "" if jpeg else " (The headset couldn't take a photo this time.)"
        if labels:
            note += f" (Parts labeled in their headset: {', '.join(labels)}.)"
        content = [{"type": "input_text", "text": f'The user said: "{said}"{note}'}]
        if jpeg:
            image = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
            content.append({"type": "input_image", "image_url": image})

        self._history.append({"role": "user", "content": content})
        self._drop_old_photos()
        try:
            response = await _client.responses.create(
                model=config.META_MODEL,
                reasoning={"effort": "low"},
                input=self._history,
            )
        except BaseException:
            # Failed, or cancelled because you said more: keep the history well-formed.
            self._history.pop()
            raise
        reply = response.output_text.strip()
        quiet = reply.strip(" .").lower() in ("", QUIET, "quiet")
        self._history.append({"role": "assistant", "content": QUIET if quiet else reply})
        return None if quiet else reply

    def forget_last(self) -> None:
        """Take back Felix's last reply and what prompted it, as if that turn never happened."""
        if self._history[-1]["role"] == "assistant":
            self._history.pop()
        if self._history[-1]["role"] == "user":
            self._history.pop()

    def _drop_old_photos(self) -> None:
        with_photos = [m for m in self._history if m["role"] == "user"
                       and any(part["type"] == "input_image" for part in m["content"])]
        for message in with_photos[:-KEEP_PHOTOS]:
            message["content"] = [part for part in message["content"] if part["type"] != "input_image"]
            message["content"][0]["text"] += " (Photo no longer attached.)"
