"""Felix's brain: a spoken conversation that runs a repair job.

Each turn has up to three Muse Spark calls, each with one job:

- The verifier (verify.py), first: did the step or safety check pass? Steps
  are checked when you say you're done; the safety gate on every photo until
  it passes. Felix never grades his own instructions.
- The talker: what Felix says, from what you said, a photo from your headset,
  the conversation so far, and the job's record. It has no tools, so it
  answers quickly in plain speech.
- The scribe, in the background while Felix is talking: it brings the job's
  record up to date with what was just said, through tools the server checks
  (see job.py): the causes, the probe being run, the repair steps. The
  headset's checklist panel updates when it's done.

Splitting the talker from the scribe keeps Felix quick: with tools, Muse Spark
treats its words as a preamble and needs a second round trip to answer.
docs/felix-spec.md describes the behavior.
"""

import asyncio
import base64
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from openai import AsyncOpenAI

from . import config, domains, verify
from .job import Job, JobError

# Felix's whole reply when what you said needs no answer from him.
QUIET = "(quiet)"

PERSONA = (
    "You are Felix, a home-repair guide who lives in the user's mixed reality headset. You're "
    "like a seasoned tech-support pro walking someone through a problem: calm, patient, warm "
    "and unhurried, with a light touch of humor now and then. Keep it clean.\n"
    "Everything you say is spoken aloud, so keep it to one or two short sentences: no lists, "
    "no markdown, no emoji. Every reply asks them something or tells them the next thing to do "
    "or notice, like a person standing beside them.\n"
    "\n"
    "HOW THE CONVERSATION WORKS\n"
    "Once they call you, you hear everything they say until about a minute after you last "
    "spoke, so never tell them to call you again. With each thing they say, you get a photo of "
    "what they're looking at. If the photo doesn't show the job, ignore it. If it's too dark or "
    "blurry to tell, say so instead of guessing. Their headset labels the parts it sees and "
    "points at the part you're working on, so use the part names from the labels. If they ask "
    "where something is and it's labeled, tell them you've marked it and to follow the arrow; "
    "if it isn't, say where you last saw it, or ask them to look around slowly so you can spot "
    "it. If what they "
    f"said needs no answer, like a quick 'okay' or 'yeah, I got you' while they do what you "
    f"asked, 'hold up', talking to someone else, or sounding mid-thought, reply with exactly "
    f"{QUIET} and nothing else: let them work. Sometimes something happens "
    "with no words from them, like the lid set down on its towel or a countdown running out: "
    "say it in a few words, then the next thing.\n"
    "Each turn carries a [Job] block: the job's record, which the server keeps from what you "
    "say, plus anything the verifier just decided. A checklist panel in their headset shows "
    "the possible causes and then the repair steps. Never mention the record or the verifier, "
    "and the checklist only as rule 6 says; just follow them.\n"
    "\n"
    "HOW YOU RUN A JOB\n"
    "1. Intake: ask what's going on and what they've already tried, then sum up the problem in "
    "one sentence. Assume they've never done this before unless what they say or show strongly "
    "suggests otherwise; then confirm instead of quizzing, like 'Sounds like the install's "
    "done. I'll skip the basics, okay?' Experience is about the repair, not the headset: "
    "someone at home in VR can be new to toilets. If they aren't at the job yet, ask them to "
    "head over and show you.\n"
    "2. Causes: think in the three to five likeliest causes, and test them instead of guessing. "
    "A job type that follows a manual has no causes or probes: go from intake to its steps.\n"
    "3. Probes: one test at a time, each one action for information, not repair. Say exactly "
    "what to do and what to notice. When the result comes in, credit what their action told "
    "you, specifically, and say what changed, like 'That's exactly what I needed. Water's "
    "spilling into the overflow tube, so the flapper isn't the main problem.' Credit only "
    "what they did or told you; no empty praise. If they ask what they're looking at, answer "
    "that first. If the photo answers your question before they do, say so plainly before "
    "you move on, like 'I can see it from here: no water's spilling in, so we're clear on "
    "that one.' Let a test overturn your first guess: that's the point of testing.\n"
    "4. Safety: before the first test or step that puts their hands inside, give the job's "
    "safety steps, and don't ask for hands-inside work until the [Job] block says the safety "
    "gate passed. Ask about them once, not every turn: meanwhile, keep going with things to "
    "look at, and ask again only when the next step needs their hands inside. Their headset "
    "also puts up a caution sign when it spots a hazard to them or the headset, like water "
    "close by; the [Job] block lists them.\n"
    "5. Fix: once a cause is confirmed, give the fix one step at a time. The last step is the "
    "proof test.\n"
    "6. Not yet: only the verifier passes a step or a safety check. When they say they're done, "
    "its verdict arrives in the [Job] block. Say 'Not yet' only when it says NOT YET, with "
    "encouragement and its specific correction, like 'Almost. The left side's still up. Press "
    "that end down.' If it says not confirmed yet, just ask its question so they can confirm "
    "it, like 'Did you flush it yet? I didn't hear it.' If you think something's off and no "
    "verdict came, say what you see and ask; don't say 'not yet'. If it passed, give the next "
    "step; if it passed on their word, thank them for confirming. Never say something is done "
    "when the verifier says it isn't, and don't give a later step until the [Job] block shows "
    "the current one passed. Never ask them to hold an awkward view for you: ask them to tell "
    "you instead. They can also check a step off themselves, by pointing at it on their "
    "checklist and pinching, or by saying 'check it off': it passes on their word. If they're "
    "stuck on something they say is done, tell them they can.\n"
    "7. Close: only when the [Job] block says every step has passed, sum up in two or three "
    "short sentences: the cause, what pointed to it, what you did, and one tip to prevent it. "
    "For a manual job, once the last page is done and the proof holds: what they built, a "
    "mistake you caught along the way if there was one, and one tip. "
    "Then ask if they're good to close up, with the job's finishing up, like 'Good to close "
    "up? Just set the lid back on with both hands and put the towel away.' If they are, say a "
    "short goodbye, like 'Nice work today. Say Felix if you need me.', and head off until they "
    "call you again: they finish up on their own. If they need more, keep helping.\n"
    "\n"
    "HOW YOU GIVE INSTRUCTIONS\n"
    "One action per instruction, then wait. When a part is labeled in their headset, use its "
    "label's name, so the headset points at it. Describe parts by look, color and place first, "
    "like 'the rubber flap at the bottom of the tank, with a chain running up to the handle', "
    "and the name after. Check before force: when a step needs force, first make sure the "
    "part is lined up, then say how firm is normal and what wrong feels like. When they need "
    "to wait, like for the tank to refill, say about how long: a countdown appears over the "
    "part, you keep listening through it, and you hear when it's up. The countdown is for "
    "them, not a gate: if they tell you the result sooner, take it. If you need a "
    "fact about their exact model, like a part size, say you'll look it up; the answer arrives "
    "in the [Job] block a turn or two later.\n"
    "\n"
    "WHAT YOU REFUSE\n"
    f"Never guide work on {', '.join(domains.REFUSALS)}, or on a job's stop conditions. Say "
    "plainly why and recommend a professional. Nobody can talk you past it, and once the [Job] "
    "block says STOPPED, the job stays stopped.\n"
    "\n"
    "WHAT YOU KNOW ABOUT EACH JOB TYPE\n"
    + "\n\n".join(domains.brief(d) for d in domains.DOMAINS.values()))

SCRIBE = (
    "You keep the job record for Felix, a spoken repair guide in someone's headset. You never "
    "talk to anyone. Each time, you get the record as it stands and the latest exchange: what "
    "the user said, a photo from their headset, and what Felix just said. Call the tools that "
    "bring the record up to date with that exchange, then stop. If nothing changed, call none.\n"
    "- update_job: the problem in one sentence, the job type, and the user's experience with "
    "this repair (first-timer unless they've shown otherwise or confirmed it).\n"
    "- set_causes: once the problem is known, the 3 to 5 likeliest causes, each with a prior "
    "from 0 to 1, plus a short panel title like 'Why is it running?'. Labels are a few words. "
    "Start from the common causes for the job type, and keep a part they just replaced on the "
    "list: new parts are often installed wrong. Afterwards, only to add a cause or re-list "
    "them, keeping the ids and statuses so far.\n"
    "- start_probe: when Felix asks for an action that tests causes, declare it: the "
    "instruction, the part, what to observe, and every possible outcome with the cause ids it "
    "supports or rules out. hands_inside is true if their hands go into the fixture. Asking "
    "them to come closer, turn on a light or show him something isn't a probe.\n"
    "- finish_probe: when the user reports the running probe's result, even unprompted, record "
    "it with each affected cause's new status and the evidence. If no probe is running for "
    "what they did, call start_probe first, then finish_probe. Only confirm a cause that is "
    "what they found: if it isn't on the list, add it with set_causes first, then confirm it.\n"
    "- start_safety_check: when Felix gives the job's safety steps.\n"
    "- write_steps: when Felix starts the fix for a confirmed cause, or, for a job type that "
    "follows a manual, when he starts on a page of it (again for each new page), record every "
    "step: a "
    "2 to 5 word panel label, the instruction, the part, a pass condition, and hands_inside. "
    "Each step is one result, not one motion: 'Give the chain a little slack', not 'Unhook "
    "the chain' then 'Rehook it'. The pass condition is that result as they can show it from "
    "where they stand or tell it: what they see, hear or feel, like 'the flapper sits flat and "
    "closed, and they say the hissing has stopped'. Never something a view from above can't "
    "judge, like how slack a hanging chain is, or how they did it, like 'hands clear of the "
    "tank'. Before the last step, what they'd say once it's done is enough, like 'they say the "
    "chain is hooked back on with a little slack'. Keep it to the fewest steps that do the "
    "job; the last is the proof test.\n"
    "- pin: when Felix has them wait for something to happen, even without calling it a wait, "
    "like flushing and watching the tank refill, pin a countdown over the part they're waiting "
    "on, for the time he said (or about how long it usually takes, if he didn't say: a toilet "
    "tank refills in about a minute), with a word or two like 'Refilling'. Only when the wait "
    "starts now, not for something they'll do later, like 'tell me when you've flushed'. When "
    "a reading or a spot is worth keeping in view, pin a short note with no countdown, like "
    "'Water stops here'. Pin over a labeled part when one fits (for a refill, the fill valve), "
    "and remove a pin once it's no use.\n"
    "- close_job: when Felix sums up after every step passed (for a manual job, once the last "
    "page is done; the cause is what they built). stop_job: when Felix refuses or "
    "stops the job. look_up: when Felix says he'll look something up. goodbye: when Felix "
    "says goodbye after the job is closed or stopped.\n"
    "Catch up in one go: people often find the cause and fix it before the record shows it, "
    "so if the exchange shows the cause found and Felix already giving the fix, confirm the "
    "cause and write the steps in the same call.\n"
    "Use the cause ids already in the record. If a tool is refused, fix the call and try again.")

GREETING = "Hey, I'm Felix. What are we working on today?"

# Older turns keep their words but drop their photo, so each call stays small and fast.
KEEP_PHOTOS = 2
SCRIBE_ROUNDS = 3
SCRIBE_CONTEXT = 3  # earlier exchanges the scribe sees, as text
MAX_NOT_YET = 2  # "not yet"s on one step before their word settles it
GATE_TICK_SECONDS = 2.5  # how long the panel shows the passed safety check
FOUND_SECONDS = 3.5  # how long it shows the cause just found, before the fix's steps

_STRING_LIST = {"type": "array", "items": {"type": "string"}}
_STATUS = {"type": "string", "enum": ["open", "testing", "ruled_out", "confirmed"]}
TOOLS = [
    {"type": "function", "name": "update_job",
     "description": "Record the problem in one sentence, the job type, and how experienced "
                    "the user is with this repair.",
     "parameters": {"type": "object", "properties": {
         "problem": {"type": "string"},
         "domain": {"type": "string", "enum": list(domains.DOMAINS)},
         "experience": {"type": "string", "enum": ["first-timer", "some experience", "experienced"]},
         "experience_note": {"type": "string", "description": "What showed it, or 'confirmed'."}}}},
    {"type": "function", "name": "set_causes",
     "description": "Replace the list of possible causes, shown on the headset's checklist.",
     "parameters": {"type": "object", "required": ["causes"], "properties": {
         "title": {"type": "string", "description": "A short panel title, like 'Why is it running?'"},
         "causes": {"type": "array", "items": {"type": "object",
             "required": ["id", "label", "prior", "status"], "properties": {
                 "id": {"type": "string", "description": "Short and stable, like 'flapper'."},
                 "label": {"type": "string", "description": "A few words."},
                 "prior": {"type": "number"}, "status": _STATUS,
                 "for": _STRING_LIST, "against": _STRING_LIST}}}}}},
    {"type": "function", "name": "start_probe",
     "description": "Declare a probe Felix just asked for: one action for information, not repair.",
     "parameters": {"type": "object",
         "required": ["instruction", "target_part", "observe", "outcomes", "hands_inside"],
         "properties": {
             "instruction": {"type": "string"},
             "target_part": {"type": "string", "description": "The part's name."},
             "observe": {"type": "string", "description": "What to look or listen for."},
             "hands_inside": {"type": "boolean"},
             "outcomes": {"type": "array", "items": {"type": "object", "required": ["result"],
                 "properties": {"result": {"type": "string"},
                                "supports": _STRING_LIST, "rules_out": _STRING_LIST}}}}}},
    {"type": "function", "name": "finish_probe",
     "description": "Record what the running probe showed and how it changes each cause.",
     "parameters": {"type": "object", "required": ["probe_id", "result", "updates"], "properties": {
         "probe_id": {"type": "string"}, "result": {"type": "string"},
         "updates": {"type": "array", "items": {"type": "object", "required": ["id", "status"],
             "properties": {"id": {"type": "string"}, "status": _STATUS,
                            "for": {"type": "string", "description": "Evidence for it, if any."},
                            "against": {"type": "string",
                                        "description": "Evidence against it, if any."}}}}}}},
    {"type": "function", "name": "start_safety_check",
     "description": "Felix gave the job's safety steps; the server checks them by eye when the "
                    "user says they're done.",
     "parameters": {"type": "object", "properties": {}}},
    {"type": "function", "name": "write_steps",
     "description": "Record the repair steps for the confirmed cause. The last is the proof test.",
     "parameters": {"type": "object", "required": ["title", "steps"], "properties": {
         "title": {"type": "string", "description": "A short panel title for the fix."},
         "steps": {"type": "array", "items": {"type": "object",
             "required": ["label", "instruction", "target_part", "pass_condition", "hands_inside"],
             "properties": {
                 "label": {"type": "string",
                           "description": "The panel line: 2 to 5 words, like 'Loosen the chain'."},
                 "instruction": {"type": "string", "description": "One physical action."},
                 "target_part": {"type": "string"},
                 "pass_condition": {"type": "string",
                                    "description": "What a photo or their words must show."},
                 "hands_inside": {"type": "boolean"}}}}}}},
    {"type": "function", "name": "pin",
     "description": "Float a short note over a part in their headset, with a countdown if "
                    "they're waiting on it. Pinning the same part again replaces its note; "
                    "empty text removes it.",
     "parameters": {"type": "object", "required": ["part", "text"], "properties": {
         "part": {"type": "string",
                  "description": "The part it floats over, named as labeled in their headset."},
         "text": {"type": "string",
                  "description": "1 to 4 words, like 'Refilling' or 'Front left: 32 psi'."},
         "seconds": {"type": "number",
                     "description": "A countdown for a wait, like 60. Leave it out for a note "
                                    "that stays."}}}},
    {"type": "function", "name": "look_up",
     "description": "Search the web in the background, like a part size for a model number. "
                    "The answer reaches Felix in a later turn.",
     "parameters": {"type": "object", "required": ["question"], "properties": {
         "question": {"type": "string"}}}},
    {"type": "function", "name": "close_job",
     "description": "Close the job once every step has passed.",
     "parameters": {"type": "object", "required": ["cause", "evidence", "done", "proof", "tip"],
         "properties": {k: {"type": "string"} for k in ("cause", "evidence", "done", "proof", "tip")}}},
    {"type": "function", "name": "goodbye",
     "description": "Felix said goodbye after the job closed or stopped: he heads off until "
                    "they call him again.",
     "parameters": {"type": "object", "properties": {}}},
    {"type": "function", "name": "stop_job",
     "description": "Stop the job for a refusal or a stop condition. It stays stopped.",
     "parameters": {"type": "object", "required": ["reason"], "properties": {
         "reason": {"type": "string"}}}},
]

_WAKE = re.compile(rf"\b{re.escape(config.WAKE_WORD)}\b", re.IGNORECASE)
_NOT_YET = re.compile(r"^\s*not (yet|quite)\b[,.!;:]*\s*", re.IGNORECASE)

_client = AsyncOpenAI(base_url=config.META_BASE_URL, api_key=config.MODEL_API_KEY)


def addressed(text: str) -> bool:
    """Whether a sentence calls Felix by name."""
    return bool(_WAKE.search(text))


@dataclass
class Reply:
    text: str | None  # None: he stays quiet
    panel: dict | None  # the checklist, when the verifier changed it this turn
    target: str  # the part he's working on, for the headset to point at


class Felix:
    """Felix's side of one session: the conversation and the job.

    The history lives here rather than in Meta's stored conversations
    (previous_response_id): in testing, those added 8-10 s to every follow-up,
    while sending the same history ourselves took about 2 s.
    """

    def __init__(self, log_path: Path | None = None,
                 record: Callable[..., None] = lambda kind, **data: None,
                 on_update: Callable[[dict | None, str], None] = lambda panel, target: None,
                 on_pins: Callable[[], None] = lambda: None,
                 on_goodbye: Callable[[], None] = lambda: None) -> None:
        self.job = Job(log_path)
        self._record = record
        self._on_update = on_update  # the scribe changed the panel or the target part
        self._on_pins = on_pins  # the scribe changed the pins (job.pins)
        self._on_goodbye = on_goodbye  # Felix said goodbye: he heads off
        self._history: list[dict] = [{"role": "system", "content": PERSONA}]
        self._exchanges: list[tuple[str, str]] = []  # (you, Felix), for the scribe's context
        self._photos: dict[str, bytes] = {}  # recent photos by file name, for before/after checks
        self._undo: int | None = None  # where the last turn started in the history
        self._turn: tuple[str, bytes | None, str | None] = ("", None, None)  # said, photo, file
        self._scribe: asyncio.Task | None = None
        self._catching_up: asyncio.Task | None = None  # checking steps just written
        self._tasks: set[asyncio.Task] = set()
        # What happened since his last turn that he should hear about, like a step they
        # checked off themselves or a countdown that ran out.
        self._news: list[str] = []
        self._checked_off = False  # they checked something off since his last turn
        self._labels: list[str] = []  # the parts labeled in their headset, for the scribe
        self._said_at = time.monotonic()  # when he said the line the scribe is recording

    def greet(self) -> str:
        self._history.append({"role": "assistant", "content": GREETING})
        self._exchanges.append(("", GREETING))
        self._background(self._warm_up())
        return GREETING

    async def _warm_up(self) -> None:
        """A tiny call while Felix says hello: the first call is slow (12 s in testing), and
        Meta caches the long instructions it starts with, so his first answer comes quicker."""
        try:
            await _client.responses.create(
                model=config.META_MODEL, reasoning={"effort": "minimal"},
                input=self._history[:1] + [{"role": "user", "content": "(Warming up: reply OK.)"}])
        except Exception as error:
            self._record("error", during="warm-up", error=repr(error))

    async def turn(self, said: str, jpeg: bytes | None, photo: str | None = None,
                   labels: list[str] = (), sound: str = "",
                   seen: list[str] | None = None) -> Reply:
        """What Felix says about what you just said. Call said_it() once he has said it.

        sound is what the mic picked up besides speech (see sounds.py). With seen, you
        said nothing: Felix speaks up on his own about what happened, like the lid the
        verifier just saw set down (see look()) or a countdown that ran out (see news()).
        """
        if said and (verify.says_done(said) or verify.affirms(said) or verify.checks_off(said)):
            await self.settle()  # the verifier needs the steps from his last reply
        if self._catching_up is not None:
            await asyncio.wait([self._catching_up])  # steps just written may have passed
            self._catching_up = None
        self._undo = len(self._history)
        self._turn = (said, jpeg, photo)
        self._labels = list(labels)
        panel_before = self.job.panel()
        gate_open = not self.job.gate_passed()
        if jpeg and photo:
            self._remember_photo(photo, jpeg)
        news, checked_off = [], False
        try:
            if seen is None and verify.checks_off(said):
                self.check_off(self._next_item())
            news, self._news = self._news, []
            checked_off, self._checked_off = self._checked_off, False
            if seen is not None:
                verdicts = news + seen
            elif checked_off:
                verdicts = news  # they settled it themselves: nothing to check
            else:
                verdicts = news + await self._verify_if_done(said, jpeg, photo, sound, labels)
            if gate_open and self.job.gate_passed():
                panel_before = self.job.panel()  # the gate's tick shows first, then this
            note = "" if jpeg else " (The headset couldn't take a photo this time.)"
            if labels:
                note += f" (Parts labeled in their headset: {', '.join(labels)}.)"
            heard = (f'The user said: "{said}"' if said else
                     "(The user didn't say anything: something happened while they worked, "
                     "below. Speak up about it.)")
            text = f"{heard}{note}\n\n[Job]\n{self.job.summary(for_felix=True)}"
            if sound:
                text += f"\nMic: {sound}"
            if verdicts:
                text += "\n" + "\n".join(verdicts)
            content = [{"type": "input_text", "text": text}]
            if jpeg:
                content.append({"type": "input_image", "image_url": _data_url(jpeg)})
            self._history.append({"role": "user", "content": content})
            self._drop_old_photos()
            start = time.perf_counter()
            response = await _client.responses.create(
                model=config.META_MODEL, reasoning={"effort": config.AGENT_EFFORT},
                input=self._history)
            think_ms = round((time.perf_counter() - start) * 1000)
        except BaseException:
            self.forget_last()  # failed, or cancelled because you said more
            self._news[:0] = news  # still news for the turn that replaces this one
            self._checked_off |= checked_off
            raise
        reply = response.output_text.strip()
        if not any("NOT YET" in v for v in verdicts):
            # A "not yet" is the verifier's call: from Felix alone, it read as a demand that
            # never ends. What he saw stays; the verdict word goes.
            reply = _NOT_YET.sub("", reply, count=1)
            reply = reply[:1].upper() + reply[1:]
        quiet = reply.strip(" .").lower() in ("", QUIET, "quiet")
        self._history.append({"role": "assistant", "content": QUIET if quiet else reply})
        self._record("felix_thinks", think_ms=think_ms, verdicts=verdicts)
        self.job.save()
        panel = self.job.panel()
        return Reply(text=None if quiet else reply,
                     panel=panel if panel != panel_before else None,
                     target=self.job.target_part())

    def said_it(self, reply: str) -> None:
        """Felix said his reply: the scribe brings the job's record up to date meanwhile.

        Records are kept in order: each scribe waits for the one before it.
        """
        said, jpeg, photo = self._turn
        self._undo = None
        self._exchanges.append((said, reply))
        gate = self.job.open_gate()
        if gate and not self.job.gate_requested and _mentioned(reply, gate):
            # He gave the safety steps: watch for them now, whether or not the scribe records
            # it. In one headset run it didn't, so he asked about the lid three times.
            self.job.start_safety_check()
            self._show(self.job.panel())
        previous = self._scribe
        said_at = time.monotonic()

        async def update() -> None:
            if previous is not None:
                await asyncio.wait([previous])
            self._said_at = said_at  # a countdown he gave starts from when he said it
            await self._update_record(said, reply, jpeg, photo)

        self._scribe = asyncio.create_task(update())

    def forget_last(self) -> None:
        """Take back the last turn's words, as if he never answered.

        What the verifier saw that turn stays in the job: it really happened.
        """
        if self._undo is None:
            return
        del self._history[self._undo:]
        self._undo = None

    async def settle(self) -> None:
        """Wait for the scribe to finish the record from Felix's latest reply."""
        if self._scribe is not None:
            await asyncio.wait([self._scribe])

    # -- the scribe: the job's record, kept in the background

    async def _update_record(self, said: str, reply: str, jpeg: bytes | None,
                             photo: str | None) -> None:
        panel_before, target_before = self.job.panel(), self.job.target_part()
        found_before = any(c["status"] == "confirmed" for c in self.job.causes)
        steps_before = self.job.steps  # write_steps replaces the list
        earlier ="\n".join(f"User: {you}\nFelix: {felix}" if you else f"Felix: {felix}"
                            for you, felix in self._exchanges[-SCRIBE_CONTEXT - 1:-1])
        text = f"[Record]\n{self.job.summary()}\n\n"
        if (domain := domains.DOMAINS.get(self.job.domain or "")) and domain.get("causes"):
            text += f"[Common causes for this job type]\n{'; '.join(domain['causes'])}\n\n"
        text += f"[Labeled in their headset]\n{', '.join(self._labels) or 'nothing yet'}\n\n"
        text += (f"[Earlier]\n{earlier or '(nothing yet)'}\n\n"
                 f'[Latest exchange]\nUser: "{said}"\nFelix: "{reply}"')
        content = [{"type": "input_text", "text": text}]
        if jpeg:
            content.append({"type": "input_image", "image_url": _data_url(jpeg)})
        messages = [{"role": "system", "content": SCRIBE}, {"role": "user", "content": content}]
        try:
            for _ in range(SCRIBE_ROUNDS):
                start = time.perf_counter()
                response = await _client.responses.create(
                    model=config.META_MODEL, reasoning={"effort": config.SCRIBE_EFFORT},
                    input=messages, tools=TOOLS)
                calls = [item for item in response.output if item.type == "function_call"]
                outputs, refused = [], False
                for call in calls:
                    output, ok = self._run_tool(call.name, _args(call.arguments))
                    outputs.append({"type": "function_call_output", "call_id": call.call_id,
                                    "output": output})
                    refused |= not ok
                self._record("scribe", think_ms=round((time.perf_counter() - start) * 1000),
                             tools=[{"name": c.name, "args": _args(c.arguments)} for c in calls])
                if not refused:
                    break
                messages += [item.model_dump(exclude_none=True) for item in response.output]
                messages += outputs
        except Exception as error:
            self._record("error", during="scribe", error=repr(error))
        step = self.job.current_step()
        if step and step["before_photo"] is None:
            step["before_photo"] = photo  # the "before" for the verifier's comparison
        self.job.save()
        found = any(c["status"] == "confirmed" for c in self.job.causes)
        flash = found and not found_before and self.job.phase == "repair"
        if self.job.steps is not steps_before and step and jpeg:
            # Felix's next turn waits for this (see turn), so he doesn't ask for what passed.
            self._catching_up = asyncio.create_task(self._catch_up(jpeg, photo, show=not flash))
        if flash:
            # The cause was found and the fix written at once: show the find, then the fix.
            self._show(self.job.causes_panel())
            self._background(self._show_later(FOUND_SECONDS))
            return
        panel, target = self.job.panel(), self.job.target_part()
        if panel != panel_before or target != target_before:
            self._record("panel", **panel)
            self._on_update(panel if panel != panel_before else None, target)

    async def _catch_up(self, jpeg: bytes, photo: str | None, show: bool = True) -> None:
        """Steps just written may already be done: people often fix it while the record
        catches up. Check them against what they've said lately, so Felix doesn't ask for
        what they already told him. show=False leaves the panel to the found cause's flash,
        which moves on to the steps by itself."""
        said = " ".join(you for you, _ in self._exchanges[-4:] if you)
        if said and self.job.current_step():
            await self._grade_steps(said, jpeg, photo, labels=self._labels, quiet=True, show=show)

    def _run_tool(self, name: str, args: dict) -> tuple[str, bool]:
        """(the output the scribe sees, whether the server accepted the call)"""
        job = self.job
        try:
            match name:
                case "update_job":
                    return job.update(**args), True
                case "set_causes":
                    return job.set_causes(args.get("title", ""), args.get("causes") or []), True
                case "start_probe":
                    return job.start_probe(**args), True
                case "finish_probe":
                    return job.finish_probe(args.get("probe_id", ""), args.get("result", ""),
                                            args.get("updates") or []), True
                case "start_safety_check":
                    return job.start_safety_check(), True
                case "write_steps":
                    return job.write_steps(args.get("title", ""), args.get("steps") or []), True
                case "close_job":
                    return job.close(**{k: args.get(k, "") for k in
                                        ("cause", "evidence", "done", "proof", "tip")}), True
                case "stop_job":
                    return job.stop(args.get("reason", "")), True
                case "pin":
                    result = job.pin(args.get("part", ""), args.get("text", ""),
                                     args.get("seconds") or 0, start=self._said_at)
                    self._on_pins()
                    return result, True
                case "look_up":
                    self._look_up(args.get("question", ""))
                    return "Looking it up in the background.", True
                case "goodbye":
                    if job.phase not in ("closed", "stopped"):
                        raise JobError("Felix only heads off once the job is closed or stopped.")
                    self._on_goodbye()
                    return "Felix heads off.", True
                case _:
                    return f"Unknown tool {name}.", False
        except (JobError, TypeError) as error:
            self._record("tool_refused", tool=name, error=str(error))
            return f"Refused: {error}", False

    # -- the verifier, run by the server before Felix answers

    async def _verify_if_done(self, said: str, jpeg: bytes | None, photo: str | None,
                              sound: str = "", labels: list[str] = ()) -> list[str]:
        """Grade what's pending before Felix answers: the safety gate when you mention it or
        say you're done once he's asked for it, otherwise the steps when you say you're done
        or answer yes to his question.

        Other photos are checked in the background instead, so Felix doesn't make you wait
        for a check you didn't ask for, and the record keeps up with what he sees.
        """
        if jpeg is None:
            return []
        check = self._pending_check(said)
        if check == "gate":
            gate = self.job.open_gate()
            return await self._check_gate(_mentioned(said, gate) or gate, said, jpeg)
        if check == "steps":
            line = await self._grade_steps(said, jpeg, photo, sound, labels)
            return [line] if line else []
        if self.job.gate_requested and self.job.open_gate():
            self._background(self.look(jpeg, photo))
        elif self.job.current_step():
            self._background(self._grade_steps(said, jpeg, photo, sound, labels, quiet=True))
        return []

    def will_check(self, said: str) -> bool:
        """Whether Felix checks your work before he answers this, so he'll take longer."""
        return not verify.checks_off(said) and bool(self._pending_check(said))

    def _pending_check(self, said: str) -> str:
        """What gets checked before Felix answers: "gate", "steps", or "" for nothing."""
        gate = self.job.open_gate()
        if gate:
            if _mentioned(said, gate) or (self.job.gate_requested and verify.says_done(said)):
                return "gate"
            if self.job.gate_requested:
                return ""
        if not self.job.current_step():
            return ""
        asked = self._exchanges[-1][1].rstrip() if self._exchanges else ""
        if verify.says_done(said) or (asked.endswith("?") and verify.affirms(said)):
            return "steps"
        return ""

    def check_off(self, item: str) -> str | None:
        """They checked something off themselves, on the checklist or by saying "check it
        off": a step, with every step before it, or a safety check their word can settle.
        It passes on their word, and Felix hears about it in his next turn. Returns what was
        checked off, or None if it can't be."""
        seen = "They checked it off themselves."
        gate = next((g for g in self.job.open_gate() if g["id"] == item), None)
        if gate is not None:
            if not gate.get("word_counts"):
                return None  # a strict safety check needs the verifier's eyes
            self.job.record_gate(gate["id"], True, seen, on_word=True)
            self._record("verify", check=gate["id"], passed=True, on_word=True, checked_off=True,
                         seen=seen, correction="")
            self._news.append(f"Safety check '{gate['short']}': PASSED on their word: they "
                              "checked it off themselves.")
            if self.job.gate_passed():
                self._news.append("The safety gate passed: hands-inside work is allowed now.")
                self._show(self.job.gate_panel())
                self._background(self._show_later(GATE_TICK_SECONDS))
            else:
                self._show(self.job.panel())
            self.job.save()
            self._checked_off = True
            return gate["short"]
        left = [s for s in self.job.steps if s["status"] != "passed"]
        ids = [s["id"] for s in left]
        if self.job.phase != "repair" or item not in ids:
            return None
        done = left[:ids.index(item) + 1]
        for s in done:
            self.job.record_step(s, True, seen, "", None, on_word=True)
        names = ", ".join(s["id"] for s in done)
        self._record("verify", check=names, passed=True, on_word=True, checked_off=True,
                     seen=seen, correction="")
        following = self.job.current_step()
        after = (f" Next step: {following['instruction']}" if following
                 else " Every step has passed: sum up and close out.")
        self._news.append(f"Verifier, step {names}: PASSED on their word: they checked it "
                          f"off themselves. Thank them, with no 'not yet'.{after}")
        self.job.save()
        self._show(self.job.panel())
        self._checked_off = True
        return done[-1]["label"]

    def acknowledge(self, caution_id: str, how: str) -> str | None:
        """They acknowledged a caution sign: Felix says it in his own words in his next
        turn. Returns the sign's line, or None if it was already acknowledged."""
        caution = self.job.acknowledge(caution_id, how)
        if caution is None:
            return None
        self._news.append(f"They acknowledged the caution sign '{caution['line']}' ({how}). Say "
                          "it once in your own words, calmly, with what to do if it happens, "
                          "then carry on.")
        self.job.save()
        return caution["line"]

    def news(self, line: str) -> None:
        """Something happened that Felix should hear about in his next turn, like a
        countdown that ran out."""
        self._news.append(line)

    def has_news(self) -> bool:
        return bool(self._news)

    def _next_item(self) -> str:
        """What "check it off" means: the safety check Felix asked for, else the current step."""
        if self.job.gate_requested and (gate := self.job.open_gate()):
            return gate[0]["id"]
        step = self.job.current_step()
        return step["id"] if step else ""

    def watching(self) -> bool:
        """Whether Felix is waiting for something he can see without being told: for now,
        the safety steps he asked for, like the lid set flat on its towel."""
        return bool(self.job.gate_requested and self.job.open_gate())

    async def look(self, jpeg: bytes, photo: str | None) -> list[str]:
        """Check a photo taken while they worked for what Felix is waiting to see. Only a
        pass counts, since they didn't claim anything. Returns the verifier's lines when
        something just passed, for Felix to say so."""
        if not self.watching():
            return []
        lines = await self._check_gate(self.job.open_gate(), "", jpeg, quiet=True)
        return lines if self.job.gate_passed() else []

    async def _check_gate(self, items: list[dict], said: str, jpeg: bytes,
                          quiet: bool = False) -> list[str]:
        """Only a pass, or a "not yet" on something they said is done, reaches Felix: asking
        "this lid?", or saying "done" about the chain, isn't a claim about the lid. quiet
        leaves out of the session record checks that didn't pass, for the photos Felix
        takes every few seconds while he watches."""
        asked = self._exchanges[-1][1] if self._exchanges else ""
        # While watching, they haven't said anything, so the photo alone must show it.
        verdicts = await asyncio.gather(*(verify.check(
            g["say"], g["check"], said, jpeg, asked=asked,
            word_counts=g.get("word_counts", False) and not quiet) for g in items))
        if self.job.gate_passed():
            return []  # another check passed it meanwhile
        lines = []
        for g, v in zip(items, verdicts):
            misses = sum(c["check"] == g["id"] and not c["passed"] for c in self.job.safety_checks)
            # For a low-risk check, their word settles it unless the photo plainly shows
            # otherwise, and after two "not yet"s, even then, as with the steps.
            on_word = (v["claimed"] and not v["passed"] and g.get("word_counts", False)
                       and (not v["contradicts"] or misses >= MAX_NOT_YET))
            passed = v["passed"] or on_word
            if passed or not quiet:
                self._record("verify", check=g["id"], passed=passed, on_word=on_word,
                             claimed=v["claimed"], contradicts=v["contradicts"],
                             seen=v["seen"], correction=v["correction"], watching=quiet)
            if not (passed or v["claimed"]):
                continue
            self.job.record_gate(g["id"], passed, v["seen"], on_word)
            lines.append(f"Verifier, safety check '{g['short']}': "
                         + ("PASSED on their word" if on_word else "PASSED" if passed
                            else f"NOT YET. Correction: {v['correction']}")
                         + f" (seen: {v['seen']})")
        if self.job.gate_passed():
            lines.append("The safety gate passed: hands-inside work is allowed now.")
            # Tick it off where they can see it, then move the panel on.
            self._show(self.job.gate_panel())
            self._background(self._show_later(GATE_TICK_SECONDS))
        return lines

    async def _grade_steps(self, said: str, jpeg: bytes, photo: str | None, sound: str = "",
                           labels: list[str] = (), quiet: bool = False,
                           show: bool = True) -> str | None:
        """The current step, and any later ones their report shows worked: "I flushed and it
        stopped" passes the step before the flush too.

        quiet is for photos from turns where they didn't say they were done: only a pass
        counts, and nothing reaches Felix this turn. Returns the verifier's line for Felix,
        or None when there's nothing new.
        """
        left = [s for s in self.job.steps if s["status"] != "passed"]
        step = left[0]
        before = self._photos.get(step["before_photo"] or "")
        misses = sum(not a["passed"] for a in step["attempts"])
        asked = self._exchanges[-1][1] if self._exchanges else ""
        v = await verify.check_steps(left, said, jpeg, before, misses, sound, asked, labels)
        if step["status"] == "passed":
            return None  # another check passed it meanwhile
        passed = [s for s in left if s["id"] in v["passed"] and s["status"] != "passed"]
        if quiet and not passed:
            return None
        # After two "not yet"s, their word settles it: the view can't show everything.
        on_word = not passed and misses >= MAX_NOT_YET
        if on_word:
            passed = [step]
        for s in passed:
            self.job.record_step(s, True, v["seen"], "", photo, on_word)
        contradicted = step["id"] in v["contradicted"]
        if not passed:
            self.job.record_step(step, False, v["seen"], v["correction"], photo)
        self._record("verify", check=", ".join(s["id"] for s in passed) or step["id"],
                     passed=bool(passed), on_word=on_word, contradicted=contradicted,
                     watching=quiet, seen=v["seen"], correction=v["correction"])
        if quiet:
            if show:
                self._show(self.job.panel())
            return None
        if not passed and contradicted:
            return (f"Verifier, step {step['id']}: NOT YET, the view shows it isn't done. "
                    f"Seen: {v['seen']} Correction: {v['correction']}")
        if not passed:
            return (f"Verifier, step {step['id']}: not confirmed yet, though nothing looks wrong. "
                    f"Don't say 'not yet'; ask them to confirm, like: {v['correction']}")
        following = self.job.current_step()
        after = (f" Next step: {following['instruction']}" if following
                 else " Every step has passed: sum up and close out.")
        if on_word:
            return (f"Verifier, step {step['id']}: PASSED on their word. They've said it's done "
                    f"{misses + 1} times and the view can't confirm it (seen: {v['seen']}). "
                    f"Thank them for confirming, with no 'not yet'.{after}")
        return (f"Verifier, step {', '.join(s['id'] for s in passed)}: PASSED. "
                f"Seen: {v['seen']}.{after}")

    def _show(self, panel: dict) -> None:
        self._record("panel", **panel)
        self._on_update(panel, self.job.target_part())

    async def _show_later(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
        self._show(self.job.panel())

    # -- looking things up, in the background

    def _background(self, coroutine) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _look_up(self, question: str) -> None:
        async def run() -> None:
            start = time.perf_counter()
            try:
                response = await _client.responses.create(
                    model=config.META_MODEL, reasoning={"effort": "low"},
                    tools=[{"type": "web_search"}],
                    input=f"{question} Answer in one or two sentences with the key fact.")
                # Spark narrates while it searches ("I'll look that up..."); keep its last message.
                last = [item for item in response.output if item.type == "message"][-1]
                answer = "".join(getattr(part, "text", "") for part in last.content).strip()
            except Exception as error:
                answer = f"(The search failed: {error})"
            self.job.notes.append({"question": question, "answer": answer})
            self.job.save()
            self._record("looked_up", question=question, answer=answer,
                         think_ms=round((time.perf_counter() - start) * 1000))

        self._background(run())

    # -- housekeeping

    def _remember_photo(self, name: str, jpeg: bytes) -> None:
        self._photos[name] = jpeg
        keep = {s["before_photo"] for s in self.job.steps} | {name}
        for old in list(self._photos)[:-6]:
            if old not in keep:
                del self._photos[old]

    def _drop_old_photos(self) -> None:
        """Older turns keep what you said but lose their photo and their [Job] block."""
        turns = [m for m in self._history if m["role"] == "user" and isinstance(m["content"], list)]
        for message in turns[:-KEEP_PHOTOS]:
            text = message["content"][0]["text"]
            if "\n\n[Job]" not in text and len(message["content"]) == 1:
                continue  # already trimmed
            had_photo = len(message["content"]) > 1
            text = text.split("\n\n[Job]")[0]
            message["content"] = [{"type": "input_text",
                                   "text": text + (" (Photo no longer attached.)" if had_photo else "")}]


def _mentioned(said: str, gate: list[dict]) -> list[dict]:
    """The safety checks what they said is about, like the lid."""
    words = said.lower()
    return [g for g in gate if any(re.search(rf"\b{k}\b", words) for k in g.get("keywords", []))]


def _data_url(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()


def _args(arguments: str) -> dict:
    try:
        args = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return {}
    return args if isinstance(args, dict) else {}
