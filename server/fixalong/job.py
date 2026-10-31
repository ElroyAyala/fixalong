"""One repair job: what Felix suspects, what he's tested, and the steps to fix it.

Felix changes the job only through his tools, and the server checks every
change: a probe must say beforehand what each outcome would rule in or out,
every step needs a pass condition, a step only passes when the separate
verifier says so, hands-inside work waits for the safety gate, and the job
only closes once every step has passed. The job also renders the headset's
checklist panel and writes the session's structured log (server/logs/).
"""

import copy
import json
import time
from datetime import datetime
from pathlib import Path

from .domains import DOMAINS

STATUSES = ("open", "testing", "ruled_out", "confirmed")
MAX_CAUSES = 6
MAX_STEPS = 8
PANEL_ROWS = 6
MAX_PIN_TEXT = 32  # a few words, readable at a glance
MAX_WAIT = 30 * 60  # the longest countdown, in seconds


class JobError(ValueError):
    """A tool call the server won't accept; the message goes back to Felix."""


class Job:
    def __init__(self, log_path: Path | None = None) -> None:
        self.log_path = log_path
        self.started = datetime.now().isoformat(timespec="seconds")
        self._t0 = time.monotonic()
        self.phase = "intake"  # intake, diagnose, repair, closed, stopped
        self.domain: str | None = None
        self.problem = ""
        self.experience = "first-timer"  # assumed until they show otherwise
        self.experience_note = "assumed"
        self.causes_title = ""
        self.causes: list[dict] = []
        self.probes: list[dict] = []
        self.steps_title = ""
        self.steps: list[dict] = []
        self.gate: list[dict] = []  # the domain's safety checks, once the job type is known
        self.gate_requested = False  # Felix has given the safety steps
        self.closeout: dict | None = None
        self.stop_reason = ""
        self.notes: list[dict] = []  # things Felix looked up
        self.pins: dict[str, dict] = {}  # notes and countdowns over parts, by part
        self.cautions: list[dict] = []  # hazard signs in their headset, and when each was seen
        # The log's running history.
        self.cause_history: list[dict] = []
        self.verifications: list[dict] = []
        self.safety_checks: list[dict] = []
        self.pin_history: list[dict] = []

    def now(self) -> float:
        return round(time.monotonic() - self._t0, 1)

    # -- Felix's tools

    def update(self, problem: str = "", domain: str = "", experience: str = "",
               experience_note: str = "") -> str:
        self._require_open()
        if domain:
            if domain not in DOMAINS:
                raise JobError(f"Unknown job type '{domain}'. Known: {', '.join(DOMAINS)}.")
            if domain != self.domain:
                self.gate = [{**g, "passed": False, "seen": ""} for g in DOMAINS[domain]["gate"]]
            self.domain = domain
        if problem:
            self.problem = problem.strip()
        if experience:
            self.experience = experience
            self.experience_note = experience_note or ""
        return "ok"

    def set_causes(self, title: str, causes: list[dict]) -> str:
        self._require_open()
        if not causes:
            raise JobError("List at least one possible cause.")
        if len(causes) > MAX_CAUSES:
            raise JobError(f"Keep it to the {MAX_CAUSES} likeliest causes.")
        clean, ids = [], set()
        for c in causes:
            cause_id = str(c.get("id") or "").strip()
            label = str(c.get("label") or "").strip()
            status = c.get("status") or "open"
            if not cause_id or not label:
                raise JobError("Every cause needs an id and a label.")
            if cause_id in ids:
                raise JobError(f"Cause id '{cause_id}' is used twice.")
            if status not in STATUSES:
                raise JobError(f"Status must be one of {', '.join(STATUSES)}.")
            ids.add(cause_id)
            clean.append({"id": cause_id, "label": label, "prior": _prior(c.get("prior")),
                          "status": status, "for": list(c.get("for") or []),
                          "against": list(c.get("against") or [])})
        self.causes = clean
        if title:
            self.causes_title = title.strip()
        if self.phase == "intake":
            self.phase = "diagnose"
        self.cause_history.append({"t": self.now(), "causes": copy.deepcopy(clean)})
        return "ok"

    def start_probe(self, instruction: str, target_part: str, observe: str,
                    outcomes: list[dict], hands_inside: bool = False) -> str:
        self._require_open()
        if not self.causes:
            raise JobError("List the possible causes (set_causes) before starting a probe.")
        if hands_inside and not self.gate_passed():
            raise JobError("Safety first: call start_safety_check before any probe that puts "
                           "hands inside.")
        if not instruction.strip() or not observe.strip():
            raise JobError("A probe needs an instruction and what you'll observe.")
        if len(outcomes or []) < 2:
            raise JobError("List at least two possible outcomes, decided before the probe runs.")
        known = {c["id"] for c in self.causes}
        for o in outcomes:
            named = set(o.get("supports") or []) | set(o.get("rules_out") or [])
            if not str(o.get("result") or "").strip():
                raise JobError("Every outcome needs a result.")
            if not named:
                raise JobError(f"Outcome '{o.get('result')}' must support or rule out a cause.")
            unknown = named - known
            if unknown:
                raise JobError(f"Unknown cause ids: {', '.join(sorted(unknown))}.")
        for p in self.probes:
            if p["status"] == "running":
                p["status"], p["result"], p["finished"] = "dropped", "", self.now()
        probe = {"id": f"p{len(self.probes) + 1}", "instruction": instruction.strip(),
                 "target_part": target_part.strip().lower(), "observe": observe.strip(),
                 "outcomes": outcomes, "hands_inside": bool(hands_inside),
                 "status": "running", "result": "", "started": self.now(), "finished": None}
        self.probes.append(probe)
        tested = {i for o in outcomes for i in (o.get("supports") or []) + (o.get("rules_out") or [])}
        for c in self.causes:
            if c["id"] in tested and c["status"] == "open":
                c["status"] = "testing"
        return f"Probe {probe['id']} started."

    def finish_probe(self, probe_id: str, result: str, updates: list[dict]) -> str:
        """Record a probe's result and what it changed about the causes, together."""
        probe = next((p for p in self.probes if p["id"] == probe_id), None)
        if probe is None:
            raise JobError(f"No probe '{probe_id}'.")
        if probe["status"] != "running":
            raise JobError(f"Probe {probe_id} isn't running.")
        if not updates:
            raise JobError("Say what the result changed: at least one cause update.")
        causes = {c["id"]: c for c in self.causes}
        for u in updates:
            cause = causes.get(u.get("id"))
            if cause is None:
                raise JobError(f"Unknown cause id '{u.get('id')}'.")
            if u.get("status") not in STATUSES:
                raise JobError(f"Status must be one of {', '.join(STATUSES)}.")
        for u in updates:
            cause = causes[u["id"]]
            cause["status"] = u["status"]
            if u.get("for"):
                cause["for"].append(u["for"])
            if u.get("against"):
                cause["against"].append(u["against"])
        probe.update(status="done", result=result.strip(), finished=self.now(), updates=updates)
        self.cause_history.append({"t": self.now(), "after_probe": probe_id,
                                   "causes": copy.deepcopy(self.causes)})
        return "ok"

    def write_steps(self, title: str, steps: list[dict]) -> str:
        self._require_open()
        if not steps:
            raise JobError("List at least one step.")
        if len(steps) > MAX_STEPS:
            raise JobError(f"Keep it to {MAX_STEPS} steps or fewer.")
        clean = []
        for i, s in enumerate(steps, 1):
            instruction = str(s.get("instruction") or "").strip()
            label = str(s.get("label") or "").strip()
            condition = str(s.get("pass_condition") or "").strip()
            if not instruction or not label:
                raise JobError(f"Step {i} needs a short label and an instruction.")
            if len(label) > 40:
                raise JobError(f"Step {i}'s label is too long for the panel: a few words.")
            if not condition:
                raise JobError(f"Step {i} needs a pass_condition, decided before the user acts.")
            hands = bool(s.get("hands_inside"))
            if hands and not self.gate_passed():
                raise JobError("Safety first: call start_safety_check before any step that puts "
                               "hands inside.")
            clean.append({"id": f"s{i}", "label": label, "instruction": instruction,
                          "target_part": str(s.get("target_part") or "").strip().lower(),
                          "pass_condition": condition, "hands_inside": hands,
                          "status": "todo", "attempts": [], "before_photo": None})
        self.steps = clean
        self.steps_title = (title or "").strip()
        self.steps[0]["status"] = "current"
        self.phase = "repair"
        return "Steps saved; step s1 is current. A step passes only when the verifier says so."

    def start_safety_check(self) -> str:
        """Felix is giving the safety steps; the verifier checks them when they say they're done."""
        self._require_open()
        if not self.domain:
            raise JobError("Set the job type first (update_job).")
        if self.gate_passed():
            return "The safety gate already passed; hands-inside work is allowed."
        self.gate_requested = True
        return "ok"

    def close(self, cause: str, evidence: str, done: str, proof: str, tip: str) -> str:
        self._require_open()
        if not self.steps or any(s["status"] != "passed" for s in self.steps):
            raise JobError("Not every step has passed the verifier yet, so the job can't close.")
        self.closeout = {"cause": cause, "evidence": evidence, "done": done,
                         "proof": proof, "tip": tip, "t": self.now()}
        self.phase = "closed"
        return "Job closed."

    def stop(self, reason: str) -> str:
        """Locked for the rest of the session: nobody talks Felix past it."""
        self.stop_reason = reason.strip()
        self.phase = "stopped"
        return "Job stopped. It stays stopped for this session."

    def pin(self, part: str, text: str, seconds=0, start: float | None = None) -> str:
        """A short note over a part in their headset, with a countdown if they're waiting
        on it. Pinning a part again replaces its note; empty text removes it.

        start is when Felix asked them to wait (time.monotonic()), so a countdown
        recorded a few seconds later still ends on time.
        """
        part, text = str(part or "").strip().lower(), str(text or "").strip()
        if not part:
            raise JobError("Name the part the pin goes over.")
        if not text:
            self.pins.pop(part, None)
            self.pin_history.append({"t": self.now(), "part": part, "removed": True})
            return "Pin removed."
        if len(text) > MAX_PIN_TEXT:
            raise JobError("A pin is a few words, like 'Refilling' or 'Front left: 32 psi'.")
        try:
            seconds = float(seconds or 0)
        except (TypeError, ValueError):
            raise JobError("seconds must be a number.") from None
        if not 0 <= seconds <= MAX_WAIT:
            raise JobError(f"A countdown runs for up to {MAX_WAIT // 60} minutes.")
        start = time.monotonic() if start is None else start
        self.pins[part] = {"part": part, "text": text, "seconds": seconds,
                           "ends_at": start + seconds if seconds else None}
        self.pin_history.append({"t": self.now(), "part": part, "text": text, "seconds": seconds})
        return "Pinned." + (" You'll hear when the countdown runs out." if seconds else "")

    def caution(self, name: str, line: str) -> dict:
        """A hazard sign in their headset: the hazard's short name and the sign's line."""
        caution = {"id": f"h{len(self.cautions) + 1}", "name": name, "line": line,
                   "t": self.now(), "seen": None, "acknowledged": None, "how": ""}
        self.cautions.append(caution)
        return caution

    def seen_caution(self, caution_id: str) -> None:
        """They looked at the sign, so its line opened."""
        for c in self.cautions:
            if c["id"] == caution_id and c["seen"] is None:
                c["seen"] = self.now()

    def acknowledge(self, caution_id: str, how: str) -> dict | None:
        """They acknowledged a sign; None if it's unknown or already acknowledged."""
        caution = next((c for c in self.cautions
                        if c["id"] == caution_id and c["acknowledged"] is None), None)
        if caution is not None:
            caution["acknowledged"], caution["how"] = self.now(), how
        return caution

    # -- what the verifier decides

    def open_gate(self) -> list[dict]:
        """Safety checks not passed yet (none once the job is over)."""
        if self.phase in ("closed", "stopped"):
            return []
        return [g for g in self.gate if not g["passed"]]

    def record_gate(self, gate_id: str, passed: bool, seen: str, on_word: bool = False) -> None:
        for g in self.gate:
            if g["id"] == gate_id:
                g["passed"], g["seen"] = passed, seen
        check = {"t": self.now(), "check": gate_id, "passed": passed, "seen": seen}
        if on_word:
            check["on_word"] = True
        self.safety_checks.append(check)

    def record_step(self, step: dict, passed: bool, seen: str, correction: str,
                    photo: str | None, on_word: bool = False) -> None:
        """on_word: passed on the user's word after the view couldn't confirm it."""
        attempt = {"t": self.now(), "passed": passed, "seen": seen,
                   "correction": "" if passed else correction, "photo": photo}
        if on_word:
            attempt["on_word"] = True
        step["attempts"].append(attempt)
        self.verifications.append({"step": step["id"], **attempt})
        if not passed:
            return
        step["status"] = "passed"
        following = next((s for s in self.steps if s["status"] == "todo"), None)
        if following:
            following["status"] = "current"
            following["before_photo"] = photo

    def current_step(self) -> dict | None:
        return next((s for s in self.steps if s["status"] == "current"), None)

    def running_probe(self) -> dict | None:
        return next((p for p in self.probes if p["status"] == "running"), None)

    def gate_passed(self) -> bool:
        """Once the job type is known: every safety check passed, or it has none."""
        return self.domain is not None and all(g["passed"] for g in self.gate)

    def target_part(self) -> str:
        """The part Felix is working on right now, for the headset to point at."""
        if self.phase == "repair" and (step := self.current_step()):
            return step["target_part"]
        if probe := self.running_probe():
            return probe["target_part"]
        return ""

    def _require_open(self) -> None:
        if self.phase == "stopped":
            raise JobError(f"This job is stopped ({self.stop_reason}). Don't guide any more work "
                           "on it; recommend a professional.")
        if self.phase == "closed":
            raise JobError("This job is closed.")

    # -- what Felix and the headset see

    def summary(self, for_felix: bool = False) -> str:
        """The job as a few lines, for Felix's next turn or the scribe.

        Things Felix looked up show until he has seen them once (for_felix).
        """
        lines = [f"Phase: {self.phase}. Job type: {self.domain or 'not set'}. "
                 f"Problem: {self.problem or 'not stated yet'}. "
                 f"Experience: {self.experience} ({self.experience_note or 'confirmed'})."]
        if self.stop_reason:
            lines.append(f"STOPPED: {self.stop_reason}")
        if self.gate:
            lines.append("Safety gate: " + "; ".join(
                f"{g['id']} {'passed' if g['passed'] else 'not yet'}" for g in self.gate)
                + (". Hands-inside work is allowed." if self.gate_passed() else
                   ". Hands-inside work waits for it. The safety steps were already given: "
                   "don't repeat them unless they ask or the next step needs their hands inside."
                   if self.gate_requested else
                   ". Hands-inside work is NOT allowed yet: give the safety steps first."))
        if self.causes:
            lines.append("Causes: " + "; ".join(
                f"{c['id']} {c['label']} ({c['status']}, prior {c['prior']})" for c in self.causes))
        if probe := self.running_probe():
            lines.append(f"Waiting on probe {probe['id']}: {probe['instruction']} "
                         f"(observe: {probe['observe']})")
        if self.steps:
            lines.append("Steps: " + "; ".join(
                f"{s['id']} [{s['status']}] {s['instruction']} (passes if: {s['pass_condition']})"
                for s in self.steps))
        if self.pins:
            lines.append("Pinned in their headset: " + "; ".join(
                f"over the {p['part']}, '{p['text']}'" + _time_left(p) for p in self.pins.values()))
        if self.cautions:
            lines.append("Caution signs in their headset: " + "; ".join(
                f"'{c['line']}' " + ("(acknowledged)" if c["acknowledged"] is not None else
                                     "(not acknowledged yet: before a step that puts their "
                                     "hands near it, ask them to look at the sign and say "
                                     "'got it')")
                for c in self.cautions))
        for note in self.notes:
            if not note.get("told"):
                lines.append(f"Looked up '{note['question']}': {note['answer']}")
                note["told"] = note.get("told") or for_felix
        return "\n".join(lines)

    def panel(self) -> dict:
        """The headset's checklist: a title and rows, each with a mark and a style. A row
        with an id can be checked off on the headset: a step not passed yet, or a safety
        check their word can settle."""
        if self.phase == "stopped":
            return {"title": "Stopped: call a professional",
                    "rows": [{"text": self.stop_reason, "mark": "bang", "style": "found"}],
                    "moment": ""}
        if self.gate_requested and self.open_gate():
            return self.gate_panel()
        if self.phase in ("repair", "closed") and self.steps:
            done = DOMAINS.get(self.domain or "", {}).get("done_title", "Fixed!")
            title = done if self.phase == "closed" else (self.steps_title or "The fix")
            rows = [{"text": s["label"],
                     "mark": {"passed": "check", "current": "dot"}.get(s["status"], "none"),
                     "style": {"passed": "dim", "current": "active"}.get(s["status"], "normal"),
                     "id": "" if s["status"] == "passed" or self.phase == "closed" else s["id"]}
                    for s in self.steps]
            current = next((i for i, s in enumerate(self.steps) if s["status"] == "current"), 0)
            start = max(0, min(current - 1, len(rows) - PANEL_ROWS))
            fixed = all(s["status"] == "passed" for s in self.steps)
            return {"title": title, "rows": rows[start:start + PANEL_ROWS],
                    "moment": "fixed" if fixed else ""}
        if self.causes:
            return self.causes_panel()
        return {"title": "", "rows": [], "moment": ""}

    def causes_panel(self) -> dict:
        """The causes, the found one first. moment is "found" once one is confirmed."""
        order = {"confirmed": 0, "testing": 1, "open": 2, "ruled_out": 3}
        causes = sorted(self.causes, key=lambda c: (order[c["status"]], -c["prior"]))
        return {"title": self.causes_title or "Possible causes",
                "rows": [{"text": c["label"],
                          "mark": {"ruled_out": "check", "testing": "question",
                                   "confirmed": "bang"}.get(c["status"], "none"),
                          "style": {"ruled_out": "dim", "testing": "active",
                                    "confirmed": "found"}.get(c["status"], "normal")}
                         for c in causes[:PANEL_ROWS]],
                "moment": "found" if any(c["status"] == "confirmed" for c in causes) else ""}

    def gate_panel(self) -> dict:
        """The safety checks, ticked as they pass."""
        return {"title": "Before your hands go in",
                "rows": [{"text": g["short"], "mark": "check" if g["passed"] else "dot",
                          "style": "dim" if g["passed"] else "active",
                          "id": g["id"] if g.get("word_counts") and not g["passed"] else ""}
                         for g in self.gate],
                "moment": ""}

    # -- the session log

    def save(self) -> None:
        if self.log_path is None:
            return
        diagnosis = next((c["label"] for c in self.causes if c["status"] == "confirmed"), None)
        record = {
            "started": self.started, "phase": self.phase, "domain": self.domain,
            "problem": self.problem, "experience": self.experience,
            "experience_note": self.experience_note,
            "safety_checks": self.safety_checks, "causes_over_time": self.cause_history,
            "probes": self.probes, "steps": self.steps, "verifications": self.verifications,
            "diagnosis": diagnosis, "closeout": self.closeout, "stopped": self.stop_reason or None,
            "looked_up": [{k: v for k, v in n.items() if k != "told"} for n in self.notes],
            "pins": self.pin_history, "cautions": self.cautions,
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(json.dumps(record, indent=2), encoding="utf-8")


def _time_left(pin: dict) -> str:
    if pin["ends_at"] is None:
        return ""
    left = pin["ends_at"] - time.monotonic()
    return f" (countdown: {left:.0f} s left)" if left > 0 else " (countdown done)"


def _prior(value) -> float:
    try:
        return round(min(max(float(value), 0.0), 1.0), 2)
    except (TypeError, ValueError):
        return 0.0
