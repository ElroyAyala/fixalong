"""Replay a recorded session's photos through Felix's current brain.

    .venv\\Scripts\\python.exe replay.py                      # the latest session
    .venv\\Scripts\\python.exe replay.py 20261029-213000-123  # a specific one

For each photo Felix answered, prints what he said then and what he says now,
with timings. Nothing is sent to the headset and no audio is generated.
"""

import asyncio
import json
import sys
import time

from fixalong import config, felix


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
    answers = [e for e in events if e["kind"] == "felix_says" and "photo" in e]
    print(f"Session {session_id}: {len(answers)} photo answers to replay")
    for then in answers:
        jpeg = (folder / then["photo"]).read_bytes()
        start = time.perf_counter()
        now = await felix.describe_photo(jpeg)
        took = round((time.perf_counter() - start) * 1000)
        print(f"\n{then['photo']}")
        print(f"  then ({then.get('think_ms', '?')} ms): {then['text']}")
        print(f"  now  ({took} ms): {now}")


if __name__ == "__main__":
    asyncio.run(main())
