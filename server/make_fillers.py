"""Make Felix's filler clips in his own voice: a quick "one second" or "let me see"
that plays at once while he thinks. Replaces every clip in fillers/; listen to
the takes and delete any that sound off.

    .venv\\Scripts\\python.exe make_fillers.py
"""

import wave

from fixalong import config, voice

# look: he's about to check your work; plain: anything else. Words that sound like
# approval stay out of "look", so "alright" never comes before a "not yet." MMS-TTS
# garbles very short words ("mm-hm", "okay", "got it"), so these are short phrases
# that Muse Voice Transcribe heard right in every take.
FILLERS = {
    "plain": {"one-second": "One second.", "give-me-a-second": "Give me a second.",
              "one-moment": "One moment."},
    "look": {"let-me-see": "Let me see.", "let-me-check": "Let me check.",
             "let-me-take-a-look": "Let me take a look."},
}
TAKES = 2


def main() -> None:
    for kind, lines in FILLERS.items():
        folder = voice.FILLERS_DIR / kind
        folder.mkdir(exist_ok=True)
        for old in folder.glob("*.wav"):
            old.unlink()
        for name, text in lines.items():
            for take in range(1, TAKES + 1):
                pcm = voice.synthesize(text, seed=take)
                with wave.open(str(folder / f"{name}-{take}.wav"), "wb") as clip:
                    clip.setnchannels(1)
                    clip.setsampwidth(2)
                    clip.setframerate(config.VOICE_SAMPLE_RATE)
                    clip.writeframes(pcm)
                print(f"{kind}/{name}-{take}.wav  {len(pcm) / 2 / config.VOICE_SAMPLE_RATE:.1f} s")


if __name__ == "__main__":
    main()
