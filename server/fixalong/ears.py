"""Felix's ears: the headset mic, relayed to Muse Voice Transcribe in realtime.

One transcription stream per headset session, in ENDPOINTING mode, so Meta's
model decides where each sentence ends. The stream only opens while audio is
flowing: Meta closes it if audio falls behind real time, which is also why the
headset sends silence while Felix talks instead of pausing.
"""

import asyncio
import contextlib
import json
import logging
import uuid
from collections.abc import Callable

import websockets

from . import config

log = logging.getLogger("fixalong.ears")


class Ears:
    def __init__(self, on_partial: Callable[[str], None], on_sentence: Callable[[str], None]):
        self._on_partial = on_partial
        self._on_sentence = on_sentence
        self._audio: asyncio.Queue[bytes] = asyncio.Queue(maxsize=50)
        self._task = asyncio.create_task(self._run())

    def hear(self, pcm: bytes) -> None:
        with contextlib.suppress(asyncio.QueueFull):
            self._audio.put_nowait(pcm)  # if the stream is reconnecting, old audio is dropped

    async def close(self) -> None:
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    async def _run(self) -> None:
        while True:
            first = await self._audio.get()  # (re)connect only once audio is flowing
            try:
                await self._stream(first)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                log.warning("transcription stream ended: %r", error)
            # Audio queued while reconnecting would arrive faster than real time.
            while not self._audio.empty():
                self._audio.get_nowait()

    async def _stream(self, first: bytes) -> None:
        url = f"{config.ASR_URL}?sessionId=fixalong-{uuid.uuid4()}"
        async with websockets.connect(url, open_timeout=15, max_size=None) as ws:
            await ws.send(json.dumps({
                "authorization": {"accessToken": f"Bearer {config.MODEL_API_KEY}"},
                "audioEncoding": "PCM_24KHZ",
                "model": config.ASR_MODEL,
                "mode": "ENDPOINTING",
                "partialMode": "CUMULATIVE",
                "emitAudioProgress": False,
                "keywords": [config.WAKE_WORD],
            }))
            ack = json.loads(await ws.recv())
            if "sessionId" not in ack:
                raise RuntimeError(f"handshake refused: {ack}")
            log.info("listening (transcription session %s)", ack["sessionId"])
            await ws.send(first)
            sender = asyncio.create_task(self._send(ws))
            try:
                async for message in ws:
                    if isinstance(message, bytes):
                        continue
                    event = json.loads(message)
                    kind = event.get("type")
                    if kind == "transcript":
                        self._on_partial(event["transcript"])
                    elif kind == "speechComplete":
                        # Empty when the speech had no words; it still means you stopped.
                        self._on_sentence(event["transcript"].strip())
                    elif kind == "error":
                        raise RuntimeError(event.get("message"))
            finally:
                sender.cancel()

    async def _send(self, ws) -> None:
        while True:
            await ws.send(await self._audio.get())
