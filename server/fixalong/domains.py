"""What Felix knows about each kind of job: its safety gate, refusals, parts,
starting causes and proof. docs/felix-spec.md is the source for all of it.

The toilet is a repair: Felix finds the cause, then fixes it. Flat-pack
furniture follows its manual instead: no cause to find, and its own common
mistakes to catch. The smoke alarm comes later.
"""

# Refused in every job: Felix says why and recommends a professional.
REFUSALS = ["gas lines or gas appliances", "breaker panels and mains wiring",
            "opening a power supply", "microwaves or CRT screens", "refrigerant"]

TOILET = {
    "name": "toilet",
    # Checked by eye before any step that puts hands inside the tank.
    "gate": [
        {"id": "lid",
         "short": "Tank lid flat on a towel",
         # Low risk, and the lid is often out of view: their clear word counts too.
         "word_counts": True,
         # Mentioning these gets it checked, even before Felix asks.
         "keywords": ["lid", "towel"],
         "say": "Lay a towel on the floor, then lift the tank lid with both hands and set it "
                "flat on the towel. Porcelain cracks if it's dropped or leaned against something.",
         # The open tank is the evidence: once they're looking into it, the lid is out of
         # view. In a headset run, waiting to see it on the towel kept the gate shut through
         # the whole fix, so Felix kept asking and the steps couldn't be recorded.
         "check": "The tank lid is off the toilet and set down somewhere safe, like flat on a "
                  "towel or the floor (their hands may still rest on it as they let go). A view "
                  "of the open tank with its lid off counts, even with the lid out of view, "
                  "unless it shows the lid carried in the air, leaning against the wall, or "
                  "balanced on the bowl."},
    ],
    "stops": ["cracked porcelain", "water on the floor",
              "a shutoff valve that won't turn by hand or that leaks"],
    # Hazards to the person or the headset: each gets a caution sign (hazards.py).
    "hazards": ["an open tank of water close below the headset",
                "flushing with the tank lid off, which can splash",
                "a cleaner tablet dissolving in the tank, which tints the water blue (a blue "
                "plastic part, like the fill valve's cap, isn't one)",
                "the tank lid leaned against the wall or balanced on the bowl, where it can fall "
                "and crack"],
    # How Felix says a caution once they've acknowledged its sign.
    "caution": "I noticed we're working near water. If anything starts spraying, step back and "
               "take the headset off first. You don't need it to turn the shutoff valve.",
    "parts": ["tank lid", "flapper", "chain", "flush handle", "fill valve", "float", "overflow tube",
              "refill tube", "shutoff valve", "supply line"],
    # What people call things, so Felix doesn't go looking for the wrong problem.
    "words": "People often call the flapper 'the gasket' or 'the seal', and 'leaking' often "
             "means water running into the bowl. Before assuming an outside leak, ask whether "
             "they see water on the floor or hear it running inside.",
    "causes": [
        "the flapper isn't sealing (worn, warped, or not seated on the drain opening)",
        "a flapper ear isn't clipped onto its peg at the base of the overflow tube, so the "
        "flapper sits crooked (common right after installing a new one)",
        "the chain is too short or caught, so it holds the flapper open",
        "the water level is set too high, so water spills into the overflow tube",
        "the fill valve doesn't shut off",
        "the flush handle sticks",
    ],
    "probes": [
        "look at the overflow tube: water spilling into it means the level is too high, "
        "so the flapper isn't the main cause",
        "push the flapper down with a finger: if the running stops, it's the flapper or "
        "the chain; if it keeps running, both are ruled out",
        "lift the float gently: if the water stops, the level is set too high; if not, "
        "the fill valve is faulty",
        "look at the flapper's two side ears, where they clip onto pegs on each side of the "
        "overflow tube's base: both should be on, with the flapper centered over the drain",
        "with the flapper closed, ask whether the chain hangs a little loose or pulls tight: "
        "from above, a hanging chain looks straight either way",
    ],
    # Their word is the proof. A look only adds to it when the water level was a suspect:
    # in a headset run, asking for that look after a clear report felt like doubting them.
    "proof": "after a flush and the refill (about a minute), the user confirms they no longer "
             "hear water running. Only if the water level was a suspect, also a look that it "
             "sits below the top of the overflow tube",
    "finish": "Set the tank lid back on with both hands, and put the towel away.",
    "force": [
        "A flapper ear snaps onto its peg with firm thumb pressure: line the ear's hole up "
        "with the peg first, then press until it pops on.",
        "Start a nut by hand. If it gets hard to turn after a turn or two, it's cross-threaded: "
        "back it off and start again.",
        "Nuts on the tank: hand-tight, then a quarter turn more. Porcelain cracks if you crank it.",
        "If the shutoff valve won't turn by hand, stop there: forcing an old valve can break it.",
    ],
}

# Building furniture from its paper manual: no cause to find, and the checker catches what's
# plain to see, like a panel put in backwards.
FLAT_PACK = {
    "name": "flat-pack furniture",
    # For the labels, since it isn't a repair: what they're doing, and the part names it uses.
    "work": "builds flat-pack furniture from its manual",
    "done_title": "Built!",  # the checklist's title once it's done, in place of "Fixed!"
    # How it runs, in place of finding a cause.
    "flow": "This job follows the paper manual instead of finding a cause: no causes or probes. "
            "Ask what they're building, and to hold up the manual. If they haven't checked the "
            "parts yet, have them lay the panels out and hold up each hardware bag, and name "
            "what the first steps need. Then read the steps from the page they hold up, a page "
            "at a time, and give them one at a time in plain words, naming parts by the "
            "manual's letters and by look, like 'the long side panel, marked B, with the row of "
            "holes facing up'. What each step's picture shows is how it's checked: which way a "
            "panel faces, which holes, which screws. If you can't read the page, ask them to "
            "hold it closer and flatter. When a page's steps are done, ask for the next page.",
    "gate": [],
    "stops": ["a cracked or split panel that carries weight: get a replacement part from the "
              "maker instead of building with it"],
    "parts": ["manual", "side panel", "top panel", "bottom panel", "shelf", "back panel", "door",
              "drawer", "cam lock", "cam bolt", "wooden dowel", "screw", "hex key",
              "hardware bag", "anti-tip strap"],
    "words": "Manuals name panels by letter or number, and hardware by the code on its bag: use "
             "the manual's names. A cam lock is the round metal disc that turns to grab a bolt; "
             "people call it 'the round thing' or 'the circle screw'.",
    # The mistakes to watch for, in place of causes.
    "mistakes": [
        "a panel put in backwards or upside down: its finished edge, or its pre-drilled holes, "
        "face the wrong way (the most common one)",
        "a cam lock not turned all the way, so the joint pulls apart",
        "the wrong screw from a look-alike bag, like a long one where a short one goes",
        "the back panel nailed on before the frame is square",
        "screws driven with a drill, which strips particleboard",
    ],
    "proof": "the piece stands level and solid: a gentle push at a top corner doesn't make it "
             "rack or wobble, doors and drawers close evenly, and the only hardware left over is "
             "the spares the manual says to expect",
    "finish": "If it's tall, strap it to the wall with its anti-tip kit, and put the hex key "
              "somewhere you'll find it.",
    "hazards": ["a tall piece standing up without its anti-tip strap, which can tip over",
                "a big or heavy panel one person is lifting alone",
                "screws, dowels or the hex key on the floor right where they're kneeling",
                "a power drill on particleboard, which strips it where a hex key won't"],
    "caution": "That's a tall one, so keep a hand on it until it's strapped to the wall. "
               "Furniture tipping over is a real injury, especially with kids around.",
    "force": [
        "Snug with the hex key, then stop: particleboard strips if you crank it, and a drill "
        "strips it fast.",
        "A cam lock turns about half a turn until it's snug. If it spins freely, its bolt isn't "
        "seated: back it off and line the bolt up first.",
        "Wooden dowels go in with a light tap. If one won't go, check that the holes line up "
        "instead of forcing it.",
        "Square the frame before nailing the back panel: measure corner to corner both ways, "
        "and the two should match.",
    ],
}

DOMAINS = {d["name"]: d for d in (TOILET, FLAT_PACK)}


def brief(domain: dict) -> str:
    """The domain's facts, as a block of Felix's instructions."""
    lines = [f"Job type: {domain['name']}."]
    if domain.get("flow"):
        lines.append("How it runs: " + domain["flow"])
    if domain["gate"]:
        lines.append("Safety gate before any hands go inside: "
                     + " ".join(g["say"] for g in domain["gate"]))
    if domain.get("words"):
        lines.append("Words: " + domain["words"])
    lines.append("Stop and recommend a professional for: " + ", ".join(domain["stops"]) + ".")
    if domain.get("caution"):
        lines.append("Saying a caution, once they've acknowledged its sign, like: "
                     + domain["caution"])
    lines.append("Parts (use these names): " + ", ".join(domain["parts"]) + ".")
    if domain.get("causes"):
        lines.append("Common causes: " + "; ".join(domain["causes"]) + ".")
    if domain.get("probes"):
        lines.append("Good probes: " + "; ".join(domain["probes"]) + ".")
    if domain.get("mistakes"):
        lines.append("Common mistakes to catch: " + "; ".join(domain["mistakes"]) + ".")
    lines.append("Proof that it's done: " + domain["proof"] + ".")
    if domain.get("finish"):
        lines.append("Finishing up, after the closeout: " + domain["finish"])
    lines.append("Force: " + " ".join(domain["force"]))
    return "\n".join(lines)
