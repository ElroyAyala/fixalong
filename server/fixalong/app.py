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
    server -> headset   {"type": "say", "text": str, "audio": "<base64 16-bit mono PCM>",
                         "sample_rate": int, "follow_up": seconds}
                        {"type": "quiet", "follow_up": seconds}  Felix chose not to answer
                        {"type": "snap", "id": str}       take a photo now
                        {"type": "listening", "text": str} what Felix is hearing
                        {"type": "heard", "text": str}     what Felix is about to answer

follow_up is how long Felix keeps listening without his name: the
conversation stays open until CONVERSATION_SECONDS after he last spoke.

Every connection is recorded as a session (see session.py).
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

from . import config, felix, voice
from .ears import Ears
from .session import Session, monitor

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
        self.conversation = felix.Conversation()
        self.ears = Ears(on_partial=self.on_partial, on_sentence=self.on_sentence)
        self._send_lock = asyncio.Lock()
        self._turn: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()
        self._photo_requests: dict[str, asyncio.Future] = {}
        self._unanswered: list[str] = []  # what you've said to Felix that he hasn't answered
        self._answering = False  # he has decided what to say and is saying it
        self._open_until = 0.0  # the conversation is open (no name needed) until then
        self._speaking_until = 0.0
        self._last_partial = ""
        self._speech_started: float | None = None
        self._heard_at = 0.0  # when you last said anything

    async def run(self) -> None:
        while True:
            message = await self.ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                self.session.record_mic(message["bytes"])
                self.ears.hear(message["bytes"])
                continue
            msg = json.loads(message["text"])
            kind = msg.get("type")
            if kind == "hello":
                self.session.event("hello", app=msg.get("app"), device=msg.get("device"))
                self.start_turn(self.say(self.conversation.greet()), "greeting")
            elif kind == "photo":
                self.on_photo(msg)
            elif kind == "log":
                self.session.event("headset_log", level=msg.get("level"), text=msg.get("text"))
            else:
                self.session.event("unknown_message", type=kind)

    async def close(self) -> None:
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
        if felix.addressed(text) or self.conversation_open(self._speech_started):
            self.spawn(self.send({"type": "listening", "text": text}))

    def on_sentence(self, text: str) -> None:
        # What counts is when you started talking, not when the sentence ended.
        now = time.monotonic()
        started = self._speech_started or now
        self._last_partial = ""
        self._speech_started = None
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
        await self.send({"type": "heard", "text": " ".join(self._unanswered)})
        jpeg, photo = await self.request_photo()
        count = len(self._unanswered)
        said = " ".join(self._unanswered)
        start = time.perf_counter()
        reply = await self.conversation.reply(said, jpeg)
        think_ms = ms(start)
        if reply is None:
            del self._unanswered[:count]
            self.session.event("felix_quiet", said=said, photo=photo, think_ms=think_ms)
            await self.send({"type": "quiet",
                             "follow_up": max(0.0, self._open_until - time.monotonic())})
            return
        try:
            start = time.perf_counter()
            audio = await voice.speak(reply)
            voice_ms = ms(start)
            await self.until_you_pause()
        except asyncio.CancelledError:
            self.conversation.forget_last()  # you kept talking, so he never said it
            raise
        del self._unanswered[:count]
        await self.say(reply, audio=audio, voice_ms=voice_ms, said=said, photo=photo,
                       think_ms=think_ms)

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

    async def request_photo(self) -> tuple[bytes | None, str | None]:
        request = uuid.uuid4().hex[:8]
        future = asyncio.get_running_loop().create_future()
        self._photo_requests[request] = future
        try:
            await self.send({"type": "snap", "id": request})
            return await asyncio.wait_for(future, config.PHOTO_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            self.session.event("photo_timeout", id=request)
            return None, None
        finally:
            self._photo_requests.pop(request, None)

    async def say(self, text: str, audio: bytes | None = None, **context) -> None:
        self._answering = True
        try:
            if audio is None:
                start = time.perf_counter()
                audio = await voice.speak(text)
                context["voice_ms"] = ms(start)
            speech = self.session.save_speech(audio, config.VOICE_SAMPLE_RATE)
            self.session.event("felix_says", text=text, audio=speech, **context)
            await self.send({"type": "say", "text": text,
                             "audio": base64.b64encode(audio).decode(),
                             "sample_rate": config.VOICE_SAMPLE_RATE,
                             "follow_up": config.CONVERSATION_SECONDS})
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
