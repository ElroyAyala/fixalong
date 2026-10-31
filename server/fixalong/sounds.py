"""What the headset mic hears besides speech, as evidence for Felix.

The headset's mic is tuned for voices: in silence it sends exact zeros, and
a quiet trickle never gets through. A flush and the tank refilling do,
faintly: a steady sound, well below speech, that stops when the tank is full.
So a long run of quiet but not silent audio is a clue, like "something ran
for 40 seconds and stopped", though never proof of what it was.
"""

import array
import math
import time

from . import config

WINDOW_SECONDS = 0.5
SILENT_DB = -95.0  # below this, the mic is sending (near) zeros
SPEECH_DB = -55.0  # above this, it's speech or something loud up close
MIN_RUN_SECONDS = 15.0  # shorter runs were handling noise, like moving the lid; a refill ran 40-60 s
GAP_WINDOWS = 1  # a run survives one silent window
RECENT_SECONDS = 180.0  # older runs aren't worth mentioning


class Sounds:
    """Tracks runs of steady, quiet, non-speech sound in the mic stream."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._window = int(config.MIC_SAMPLE_RATE * WINDOW_SECONDS)
        self._pending = array.array("h")
        self._run_start: float | None = None
        self._run_last: float | None = None  # the last window that had sound
        self._quiet_windows = 0
        self._loud = 0
        self._windows = 0
        self.runs: list[tuple[float, float]] = []  # (start, end), finished runs

    def hear(self, pcm: bytes) -> None:
        self._pending.frombytes(pcm[: len(pcm) - len(pcm) % 2])
        while len(self._pending) >= self._window:
            samples = self._pending[: self._window]
            del self._pending[: self._window]
            self._add(_db(samples), self._clock())

    def _add(self, db: float, now: float) -> None:
        if db < SILENT_DB:
            self._quiet_windows += 1
            if self._run_start is not None and self._quiet_windows > GAP_WINDOWS:
                self._finish()
            return
        self._quiet_windows = 0
        if self._run_start is None:
            self._run_start, self._loud, self._windows = now - WINDOW_SECONDS, 0, 0
        self._run_last = now
        self._windows += 1
        self._loud += db > SPEECH_DB

    def _finish(self) -> None:
        start, end = self._run_start, self._run_last
        # Mostly quiet, not mostly talking: speech has its own quiet edges.
        if end - start >= MIN_RUN_SECONDS and self._loud <= self._windows * 0.3:
            self.runs.append((start, end))
        self._run_start = self._run_last = None

    def describe(self) -> str:
        """The latest steady sound, in a sentence for Felix, or "" if there's been none lately."""
        now = self._clock()
        ongoing = (self._run_start is not None and self._run_last - self._run_start >= MIN_RUN_SECONDS
                   and self._loud <= self._windows * 0.3)
        if ongoing:
            return (f"The headset mic has been picking up a steady quiet sound, maybe running "
                    f"water, for {self._run_last - self._run_start:.0f} s so far.")
        if not self.runs or now - self.runs[-1][1] > RECENT_SECONDS:
            return ""
        start, end = self.runs[-1]
        return (f"The headset mic picked up a steady quiet sound, maybe running water, for "
                f"{end - start:.0f} s; it stopped {now - end:.0f} s ago and has been quiet since. "
                "The mic only catches louder water, like a flush refilling, not a slow trickle.")


def _db(samples: array.array) -> float:
    rms = math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0.0
    return 20 * math.log10(max(rms, 0.01) / 32768)
