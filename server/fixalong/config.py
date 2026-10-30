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

# Felix's voice (ElevenLabs). The voice ID isn't secret, so it lives here.
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_MODEL = "eleven_flash_v2_5"
FELIX_VOICE_ID = "iP95p4xoKVk53GoZ742B"  # Chris, a stand-in until a voice is picked
VOICE_SAMPLE_RATE = 24000  # 16-bit mono PCM, which Unity can play without decoding

# Every session is recorded here (events, photos, Felix's speech) for review
# and replay. Git-ignored: these are photos of someone's home.
SESSIONS_DIR = SERVER_DIR / "sessions"
