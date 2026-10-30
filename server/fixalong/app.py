"""The headset connects here over one WebSocket; the live view runs here too.

Run from server/:

    .venv\\Scripts\\python.exe -m uvicorn fixalong.app:app --host 0.0.0.0 --port 8765

Then open http://localhost:8765 on this PC for the live view.

Headset messages are JSON text frames:

    headset -> server   {"type": "hello", "app": str, "device": str}
                        {"type": "photo", "image": "<base64 JPEG>"}
                        {"type": "log", "level": str, "text": str}
    server -> headset   {"type": "say", "text": str,
                         "audio": "<base64 16-bit mono PCM>", "sample_rate": int}
                        {"type": "status", "text": str}

Every connection is recorded as a session (see session.py).
"""

import base64
import json
import logging
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse

from . import config, felix, voice
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

async def say(ws: WebSocket, session: Session, text: str, **context) -> None:
    start = time.perf_counter()
    audio = await voice.speak(text)
    speech = session.save_speech(audio, config.VOICE_SAMPLE_RATE)
    session.event("felix_says", text=text, audio=speech, voice_ms=ms(start), **context)
    await ws.send_json({"type": "say", "text": text,
                        "audio": base64.b64encode(audio).decode(),
                        "sample_rate": config.VOICE_SAMPLE_RATE})


async def handle_photo(ws: WebSocket, session: Session, image_b64: str) -> None:
    jpeg = base64.b64decode(image_b64) if image_b64 else b""
    if not jpeg:
        await say(ws, session, "I didn't get a picture. Try pinching again.")
        return
    photo = session.save_photo(jpeg)
    session.event("photo", file=photo, kb=len(jpeg) // 1024)
    await ws.send_json({"type": "status", "text": "Taking a look..."})
    start = time.perf_counter()
    text = await felix.describe_photo(jpeg)
    await say(ws, session, text, photo=photo, think_ms=ms(start))


@app.websocket("/ws")
async def headset(ws: WebSocket) -> None:
    await ws.accept()
    session = Session()
    session.event("connected", address=ws.client.host if ws.client else None)
    log.info("headset connected: session %s", session.id)
    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            try:
                if kind == "hello":
                    session.event("hello", app=msg.get("app"), device=msg.get("device"))
                    await say(ws, session, felix.GREETING)
                elif kind == "photo":
                    await handle_photo(ws, session, msg.get("image", ""))
                elif kind == "log":
                    session.event("headset_log", level=msg.get("level"), text=msg.get("text"))
                else:
                    session.event("unknown_message", type=kind)
            except WebSocketDisconnect:
                raise
            except Exception as error:
                log.exception("failed handling %r", kind)
                session.event("error", during=kind, error=repr(error))
                await say(ws, session, "Sorry, something went wrong on my end. Try that again.")
    except WebSocketDisconnect:
        log.info("headset disconnected: session %s", session.id)
    finally:
        session.event("disconnected")
        session.close()


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
