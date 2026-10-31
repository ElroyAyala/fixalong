"""The headset connects here over one WebSocket; the live view runs here too.

Run from server/:

    .venv\\Scripts\\python.exe -m uvicorn fixalong.app:app --host 0.0.0.0 --port 8765

Then open http://localhost:8765 on this PC for the live view.

The headset streams its mic as binary frames (24 kHz 16-bit mono PCM) and
sends everything else as JSON text frames:

    headset -> server   {"type": "hello", "app": str, "device": str}
                        {"type": "photo", "image": "<base64 JPEG>", "id": str}
                            (answers a "snap"; an empty image means the camera wasn't ready)
                        {"type": "log", "level": str, "text": str}
                        {"type": "tap", "id": str}   you checked a row off on the checklist
                        {"type": "caution_seen", "id": str}  you looked at a caution sign
                        {"type": "caution_ack", "id": str}   you pinched it: "got it"
    server -> headset   {"type": "say", "text": str, "audio": "<base64 16-bit mono PCM>",
                         "sample_rate": int, "follow_up": seconds, "focus": [part names]}
                        {"type": "filler", "audio": str, "sample_rate": int}
                            a quick "mm-hm" while he thinks: no caption, same voice
                        {"type": "quiet", "follow_up": seconds}  Felix chose not to answer
                        {"type": "snap", "id": str}       take a photo now
                        {"type": "wake"}                   Felix heard his name: he's listening
                        {"type": "listening", "text": str} what Felix is hearing
                        {"type": "heard", "text": str}     what Felix is about to answer
                        {"type": "labels", "photo": snap id, "parts": [{"name", "x", "y"}],
                         "complete": bool}
                            the parts in that photo, on a 0-1000 grid from its top left;
                            complete means every part in view, not just one Felix named
                        {"type": "focus", "focus": [part names]}  point at these labels
                        {"type": "pins", "pins": [{"part", "text", "countdown": bool,
                                                   "seconds_left": float}]}
                            Felix's notes and countdowns, each over the labeled part named;
                            the whole set each time, so a pin left out is removed
                        {"type": "listen", "follow_up": seconds}  keep listening this long,
                            like through a countdown
                        {"type": "caution", "id": str, "text": str, "photo": snap id,
                         "x": int, "y": int}
                            a hazard to you or the headset: a sign at that point in that
                            photo, on the same grid as labels, until you acknowledge it
                        {"type": "caution_done", "id": str}  you acknowledged it: it closes
                        {"type": "farewell"}  the job's done and Felix said goodbye: he heads
                            off, and the panel, labels and pins clear; "Felix" brings him back
                        {"type": "panel", "title": str, "rows": [{"text", "mark", "style", "id"}],
                         "moment": str}
                            Felix's checklist: the possible causes, then the repair steps.
                            mark is check, question, bang, dot or none; style is normal,
                            active, found or dim. A row with an id can be checked off
                            (see "tap"). No rows hides the panel. moment is "found" once
                            the cause is found, "fixed" once every step passed, otherwise
                            empty: the headset chimes when it changes.

follow_up is how long Felix keeps listening without his name: the
conversation stays open until CONVERSATION_SECONDS after he last spoke.
focus lists the labeled parts Felix is talking about, so the headset can
point at them; an empty list puts the arrow away.

Every connection is recorded as a session (see session.py), and its job as a
structured log in server/logs/ (see job.py).
"""

import asyncio
import base64
import contextlib
import json
import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse

from . import config, domains, felix, hazards, parts, verify, voice
from .ears import Ears
from .session import Session, monitor
from .sounds import Sounds

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("fixalong")

app = FastAPI(title="fixalong")


def ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


@app.get("/health")
def health() -> dict:
    return {"ok": True,
            "meta_key": bool(config.MODEL_API_KEY),
            "voice_key": bool(config.ELEVENLABS_API_KEY)}


# -- the headset ---------------------------------------------------------------

class Headset:
    """One connected headset: its session record, Felix's ears, and the conversation.

    The receive loop never waits on Felix: his turns run as tasks, so mic audio
    keeps flowing to the transcription stream while he thinks and talks. He
    waits for you to pause before he speaks, and if you say more before he
    starts answering, he starts over with all of it.
    """

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.session = Session()
        self._jobs = 0
        self.felix = self.new_felix()
        self._leaving = False  # Felix is heading off after a goodbye
        self.ears = Ears(on_partial=self.on_partial, on_sentence=self.on_sentence)
        self.sounds = Sounds()  # what the mic hears besides speech, like a refill running
        self._send_lock = asyncio.Lock()
        self._turn: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()
        self._photo_requests: dict[str, asyncio.Future] = {}
        self._unanswered: list[str] = []  # what you've said to Felix that he hasn't answered
        self._answering = False  # he has decided what to say and is saying it
        self._open_until = 0.0  # the conversation is open (no name needed) until then
        self._woke = False  # this sentence called him by name and the headset has blipped
        self._speaking_until = 0.0
        self._filled_at = -config.FILLER_GAP_SECONDS  # his last "mm-hm"
        self._last_partial = ""
        self._speech_started: float | None = None
        self._heard_at = 0.0  # when you last said anything
        self._labels: list[str] = []  # every part labeled this session, oldest first
        self._labeling = False
        self._checking_hazards = False
        self._hazards_at = -config.HAZARD_GAP_SECONDS  # the last hazard check
        self._named: dict[str, list[str]] = {}  # parts found for a reply he hasn't said yet
        self._last_reply = ""
        self._target = ""  # the part Felix is working on, from the job
        self._last_photo: tuple[bytes, str | None, str] | None = None  # (JPEG, file, snap id)
        self._countdowns: set[tuple[str, float]] = set()  # (part, ends_at) Felix will check in on
        self._looked_for: set[str] = set()  # pinned parts searched for a label
        self._closed = False

    async def run(self) -> None:
        self.spawn(self.watch())
        while True:
            message = await self.ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                self.session.record_mic(message["bytes"])
                self.ears.hear(message["bytes"])
                self.sounds.hear(message["bytes"])
                continue
            msg = json.loads(message["text"])
            kind = msg.get("type")
            if kind == "hello":
                self.session.event("hello", app=msg.get("app"), device=msg.get("device"))
                self.start_turn(self.say(self.felix.greet()), "greeting")
            elif kind == "photo":
                self.on_photo(msg)
            elif kind == "tap":
                self.on_tap(msg.get("id") or "")
            elif kind == "caution_seen":
                self.felix.job.seen_caution(msg.get("id") or "")
                self.session.event("caution_seen", id=msg.get("id"))
            elif kind == "caution_ack":
                self.on_caution_ack(msg.get("id") or "")
            elif kind == "log":
                self.session.event("headset_log", level=msg.get("level"), text=msg.get("text"))
            else:
                self.session.event("unknown_message", type=kind)

    def new_felix(self) -> felix.Felix:
        """Felix for a new job. The session's first job logs under the session's name; a job
        after a goodbye adds its number."""
        self._jobs += 1
        job = self._jobs
        name = self.session.id if job == 1 else f"{self.session.id}-{job}"

        def current() -> bool:
            # An earlier job's Felix may still finish background work; it stays off the headset.
            return job == self._jobs

        return felix.Felix(
            log_path=config.LOGS_DIR / f"{name}.json", record=self.session.event,
            on_update=lambda panel, target: current() and self.on_job_update(panel, target),
            on_pins=lambda: current() and self.on_pins(),
            on_goodbye=lambda: current() and self.on_goodbye())

    async def close(self) -> None:
        self._closed = True
        await self.ears.close()
        for task in [self._turn, *self._tasks]:
            if task is not None:
                task.cancel()
        self.session.event("disconnected")
        self.session.close()

    async def send(self, message: dict) -> None:
        async with self._send_lock:
            await self.ws.send_json(message)

    def spawn(self, coroutine) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # -- what Felix hears

    def conversation_open(self, at: float) -> bool:
        return at < self._open_until

    def on_partial(self, text: str) -> None:
        if text == self._last_partial:
            return
        self._heard_at = time.monotonic()
        if not self._last_partial:
            self._speech_started = self._heard_at
        self._last_partial = text
        self.session.live("hearing", text=text)
        listening = self.conversation_open(self._speech_started)
        if felix.addressed(text) and not listening and not self._woke:
            self._woke = True  # once per sentence: the headset blips to say he heard his name
            self.spawn(self.send({"type": "wake"}))
        if felix.addressed(text) or listening:
            self.spawn(self.send({"type": "listening", "text": text}))

    def on_sentence(self, text: str) -> None:
        # What counts is when you started talking, not when the sentence ended.
        now = time.monotonic()
        started = self._speech_started or now
        self._last_partial = ""
        self._speech_started = None
        self._woke = False
        self._heard_at = now
        if not text:
            return
        called = felix.addressed(text)
        for_felix = called or self.conversation_open(started)
        self.session.event("heard", text=text, for_felix=for_felix)
        if not for_felix:
            return
        if called:
            self._open_until = max(self._open_until, now + config.CONVERSATION_SECONDS)
        self._unanswered.append(text)
        self.respond()

    def on_tap(self, item: str) -> None:
        """You checked something off on the checklist yourself: it passes on your word,
        and Felix answers as if you'd told him."""
        checked = self.felix.check_off(item)
        self.session.event("tapped", id=item, checked=checked)
        if checked is None:
            return
        self._open_until = max(self._open_until, time.monotonic() + config.CONVERSATION_SECONDS)
        self._unanswered.append(f'I checked off "{checked}" on my checklist.')
        self.respond()

    def on_caution_ack(self, caution_id: str) -> None:
        """You pinched a caution sign: Felix answers as if you'd said "got it"."""
        if not self.acknowledge(caution_id, "pinched the sign"):
            return
        self._open_until = max(self._open_until, time.monotonic() + config.CONVERSATION_SECONDS)
        self._unanswered.append('I tapped "got it" on the caution sign.')
        self.respond()

    def acknowledge(self, caution_id: str, how: str) -> bool:
        """You acknowledged a caution sign: it closes, and Felix says it in his own words."""
        line = self.felix.acknowledge(caution_id, how)
        self.session.event("caution_acknowledged", id=caution_id, how=how, line=line)
        if line is None:
            return False
        self.spawn(self.send({"type": "caution_done", "id": caution_id}))
        return True

    def respond(self) -> None:
        """Answer what you've said: now, or by starting over if he hasn't started answering."""
        if self._turn is None or self._turn.done():
            self.start_turn(self.voice_turn(), "voice")
        elif not self._answering:
            # He hasn't started answering yet: start over with everything you said.
            self.session.event("rethink", text=" ".join(self._unanswered))
            previous = self._turn
            previous.cancel()
            self._turn = asyncio.create_task(self._run_turn(self.voice_turn(after=previous), "voice"))
        # Otherwise he's already answering; he gets to this once he's done (see _run_turn).

    def on_photo(self, msg: dict) -> None:
        jpeg = base64.b64decode(msg.get("image") or "")
        photo = self.session.save_photo(jpeg) if jpeg else None
        if photo:
            self.session.event("photo", file=photo, kb=len(jpeg) // 1024)
        future = self._photo_requests.pop(msg.get("id"), None)
        if future is not None and not future.done():
            future.set_result((jpeg or None, photo))

    # -- Felix's turns: one at a time

    def start_turn(self, coroutine, label: str) -> None:
        if self._turn is not None and not self._turn.done():
            coroutine.close()
            self.session.event("busy", ignored=label)
            return
        self._turn = asyncio.create_task(self._run_turn(coroutine, label))

    async def _run_turn(self, coroutine, label: str) -> None:
        try:
            await coroutine
        except asyncio.CancelledError:
            raise
        except Exception as error:
            log.exception("%s turn failed", label)
            self.session.event("error", during=label, error=repr(error))
            with contextlib.suppress(Exception):
                await self.say("Sorry, something went wrong on my end. Try that again.")
        if self._unanswered:  # you spoke while he was answering
            self._turn = asyncio.create_task(self._run_turn(self.voice_turn(), "voice"))

    async def voice_turn(self, after: asyncio.Task | None = None) -> None:
        if after is not None:
            await asyncio.wait([after])  # the turn this one replaces
        await asyncio.sleep(max(0.0, self._speaking_until - time.monotonic()))  # let him finish
        count = len(self._unanswered)
        said = " ".join(self._unanswered)
        await self.send({"type": "heard", "text": said})
        for caution in self.felix.job.cautions:
            if caution["acknowledged"] is None \
                    and verify.acknowledges(said, looked=caution["seen"] is not None):
                self.acknowledge(caution["id"], "said so")
        thought = asyncio.Event()  # set once he knows what he'll say
        self.spawn(self.fill_in(thought, self.felix.will_check(said)))
        try:
            jpeg, photo, photo_id = await self.request_photo()
            if jpeg:
                self.label(jpeg, photo, photo_id)
            start = time.perf_counter()
            turn = await self.felix.turn(said, jpeg, photo, self._labels, self.sounds.describe())
        finally:
            thought.set()
        await self.answer(turn, said, count, jpeg, photo, photo_id, ms(start))

    async def fill_in(self, thought: asyncio.Event, checking: bool) -> None:
        """A quick "mm-hm" if Felix is slow to answer, or a "let me look" when he's checking
        your work, so you know he heard you. Not while you're talking again, and not often."""
        wait = config.FILLER_CHECKING_SECONDS if checking else config.FILLER_SECONDS
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(thought.wait(), wait)
            return  # he answered first
        now = time.monotonic()
        if (self._last_partial or now < self._speaking_until
                or now - self._filled_at < config.FILLER_GAP_SECONDS):
            return
        audio = voice.filler("look" if checking else "plain")
        if not audio:
            return
        self._filled_at = now
        # His answer waits for it to finish (see say), and the headset mutes the mic meanwhile.
        self._speaking_until = now + len(audio) / 2 / config.VOICE_SAMPLE_RATE
        self.session.event("filler", checking=checking)
        await self.send({"type": "filler", "audio": base64.b64encode(audio).decode(),
                         "sample_rate": config.VOICE_SAMPLE_RATE})

    async def noticed_turn(self, seen: list[str], jpeg: bytes | None = None,
                           photo: str | None = None, photo_id: str = "") -> None:
        """Felix speaks up on his own: about something he saw while watching, like the lid
        set down, or about his news, like a countdown that ran out."""
        if jpeg is None:
            jpeg, photo, photo_id = await self.request_photo()
            if jpeg:
                self.label(jpeg, photo, photo_id)
        start = time.perf_counter()
        turn = await self.felix.turn("", jpeg, photo, self._labels, self.sounds.describe(),
                                     seen=seen)
        await self.answer(turn, "", 0, jpeg, photo, photo_id, ms(start))

    async def answer(self, turn: felix.Reply, said: str, count: int, jpeg: bytes | None,
                     photo: str | None, photo_id: str, think_ms: int) -> None:
        """Say Felix's reply once you've paused, after the first count things you said."""
        if turn.panel is not None:  # the verifier passed something
            self.session.event("panel", **turn.panel)
            await self.show_panel(turn.panel)
        reply = turn.text
        if reply is None:
            del self._unanswered[:count]
            self.session.event("felix_quiet", said=said, photo=photo, think_ms=think_ms)
            await self.send({"type": "quiet",
                             "follow_up": max(0.0, self._open_until - time.monotonic())})
            return
        self._target = turn.target
        if jpeg:
            # Look for exactly what he means, so the arrow lands on it: a spot on a labeled
            # part, like the flapper's ears, or a part with no label yet, like a thin chain.
            self.spawn(self._label(jpeg, photo, photo_id, named_in=reply))
        try:
            start = time.perf_counter()
            audio = await voice.speak(reply)
            voice_ms = ms(start)
            await self.until_you_pause()
        except asyncio.CancelledError:
            self.felix.forget_last()  # you kept talking, so he never said it
            raise
        del self._unanswered[:count]
        await self.say(reply, audio=audio, wanted=parts.asked_for(said, self._labels),
                       voice_ms=voice_ms, said=said, photo=photo, think_ms=think_ms)
        self.felix.said_it(reply)  # the scribe updates the job while he talks

    async def watch(self) -> None:
        """While Felix waits for something he can see, like the lid set down on its towel,
        the headset takes a photo every few seconds, so he catches it without asking. He
        only looks while nobody's talking, and stops a while after he last spoke."""
        while not self._closed:
            await asyncio.sleep(config.WATCH_SECONDS)
            if (self.felix.job.phase == "closed" and not self._leaving and self.idle()
                    and time.monotonic() > self._open_until):
                self.spawn(self.farewell())  # the job's done and the conversation ended
                continue
            if not (self.felix.watching() and self.idle()
                    and time.monotonic() - self._speaking_until < config.WATCH_FOR_SECONDS):
                continue
            jpeg, photo, photo_id = await self.request_photo()
            if not jpeg:
                continue
            self.label(jpeg, photo, photo_id)  # so the parts are labeled as soon as you look in
            try:
                seen = await self.felix.look(jpeg, photo)
            except Exception as error:
                self.session.event("error", during="watching", error=repr(error))
                continue
            if seen and self.idle():
                self.start_turn(self.noticed_turn(seen, jpeg, photo, photo_id), "noticed")

    def on_goodbye(self) -> None:
        if not self._closed:
            self.spawn(self.farewell())

    async def farewell(self) -> None:
        """The job's done and Felix said goodbye, or the conversation ended after it. Once
        he's done talking, he heads off, and the next "Felix" starts a new job."""
        if self._leaving:
            return
        self._leaving = True
        give_up = time.monotonic() + 15  # in case a last exchange runs long
        while not self.idle() and time.monotonic() < give_up:
            await asyncio.sleep(0.3)
        self.session.event("farewell")
        await self.send({"type": "farewell"})
        self._open_until = 0.0  # he needs his name again
        self._labels, self._target, self._named = [], "", {}
        self._countdowns.clear()
        self._looked_for.clear()
        self.felix = self.new_felix()
        self.felix.greet()  # his history starts as it does at hello, though he doesn't say it
        self._leaving = False

    def idle(self) -> bool:
        """Nobody's talking, and Felix isn't working on an answer."""
        return ((self._turn is None or self._turn.done()) and not self._unanswered
                and not self._last_partial and time.monotonic() > self._speaking_until)

    def on_job_update(self, panel: dict | None, target: str) -> None:
        """The scribe changed the job: show the new checklist, and point at the new part."""
        if self._closed:
            return
        if panel is not None:
            self.spawn(self.show_panel(panel))
        if target != self._target:
            self._target = target
            focus = parts.match(target, self._labels)
            if focus:
                self.spawn(self.send({"type": "focus", "focus": focus}))

    async def show_panel(self, panel: dict) -> None:
        await self.send({"type": "panel", "title": panel["title"], "rows": panel["rows"],
                         "moment": panel.get("moment", "")})

    # -- pins: notes and countdowns over parts

    def on_pins(self) -> None:
        """The scribe pinned or removed a note. A countdown keeps Felix listening until a
        while after it ends, and he checks in when it does."""
        if self._closed:
            return
        self.spawn(self.send_pins())
        now = time.monotonic()
        for pin in self.felix.job.pins.values():
            part = pin["part"]
            if not parts.match(part, self._labels) and part not in self._looked_for \
                    and self._last_photo:
                # Nothing labeled there yet: look for it, so the pin has a spot.
                self._looked_for.add(part)
                self.spawn(self._label(*self._last_photo, named_in=f"Look at the {part}.",
                                       point=False))
            countdown = (part, pin["ends_at"])
            if pin["ends_at"] and pin["ends_at"] > now and countdown not in self._countdowns:
                self._countdowns.add(countdown)
                self._open_until = max(self._open_until, pin["ends_at"] + config.CONVERSATION_SECONDS)
                self.spawn(self.send({"type": "listen", "follow_up": self._open_until - now}))
                self.spawn(self.when_up(*countdown))

    async def send_pins(self) -> None:
        now = time.monotonic()
        await self.send({"type": "pins", "pins": [
            {"part": (parts.match(p["part"], self._labels) or [p["part"]])[0], "text": p["text"],
             "countdown": p["ends_at"] is not None,
             "seconds_left": max(0.0, p["ends_at"] - now) if p["ends_at"] else 0.0}
            for p in self.felix.job.pins.values()]})

    async def when_up(self, part: str, ends_at: float) -> None:
        """When a countdown runs out, Felix hears about it and checks in: right away if
        nobody's talking, otherwise in his next answer."""
        await asyncio.sleep(max(0.0, ends_at - time.monotonic()))
        pin = self.felix.job.pins.get(part)
        if self._closed or pin is None or pin["ends_at"] != ends_at:
            return  # replaced or removed meanwhile
        self.session.event("countdown_done", part=part, text=pin["text"])
        self.felix.news(f"The countdown '{pin['text']}' over the {part} just ran out: check "
                        "in with them about it.")
        while not self._closed and self.felix.has_news():
            if self.idle():
                self.start_turn(self.noticed_turn([]), "countdown")
                break
            await asyncio.sleep(0.5)
        # The headset shows it done for a while; then it goes, unless it was replaced.
        await asyncio.sleep(config.PIN_DONE_SECONDS)
        if self.felix.job.pins.get(part) is pin:
            self.felix.job.pin(part, "")
            await self.send_pins()

    async def until_you_pause(self) -> None:
        """Wait until you've stopped talking, so Felix never cuts in.

        If you finish another sentence meanwhile, on_sentence replaces this turn.
        """
        give_up = time.monotonic() + 10  # in case a sentence never ends
        while time.monotonic() < give_up:
            quiet_for = time.monotonic() - self._heard_at
            if not self._last_partial and quiet_for >= config.PAUSE_SECONDS:
                return
            await asyncio.sleep(0.1)

    async def request_photo(self) -> tuple[bytes | None, str | None, str]:
        """A photo from the headset: (JPEG, saved file, snap id)."""
        request = uuid.uuid4().hex[:8]
        future = asyncio.get_running_loop().create_future()
        self._photo_requests[request] = future
        try:
            await self.send({"type": "snap", "id": request})
            jpeg, photo = await asyncio.wait_for(future, config.PHOTO_TIMEOUT_SECONDS)
            if jpeg:
                self._last_photo = (jpeg, photo, request)
            return jpeg, photo, request
        except asyncio.TimeoutError:
            self.session.event("photo_timeout", id=request)
            return None, None, request
        finally:
            self._photo_requests.pop(request, None)

    # -- labels on the parts Felix sees

    def label(self, jpeg: bytes, photo: str | None, photo_id: str) -> None:
        """Find the parts in a photo in the background, one photo at a time."""
        if self._labeling:
            return
        self._labeling = True
        self.spawn(self._label(jpeg, photo, photo_id))
        self.check_hazards(jpeg, photo, photo_id)

    # -- caution signs for hazards to you or the headset

    def check_hazards(self, jpeg: bytes, photo: str | None, photo_id: str) -> None:
        """Look for hazards in a photo in the background, once the job type is known: one
        check at a time, and not every photo while the headset watches."""
        job = self.felix.job
        now = time.monotonic()
        if (self._checking_hazards or now - self._hazards_at < config.HAZARD_GAP_SECONDS
                or job.domain not in domains.DOMAINS or job.phase in ("closed", "stopped")):
            return
        self._checking_hazards = True
        self._hazards_at = now
        self.spawn(self._check_hazards(jpeg, photo, photo_id))

    async def _check_hazards(self, jpeg: bytes, photo: str | None, photo_id: str) -> None:
        """Each new hazard gets a caution sign, and Felix keeps listening, so "got it"
        needs no name."""
        job = self.felix.job
        try:
            start = time.perf_counter()
            found = await hazards.find(jpeg, job.domain, domains.DOMAINS[job.domain]["hazards"],
                                       [c["name"] for c in job.cautions])
            self.session.event("hazards", photo=photo, hazards=found, think_ms=ms(start))
            if not found or job is not self.felix.job or job.phase in ("closed", "stopped"):
                return
            for hazard in found:
                caution = job.caution(hazard["name"], hazard["line"])
                await self.send({"type": "caution", "id": caution["id"], "text": caution["line"],
                                 "photo": photo_id, "x": hazard["x"], "y": hazard["y"]})
            job.save()
            now = time.monotonic()
            self._open_until = max(self._open_until, now + config.CONVERSATION_SECONDS)
            await self.send({"type": "listen", "follow_up": self._open_until - now})
        except Exception as error:
            log.exception("hazard check failed")
            self.session.event("error", during="hazards", error=repr(error))
        finally:
            self._checking_hazards = False

    async def _label(self, jpeg: bytes, photo: str | None, photo_id: str,
                     named_in: str | None = None, point: bool = True) -> None:
        """Label the parts in a photo, or with named_in, just the part that reply is about.
        point=False only labels it, for a pin, without pointing the arrow at it."""
        try:
            start = time.perf_counter()
            if named_in is None:
                domain = domains.DOMAINS.get(self.felix.job.domain or "", {})
                found = await parts.find(jpeg, self._labels, domain.get("work", ""),
                                         domain["parts"] if domain.get("work") else ())
            else:
                found = await parts.find_named(jpeg, named_in, self._labels)
            self.session.event("parts", photo=photo, parts=found, think_ms=ms(start),
                               named_in=named_in)
            complete = named_in is None
            if found or complete:
                # A complete list, even an empty one, tells the headset which of its
                # tags this photo should have shown but didn't: those are covered now.
                await self.send({"type": "labels", "photo": photo_id, "parts": found,
                                 "complete": complete})
            if not found:
                return
            new = [p["name"] for p in found if p["name"] not in self._labels]
            self._labels += new
            if new and self.felix.job.pins:
                await self.send_pins()  # a pin may have been waiting for its part's label
            if not point:
                return
            if named_in is None:
                # Felix may already be working on a part this photo just labeled.
                focus = (parts.match(self._target, self._labels)
                         or parts.mentioned(self._last_reply, self._labels))
            elif named_in == self._last_reply:
                focus = [p["name"] for p in found]  # he's already saying it
            else:
                self._named[named_in] = [p["name"] for p in found]  # say() points when he does
                focus = []
            if focus:
                await self.send({"type": "focus", "focus": focus})
        except Exception as error:
            log.exception("labeling failed")
            self.session.event("error", during="labels", error=repr(error))
        finally:
            if named_in is None:
                self._labeling = False

    async def say(self, text: str, audio: bytes | None = None, wanted: list[str] = (),
                  **context) -> None:
        """Say a line, pointing at what it's about: what you asked where to find (wanted),
        else the exact spot found for it, the part being worked on, or a part it names."""
        self._answering = True
        try:
            if audio is None:
                start = time.perf_counter()
                audio = await voice.speak(text)
                context["voice_ms"] = ms(start)
            await asyncio.sleep(max(0.0, self._speaking_until - time.monotonic()))  # a filler
            # The exact spot he means, when it's been found, beats the part as a whole.
            named = self._named.pop(text, [])
            focus = (list(wanted) or named or parts.match(self._target, self._labels)
                     or parts.mentioned(text, self._labels))
            speech = self.session.save_speech(audio, config.VOICE_SAMPLE_RATE)
            self.session.event("felix_says", text=text, audio=speech, focus=focus, **context)
            await self.send({"type": "say", "text": text,
                             "audio": base64.b64encode(audio).decode(),
                             "sample_rate": config.VOICE_SAMPLE_RATE,
                             "follow_up": config.CONVERSATION_SECONDS,
                             "focus": focus})
            self._last_reply = text
            self._speaking_until = time.monotonic() + len(audio) / 2 / config.VOICE_SAMPLE_RATE
            self._open_until = self._speaking_until + config.CONVERSATION_SECONDS
        finally:
            self._answering = False


@app.websocket("/ws")
async def headset_link(ws: WebSocket) -> None:
    await ws.accept()
    headset = Headset(ws)
    headset.session.event("connected", address=ws.client.host if ws.client else None)
    log.info("headset connected: session %s", headset.session.id)
    try:
        await headset.run()
    except WebSocketDisconnect:
        pass
    finally:
        log.info("headset disconnected: session %s", headset.session.id)
        await headset.close()


# -- the live view (this PC only: sessions hold photos of someone's home) -------

def require_local(client) -> None:
    if client is None or client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "The live view is only available on the server's own PC.")


def session_dir(session_id: str) -> Path:
    folder = (config.SESSIONS_DIR / session_id).resolve()
    if folder.parent != config.SESSIONS_DIR.resolve() or not folder.is_dir():
        raise HTTPException(404, "No such session.")
    return folder


@app.get("/", response_class=HTMLResponse)
def live_view(request: Request) -> str:
    require_local(request.client)
    return Path(__file__).with_name("monitor.html").read_text(encoding="utf-8")


@app.get("/api/sessions")
def list_sessions(request: Request) -> list[dict]:
    require_local(request.client)
    if not config.SESSIONS_DIR.is_dir():
        return []
    folders = sorted((p for p in config.SESSIONS_DIR.iterdir() if p.is_dir()), reverse=True)
    return [{"id": p.name,
             "events": sum(1 for _ in (p / "events.jsonl").open(encoding="utf-8"))}
            for p in folders if (p / "events.jsonl").exists()]


@app.get("/api/sessions/{session_id}/events")
def session_events(request: Request, session_id: str) -> list[dict]:
    require_local(request.client)
    lines = (session_dir(session_id) / "events.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


@app.get("/sessions/{session_id}/{kind}/{name}")
def session_file(request: Request, session_id: str, kind: str, name: str) -> FileResponse:
    require_local(request.client)
    if kind not in ("photos", "felix"):
        raise HTTPException(404, "No such file.")
    path = (session_dir(session_id) / kind / name).resolve()
    if path.parent.name != kind or not path.is_file():
        raise HTTPException(404, "No such file.")
    return FileResponse(path)


@app.websocket("/monitor")
async def live_feed(ws: WebSocket) -> None:
    if ws.client is None or ws.client.host not in ("127.0.0.1", "::1"):
        await ws.close(code=1008)
        return
    await ws.accept()
    queue = monitor.subscribe()
    try:
        while True:
            await ws.send_json(await queue.get())
    except WebSocketDisconnect:
        pass
    finally:
        monitor.unsubscribe(queue)
