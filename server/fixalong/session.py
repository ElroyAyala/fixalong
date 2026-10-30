"""Session recording: everything one headset connection does, kept on disk.

    server/sessions/<id>/
        events.jsonl   one JSON object per line: t (seconds since start), at, kind, ...
        photos/        every headset photo
        felix/         every line Felix speaks, as WAV
        mic.wav        everything the headset mic heard (silence while Felix talks)

Every recorded event is also pushed to the live view.
"""

import asyncio
import json
import time
import wave
from datetime import datetime

from . import config


class Monitor:
    """The browsers watching the live view."""

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._queues.discard(queue)

    def publish(self, message: dict) -> None:
        for queue in list(self._queues):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                pass  # a stalled browser misses events rather than slowing Felix down


monitor = Monitor()


class Session:
    def __init__(self) -> None:
        self.id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
        self.dir = config.SESSIONS_DIR / self.id
        (self.dir / "photos").mkdir(parents=True)
        (self.dir / "felix").mkdir()
        self._events = (self.dir / "events.jsonl").open("a", encoding="utf-8")
        self._start = time.monotonic()
        self._files = 0
        self._mic: wave.Wave_write | None = None

    def event(self, kind: str, **data) -> None:
        record = {"t": round(time.monotonic() - self._start, 3),
                  "at": datetime.now().isoformat(timespec="milliseconds"),
                  "kind": kind, **data}
        self._events.write(json.dumps(record) + "\n")
        self._events.flush()
        monitor.publish({"session": self.id, "event": record})

    def live(self, kind: str, **data) -> None:
        """An event for the live view only, not the record (like partial transcripts)."""
        monitor.publish({"session": self.id, "event": {
            "t": round(time.monotonic() - self._start, 3), "kind": kind, **data}})

    def record_mic(self, pcm: bytes) -> None:
        if self._mic is None:
            self._mic = wave.open(str(self.dir / "mic.wav"), "wb")
            self._mic.setnchannels(1)
            self._mic.setsampwidth(2)
            self._mic.setframerate(config.MIC_SAMPLE_RATE)
        self._mic.writeframes(pcm)

    def save_photo(self, jpeg: bytes) -> str:
        name = f"photos/{self._next():03d}.jpg"
        (self.dir / name).write_bytes(jpeg)
        return name

    def save_speech(self, pcm: bytes, sample_rate: int) -> str:
        name = f"felix/{self._next():03d}.wav"
        with wave.open(str(self.dir / name), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(sample_rate)
            out.writeframes(pcm)
        return name

    def close(self) -> None:
        if self._mic is not None:
            self._mic.close()
        self._events.close()

    def _next(self) -> int:
        self._files += 1
        return self._files
