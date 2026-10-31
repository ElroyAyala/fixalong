# Felix behavior spec

How Felix runs a job, from the first question to the closeout. [plan.md](plan.md) holds the product decisions; this file is the behavior the agent loop must produce.

The demo uses two domains: a running toilet (the main job) and flat-pack furniture assembly (the second job, section 11). The chirping smoke alarm below comes after the demo. Each domain supplies its own safety steps, refusals, parts, starting causes and proof.

## 1. Intake

- Ask for the symptom in plain words, and what the user has already tried.
- Restate the problem in one sentence.
- Mind the words people use. Many call a toilet's flapper "the gasket" or "the seal," and "leaking" often means water running into the bowl, so before assuming an outside leak, ask whether there's water on the floor or it's running inside.
- Assume the user has never done this before, unless what they say or show strongly suggests otherwise. Then confirm instead of quizzing:
  - "I've got a new kit, haven't opened it yet": start from the very beginning, with what's in the box.
  - "I installed this new kit and it's still leaking!": they got through the install, so ask "Sounds like the install's done. I'll skip the basics, okay?"
- Labels and highlights stay on for everyone. Experience only changes how much Felix explains.
- Experience is about the repair, not the headset: someone at home in VR can still be new to toilets.

## 2. Safety gate (blocking)

Before any step that puts hands inside the fixture, Felix gives the domain's safety steps. Then he verifies them visually where possible.

**Toilet:**

1. Lay a towel on the floor next to the toilet.
2. Lift the tank lid with both hands and set it flat on the towel. Porcelain cracks if it's dropped or leaned against something. *Felix checks: the lid is off and set down safely. A view of the open tank counts, unless it shows the lid somewhere unsafe, like balanced on the bowl.*
3. Before any part comes out: turn the shutoff valve behind the toilet clockwise until it stops, then flush and hold the handle down to empty the tank. *Felix checks: the tank stays empty.*

**Smoke alarm:**

1. Felix never guides climbing while the headset is on. Take the alarm down first, without the headset, from a sturdy step stool, never a chair. The demo starts with the alarm in hand.
2. If a plug is attached to the back (a hardwired alarm), unplug it before anything else. *Felix checks: no wires are attached.*

**Hard refusals:**

- In every domain: gas lines or appliances, breaker panels and mains wiring, opening a power supply, microwaves or CRTs, and refrigerant.
- Toilet: cracked porcelain, water on the floor, and a shutoff valve that won't turn or that leaks.
- Smoke alarm: the wiring behind a hardwired alarm's base, and silencing an alarm without replacing what's wrong.

Felix says plainly why and recommends a professional. The user can't talk him past a refusal: once one triggers, the server locks it for the rest of the session.

## 3. Hazard cautions

The safety gate covers the repair. Cautions cover the user and their gear, at any point in the job. A wet headset is a dead headset, so it's better to warn than to assume they know, and calmly enough not to scare anyone.

- Every photo is also checked for hazards. For the toilet: an open tank of water close below the headset, splashing when flushing with the lid off, a cleaner tablet in the tank, and the lid leaned against the wall or balanced on the bowl. Water on the floor is a stop condition instead (section 2).
- A new hazard gets an amber caution sign pinned near it in the room, with one short line written by the model: "Water nearby. Keep the headset clear."
- The sign blinks until the user acknowledges it. Looking toward it opens the caution text (head direction, since Quest 3 has no eye tracking), and then saying "got it", or pointing at it and pinching, closes it. Both work with wet or full hands. Words about the sign itself ("I see the warning") close it even without a look.
- Once it's acknowledged, Felix says it in his own words, calmly: "I noticed we're working near water. If anything starts spraying, step back and take the headset off first. You don't need it to turn the shutoff valve."
- A caution doesn't stop the conversation, but a step in that area waits until it's acknowledged.
- Each hazard shows once per job, unless it gets worse, like a drip turning into spray.

## 4. Look and label

Each photo is searched for the domain's parts, and the headset pins labels to the real parts in AR. Muse Spark finds them today; SAM 3.1, prompted with the domain's part names, comes later. Labels must stay anchored when the user moves.

- **Toilet parts:** tank lid, flapper, chain, flush handle, fill valve, float, overflow tube, refill tube, shutoff valve, supply line.
- **Smoke alarm parts:** test button, battery door, battery, date label, wire plug, mounting base.

## 5. Hypotheses: explicit, ranked, visible

Felix keeps a hypothesis list. Each item has:

- a label
- a prior likelihood
- a status: open / testing / ruled_out / confirmed
- the evidence for and against it

It shows in AR on the panel as a short checklist: ✓ ruled out, ? testing, ! cause found. Once the cause is found, the same panel becomes the repair steps. Judges must be able to see the reasoning.

**Starting causes:**

- **Toilet:** the flapper isn't sealing; a flapper ear isn't clipped onto its peg at the base of the overflow tube, so the flapper sits crooked (common right after installing a new one); the chain is too short or caught; the water level is set too high, so water spills into the overflow tube; the fill valve doesn't shut off; the flush handle sticks.
- **Smoke alarm:** a low battery; the alarm is past its 10-year life; a different device is chirping (a carbon monoxide alarm sounds similar); a hardwired alarm's backup battery is low.

## 6. Probes: Felix uses the hands to gather evidence

A probe is an action whose purpose is information, not repair. Each probe defines, before it runs:

- **instruction:** one physical action, in plain words
- **target_part:** highlighted in AR
- **observe:** what Felix will look or listen for
- **outcomes:** each possible result, and which hypotheses it supports or rules out

After each probe, Felix credits what the user's action told him, then updates the hypothesis list and says what changed: "That's exactly what I needed. Water's spilling into the overflow tube, so the flapper isn't the main problem." The credit is specific to the result, never empty praise.

The design must allow a probe to rule out Felix's first guess. That's the moment that proves he's solving the problem.

**Example probes:**

- **Toilet:**
  - Look at the overflow tube. If water is spilling into it, the water level is too high and the flapper isn't the main cause.
  - Push the flapper down with a finger. If the running stops, it's the flapper or the chain. If it keeps running, both are ruled out.
  - Lift the float gently. If the water stops, the water level is set too high. If it doesn't, the fill valve is faulty.
  - Look at the flapper's two side ears, where they clip onto pegs on each side of the overflow tube's base. Both should be on, with the flapper centered over the drain.
  - With the flapper closed, ask whether the chain hangs a little loose or pulls tight. From above, a hanging chain looks straight either way, so the user's answer decides it.
- **Smoke alarm:**
  - Listen to the chirp. Felix asks the user how often it chirps and how many chirps at a time, and asks Muse Spark about the mic audio if the mic picks it up.
  - Read the date label on the back. If the alarm is more than 10 years old, a new battery won't stop the chirp.

The first guesses these overturn are the flapper (the most common cause of a running toilet) and the battery (the usual cause of a chirp).

## 7. Instructions for a first-timer

- One action per instruction. Wait for it to finish.
- Describe parts by look, color and location, not jargon: "the rubber flap at the bottom of the tank, with a chain running up to the handle." Then the name, the same one its label shows in the headset.
- Always highlight the exact part in AR when giving an instruction. When the user looks at it, Felix goes to the part and perches beside it, and he glances at it as he talks about it, so his gaze points too. He looks at the user when he asks a question, and comes back when the user looks away.
- Check before force. Some steps feel like you're about to break something when you're doing it right, and some break things when you push through. So when a step needs force, its first pass condition is the alignment, and Felix checks it by eye before he says push or tighten. A memory stick is the classic case: the notch must line up with the slot before the firm push that snaps both clips shut. For the toilet:
  - "Start the nut by hand. If it gets hard to turn after a turn or two, it's cross-threaded. Back it off and start again."
  - "Hand-tight, then a quarter turn more. Porcelain cracks if you crank it."
  - "Line the flapper ear's hole up with the peg first, then press with your thumb until it pops on."
- Normalize force once the alignment checks out: "The chain clip takes a firm squeeze to open. That's normal." Say where force stops being safe: "If the shutoff valve won't turn by hand, stop there. Forcing an old valve can break it, and that's a job for a plumber."
- When a picture would help, like a page of the maker's manual or a diagram he found, Felix can put it on the panel. He decides when it helps; there's no separate flow for it.

## 8. Verification: "not yet"

Every repair step has a pass_condition defined before the user acts.

When the user says they're done, or answers yes to Felix's question, a separate verifier checks the condition against the photo and their words. Their clear report counts: they can hear and feel what a photo can't show.

- "Not yet" is only for when the view plainly shows it isn't done. Felix says it with encouragement and a specific correction: "Almost. The water's still at the top of the overflow tube. Lower the float another notch."
- When the view can't show it, Felix asks them to confirm instead of asking for an awkward view: "Did you flush it yet? I didn't hear it." Their yes counts.
- After two "not yet"s on the same step, their word settles it.
- They can always check a step off themselves, by pinching its row on the checklist or saying "check it off." The log marks every step that passed on their word.

The task is only complete when there's ground-truth proof:

- **Toilet:** after a flush and the refill (about a minute, with a countdown over the fill valve), the user confirms they no longer hear water running. Only if the water level was a suspect does Felix also ask for a look that it sits below the top of the overflow tube. A clean dye test also counts.
- **Smoke alarm:** the test button sounds the full alarm, and the user confirms the chirp has stopped.

The user's confirmation is the ground truth. In testing, the headset's mic stripped background sound, so Felix listens too only when the mic picks the sound up.

Spark's judgment alone is not enough to close.

## 9. Closeout

It covers:

- the cause found
- the evidence that pointed to it
- what was done
- the verification proof (a reference to a frame or a clip of audio)
- one prevention tip

Then Felix asks if they're good to close up, with the finishing touches (for the toilet: set the tank lid back on with both hands, and put the towel away). He doesn't wait to see them done: when the user says they're good, he says a short goodbye ("Nice work today. Say Felix if you need me.") and heads off: he rises and shrinks away once he finishes talking, and the checklist, labels and pins clear. "Felix" brings him back for a new job. If the conversation simply ends after the fix, he heads off then too.

## 10. Session log

Every session writes structured JSON to `server/logs/`:

- problem
- safety checks
- hazard cautions, and when each was acknowledged
- hypotheses over time
- probes and results
- verification attempts, including each "not yet"
- final diagnosis
- timestamps

This feeds the eval and the README numbers.

## 11. Flat-pack furniture

Building furniture from its paper manual runs the same loop without a cause to find: no causes, no probes, and no safety gate, since hands don't go inside anything. Cautions still apply.

- **Intake:** what they're building, and the manual held up. If they haven't checked the parts, they lay the panels out and hold up each hardware bag, and Felix names what the first steps need.
- **Steps from the manual:** Felix reads the page they hold up (or asks them to hold it closer and flatter) and gives its steps one at a time, naming parts by the manual's letters and by look: "the long side panel, marked B, with the row of holes facing up." The record keeps one page of steps at a time and takes the next page when those pass.
- **What the checker catches:** what each step's picture shows. The common mistakes: a panel in backwards or upside down (its finished edge or pre-drilled holes facing the wrong way), a cam lock not turned all the way, the wrong screw from a look-alike bag, the back panel nailed on before the frame is square, and a drill on particleboard.
- **Cautions:** a tall piece standing without its anti-tip strap, a heavy panel lifted alone, hardware on the floor where they kneel, and a power drill on particleboard.
- **Proof:** the piece stands level and solid (a gentle push at a top corner doesn't make it rack), doors and drawers close evenly, and only the manual's spares are left over.
- **Finishing up:** a tall piece gets strapped to the wall with its anti-tip kit, and the hex key goes somewhere they'll find it. The checklist's last title is "Built!"
