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
| Calling Felix | Say "Felix"; a pinch is the backup | Hands stay free for the repair. Transcription runs all session and is cheap; the agent model only runs when you call him. |
| Felix's voice | ElevenLabs, generated on the server | A characterful voice, and the key stays on the server. A stock or designed voice, never one imitating a real person. |
| Where the agent runs | Python server on the PC; the headset is a thin client | Keeps the API key off the headset. The same server can move to the cloud later. |
| Repair know-how | Web search, plus reference videos we record ourselves | Covers any repair; our own videos keep the rights clean. |
| Tool memory | After highlights | It reuses the photo-to-room step that highlights need. |
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

- **Headset:** shows passthrough and Felix, captures camera frames and mic audio, and plays back what the server sends: Felix's voice, the quest log panel and highlights. No decisions are made here, and no keys are stored here. It saves room positions as Quest spatial anchors.
- **Server:** one session per headset over a WebSocket. It runs the agent loop, holds the API keys, enforces the safety gates, turns Felix's words into audio, saves every headset photo, and serves a browser page that shows the agent's reasoning and tool calls live.

## The agent

### Phases

1. **Arrival:** Felix appears and asks what you're working on.
2. **Investigate:** you describe the problem and show Felix what he asks to see. He narrows down the cause.
3. **Plan:** he writes the quest log as structured JSON: ordered steps, each with a safety gate or a check.
4. **Guide:** one step at a time. He explains the step, highlights the part, waits for "done," then checks the result.
5. **Complete:** a final test: flush, the tank refills, and the water stops running.

### When Felix runs

Felix's agent loop only runs when you call him, by saying "Felix" or pinching. Within that turn he can take photos and call tools; between turns, only the cheap transcription runs.

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
| `remember_item` | Saves where a tool appears in the photo as a spot in the room | Muse Spark points, spatial anchor |
| `find_item` | Shows where a tool was last seen | Server code, spatial anchor |

### Rules that live in code, not in the model

The API only supports `tool_choice: "auto"`, so the model always decides for itself whether to call a tool. Safety therefore can't rest on a prompt instruction:

- **Safety gates:** the server refuses to advance past a gated step without evidence. For example, the water must be off and the tank drained before the flapper comes out.
- **Separate verifier:** each step is checked by its own call, with structured yes/no output and a reason, comparing before and after frames. The agent that gave the instruction doesn't grade it.
- **Validated quest log:** every step must have a check, and the server rejects a plan that doesn't.
- **Stop conditions:** cracked porcelain, water on the floor, or anything beyond a safe DIY repair ends the quest with "call a professional."

### Design constraints from Meta's guidance

- Meta's passthrough guidance says not to make users read fine text through passthrough. Felix reads labels and part numbers from photos and says them out loud.
- Felix, the quest log panel and highlights stay out of the work area, so they never cover your hands.

## Open research

Each item gets answered before the part that depends on it is built.

1. **Images in tool results:** can a `function_call_output` carry an image in Meta's Responses API, or does `look` have to attach the photo to a new user turn?
2. **Video timestamps:** can Muse Spark say where in a reference video a step happens, so Felix can play just that clip?
3. **Photo point to room position:** *answered.* Meta's `PassthroughCameraAccess.ViewportPointToRay()` turns a photo point into a ray from the camera, and MR Utility Kit's `EnvironmentRaycastManager.Raycast()` finds where it meets a real surface using live depth. Meta's CameraToWorld sample shows the pattern. Highlights and tool memory both use it.
4. **Latency:** how fast Muse Spark vision calls and SAM 3.1 return at each reasoning effort, which sets what a turn can afford.
5. **Voice relay:** streaming the headset mic through the server to Muse Voice Transcribe realtime (24 kHz, 16-bit PCM), so the key stays on the server.
6. **Wake word:** catching "Felix" reliably in the realtime transcript (Transcribe's keyword hint helps) and ignoring speech that isn't for him.
7. **Felix's voice:** *decided:* ElevenLabs on the server. Still to pick: the voice, and whether to stream audio to the headset or send whole clips.
8. **Spatial anchors:** saving and reloading room positions across sessions (`OVRSpatialAnchor`) for tool memory.
9. **Unity setup:** *answered.* Unity 6000.6.2f1 from the URP blank template, the OpenXR plugin (1.19), and Meta XR Core SDK, MR Utility Kit and Interaction SDK at v207.0.1. Meta's Project Setup Tool applies the remaining settings. The camera supports up to 1280×1280 (1728×1728 on Horizon OS v209 and later), so the app reads the actual size at runtime instead of assuming one.

## Build order

1. Repo skeleton: folders, `.gitignore` files, README. *(done)*
2. Server talks to Meta: a live Muse Spark call with text and with an image. *(done)*
3. Thin headset loop: passthrough on launch, a placeholder Felix greets you out loud, a pinch takes a photo, the server sends it to Muse Spark, and Felix speaks the answer. The server saves every headset photo.
4. Voice in: Muse Voice Transcribe realtime, with "Felix" as the wake word.
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
