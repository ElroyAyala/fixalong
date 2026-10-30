# fixalong plan

fixalong is a hands-free repair guide for Meta Quest 3. Its agent, Felix, lives in your room through passthrough. You tell him what's wrong, he looks through the headset's cameras, works out the cause, and builds a quest log: the steps to fix it, each with a safety gate or a check. He highlights the part to work on, waits while you do the step, then checks your work before moving on.

Built for the Meta Global AI Developer Hackathon, Indie track, "Build for Your World."

## The experience

1. You launch fixalong. Passthrough is on from the start, so you see your room.
2. Felix appears, a small floating companion, and asks what you're working on today.
3. You describe the problem: "Felix, my toilet keeps running."
4. You start each action yourself: "Felix, take a photo of my toilet." Felix identifies it out loud ("That's a two-piece toilet. You can lift the tank lid off.") and asks for what he needs to see next.
5. Once he knows the cause, Felix builds the quest log and guides you through it step by step, highlighting parts and checking your work.
6. Felix remembers where he last saw your tools, so "Felix, where's my screwdriver?" shows you the spot, even in a later session.

Everything happens in the headset, and Felix only acts when you call him.

## Decisions

| Area | Decision | Why |
|---|---|---|
| Engine | Unity 6000.6.2f1 (URP), OpenXR, Meta XR SDK v207 | Meta's passthrough camera, hand tracking and mixed reality tools are Unity-first. OpenXR is Meta's recommended plugin; the Oculus plugin is deprecated. |
| Demo repair | Running toilet | Ground level, so it's safe in a headset. Several possible causes, so the agent has to diagnose. Wasted water gives it real impact. |
| Agent | Felix, a small floating companion | Gives the "Felix arrives" moment without heavy art work. Not Disney's Fix-It Felix: no shared name or look. |
| Calling Felix | Say "Felix" | Hands stay free for the repair. Transcription runs all session and is cheap; the agent model only runs once you've called him. A pinch backup was dropped: the Quest menu gesture is also a pinch, so it took stray photos. |
| Felix's voice and manner | ElevenLabs on the server, in Eric, a calm stock voice. He talks like a patient tech-support pro and investigates before he suggests a fix. | The key stays on the server, and a stock voice imitates no real person. In testing, a sassy Felix rushed people toward fixes before he'd checked anything. |
| Where the agent runs | Python server on the PC; the headset is a thin client | Keeps the API key off the headset. The same server can move to the cloud later. |
| Moving around | Boundaryless app; the headset reaches the server over home Wi-Fi | You can walk off to get a tool without a boundary warning or a cable. Meta allows boundaryless mode for passthrough-only apps. A site off the home network would need the server in the cloud. |
| Repair know-how | Web search, plus reference videos we record ourselves | Covers any repair; our own videos keep the rights clean. |
| Felix's eyes | A photo with everything you say to him, never in the background | Calls stay yours to start, and every photo can also refresh tool memory. Felix ignores photos that don't show the job. Once the agent loop exists, he can ask for extra shots. |
| Conversation | Once you call him, the conversation stays open until a minute after he last spoke. He waits until you pause before he speaks, stays quiet when nothing needs an answer, and starts over if you add more before he answers. No interrupting him yet. | In testing, an 8-second window missed answers given after doing what he asked. The mic pauses while he speaks, so he never hears himself. |
| Tool memory | After highlights. Felix identifies a tool once; the Quest anchors its spot. | "Felix, where's my wrench?" asks the headset for the anchor, so Felix never has to watch. The Quest remembers the place, not the object: a moved tool shows where it was last marked or seen. |
| Game layer | Quest log now, XP later | The quest log is the agent's plan, so it's core. XP sits on top. |
| Build order | Thin headset loop early | The ideal experience is in the headset, and Unity is the unfamiliar part. |
| Repo | One repo: `unity/`, `server/`, `docs/` | One public link with everything. |
| Open-weights bonus | Skipped for now | Muse Glimmer needs more than the RTX 4070's 12 GB; revisit once the agent works. |

## Meta models

| Job | Model |
|---|---|
| Agent: reasoning, tool calls, diagnosis, quest log | Muse Spark 1.3 (`muse-spark-1.3`) |
| Vision: reading the scene, pointing at parts and tools, checking steps | Muse Spark 1.3 |
| Watching reference videos | Muse Spark (mp4 video input) |
| Highlighting the exact part | SAM 3.1 (`sam-3.1`) |
| Listening, including the "Felix" wake word | Muse Voice Transcribe (`muse-voice-transcribe-1.0`), realtime |

Muse Wonder (`muse-wonder-1.0`) is held in reserve in case Spark's planning falls short. Meta's API has no text-to-speech model, so the server gives Felix his voice with ElevenLabs.

## How it fits together

```text
Quest 3 (Unity)                    PC server (Python)              Meta Model API
  camera frames  ───────────────▶  session + agent loop  ───────▶  Muse Spark 1.3
  mic audio      ───────────────▶  voice relay           ───────▶  Muse Voice Transcribe
  Felix, quest log, highlights ◀── safety gates (code)   ───────▶  SAM 3.1
  Felix's voice (audio)        ◀── speech synthesis      ───────▶  ElevenLabs
                                   browser agent view
```

- **Headset:** shows passthrough and Felix, captures camera frames and mic audio, and plays back what the server sends: Felix's voice, the quest log panel and highlights. No decisions are made here, and no keys are stored here. It saves room positions as Quest spatial anchors. It reaches the server over home Wi-Fi, with USB (`adb reverse`) as a fallback.
- **Server:** one session per headset over a WebSocket. It runs the agent loop, holds the API keys, enforces the safety gates, turns Felix's words into audio, saves every headset photo, and serves a browser page that shows the agent's reasoning and tool calls live.

## The agent

### Phases

1. **Arrival:** Felix appears and asks what you're working on.
2. **Investigate:** you describe the problem and show Felix what he asks to see. He narrows down the cause.
3. **Plan:** he writes the quest log as structured JSON: ordered steps, each with a safety gate or a check.
4. **Guide:** one step at a time. Before the first hands-on step, he gives one short safety tip that fits the job. He explains each step, highlights the part, waits for "done," then checks the result.
5. **Complete:** a final test: flush, the tank refills, and the water stops running.
6. **Close out:** putting things back, cleaning up, and one thing to keep an eye on later.

### When Felix runs

Felix's agent loop only runs once you've called him by saying "Felix", and only while that conversation stays open. Within each turn he can take photos and call tools; between turns, only the cheap transcription runs.

### Tools Felix can call

| Tool | What it does | Model behind it |
|---|---|---|
| `look` | Takes a photo from the headset and asks a question about it | Muse Spark |
| `web_search` (built-in) | Finds instructions for any repair, with sources | Muse Spark |
| `watch_reference` | Asks a question about a reference video we recorded | Muse Spark |
| `highlight` | Finds a named part in the photo and outlines it | Muse Spark points, SAM 3.1 masks |
| `write_quest_log` | Commits the plan; the server validates it | Server code |
| `ask_user` | Asks a question and waits for a spoken answer | Muse Voice Transcribe |
| `check_step` | Takes a photo and asks the verifier whether the step is done | Muse Spark, as a separate verifier call |
| `remember_item` | Marks a tool in the photo; the headset anchors that spot in the room | Muse Spark points, spatial anchor on the Quest |
| `find_item` | Asks the headset where a tool's anchor is and points you to it | Spatial anchor on the Quest |

### Rules that live in code, not in the model

The API only supports `tool_choice: "auto"`, so the model always decides for itself whether to call a tool. Safety therefore can't rest on a prompt instruction:

- **Safety gates:** the server refuses to advance past a gated step without evidence. For example, the water must be off and the tank drained before the flapper comes out.
- **Separate verifier:** each step is checked by its own call, with structured yes/no output and a reason, comparing before and after frames. The agent that gave the instruction doesn't grade it.
- **Validated quest log:** every step must have a check, and the server rejects a plan that doesn't.
- **Stop conditions:** cracked porcelain, water on the floor, or anything beyond a safe DIY repair ends the quest with "call a professional."

### Design constraints from Meta's guidance

- Meta's passthrough guidance says not to make users read fine text through passthrough. Felix reads labels and part numbers from photos and says them out loud.
- Felix, the quest log panel and highlights stay out of the work area, so they never cover your hands.
- Without a boundary, nothing warns you about walls or stairs. Meta's boundaryless best practices apply, and Felix should never ask you to look at him while you're walking.

## Open research

Each item gets answered before the part that depends on it is built.

1. **Images in tool results:** can a `function_call_output` carry an image in Meta's Responses API, or does `look` have to attach the photo to a new user turn?
2. **Video timestamps:** can Muse Spark say where in a reference video a step happens, so Felix can play just that clip?
3. **Photo point to room position:** *answered.* Meta's `PassthroughCameraAccess.ViewportPointToRay()` turns a photo point into a ray from the camera, and MR Utility Kit's `EnvironmentRaycastManager.Raycast()` finds where it meets a real surface using live depth. Meta's CameraToWorld sample shows the pattern. Highlights and tool memory both use it.
4. **Latency:** how fast Muse Spark vision calls and SAM 3.1 return at each reasoning effort, which sets what a turn can afford. *Measured so far:* a Muse Spark turn with a photo takes about 2-3.5 s at low effort and 1.5 s at minimal. Meta's stored conversations (`previous_response_id`) added 8-10 s per follow-up, so the server keeps the history itself and attaches only the last two photos. SAM 3.1 is still to measure.
5. **Voice relay:** *answered.* The headset streams 24 kHz 16-bit mono PCM to the server, which relays it to `wss://api.meta.ai/v1/asr/realtime` in `ENDPOINTING` mode; Meta's model marks where each sentence ends (`speechComplete`). Audio must keep real-time pace or the stream closes (code 1008), so the headset sends silence while Felix talks rather than pausing.
6. **Wake word:** "Felix" is passed as a recognition keyword, and the server checks each finished sentence for his name. Still to measure: how reliably it's caught in a noisy bathroom.
7. **Felix's voice:** *decided:* ElevenLabs on the server, in Eric, a calm stock voice. Still to decide: whether to stream audio to the headset or send whole clips.
8. **Spatial anchors:** saving and reloading room positions across sessions (`OVRSpatialAnchor`) for tool memory.
9. **Unity setup:** *answered.* Unity 6000.6.2f1 from the URP blank template, the OpenXR plugin (1.19), and Meta XR Core SDK, MR Utility Kit and Interaction SDK at v207.0.1. Meta's Project Setup Tool applies the remaining settings. The camera supports up to 1280×1280 (1728×1728 on Horizon OS v209 and later), so the app reads the actual size at runtime instead of assuming one.

## Build order

1. Repo skeleton: folders, `.gitignore` files, README. *(done)*
2. Server talks to Meta: a live Muse Spark call with text and with an image. *(done)*
3. Thin headset loop: passthrough on launch, a placeholder Felix greets you out loud, a pinch takes a photo (later removed), the server sends it to Muse Spark, and Felix speaks the answer. Every session is recorded, with a live view and replay. *(done)*
4. Voice in: the headset streams its mic through the server to Muse Voice Transcribe realtime. "Felix" opens a conversation that stays open until a minute after he last spoke, everything you say to him comes with a photo, and he remembers the conversation within a session. *(done)*
5. The agent loop, worked on at the desk: replay saved headset photos and type answers in the browser agent view. Get Felix to diagnose and guide a running-toilet fix end to end, using web search and a reference video.
6. Safety gates, the validated quest log and the separate verifier.
7. Highlights on still images: a Muse Spark point becomes a SAM 3.1 mask, shown in the browser agent view.
8. Highlights anchored on the real part in the headset.
9. Tool memory: Felix remembers where he last saw each tool, using spatial anchors so it lasts between sessions.
10. XP and quest rewards.

Once the thin headset loop works, every photo it takes is saved, so agent work at the desk uses real headset images instead of phone photos.

## Compliance checklist

- Every model used is on the hackathon's list.
- The repo is public, and nothing from the earlier prototype is in it.
- Reference videos are our own recordings.
- Felix's name, look and voice don't borrow from Disney's Fix-It Felix or any real person.
- API keys (Meta, ElevenLabs) live in `server/.env`, which is git-ignored, and never go on the headset.
