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

from . import config, felix, parts, voice
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
        self.felix = felix.Felix(log_path=config.LOGS_DIR / f"{self.session.id}.json",
                                 record=self.session.event, on_update=self.on_job_update)
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
        self._named: dict[str, list[str]] = {}  # parts found for a reply he hasn't said yet
        self._last_reply = ""
        self._target = ""  # the part Felix is working on, from the job
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
            elif kind == "log":
                self.session.event("headset_log", level=msg.get("level"), text=msg.get("text"))
            else:
                self.session.event("unknown_message", type=kind)

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

    async def noticed_turn(self, seen: list[str], jpeg: bytes, photo: str | None,
                           photo_id: str) -> None:
        """Felix speaks up about something he saw while watching, like the lid set down."""
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
        if jpeg and not (parts.match(turn.target, self._labels)
                         or parts.mentioned(reply, self._labels)):
            # He may mean a part with no label yet, like a thin chain or the tank lid
            # before anything's labeled: look for it.
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
        await self.say(reply, audio=audio, voice_ms=voice_ms, said=said, photo=photo,
                       think_ms=think_ms)
        self.felix.said_it(reply)  # the scribe updates the job while he talks

    async def watch(self) -> None:
        """While Felix waits for something he can see, like the lid set down on its towel,
        the headset takes a photo every few seconds, so he catches it without asking. He
        only looks while nobody's talking, and stops a while after he last spoke."""
        while not self._closed:
            await asyncio.sleep(config.WATCH_SECONDS)
            if not (self.felix.watching() and self.idle()
                    and time.monotonic() - self._speaking_until < config.WATCH_FOR_SECONDS):
                continue
            jpeg, photo, photo_id = await self.request_photo()
            if not jpeg:
                continue
            try:
                seen = await self.felix.look(jpeg, photo)
            except Exception as error:
                self.session.event("error", during="watching", error=repr(error))
                continue
            if seen and self.idle():
                self.start_turn(self.noticed_turn(seen, jpeg, photo, photo_id), "noticed")

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

    async def _label(self, jpeg: bytes, photo: str | None, photo_id: str,
                     named_in: str | None = None) -> None:
        """Label the parts in a photo, or with named_in, just the part that reply is about."""
        try:
            start = time.perf_counter()
            if named_in is None:
                found = await parts.find(jpeg, self._labels)
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
            self._labels += [p["name"] for p in found if p["name"] not in self._labels]
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

    async def say(self, text: str, audio: bytes | None = None, **context) -> None:
        self._answering = True
        try:
            if audio is None:
                start = time.perf_counter()
                audio = await voice.speak(text)
                context["voice_ms"] = ms(start)
            await asyncio.sleep(max(0.0, self._speaking_until - time.monotonic()))  # a filler
            focus = (parts.match(self._target, self._labels) or parts.mentioned(text, self._labels)
                     or self._named.pop(text, []))
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
