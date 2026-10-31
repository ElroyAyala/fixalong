"""What Felix knows about each kind of job: its safety gate, refusals, parts,
starting causes and proof. docs/felix-spec.md is the source for all of it.

Only the toilet is filled in so far; the smoke alarm comes later.
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
         "check": "The tank lid is off the toilet and lying flat on a towel or on the floor "
                  "(their hands may still rest on it as they let go), not carried in the air, "
                  "leaning against the wall, or balanced on the bowl."},
    ],
    "stops": ["cracked porcelain", "water on the floor",
              "a shutoff valve that won't turn by hand or that leaks"],
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
    "proof": "after the tank refills, the user confirms they no longer hear running water, "
             "and the photo shows the water below the top of the overflow tube with nothing "
             "spilling in",
    "force": [
        "A flapper ear snaps onto its peg with firm thumb pressure: line the ear's hole up "
        "with the peg first, then press until it pops on.",
        "Start a nut by hand. If it gets hard to turn after a turn or two, it's cross-threaded: "
        "back it off and start again.",
        "Nuts on the tank: hand-tight, then a quarter turn more. Porcelain cracks if you crank it.",
        "If the shutoff valve won't turn by hand, stop there: forcing an old valve can break it.",
    ],
}

DOMAINS = {d["name"]: d for d in (TOILET,)}


def brief(domain: dict) -> str:
    """The domain's facts, as a block of Felix's instructions."""
    lines = [f"Job type: {domain['name']}."]
    lines.append("Safety gate before any hands go inside: "
                 + " ".join(g["say"] for g in domain["gate"]))
    if domain.get("words"):
        lines.append("Words: " + domain["words"])
    lines.append("Stop and recommend a professional for: " + ", ".join(domain["stops"]) + ".")
    lines.append("Parts (use these names): " + ", ".join(domain["parts"]) + ".")
    lines.append("Common causes: " + "; ".join(domain["causes"]) + ".")
    lines.append("Good probes: " + "; ".join(domain["probes"]) + ".")
    lines.append("Proof that it's fixed: " + domain["proof"] + ".")
    lines.append("Force: " + " ".join(domain["force"]))
    return "\n".join(lines)
