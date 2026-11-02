"""Felix's voice: Meta's MMS-TTS (open weights), run on this PC and returned as
16-bit mono PCM.

The model loads once, when the server starts, and a line takes about 0.3-0.7 s
on the CPU. Its alphabet is lowercase letters, apostrophes and hyphens: it reads
no punctuation and few digits. So numbers are spelled out, and each sentence and
clause is spoken on its own, with a short pause after it.

His fillers, a quick "one second" or "let me see" while he thinks, are clips made
ahead of time in the same voice (fillers/, made by make_fillers.py), so they
play at once.
"""

import asyncio
import random
import re
import threading
import wave
from pathlib import Path

import numpy as np
import torch
from transformers import AutoTokenizer, VitsModel

from . import config

_tokenizer = AutoTokenizer.from_pretrained(config.VOICE_MODEL)
_model = VitsModel.from_pretrained(config.VOICE_MODEL).eval()
_model.speaking_rate = config.VOICE_SPEAKING_RATE
_model.noise_scale = config.VOICE_NOISE
_model.noise_scale_duration = config.VOICE_DURATION_NOISE
_lock = threading.Lock()  # one line at a time

FILLERS_DIR = Path(__file__).with_name("fillers")

# The pause after each piece, by the punctuation that ends it (a dash ends a clause too).
PAUSES = {".": 0.32, "!": 0.32, "?": 0.32, ";": 0.25, ":": 0.2, ",": 0.14, "—": 0.14}
_PIECE = re.compile(r"[^.!?;:,—]+[.!?;:,—]*")

_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen "
         "fourteen fifteen sixteen seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _number(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else " " + _ONES[n % 10])
    if n < 1000:
        return _ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + _number(n % 100))
    if n < 1_000_000:
        return _number(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + _number(n % 1000))
    return " ".join(_ONES[int(d)] for d in str(n))  # a part or model number, digit by digit


def _spell(text: str) -> str:
    """Numbers and the few symbols Felix might say, as words."""
    text = re.sub(r"(\d+)\.(\d+)", lambda m: _number(int(m[1])) + " point "
                  + " ".join(_ONES[int(d)] for d in m[2]), text)
    text = re.sub(r"\d+", lambda m: " " + _number(int(m[0])) + " ", text)
    for symbol, words in (("%", " percent"), ("&", " and "), ("+", " plus ")):
        text = text.replace(symbol, words)
    return text


def _pieces(text: str) -> list[tuple[str, float]]:
    """The text as (words, pause after) pieces, split at sentence and clause ends."""
    text = re.sub(r"\s+[-–]\s+|–", "—", _spell(text).replace("\n", " "))
    pieces = []
    for match in _PIECE.finditer(text):
        piece = match[0].strip()
        if re.search(r"[A-Za-z]", piece):
            pieces.append((piece, PAUSES.get(piece[-1], PAUSES["."])))
    return pieces


def _trim(audio: np.ndarray, rate: int) -> np.ndarray:
    """Drop the model's silence at both ends of a piece, keeping a breath of it."""
    loud = np.flatnonzero(np.abs(audio) > 0.03 * (np.abs(audio).max() or 1.0))
    if not len(loud):
        return audio[:0]
    margin = int(0.03 * rate)
    return audio[max(0, loud[0] - margin):loud[-1] + margin]


def synthesize(text: str, seed: int = config.VOICE_SEED) -> bytes:
    """Text to 16-bit mono PCM at config.VOICE_SAMPLE_RATE. Blocking. The same text
    and seed always sound the same; another seed gives another take."""
    rate = _model.config.sampling_rate
    parts = []
    with _lock, torch.no_grad():
        torch.manual_seed(seed)
        for words, pause in _pieces(text):
            audio = _model(**_tokenizer(words, return_tensors="pt")).waveform[0].numpy()
            parts += [_trim(audio, rate), np.zeros(int(pause * rate), np.float32)]
    if not parts:
        return b""
    audio = np.concatenate(parts[:-1])  # no pause after the last piece
    peak = float(np.abs(audio).max()) or 1.0
    audio *= min(config.VOICE_PEAK / peak, 4.0)  # every line equally loud
    return (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()


async def speak(text: str) -> bytes:
    return await asyncio.to_thread(synthesize, text)


def _load(kind: str) -> list[bytes]:
    clips = []
    for path in sorted((FILLERS_DIR / kind).glob("*.wav")):
        with wave.open(str(path)) as clip:
            if (clip.getframerate(), clip.getnchannels(), clip.getsampwidth()) == \
                    (config.VOICE_SAMPLE_RATE, 1, 2):
                clips.append(clip.readframes(clip.getnframes()))
    return clips


# look: he's about to check your work ("Let me see"); plain: anything else ("One second").
_fillers = {kind: _load(kind) for kind in ("plain", "look")}
_last_filler = b""


def filler(kind: str) -> bytes:
    """A filler clip of that kind, never the one he just used. Empty if there are none."""
    global _last_filler
    clips = _fillers.get(kind) or []
    choices = [c for c in clips if c is not _last_filler] or clips
    _last_filler = random.choice(choices) if choices else b""
    return _last_filler
