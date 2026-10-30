# Felix's tool wishlist

Before the first headset test, we asked Muse Spark 1.3 (reasoning effort high), briefed as Felix with the plan's tool list, what else it would need to guide a running-toilet repair well. Below is its answer, unedited. It's design input for the agent loop, not a decision; we'll sort it when that step starts.

---

## Extra tools I need for a running toilet

Current tools give me one still photo at a time, short speech, and a single-photo `check_step`. For chain vs flapper vs fill-valve-high that is not enough.

### 1. `capture_clip(duration_sec: int, question: str) -> text`
**What:** 3-10s video + audio from headset, VLM answers about motion: ripples in bowl, trickle into overflow, flapper wobble, fill valve shut-off.
**Why:** A running toilet is dynamic. A still `look()` misses a slow flapper leak and can't tell normal refill from never-shutting fill valve.
**Without it:** Ask user "is the water moving?" Users miss slow leaks, I misdiagnose fill-valve-high when it is really flapper.

### 2. `listen(duration_sec: int) -> {label: hiss | trickle | refill | silent, confidence}`
**What:** Classifies bathroom audio when user is quiet.
**Why:** Key investigate signal is hiss at fill valve vs trickle into bowl. I only run on "Felix..." or pinch, so I never hear it otherwise.
**Without it:** `ask_user("do you hear hissing?")` - unreliable in echoey bathrooms with fan on.

### 3. `guide_camera(target: str) -> photo`
**What:** Shows arrow / ghost outline in passthrough and says "move closer to X" until target is centered, in focus, lit, then auto-captures. Targets: `inside-tank`, `behind-toilet-valve`, `overflow-tube-top`.
**Why:** `look()` and `check_step()` fail if user is standing and tank interior is dark, angled, or lid still on. Behind-toilet valve is almost never in frame.
**Without it:** Repeated blurry photos, `highlight()` masks the wrong thing.

### 4. `measure_gap(from_desc: str, to_desc: str) -> {inches: float, overlay_id}`
**What:** Uses Quest 3 depth + latest photo to measure: chain slack, waterline to top of overflow tube, flapper diameter.
**Why:** Diagnosis is numbers: ~0.5in chain slack, water ~1in below overflow, 2in vs 3in flapper for replacement. Can't eyeball from photo.
**Without it:** Vague speech "about a finger width" - user sets chain too tight/loose, fill level still high.

### 5. `show_card(title: str, body: str, image: image_id?) -> overlay_id`
**What:** Pins a persistent text + reference diagram in passthrough, not just short speech. E.g. correct vs kinked chain, Fluidmaster clip adjustment.
**Why:** Everything I say is spoken and must be short. User forgets steps while hands are in tank.
**Without it:** Repeat same instruction 3x, user adjusts wrong part.

### 6. `start_timer(wait_sec: int, resume_hint: str)`
**What:** Starts a visible countdown, lets me pause the turn and get re-invoked. For dye/food-color leak test, post-flush refill (2-3 min), 5-min "is it still running?" confirm.
**Why:** No wait capability now. Each call is one pinch.
**Without it:** Tell user "pinch me in 10 minutes" - they forget, or I advance before leak shows.

### 7. `save_note(key: str, value: str)` / `load_notes() -> dict`
**What:** Persist across pinch-turns: tank model, flapper type, water level seen, what we ruled out.
**Why:** I only run when called. `remember_item()` only saves tool spots, not facts.
**Without it:** Re-ask "what fill valve do you have?" every turn, lose investigate progress.

### 8. `check_inventory(items: string[]) -> {found: [], missing: []}`
**What:** Checks one photo for: towel, sponge/cup, gloves, replacement flapper size, phone flashlight. Prompts before draining.
**Why:** Must know *before* gated drain step if we have parts. Running toilet fix stalls with empty tank and no new flapper.
**Without it:** Drain tank, then discover no towel/sponge/replacement, leave toilet unusable.

### 9. `request_gate_evidence(step_id: str, need: string[]) -> pass/fail + reason`
**What:** For safety gates `water-off` and `tank-drained`: forces 2 angles + close-up of valve handle + tank interior + user touch-confirm "tank empty, valve won't turn further." Returns why verifier failed.
**Why:** Single `check_step()` photo can't prove valve fully closed vs seized half-open, or sponge-wet vs full tank.
**Without it:** Server correctly blocks me, but I can't tell user what extra photo to take - stuck loop.

### 10. `abort_job(reason: str, next_action: str)`
**What:** Clean stop + spoken handoff: shutoff valve corroded/stuck, supply line leaking, tank cracked, no shutoff found. Leaves quest log closed, suggests plumber / landlord.
**Why:** I must not coach forcing a stuck valve. No tool currently to say "stop."
**Without it:** Keep pushing user to twist harder, risk flood / broken valve.

## Where I will still struggle, even with these

- **Tank interior photo:** low light, condensation, glare on water surface hides true waterline vs stain line. `measure_gap` will read the stain, not water.
- **Intermittent chain catch:** chain only slips under flapper sometimes. Clip looks fine, 5-min timer passes, then it runs again at night.
- **Flapper wear needs touch:** photo can't tell mineral crust vs rotted rubber. Real test is rub finger - black residue = replace - which camera can't see and hygiene makes users reluctant.
- **Fill valve variants:** Fluidmaster 400A twist-lock vs Kohler float vs old ballcock look similar from top. `highlight("fill valve clip")` will outline wrong tab, user forces and snaps it.
- **Seized shutoff:** handle looks 90-degrees closed but valve still seeps. Gate evidence passes visually, tank slowly refills while user has flapper off -> spill.
- **Lid handling blind spot:** tank lid is heavy porcelain, needs two hands. Exact moment of highest break risk, headset points at ceiling, I see nothing.
- **Wet hands + voice:** pinch tracking fails with wet hands in tank, bathroom fan + echo breaks `ask_user` transcription for "yes / no, water is off."
- **Lost small parts:** chain clip / flapper ears drop in tank water, `find_item` can't see underwater, `remember_item` spot is wrong after water ripples.

