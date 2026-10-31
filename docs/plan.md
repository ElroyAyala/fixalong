# fixalong plan

fixalong is a hands-free repair guide for Meta Quest 3. Its agent, Felix, lives in your room through passthrough. You tell him what's wrong, he looks through the headset's cameras, works out the cause, and lays out the steps to fix it, each with a safety gate or a pass condition. He highlights the part to work on, waits while you do the step, then checks your work before moving on. His reasoning is on show: a checklist of possible causes that he rules in or out, one test at a time.

Built for the Meta Global AI Developer Hackathon, Indie track, "Build for Your World."

## The experience

1. You launch fixalong. Passthrough is on from the start, so you see your room.
2. Felix appears, a small floating companion, and asks what you're working on today.
3. You describe the problem: "Felix, my toilet keeps running." He asks what you've tried and sums up the problem in one sentence. He assumes you're new to this unless what you say shows otherwise, and checks before he skips the basics ("Sounds like the install's done. I'll skip the basics, okay?").
4. Before your hands go in the tank, he gives the safety steps and checks them by eye. If he spots a hazard, like water near your headset, an amber caution sign blinks next to it until you look at it and say "got it."
5. He labels the parts he sees and lists the possible causes on a panel beside him. Each test he asks for ("Push the flapper down with a finger. Does the running stop?") rules causes in or out, and the panel shows it. He tells you what each test told him: "That's what I needed."
6. Once he finds the cause, the panel becomes the repair steps. He highlights each part, waits for "done," and checks your work. If it isn't right yet, he says "Not yet" and what to change.
7. He closes the job only on proof: once the tank refills, you confirm it's quiet. Then he sums up the cause, the evidence, and one tip to keep it from happening again, asks if you're good to close up (the lid goes back on), and says goodbye when you are.
8. Felix remembers where he last saw your tools, so "Felix, where's my screwdriver?" shows you the spot, even in a later session.

Everything happens in the headset, and Felix only acts when you call him.

## The demo video

- **Main demo:** a real first-timer fixes the toilet with Felix. A teen who's at home in VR but has never opened a toilet tank gets a one-line opener and no hints. The toilet is staged with the most common mistake after installing a new kit: a chain that's too tight, or a flapper that isn't seated. The video says the fault was staged.
- **The other jobs as screenshots:** a highlight reel of where it's headed, getting harder as it goes: flat-pack furniture built from its paper manual, with Felix catching a panel put in backwards, then finding the hex key after forgetting where it was set down. It ends on Felix knowing when to stop, like refusing a gas line.
- **The rules:** the video is 3 minutes at most, and the first-timer's run takes about that, so it's the whole video. It opens with one line on what was built this week, which is all of it (a fresh repo). A few seconds of the live view, with the separate checker's verdicts, show the Meta models at work, for the judges. The rest of the submission talks shop: the choices behind Felix and why.

## Decisions

| Area | Decision | Why |
|---|---|---|
| Engine | Unity 6000.6.2f1 (URP), OpenXR, Meta XR SDK v207 | Meta's passthrough camera, hand tracking and mixed reality tools are Unity-first. OpenXR is Meta's recommended plugin; the Oculus plugin is deprecated. |
| Demo repair | Running toilet, then flat-pack furniture assembly | Toilet repair and unclogging are among the most-watched US how-to videos (about 25M and 20M views, Frontdoor, 2024), and plumbing is the most common home problem (34%, Hippo, 2025). A running toilet can waste about 200 gallons a day. It's at ground level, so it's safe in a headset, and it has several possible causes, so Felix has to diagnose. Flat-pack furniture shows the same Felix beyond repair. Nearly everyone has built a piece and put a panel in backwards, and its results are plain to see, so the separate checker can catch a real mistake. He reads the paper manual, labels the parts each step needs, and remembers where the hex key went. It's dry, light and done on the floor. Dropped: a drain cleaner job (its label calls for eye protection, and the headset isn't any), replacing a toilet supply line (too much risk of water), and a sink drain (kept for after the demo). The smoke alarm also moved to after the demo. PC, car, garage door, outlet and leak-hunt demos were considered and dropped earlier. |
| Agent | Felix, a small floating companion | Gives the "Felix arrives" moment without heavy art work. Not Disney's Fix-It Felix: no shared name or look. |
| Felix in the work | Three layers, each tested on the headset before the next. 1) When you look down, he comes down with you, riding near the top-left of your view, clear of your hands. 2) He looks at you most of the time, like someone talking with you: he glances at the part as he starts a line about it, takes a quick look now and then while you work, and looks back at you for the question. 3) When you look at the part he's pointing at, he goes to it: he shrinks to half size and perches beside it, to its left and a little above, and comes back when you look away. His caption doesn't follow him: it stays at a readable spot in your view, grows upward away from your work, and keeps the same apparent size near or far. | In testing, he stayed at eye level while you looked down into the tank, so you never saw him. Riding down with you fixed that, but up close he and his caption covered the work, and he stared at the part so long it felt odd. People follow where someone else looks, and with Felix at the part, seeing him and seeing the part take one glance instead of two. Every move has a job, so he stays a guide, not a mascot. |
| Felix watches | While Felix waits for something he can see, like the lid set down on its towel, the headset takes a photo every 3 seconds, while nobody's talking, for up to 90 seconds after he last spoke. When the photo shows it done, it ticks off and Felix speaks up on his own ("Nice, I see the lid set flat on the mat"). Photos taken while you talk about something else are checked in the background, so you never wait for a check you didn't ask for. | In testing, the tester set the lid down while looking into the tank, and Felix asked about it afterward. Every turn during the lid step also waited about 5 seconds for a check nobody asked for. Catching the action beats asking about it. |
| Waiting | When Felix asks you to wait, like letting the tank refill for a minute, a countdown floats over the part you're waiting on, he keeps listening through it, and when it ends he checks in on his own. Whether he's listening always shows: "I'm listening…" while he is, and "Say 'Felix' when you need me" once he isn't. | In testing, "watch it for a minute" left the tester unsure how long, and whether Felix was still listening. Both are built: the countdown is a pin (see the build order). |
| Calling Felix | Say "Felix" | Hands stay free for the repair. Transcription runs all session and is cheap; the agent model only runs once you've called him. A pinch backup was dropped: the Quest menu gesture is also a pinch, so it took stray photos. |
| Felix's voice and manner | ElevenLabs on the server, in Eric, a calm stock voice. He talks like a patient tech-support pro and investigates before he suggests a fix. His behavior is specified in [felix-spec.md](felix-spec.md). | The key stays on the server, and a stock voice imitates no real person. In testing, a sassy Felix rushed people toward fixes before he'd checked anything. |
| Showing his reasoning | One panel at a comfortable spot out of the work area. It doesn't follow Felix down to a part. While he diagnoses, it lists the possible causes (✓ ruled out, ? testing, ! cause found); once he finds the cause, it becomes the repair steps. | Judges must be able to see the reasoning, and one panel is one UI to build. |
| Who Felix assumes you are | A first-timer, unless what you say or show strongly suggests otherwise (the new kit is installed but still leaks). He checks before he skips the basics. Labels and highlights stay on for everyone; only how much he explains changes. | Assuming knowledge someone doesn't have loses them at the first step, and checking costs one sentence. |
| Encouragement | After each test, Felix says what your action told him ("That's what I needed. The running stopped, so it's the flapper."). A "not yet" comes with encouragement. No empty praise. | You're doing something hard and unfamiliar. Specific credit builds confidence and shows that the test mattered. |
| Hazard cautions | Every photo is also checked for hazards to you or the headset, like water near it. A new hazard gets an amber caution sign pinned next to it, with one short line from the model. It blinks until you acknowledge it: looking at it opens its line, and then you say "got it", or point at it and pinch. Then Felix says it calmly: if anything starts spraying, step back and take the headset off first, because you don't need it to turn the shutoff valve. Each hazard shows once per job unless it gets worse. | A wet headset is a dead headset. Warning before it happens beats assuming people know, and a calm sign doesn't scare anyone. Looking and speaking work with wet or full hands. Quest 3 has no eye tracking, so "looking" is head direction, as with the labels. |
| Showing things | Felix can put an image on the panel: a page of the maker's manual, a diagram, or a photo. He decides when it helps. How-to videos in the headset are deferred. | It works with what the model already does (web search, reading PDFs) instead of adding a separate flow for each kind of help. Videos weren't worth the effort, and YouTube's terms rule out playing other people's videos in the app. |
| Proof and listening | You're the proof: Felix asks whether you still hear it after the refill. He asks for a look only when what he'd see was a suspect, like the water level. Your clear report of the result passes unless the view plainly shows otherwise, and the view never fails a step for what it can't show, like how slack a hanging chain is from above. One report can pass several steps: "I flushed and it stopped" passes the step before the flush too. When the view can't show something, Felix asks you to confirm it instead of asking for a better view ("Did you flush it yet? I didn't hear it."), and your yes counts. "Not yet" is only for when the view plainly shows something's off, and only the verifier says it. After two "not yet"s on the same thing, your word settles it, and the log marks it as passed on your word. When the mic picks up the sound, a probe or a final check can also listen: Felix asks Muse Spark about the last seconds of mic audio. | In testing, the headset's mic stripped background sound, so a quiet hiss never reached the server. On the first headset run, the verifier asked for a chain's droop that a view from above can't show, and "not yet" looped even after the tester said the sound had stopped. A "not yet" should catch a real miss, not argue with someone who can hear the fix worked. On a later run, Felix said "not yet" on his own and asked for an awkward view of an unlabeled part until the tester quit. So the verifier now answers two plain questions per step (did they report it, does the view plainly contradict it) and the server decides. |
| Checking off | You can always check a step off yourself: point at its row on the checklist with either hand and pinch, or say "check it off" or "skip that." It passes on your word, along with every step before it, and Felix moves on. A dot shows where you're pointing, and a row lights up when it can be checked off. A low-risk safety check like the lid can be checked off the same way; a strict one still needs the verifier's eyes. If you're stuck on something you say is done, Felix tells you that you can. | In the run where the tester quit, nothing they could say got past a check Felix couldn't see. Checking off puts the last word with you. The pinch only counts while you point at a row with the Quest's own pointer, which isn't valid during the menu gesture, so a stray pinch like the ones that once took photos does nothing. |
| Finishing a job | After the closeout, Felix asks if you're good to close up, with the finishing touches (the lid back on, the towel away). He doesn't wait to see them done: when you say you're good, he says a short goodbye ("Nice work today. Say Felix if you need me.") and heads off: once he finishes talking, he rises and shrinks away with a woosh, and the checklist, labels and pins clear from the room. Saying "Felix" brings him back for a new job. If the conversation just ends after the fix, he heads off then too. | On the first run that reached "fixed," the end was awkward: Felix lingered with nothing to do, and the room stayed full of the job's labels. A later run asked "anything else?" with the lid still off, then left at "we're good" without confirming it. Asking "good to close up?" lets you finish on your own, and you can call him back if you need him. A clear exit marks the job as done, the way a person would pack up and leave. |
| Sound cues | Short cues, each heard from where it happens: a pop as a part label appears, a woosh when the checklist appears or moves to its next list, a click when a mark changes, a chime for the two big moments (the cause found and the job fixed), a blip from Felix the moment he hears his name, and a caution tone with each hazard sign. Kept quiet next to Felix's voice, and no sound for "not yet." | Sound tells you something happened, and where, without looking for it. Two chimes per job keep the big moments special; a sound for "not yet" would feel like a buzzer. |
| Where the agent runs | Python server on the PC; the headset is a thin client | Keeps the API key off the headset. The same server can move to the cloud later. |
| Moving around | Boundaryless app; the headset reaches the server over home Wi-Fi | You can walk off to get a tool without a boundary warning or a cable. Meta allows boundaryless mode for passthrough-only apps. A site off the home network would need the server in the cloud. |
| Repair know-how | Web search and the maker's manuals | Covers any repair. Reference videos were dropped: Felix can't pull from YouTube or show its videos, and the labels already show you the part. |
| Felix's eyes | A photo with everything you say to him, never in the background | Calls stay yours to start, and every photo can also refresh tool memory. Felix ignores photos that don't show the job. Once the agent loop exists, he can ask for extra shots. |
| Conversation | Once you call him, the conversation stays open until a minute after he last spoke. He waits until you pause before he speaks, stays quiet when nothing needs an answer, and starts over if you add more before he answers. No interrupting him yet. The moment he hears you, his caption shows your words and he glances at the part. If his answer is slow, a filler in his own voice says he heard you: "let me look" when he's checking your work, "mm-hm" or "okay" otherwise, at most one every 8 seconds and never the same clip twice in a row. | In testing, an 8-second window missed answers given after doing what he asked. The mic pauses while he speaks, so he never hears himself. On three headset runs, he took a median of 2.7-6.4 seconds to answer, and up to 10.6. His voice was only about half a second of that; the rest was the model thinking. The fillers are clips made ahead of time, so they play at once. Words that sound like approval stay out of the checking fillers, so "alright" never comes before a "not yet." |
| Part labels | Every photo Felix gets is also searched for the repair parts in view. Each part gets a name tag pinned on it in the room, and the part Felix talks about gets an arrow. New tags pop in with every name showing for a few seconds, then shrink to dots; a name comes back when you look near it. Tags hide when a newer photo no longer finds them (the lid went back on) or when you walk away. When Felix talks about a spot on a part, like the flapper's ears, a quick second look finds that exact spot, and a bigger arrow and a pulsing ring land on it. While he watches for the lid, each photo is labeled too, so the parts appear as soon as you look in. Muse Spark finds the parts today; SAM 3.1, prompted with the job's part names, takes over once it's measured. | You learn the names as you work and see exactly which part he means, without labels everywhere. Muse Spark's points were accurate on real headset photos. Thin parts like a chain are hard to spot, so Felix may point at what they attach to. |
| Tool memory | After part labels. Felix identifies a tool once; the Quest anchors its spot. | "Felix, where's my wrench?" asks the headset for the anchor, so Felix never has to watch. The Quest remembers the place, not the object: a moved tool shows where it was last marked or seen. |
| Game layer | None. fixalong is a tool: no XP, points or rewards. | People are doing something hard; they don't need one more thing to keep track of. Simple and friendly beats game-like. |
| Build order | Thin headset loop early | The ideal experience is in the headset, and Unity is the unfamiliar part. |
| Repo | One repo: `unity/`, `server/`, `docs/` | One public link with everything. |
| Open-weights bonus | Skipped for now | Muse Glimmer needs more than the RTX 4070's 12 GB; revisit once the agent works. |

## Meta models

| Job | Model |
|---|---|
| Agent: reasoning, tool calls, diagnosis, repair steps | Muse Spark 1.3 (`muse-spark-1.3`) |
| Vision: reading the scene, pointing at parts and tools, checking steps | Muse Spark 1.3 |
| Spotting hazards to you or the headset | Muse Spark 1.3 |
| Reading a maker's manual | Muse Spark (PDF input) |
| Finding and outlining parts, prompted with the job's part names | SAM 3.1 (`sam-3.1`) |
| Listening to the job: running water, a chirp | Muse Spark (audio input) |
| Listening, including the "Felix" wake word | Muse Voice Transcribe (`muse-voice-transcribe-1.0`), realtime |

Muse Wonder (`muse-wonder-1.0`) is held in reserve in case Spark's planning falls short. Meta's API has no text-to-speech model, so the server gives Felix his voice with ElevenLabs.

## How it fits together

```text
Quest 3 (Unity)                    PC server (Python)              Meta Model API
  camera frames  ───────────────▶  session + agent loop  ───────▶  Muse Spark 1.3
  mic audio      ───────────────▶  voice relay           ───────▶  Muse Voice Transcribe
  Felix, panel, highlights     ◀── safety gates (code)   ───────▶  SAM 3.1
  Felix's voice (audio)        ◀── speech synthesis      ───────▶  ElevenLabs
                                   browser agent view
```

- **Headset:** shows passthrough and Felix, captures camera frames and mic audio, and plays back what the server sends: Felix's voice, the checklist panel and highlights. No decisions are made here, and no keys are stored here. It saves room positions as Quest spatial anchors. It reaches the server over home Wi-Fi, with USB (`adb reverse`) as a fallback.
- **Server:** one session per headset over a WebSocket. It runs the agent loop, holds the API keys, enforces the safety gates, turns Felix's words into audio, saves every headset photo, and serves a browser page that shows the agent's reasoning and tool calls live.

## The agent

### How Felix runs a job

[felix-spec.md](felix-spec.md) specifies Felix's behavior, with each job's safety steps, refusals, parts, causes and proof. In short:

1. **Intake:** the symptom and what you've tried. He sums up the problem in one sentence, and assumes you're a first-timer unless you show otherwise. If you're not at it yet, he asks you to head over and show him.
2. **Safety gate:** the job's safety steps, checked by eye, before your hands go inside.
3. **Hazard cautions:** any time, a hazard to you or the headset gets a caution sign that blinks until you acknowledge it.
4. **Look and label:** the job's parts are found in each photo, and the headset pins labels on them.
5. **Hypotheses:** a ranked list of possible causes, each with a status and the evidence for and against it, shown on the panel.
6. **Probes:** actions for information, not repair. Each one states beforehand what Felix will look or listen for, and which causes each outcome supports or rules out. Afterwards, he tells you what it showed.
7. **Guide:** one action per instruction, with parts described by look and place, and a manual page or diagram on the panel when Felix judges it helps. Before any step that needs force, he checks the alignment first. Each step has a pass condition; when it fails, Felix says "Not yet," with encouragement and a specific correction.
8. **Proof and closeout:** the job closes only on the job's hard proof. Felix then sums up the cause, the evidence, what was done, and one tip to prevent it.

### When Felix runs

Felix's agent loop only runs once you've called him by saying "Felix", and only while that conversation stays open. Between turns, only the cheap transcription runs.

### Three calls, three jobs

Each turn splits Felix's work across separate Muse Spark calls (`server/fixalong/felix.py`):

1. **The verifier,** first when you say you're done or answer yes to his question, and in the background on other photos: did the current step or safety check pass? It sees the step's pass condition, your words, and the photos from before and now. Felix never grades his own instructions.
2. **The talker:** what Felix says, from your words, the photo, the conversation and the job's record. It has no tools, so it answers in plain speech, about 1-2 s after you stop talking.
3. **The scribe,** in the background while Felix talks: it brings the job's record up to date with what was just said, through tools the server checks. The checklist panel updates when it's done.

With tools in the same call, Muse Spark treated its words as a preamble ("I'll update the diagnosis") and needed a second round trip to answer. That doubled the wait to 5-17 s per turn. Splitting the talker from the scribe keeps Felix quick and his speech natural.

### Tools the scribe calls

The server checks every call (`server/fixalong/job.py`) and refuses bad ones, and the scribe retries with the reason.

| Tool | What it does |
|---|---|
| `update_job` | The problem in one sentence, the job type, and your experience with this repair |
| `set_causes` | The ranked possible causes, with priors and evidence; the panel shows them |
| `start_probe` | Declares a probe before you act: the instruction, the part, what to observe, and each outcome with the causes it supports or rules out |
| `finish_probe` | The probe's result and what it changed about each cause |
| `start_safety_check` | Felix gave the safety steps; the verifier checks them when you say you're done |
| `write_steps` | The repair steps for the confirmed cause, each one result with a short panel label and a pass condition |
| `pin` | A short note over a part in the headset, with a countdown when you're waiting on it; when a countdown runs out, Felix hears about it and checks in |
| `look_up` | A web search in the background (about 14 s), like a part size for a model number; the answer reaches Felix a turn or two later |
| `close_job` | Closes the job, once every step has passed |
| `stop_job` | Stops the job for a refusal or a stop condition; it stays stopped |

Still to build, each in its build step: `show` (a manual page on the panel), `listen` (sound as evidence), and SAM 3.1 `highlight` outlines. Cautions and tool memory turned out not to need tools of their own: every photo is checked for hazards, and tool memory works through the part labels.

### Rules that live in code, not in the model

The API only supports `tool_choice: "auto"`, so the model always decides for itself whether to call a tool. Safety therefore can't rest on a prompt instruction:

- **Safety gates:** the server refuses to advance past a gated step without evidence. For example, the water must be off and the tank drained before the flapper comes out.
- **Separate verifier:** each step is checked by its own call, with structured yes/no output and a reason, comparing before and after frames. The agent that gave the instruction doesn't grade it. A fail becomes Felix's "not yet."
- **Validated steps:** every step must have a pass condition, and the server rejects steps that don't.
- **Hazard cautions:** every photo is also checked for hazards, alongside the part labels. A step in a hazard's area waits until its caution is acknowledged.
- **Declared probes:** a probe must state its outcomes, and the causes each one supports or rules out, before it runs. The server rejects one that doesn't.
- **Proof to close:** a job closes only on the job's proof (for the toilet: you confirm it's quiet after the refill, plus a look at the water level when the level was a suspect), never on the agent's say-so.
- **Locked refusals:** gas, mains wiring and the other refusals in [felix-spec.md](felix-spec.md), plus each job's stop conditions (cracked porcelain, water on the floor, a stuck shutoff valve). Once one triggers, the server locks it for the session, so no one can talk Felix past it. *Built so far:* the scribe's `stop_job` locks the job, and Felix's record says STOPPED from then on. *Still to build:* a separate check that watches every turn for them.
- **Safety gate:** each job's gate checks must pass the verifier before the server accepts a hands-inside probe or step. For the toilet, the lid must be off and set down safely. A view of the open tank counts, since the lid is out of view once you're looking in; it fails only if the lid shows somewhere unsafe, like balanced on the bowl. A low-risk check like the lid can also pass on your clear word. The server notices the safety steps in Felix's own words, so the watching starts even if the scribe misses them.

### Session log and eval

Every session also writes a structured log to `server/logs/`: the problem, safety checks, hazard cautions and when each was acknowledged, hypotheses over time, probes and their results, every verification attempt including each "not yet," the final diagnosis, and timestamps. It's git-ignored like `server/sessions/`, since it holds what people say at home. The eval reads these logs, and its summary numbers go in the README.

### Design constraints from Meta's guidance

- Meta's passthrough guidance says not to make users read fine text through passthrough. Felix reads labels and part numbers from photos and says them out loud.
- The checklist panel and highlights stay out of the work area, so they never cover your hands. When Felix goes to a part, he perches beside it, never between your eyes and the part or where your hands go, and just above the real surface so he doesn't sink into the porcelain. His captions stay at a comfortable reading spot instead of following him down.
- Felix moves in short, smooth glides: to the part when you look at it, and back when you look away. He holds still while you look around a little, so he never chases your head.
- Without a boundary, nothing warns you about walls or stairs. Meta's boundaryless best practices apply, and Felix should never ask you to look at him while you're walking.

## Open research

Each item gets answered before the part that depends on it is built.

1. **Images in tool results:** *answered.* Yes: a `function_call_output` can carry `input_image` parts, and Muse Spark reads the photo. In a test, it named the flapper and the fill valve cap colors correctly, in about 3.6 s at low effort. The server echoes the previous output items, reasoning included, instead of using `previous_response_id`.
2. **Video timestamps:** *dropped,* along with reference videos.
3. **Photo point to room position:** *answered.* Meta's `PassthroughCameraAccess.ViewportPointToRay()` turns a photo point into a ray from the camera, and MR Utility Kit's `EnvironmentRaycastManager.Raycast()` finds where it meets a real surface using live depth. Meta's CameraToWorld sample shows the pattern. Part labels use it now; tool memory will too. It needs the spatial data permission (`com.oculus.permission.USE_SCENE`).
4. **Latency:** how fast Muse Spark vision calls and SAM 3.1 return at each reasoning effort, which sets what a turn can afford. *Measured so far:* a Muse Spark turn with a photo takes about 2-3.5 s at low effort and 1.5 s at minimal. Meta's stored conversations (`previous_response_id`) added 8-10 s per follow-up, so the server keeps the history itself and attaches only the last two photos. With the job's record added, the talker answers in about 1-2 s at minimal effort (up to 5 s), with the same behavior as low effort in desk tests. The verifier adds 2-3 s on the turns it runs. The first call of a session took about 12 s, so the server warms Muse Spark up while Felix says hello. A built-in web search takes about 14 s, so it runs in the background. SAM 3.1 is still to measure.
5. **Voice relay:** *answered.* The headset streams 24 kHz 16-bit mono PCM to the server, which relays it to `wss://api.meta.ai/v1/asr/realtime` in `ENDPOINTING` mode; Meta's model marks where each sentence ends (`speechComplete`). Audio must keep real-time pace or the stream closes (code 1008), so the headset sends silence while Felix talks rather than pausing.
6. **Wake word:** "Felix" is passed as a recognition keyword, and the server checks each finished sentence for his name. Still to measure: how reliably it's caught in a noisy bathroom.
7. **Felix's voice:** *decided:* ElevenLabs on the server, in Eric, a calm stock voice. Still to decide: whether to stream audio to the headset or send whole clips.
8. **Spatial anchors:** saving and reloading room positions across sessions (`OVRSpatialAnchor`) for tool memory.
9. **Unity setup:** *answered.* Unity 6000.6.2f1 from the URP blank template, the OpenXR plugin (1.19), and Meta XR Core SDK, MR Utility Kit and Interaction SDK at v207.0.1. Meta's Project Setup Tool applies the remaining settings. The camera supports up to 1280×1280 (1728×1728 on Horizon OS v209 and later), so the app reads the actual size at runtime instead of assuming one.
10. **SAM 3.1 for labels:** each call takes one noun phrase, so each part name is its own request (Meta's "Media segmentation" guide). Still to learn: how to read its box and mask output, the latency, and how well it finds toilet parts like the flapper and the fill valve.
11. **Listening:** *partly answered.* Muse Spark 1.2 and 1.3 accept WAV as an `input_audio` part and transcribed speech correctly, though both claimed they couldn't hear audio. Meta's docs recommend 1.2 for audio. The bigger problem is the headset. Between words, the recorded mic is nearly silent (peaks of about 20 out of 32,767), even while the toilet was hissing, so the headset's processed mic strips background sound. Still to try: an unprocessed mic source on Quest, and whether loud sounds like a flush or a smoke alarm's chirp get through.

## Build order

1. Repo skeleton: folders, `.gitignore` files, README. *(done)*
2. Server talks to Meta: a live Muse Spark call with text and with an image. *(done)*
3. Thin headset loop: passthrough on launch, a placeholder Felix greets you out loud, a pinch takes a photo (later removed), the server sends it to Muse Spark, and Felix speaks the answer. Every session is recorded, with a live view and replay. *(done)*
4. Voice in: the headset streams its mic through the server to Muse Voice Transcribe realtime. "Felix" opens a conversation that stays open until a minute after he last spoke, everything you say to him comes with a photo, and he remembers the conversation within a session. *(done)*
5. The agent loop, worked on at the desk with `replay.py` on saved headset photos: intake, causes and probes, the checklist panel in both modes, and the structured session log. Felix diagnoses and guides a running-toilet fix end to end. *(done, and run on the headset four times; each run's problems were fixed and replayed at the desk)*
6. Safety gates, hazard cautions and the caution sign, locked refusals, validated steps, and the separate verifier with "not yet." *(the safety gate, validated steps, the verifier and the stop lock are done, reworked after the first headset run: the gate is checked on every photo until it passes and ticks off on the panel, a question about it isn't graded as a claim, and your word settles a step or check after two "not yet"s. Hazard cautions and the separate refusal check are next.)*
7. Part labels and an arrow: Muse Spark names the parts in each photo with a point on each, the headset pins a name tag on each part with a depth raycast, and an arrow marks the part Felix names. The live view draws the labels on each photo. *(done; after the second headset run, new labels land one by one over about 2 seconds, with a pop each, and their names fade to dots about 2 seconds after the last one lands)*
8. Felix in the work, one layer at a time: he stays in view when you look down, he glances at the part he names, then he goes to the part. Headset only: the server already says which part he means. *(layers 1 and 2 tested: he's easy to see now, but up close he and his caption covered the work, and he looked at the part too long. Reworked: layer 2 glances like a person instead of staring, and layer 3 is built: he goes to the part and his caption stays readable in your view. All three layers tested: the tester liked the perch and the glances.)*
9. Pins and waiting: Felix can pin a short note or a countdown over any labeled part, and he decides when. Examples: the tank refilling after a flush, a drip check on a joint you just tightened, "water should stop about here" at the overflow tube, or each tire's pressure as you finish it. A countdown keeps him listening, and he checks in when it ends. A drawn fill line was considered and dropped: depth readings on water and inside a tank are too unreliable to draw a line you'd trust, so a pin marks the spot instead. *(built, not yet tested on the headset. At the desk, the scribe pinned a 60-second "Refilling" countdown over the fill valve for "give the tank about a minute to refill," and "Water stops here" on the overflow tube, and nothing for ordinary lines. A pin hangs on a thin stem above its part and keeps its size from across the room; Felix keeps listening until a minute after a countdown ends.)*
10. Placing things: the checklist settles beside the job once Felix knows where it is, at about chest height and turned toward you, and stays there when you walk off. Point at its title and pinch and hold to move it anywhere; pinch and drag its corner to resize it. In the fifth headset run, the tester went to get a light and the checklist came along. Felix keeps riding with you: the tester said he already does well going back and forth. *(built, not yet tested on the headset)*
   - If there's room and a real demo need: grab Felix and set him down somewhere, and he says something playful about it ("Careful, fragile merchandise!"). He stays at that spot, pops out to point something out, then goes back.
11. Hazard cautions and the flat-pack job: every photo is checked for hazards (the caution sign and tone; say "got it" or pinch it to acknowledge). *(Cautions built, not yet tested on the headset. At the desk, the check flagged the open tank in a photo from the seventh run ("Water nearby. Keep the headset clear.") and nothing in photos without water. It once took the blue fill valve cap for a cleaner tablet; the wording now rules that out. After "got it," Felix said: "Since we're near water, if anything starts spraying, step back and take the headset off first." The flat-pack job is built at the desk, untested with real furniture: a spoken run went from the manual's first page to three steps, each passed on the user's word, then the proof ("I pushed the top corner and it doesn't wobble"), the anti-tip strap at close-up, and goodbye. The checklist says "Built!" at the end.)* The flat-pack job follows a manual instead of finding a cause. Felix reads the page you hold up, turns it into checked steps, and labels the parts and hardware each step needs ("the two long screws from bag C"). The checker catches what's plain to see: a panel's finished edge facing in, a cam lock not turned, a screw in the wrong hole. Cautions with a real reason: a tall piece gets its anti-tip strap to the wall, a heavy panel takes two people, and a drill strips particleboard where a hex key won't. The staged mistake is a panel put in backwards. The store's brand stays out of the video. If there isn't room for everything, this job is what goes: the toilet carries the story.
12. Tool memory: tools and parts you set down get labels like the job's parts and keep them, and "where's the hex key?" points at it. The flat-pack job is the test: the hex key and the hardware bags end up all over the floor. It's in the highlight-reel screenshots. In the second headset run, the tester asked "where's the lid?" after the fix, and Felix could only recall what they'd said. *(built, not yet tested on the headset. In the flat-pack job, the labels include tools and loose hardware set down nearby. Asking where something is points the arrow at it from anywhere in the room, with the tag growing with distance, and an arrow at the edge of your view leads the way when it's off to the side or behind you. Felix says "I've marked your hex key for you, just follow the arrow," or, with no label, asks you to look around slowly so he can spot it. Asking for tools in the toilet's labels cost it the overflow tube in testing, so the toilet's labels stay as they were.)*
13. Hands as context, if there's room: which labeled part each hand is near goes to Felix with each turn, and a hand inside the tank before the safety gate passes gets a caution. Never proof: hand tracking drops out in water and with gloves on. *(Recommended to skip: hand tracking gives the wrist, not the fingertips, and the tank's parts sit 5-10 cm apart, so Felix would often name the wrong part.)*
14. Polish and the demo video.

After the demo, if there's room: coming back after a break (the job, the conversation and anchored labels survive taking the headset off), SAM 3.1 outlines prompted with the job's part names, the sink drain job (the stopper and the P-trap, without chemicals), the smoke-alarm job, showing a manual page or diagram on the panel, the eval (scoring recorded sessions; the numbers go in the README), and listening through an unprocessed mic. *(Listening is partly answered: a slow trickle records as exact zeros, but a flush and the tank refilling come through faintly as a steady sound, about 40-60 seconds long, well below speech. The server already tracks those runs and tells Felix and the verifier.)*

Once the thin headset loop works, every photo it takes is saved, so agent work at the desk uses real headset images instead of phone photos.

## Compliance checklist

- Felix's thinking, seeing and hearing run on Meta's models (Muse Spark and Muse Voice Transcribe). His voice is ElevenLabs, because Meta's list has no text-to-speech model; the rules require meaningful use of Meta's models, not Meta's models only.
- The ElevenLabs plan allows Felix's voice in a public demo video (free plans require attribution).
- The repo is public, and nothing from the earlier prototype is in it.
- Felix's name, look and voice don't borrow from Disney's Fix-It Felix or any real person.
- API keys (Meta, ElevenLabs) live in `server/.env`, which is git-ignored, and never go on the headset.
