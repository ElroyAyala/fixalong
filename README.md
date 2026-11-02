# fixalong

A hands-free repair guide in augmented reality. Put on the headset, say "Felix," and tell him what's wrong. Felix sees what you see, labels the parts in front of you, works out the cause with you one test at a time, and walks you through the fix, checking each step before the next one.

[![Watch the fixalong demo](https://img.youtube.com/vi/waCvphhuq08/maxresdefault.jpg)](https://youtu.be/waCvphhuq08)

**Demo video (3 minutes):** https://youtu.be/waCvphhuq08

Built for the Meta Global AI Developer Hackathon (Indie track, "Build for Your World"). Everything in this repo was built from scratch during the event, starting from an empty repo on October 29.

## What it does

- **Hands free.** Say "Felix" and talk. He waits until you pause, and if his answer is slow, a quick "one second" in his own voice tells you he heard.
- **Labels on the real parts.** Each photo from the headset's camera is searched for the job's parts, and the headset pins a name tag on each one in the room. An arrow marks the part Felix means, and he perches beside it.
- **A diagnosis you can follow.** A checklist beside the job lists the possible causes and rules them in or out, one test at a time: "Press down on the flapper. Did the running stop?"
- **Checked steps.** Once he finds the cause, the checklist becomes the repair steps. A separate verifier checks each one and answers "not yet" with a correction when it isn't right.
- **Safety first.** Felix gives the safety steps before your hands go in, and when a photo shows a hazard to you or the headset, like water nearby, he stops, puts up a caution sign next to it and waits for your "got it."
- **Done means proven.** The job closes only on proof: the tank refills and goes quiet. Felix sums up the cause and one tip, and says goodbye.

## Field test

Four first-timers from my family tried it on a real toilet with an installation mistake I staged. Each was left alone with the headset and one line to say. Whatever a run exposed was fixed before the next one.

| Run | First-timer | Staged fault | Result | Fixed before the next run |
|---|---|---|---|---|
| 1 | My son, 14 | Flapper ear off its peg | Stopped at "call a plumber" | Felix weighs test results together, asks again after an unsure answer, checks the user's own theory first, and goes at their pace |
| 2 | My 27-year-old | Flapper ear off its peg | Fixed | The caution sign goes up only when Felix brings it up |
| 3 | My daughter, 13 | Chain too tight | Fixed | Fewer false cautions, a second look at hedged answers, and a closeout that credits every change when the proof can't tell which one did it |
| 4 | My wife, not a VR fan | Chain too tight | Fixed, from greeting to goodbye in under three minutes | |

The job log of each run is in [docs/field-test/](docs/field-test/): the causes over time, each test and what it ruled out, and every verdict and caution.

## How Felix works

The Quest 3 is a thin client: it shows passthrough, Felix and the labels, takes photos and streams the mic. A Python server on a PC holds the API keys and runs Felix. Each turn is split across separate Muse Spark calls, each with one job:

| Call | Job |
|---|---|
| Talker | What Felix says, from the conversation, the latest photo and the job record. It has no tools, and at minimal effort it answers in about 1-2 seconds, fast enough to talk. |
| Scribe | Keeps the job record in the background through 11 function tools: causes, tests, steps, countdown pins, web look-ups and closing the job. Each test has to say beforehand what each result rules in or out, and every step gets a pass condition before you act. |
| Verifier | Grades each step against its pass condition, comparing the photo from when the step started with the one now. Felix never grades his own instructions. On 16 real headset moments, it gave the right verdict every time, in 1.4-5.6 seconds. |
| Labeler | Names the parts in each photo with a point on Meta's 0-1000 grid. The headset turns each point into a label on the real part with a depth raycast. |
| Hazard check | Watches each photo for hazards to you or the headset. |

The rules that matter live in code, not in a prompt. The server checks every tool call and refuses a test without declared outcomes or a step without a pass condition. It holds hands-inside steps until the safety check passes, holds the next step until a caution is acknowledged, and closes a job only on proof.

The design, and the reason behind each decision, is in [docs/plan.md](docs/plan.md). Felix's behavior is specified in [docs/felix-spec.md](docs/felix-spec.md).

## Built with Meta

Every model fixalong calls is a Meta model:

| Model | Where it runs | What it does |
|---|---|---|
| Muse Spark 1.3 | Meta Model API | The talker, scribe, verifier, labeler and hazard check, with Muse Spark's web search for look-ups |
| Muse Voice Transcribe | Meta Model API, realtime | Felix's ears. The headset mic streams to it in endpointing mode, so the model decides when you've finished a sentence, with "Felix" as a boosted keyword. |
| MMS-TTS (`facebook/mms-tts-eng`) | Open weights, on the PC's CPU | Felix's voice, about 0.3-0.7 seconds a line. The Meta Model API has no speech output. |

Everything else is a device or app feature, with no model behind it:

- **Meta Quest 3** in mixed reality: the Meta XR SDK 207 on OpenXR, the Passthrough Camera API for photos, the Mixed Reality Utility Kit's environment raycasts for depth, and hand tracking to pinch a checklist row or a caution sign.
- **Audio files:** Felix's quick fillers ("one second", "let me see") were made with MMS-TTS ahead of time (`server/make_fillers.py`), and the sound cues are short clips. The headset plays both as they are.

The field test and the demo video were recorded with an earlier voice. In the video, Felix's lines are re-dubbed with MMS-TTS: the same words at the same moments, taken from the session logs. His short fillers are the new ones, since MMS-TTS can't say "mm-hm" clearly.

## Run it yourself

You need a Meta Quest 3, a Windows PC on the same Wi-Fi and a Meta Model API key. The server downloads the MMS-TTS model (about 140 MB) from Hugging Face the first time it starts.

**Server** (Python 3.11):

```text
cd server
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

Paste your Meta key into `.env`, then check it and start the server:

```text
.venv\Scripts\python.exe check_meta.py
.venv\Scripts\python.exe -m uvicorn fixalong.app:app --host 0.0.0.0 --port 8765
```

Open http://localhost:8765 for the live view: what Felix hears, sees, says and decides, and which model made each call. Every session is recorded in `server/sessions/` and can be replayed in the live view, or run through the current Felix at the desk with `replay.py`.

**Headset** (Unity 6000.6.2f1 with Android Build Support):

1. Open `unity/` in Unity, on the PC that runs the server.
2. Choose **fixalong → Build Scene**. It builds the scene from code and bakes in this PC's address on the home network.
3. Choose **fixalong → Build APK**, and install `unity/Builds/fixalong.apk` on the Quest with `adb install`.
4. Launch fixalong, allow the camera, microphone and spatial data permissions, and say "Felix."

To connect over USB instead of Wi-Fi, run `adb reverse tcp:8765 tcp:8765`.

## Layout

| Folder | What |
|---|---|
| `server/` | Python server: Felix's calls, the job record and its checks, the voice relay and the live view |
| `unity/` | The Quest 3 app (Unity) |
| `docs/` | The plan, Felix's spec and the field test logs |

## License

fixalong is licensed under the [GNU Affero General Public License v3.0](LICENSE). If you run a modified version, including as a network service, you must share your changes under the same license. Third-party SDKs, packages and models (Unity, Meta XR SDK and others) keep their own licenses. Felix's voice model, MMS-TTS, is licensed CC-BY-NC 4.0, for non-commercial use only.
