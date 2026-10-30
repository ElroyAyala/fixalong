"""Replay a recorded session's conversation through Felix's current brain.

    .venv\\Scripts\\python.exe replay.py                      # the latest session
    .venv\\Scripts\\python.exe replay.py 20261029-213000-123  # a specific one

Everything you said is replayed in order through a fresh conversation, whether
or not Felix heard it at the time, with the photo taken for it (or the latest
one before it), so Felix's memory builds up the same way. Prints what Felix
said then and what he says now, with timings. Nothing is sent to the headset
and no audio is generated. (Pinch photos in early sessions are skipped.)
"""

import asyncio
import json
import sys
import time

from fixalong import config, felix


def answer_then(events: list[dict], heard: dict) -> str:
    """What Felix did at the time about a sentence you said."""
    for e in events:
        # A turn can answer several sentences at once, joined with spaces.
        said = f" {e.get('said') or ''} "
        if e["kind"] in ("felix_says", "felix_quiet") and f" {heard['text']} " in said:
            return e.get("text", felix.QUIET)
    return "(no answer)" if heard["for_felix"] else "(didn't hear it as meant for him)"


async def main() -> None:
    ids = sorted(p.name for p in config.SESSIONS_DIR.iterdir() if p.is_dir()) \
        if config.SESSIONS_DIR.is_dir() else []
    if not ids:
        sys.exit("No sessions recorded yet.")
    session_id = sys.argv[1] if len(sys.argv) > 1 else ids[-1]
    folder = config.SESSIONS_DIR / session_id
    if not folder.is_dir():
        sys.exit(f"No session {session_id}. Recorded: {', '.join(ids[-5:])}")

    events = [json.loads(line) for line in
              (folder / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"Session {session_id}")
    conversation = felix.Conversation()
    conversation.greet()
    latest_photo = None
    for i, e in enumerate(events):
        if e["kind"] == "photo":
            latest_photo = e["file"]
            continue
        if e["kind"] != "heard":
            continue
        said, then = e["text"], answer_then(events[i + 1:], e)
        photo = next((x["file"] for x in events[i + 1:i + 4]
                      if x["kind"] == "photo" and x.get("reason") != "pinch"), latest_photo)
        jpeg = (folder / photo).read_bytes() if photo else None
        start = time.perf_counter()
        now = await conversation.reply(said, jpeg) or felix.QUIET
        took = round((time.perf_counter() - start) * 1000)
        print(f"\nYou: {said}   [{photo or 'no photo'}]")
        print(f"  then: {then}")
        print(f"  now  ({took} ms): {now}")


if __name__ == "__main__":
    asyncio.run(main())
