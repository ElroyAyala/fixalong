"""Run Felix at the desk on real headset photos, without the headset.

    .venv\\Scripts\\python.exe replay.py                      # replay the latest session
    .venv\\Scripts\\python.exe replay.py 20261029-213000-123  # replay a specific one
    .venv\\Scripts\\python.exe replay.py 20261029-213000-123 --script lines.txt
    .venv\\Scripts\\python.exe replay.py 20261029-213000-123 --type

Replaying sends everything you said in a session, in order, through a fresh
Felix, each with the photo taken for it. A script is your own lines instead,
one per line as "008 | what you say", where 008 picks photos/008.jpg from the
session (blank lines and lines starting with # are skipped). With --type you
type each line the same way. Prints what Felix says, his tool calls, the
verifier's verdicts and the headset's panel, with timings. Nothing is sent to
a headset and no audio is generated. The job log goes to server/logs/desk-*.json.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

from fixalong import config, felix

MARKS = {"check": "✓", "question": "?", "bang": "!", "dot": "▸", "none": " "}


def show(kind: str, **data) -> None:
    if kind == "scribe":
        tools = ", ".join(f"{t['name']}({json.dumps(t['args'])[:160]})" for t in data["tools"])
        print(f"    · scribe {data['think_ms']} ms → {tools or 'no changes'}")
    elif kind == "panel":
        print_panel(data)
    elif kind == "error":
        print(f"    · ERROR during {data['during']}: {data['error']}")
    elif kind == "verify":
        verdict = (("checked off by them" if data.get("checked_off") else
                    "passed on their word" if data.get("on_word") else "passed") if data["passed"]
                   else f"NOT YET: {data['correction']}")
        print(f"    · verifier on {data['check']}: {verdict} (seen: {data['seen']})")
    elif kind == "tool_refused":
        print(f"    · server refused {data['tool']}: {data['error']}")
    elif kind == "looked_up":
        print(f"    · looked up '{data['question']}' in {data['think_ms']} ms: {data['answer']}")


def print_panel(panel: dict) -> None:
    if not panel["rows"]:
        print("    [panel hidden]")
        return
    print(f"    [panel] {panel['title']}")
    for row in panel["rows"]:
        print(f"      {MARKS.get(row['mark'], ' ')} {row['text']}" + ("  (dim)" if row["style"] == "dim" else ""))


async def run(lines, folder: Path, session_id: str) -> None:
    log = config.LOGS_DIR / f"desk-{session_id}-{time.strftime('%H%M%S')}.json"
    brain = felix.Felix(log_path=log, record=show)
    print(f"Felix: {brain.greet()}")
    async for said, photo in lines:
        jpeg = (folder / photo).read_bytes() if photo and (folder / photo).exists() else None
        labels = []
        print(f"\nYou: {said}   [{photo or 'no photo'}]")
        await brain.settle()  # so timings below are Felix's alone
        start = time.perf_counter()
        reply = await brain.turn(said, jpeg, photo, labels)
        took = round((time.perf_counter() - start) * 1000)
        print(f"  Felix ({took} ms): {reply.text or felix.QUIET}"
              + (f"   → pointing at {reply.target}" if reply.target else ""))
        if reply.panel is not None:
            print_panel(reply.panel)
        if reply.text:
            brain.said_it(reply.text)
            await brain.settle()
    print(f"\nJob log: {log}")


async def recorded(folder: Path):
    events = [json.loads(line) for line in
              (folder / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    latest = None
    for i, e in enumerate(events):
        if e["kind"] == "photo":
            latest = e["file"]
        elif e["kind"] == "heard":
            photo = next((x["file"] for x in events[i + 1:i + 4]
                          if x["kind"] == "photo" and x.get("reason") != "pinch"), latest)
            yield e["text"], photo


def parse(line: str):
    if "|" not in line:
        return line.strip(), None
    number, said = line.split("|", 1)
    return said.strip(), f"photos/{int(number):03d}.jpg"


async def scripted(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            yield parse(line)


async def typed():
    while True:
        line = await asyncio.to_thread(input, "\n> ")
        if line.strip().lower() in ("", "quit", "exit"):
            return
        yield parse(line)


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ids = sorted(p.name for p in config.SESSIONS_DIR.iterdir() if p.is_dir()) \
        if config.SESSIONS_DIR.is_dir() else []
    if not ids:
        sys.exit("No sessions recorded yet.")
    session_id = args[0] if args else ids[-1]
    folder = config.SESSIONS_DIR / session_id
    if not folder.is_dir():
        sys.exit(f"No session {session_id}. Recorded: {', '.join(ids[-5:])}")
    print(f"Session {session_id}")
    if "--script" in sys.argv:
        lines = scripted(Path(sys.argv[sys.argv.index("--script") + 1]))
    elif "--type" in sys.argv:
        lines = typed()
    else:
        lines = recorded(folder)
    await run(lines, folder, session_id)


if __name__ == "__main__":
    asyncio.run(main())
