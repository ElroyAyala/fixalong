"""Server settings: API endpoints, model IDs, and keys loaded from server/.env."""

import os
from pathlib import Path

from dotenv import load_dotenv

SERVER_DIR = Path(__file__).resolve().parent.parent
load_dotenv(SERVER_DIR / ".env")

# Meta Model API
META_BASE_URL = "https://api.meta.ai/v1"
META_MODEL = "muse-spark-1.3"
# How hard Felix, his scribe and the verifier think: more effort is more careful but slower.
# Felix answers out loud, so speed wins: in testing, "minimal" answered in 1-2 s with the
# same behavior as "low". The scribe works in the background. Felix waits for the verifier,
# and on 16 real headset moments "minimal" gave the right verdict every time in 1.4-5.6 s,
# against 2.5-10 s (and one wrong pass) for "low".
AGENT_EFFORT = os.environ.get("FIXALONG_AGENT_EFFORT", "minimal")
SCRIBE_EFFORT = os.environ.get("FIXALONG_SCRIBE_EFFORT", "low")
VERIFY_EFFORT = os.environ.get("FIXALONG_VERIFY_EFFORT", "minimal")
MODEL_API_KEY = os.environ.get("MODEL_API_KEY", "").strip()

# Felix's ears: Muse Voice Transcribe, streamed in realtime.
ASR_URL = "wss://api.meta.ai/v1/asr/realtime"
ASR_MODEL = "muse-voice-transcribe-1.0"
MIC_SAMPLE_RATE = 24000  # 16-bit mono PCM; the transcription model's native rate
WAKE_WORD = "Felix"
# Once you call Felix, he hears everything you say until this long after he last spoke.
CONVERSATION_SECONDS = 60
# Felix waits until you've been quiet this long before he answers, so he never cuts in.
PAUSE_SECONDS = 1.5
# If he hasn't answered this long after you finish, a quick "mm-hm" says he heard you;
# when he's checking your work, a "let me look" comes sooner. At most one per this many
# seconds, so it doesn't become a tic.
FILLER_SECONDS = 1.5
FILLER_CHECKING_SECONDS = 0.5
FILLER_GAP_SECONDS = 8
PHOTO_TIMEOUT_SECONDS = 3  # how long to wait for the headset's photo on a call
# While Felix waits for something he can see, like the lid set down on its towel, the
# headset takes a photo this often, for this long after he last spoke.
WATCH_SECONDS = 3
WATCH_FOR_SECONDS = 90
# A countdown that ran out shows "done" over its part this long, then goes.
PIN_DONE_SECONDS = 20
# Hazard checks run at most this often, since the headset photographs every few seconds while
# it watches.
HAZARD_GAP_SECONDS = 6

# Felix's voice (ElevenLabs). The voice ID isn't secret, so it lives here.
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_MODEL = "eleven_flash_v2_5"
FELIX_VOICE_ID = "cjVigY5qzO86Huf0OWal"  # Eric, an ElevenLabs stock voice: calm and patient
VOICE_SAMPLE_RATE = 24000  # 16-bit mono PCM, which Unity can play without decoding
# Steadier and a touch slower than ElevenLabs' defaults, for a calm Felix.
VOICE_SETTINGS = {"stability": 0.6, "similarity_boost": 0.75, "speed": 0.95}

# Every session is recorded here (events, photos, Felix's speech) for review
# and replay. Git-ignored: these are photos of someone's home.
SESSIONS_DIR = SERVER_DIR / "sessions"
# Each session's job as structured JSON (see job.py), for the eval. Git-ignored too.
LOGS_DIR = SERVER_DIR / "logs"
