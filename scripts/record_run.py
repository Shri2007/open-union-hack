"""Record one real run of the demo to web/replay/run.json, for the stage screen's replay mode.

It runs the actual beats on a fresh coalition against a live relay and saves exactly what the stage screen
receives: every live event, plus a member-count snapshot every second, each with its time offset.
Nothing is invented; the replay plays this file back with the original timing.

    python scripts/record_run.py --relay http://localhost:8077
"""
import argparse
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parent.parent / "web" / "replay" / "run.json"
ORDER = [1, 2, 7, 3, 4, 5, 6]  # 7 is the walkout


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--relay", default="http://localhost:8077")
    ap.add_argument("--coalition", default=f"replay-{int(time.time())}")
    args = ap.parse_args()
    relay, cid = args.relay.rstrip("/"), args.coalition

    from app.protocol import DEMO_COALITION_NEED
    from app.store import store
    store.create_coalition(DEMO_COALITION_NEED, cid)
    httpx.post(f"{relay}/demo/reset", params={"c": cid, "hard": 1}, timeout=30).raise_for_status()

    events: list[dict] = []
    lock = threading.Lock()
    start = time.monotonic()
    stop = threading.Event()

    def add(item: dict) -> None:
        item["t"] = round(time.monotonic() - start, 3)
        with lock:
            events.append(item)

    def listen() -> None:
        with httpx.stream("GET", f"{relay}/stream", params={"coalition_id": cid}, timeout=None) as r:
            name = None
            for line in r.iter_lines():
                if stop.is_set():
                    return
                if line.startswith("event: "):
                    name = line[7:]
                elif line.startswith("data: ") and name:
                    add({"kind": "event", "name": name, "data": json.loads(line[6:])})
                    name = None

    def poll() -> None:
        while not stop.is_set():
            try:
                d = httpx.get(f"{relay}/coalitions/{cid}", timeout=10).json()
                add({"kind": "counts", "counts": d["counts"]})
            except Exception:
                pass
            time.sleep(1.0)

    threading.Thread(target=listen, daemon=True).start()
    threading.Thread(target=poll, daemon=True).start()
    time.sleep(1.5)

    def last_event_age() -> float:
        with lock:
            ev = [e for e in events if e["kind"] == "event"]
        return time.monotonic() - start - (ev[-1]["t"] if ev else 0)

    def count(name: str) -> int:
        with lock:
            return sum(1 for e in events if e["kind"] == "event" and e["name"] == name)

    for n in ORDER:
        print(f"beat {n}", flush=True)
        httpx.post(f"{relay}/demo/beat/{n}", params={"c": cid}, timeout=30).raise_for_status()
        time.sleep(2)
        if n == 5:  # the trap pause is silent for 8s: wait for both trap checks instead of for quiet
            while count("trap_check") < 2:
                time.sleep(0.5)
        if n == 6:
            while count("tally") < 1:
                time.sleep(0.5)
        while last_event_age() < 4:  # the beat is done once the stream has been quiet for 4s
            time.sleep(0.5)
        time.sleep(2 if n != 6 else 8)  # a breath between beats; at the end, let the savings counter finish

    stop.set()
    with lock:
        data = {"coalition_need": DEMO_COALITION_NEED,
                "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "note": "Replay of a live run: every event and member count below came from the real relay.",
                "duration_s": round(time.monotonic() - start, 1),
                "events": sorted(events, key=lambda e: e["t"])}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print(f"saved {len(data['events'])} items, {data['duration_s']}s, to {OUT}")

    from app import db
    with db.pooled() as c, c.cursor() as cur:  # the recording is saved; the scratch coalition can go
        for t, col in (("log", "coalition_id"), ("members", "coalition_id"), ("coalitions", "id")):
            cur.execute(f"DELETE FROM {t} WHERE {col}=%s", (cid,))


if __name__ == "__main__":
    main()
