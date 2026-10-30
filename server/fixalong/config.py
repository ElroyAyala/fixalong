"""Server settings: API endpoints, model IDs, and keys loaded from server/.env."""

import os
from pathlib import Path

from dotenv import load_dotenv

SERVER_DIR = Path(__file__).resolve().parent.parent
load_dotenv(SERVER_DIR / ".env")

# Meta Model API
META_BASE_URL = "https://api.meta.ai/v1"
META_MODEL = "muse-spark-1.3"
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
PHOTO_TIMEOUT_SECONDS = 3  # how long to wait for the headset's photo on a call

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
