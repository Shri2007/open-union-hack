"""Demo beats 1–6 and reset (prompt P4). Each beat runs in the background so the presenter's key press returns at once.

Pieces built by others plug in here:
- app/vendor.py (Codex): price_for(n) and say(who, situation, fallback)
- app/tally.py (Capy): compute_tally(rows, offer_price_cents, eligible)
- app/offer_check.py (Ali): check_offer(cid, price_cents, terms_text) -> {"verdict": "pass"|"reject"|"ask_member", ...}
Until each lands, the local fallbacks below keep the demo running.
"""
import math
import queue
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import bus
from app import store as store_module
from app.protocol import DEMO_COALITION_ID, DEMO_COALITION_NEED, VENDOR_AGENT_ID, reveal_matches
from app.relay import record_system

router = APIRouter()
ROOT = Path(__file__).resolve().parent.parent
RELAY_URL = os.environ.get("RELAY_URL", "http://localhost:8077")
SEED_TARGET = int(os.environ.get("DEMO_SEED_MEMBERS", "300"))
ATTACK_SIZE = int(os.environ.get("DEMO_ATTACK_SIZE", "500"))
TRAP_PAUSE_SECONDS = float(os.environ.get("DEMO_TRAP_PAUSE", "8"))
STRIKE_SECONDS = float(os.environ.get("DEMO_STRIKE_SECONDS", "5"))
WALKOUT_DISCOUNT_CENTS = 200
_concessions: dict[str, int] = {}  # coalition_id -> cents off the curve won by a walkout


_remembered: dict[str, int] = {}  # coalition_id -> cents off the curve from Cognee vendor memory (simulated)


def quote(cid: str, n: int) -> int:
    return max(3800, price_for(n) - _concessions.get(cid, 0) - _remembered.get(cid, 0))

TRAP_TERMS = ("$58/month for the first 3 months (introductory rate), then $95/month standard rate. "
              "24-month agreement. $5/month line access fee per line.")
CLEAN_TERMS = "$58/month per line, fixed for 12 months. No added fees. Activation waived."

# ---------- pieces built by others, with fallbacks ----------
try:
    from app.vendor import price_for, say
except ImportError:
    def price_for(n: int) -> int:
        return round(100 * max(38.0, 85 - 27.1 * math.log(1 + n / 200)))

    def say(who: str, situation: str, fallback: str) -> str:
        return fallback

try:
    from app.tally import compute_tally
except ImportError:
    def compute_tally(rows, offer_price_cents, eligible=None):
        commits, reveals = {}, {}
        for r in rows:
            a = r["agent_id"]
            if eligible is not None and a not in eligible:
                continue
            if r["type"] == "COMMIT" and a not in commits:
                commits[a] = r["body"]["commitment"]
            elif r["type"] == "REVEAL":
                reveals[a] = r["body"]
        agents = set(commits) | set(reveals)
        revealed, accepted, mismatched = [], 0, 0
        for a in sorted(agents):
            if a not in reveals:
                continue
            rv = reveals[a]
            ok = a in commits and reveal_matches(commits[a], rv["price_cents"], rv["salt_hex"])
            mismatched += not ok
            accepted += ok and rv["price_cents"] >= offer_price_cents
            revealed.append({"agent_id": a, "price_cents": rv["price_cents"], "ok": ok})
        return {"accepted": accepted, "total": len(agents), "mismatched": mismatched,
                "not_revealed": len(agents) - len(revealed), "revealed": revealed}


def _check_offer(cid: str, price_cents: int, terms: str) -> dict:
    try:
        from app.offer_check import check_offer
    except ImportError:
        record_system(cid, "offer_check_missing", note="offer check (P5) not wired yet")
        return {"verdict": "unchecked"}
    return check_offer(cid, price_cents, terms)


# ---------- helpers ----------
def _s():
    return store_module.store


def chat(cid: str, who: str, text: str) -> None:
    bus.publish(cid, "chat", {"who": who, "text": text})


def offer(cid: str, price_cents: int, terms: str) -> dict:
    row = _s().append(cid, VENDOR_AGENT_ID, "OFFER",
                      {"price_cents": price_cents, "terms_text": terms, "senso_content_ids": [], "trap_checks": []})
    bus.publish(cid, "offer", {"offer_id": row["id"], "price_cents": price_cents, "terms_text": terms})
    return row


def dollars(cents: int) -> str:
    return f"${cents / 100:.0f}" if cents % 100 == 0 else f"${cents / 100:.2f}"


def _script(*args: str) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, *args], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------- Cognee vendor memory (simulated; off unless COGNEE_MEMORY=1, never raises) ----------
def _recall_memory(cid: str) -> None:
    try:
        from app import memory
        c = _s().get_coalition(cid)
        got = memory.recall_walkout(c["need"]) if c else None
        if got:
            _remembered[cid] = WALKOUT_DISCOUNT_CENTS
            chat(cid, "vendor", f"Northline remembers (simulated memory, Cognee): {got['text']} "
                                f"I'll open {dollars(WALKOUT_DISCOUNT_CENTS)} under the usual curve this time.")
    except Exception as exc:
        print(f"memory recall skipped: {exc!r}", file=sys.stderr)


def _remember_close(cid: str, price_cents: int) -> None:
    try:
        from app import memory
        c = _s().get_coalition(cid)
        if c and memory.enabled():  # cognify is slow: store in the background
            threading.Thread(target=memory.remember_walkout, args=(c["need"], price_cents), daemon=True).start()
    except Exception as exc:
        print(f"memory store skipped: {exc!r}", file=sys.stderr)


# ---------- beats ----------
def beat1(cid: str) -> None:
    chat(cid, "system", "Beat 1 · One agent asks alone.")
    chat(cid, "coalition", "Solo agent (1 customer): I've paid $85 a month since 2021. Can you do $50?")
    offer(cid, 8500, "List price, single line, month-to-month.")
    chat(cid, "vendor", say("vendor", "One customer asks for $50/month. List price is $85. Refuse politely.",
                            "Our best price for a single line is $85 a month. I'm sure you understand."))
    chat(cid, "system", "Refused. One customer has no leverage.")


def beat2(cid: str) -> None:
    chat(cid, "system", "Beat 2 · The room joins. Simulated members are seeded alongside real ones.")
    _recall_memory(cid)
    have = _s().counts(cid)["simulated"]
    proc = _script("scripts/seed_members.py", "--relay", RELAY_URL, "--coalition", cid,
                   "--n", str(max(0, SEED_TARGET - have))) if have < SEED_TARGET else None
    last = -1
    while True:
        n = _s().counts(cid)["verified"]
        if n != last and n > 0 and (n - last >= 60 or (proc and proc.poll() is not None)):
            offer(cid, quote(cid, n), f"Volume quote for {n} verified lines, 12-month term.")
            last = n
        if not proc or proc.poll() is not None:
            break
        time.sleep(1.5)
    n = _s().counts(cid)["verified"]
    if n != last:
        offer(cid, quote(cid, n), f"Volume quote for {n} verified lines, 12-month term.")
    chat(cid, "coalition", say("coalition", f"{n} verified members want a phone plan under $60. Ask for a volume price.",
                               f"{n} verified members want a plan under $60. What's your volume price?"))
    chat(cid, "vendor", say("vendor", f"You sell monthly phone plans. Quote {dollars(quote(cid, n))} per phone line per month "
                                      f"for {n} verified people, 12-month term.",
                            f"For {n} verified lines, {dollars(quote(cid, n))} a month on a 12-month term."))


def beat3(cid: str) -> None:
    chat(cid, "system", f"Beat 3 · Attack: {ATTACK_SIZE} sign-ups from one script, no identity check.")
    proc = _script("scripts/sybil_attack.py", "--relay", RELAY_URL, "--coalition", cid, "--n", str(ATTACK_SIZE))
    while proc.poll() is None:
        c = _s().counts(cid)
        offer(cid, price_for(c["verified"] + c["unverified"]),
              f"Volume quote for {c['verified'] + c['unverified']} lines (identity not checked).")
        time.sleep(2.5)
    c = _s().counts(cid)
    total = c["verified"] + c["unverified"]
    offer(cid, price_for(total), f"Volume quote for {total} lines (identity not checked).")
    chat(cid, "coalition", f"We now represent {total} lines. {dollars(price_for(total))}.")
    chat(cid, "vendor", say("vendor", f"You sell monthly phone plans. Before quoting {total} phone lines, "
                                      f"demand proof they belong to {total} different people.",
                            f"Before I quote {total} lines, prove they're {total} different people."))


def beat4(cid: str) -> None:
    chat(cid, "system", "Beat 4 · Persona checks every member for a unique, verified human.")
    c = _s().counts(cid)
    chat(cid, "persona", f"Checking {c['verified'] + c['unverified']} members…")
    removed = _s().remove_unverified(cid, "not a verified unique human")
    for agent in removed:
        bus.publish(cid, "member_removed", {"agent_id": agent, "reason": "not a verified unique human"})
    record_system(cid, "verification", removed=len(removed))
    n = _s().counts(cid)["verified"]
    chat(cid, "persona", f"{n} verified unique humans. {len(removed)} removed: no verified identity.")
    offer(cid, quote(cid, n), f"Volume quote for {n} verified lines, 12-month term.")
    chat(cid, "vendor", say("vendor", f"You sell monthly phone plans. Accept that {n} verified people each want one phone line; "
                                      f"your quote stays {dollars(quote(cid, n))} per line per month.",
                            f"{n} verified lines. {dollars(quote(cid, n))} stands."))
    chat(cid, "system", "Fakes removed. The price is back where real people put it.")


def beat5(cid: str) -> None:
    # The final offer is whatever the vendor is quoting now, so it never jumps above an earlier quote.
    p = quote(cid, _s().counts(cid)["verified"])
    d = dollars(p)
    trap = (f"{d}/month for the first 3 months (introductory rate), then $95/month standard rate. "
            "24-month agreement. $5/month line access fee per line.")
    clean = f"{d}/month per line, fixed for 12 months. No added fees. Activation waived."
    chat(cid, "system", "Beat 5 · The vendor's final offer, checked against the fine print.")
    chat(cid, "vendor", say("vendor", f"You sell monthly phone plans. Present a final offer of {d} a month per line, "
                                      "sounding generous. Don't mention the fine print.",
                            f"Final offer: {d} a month. You won't find better."))
    offer(cid, p, trap)
    result = _check_offer(cid, p, trap)
    if result.get("verdict") == "pass":
        chat(cid, "system", "Offer check passed the trap offer. Review the trap questions.")
        return
    chat(cid, "coalition", f"Rejected. {d} that becomes $95 after 3 months, plus fees, is not {d}. "
                           f"We need {d} fixed for 12 months, no added fees.")
    time.sleep(TRAP_PAUSE_SECONDS)  # keep the rejected trap check on screen long enough for the room to read it
    chat(cid, "vendor", say("vendor", f"You sell monthly phone plans. Grudgingly agree to {d} a month per line, "
                                      "fixed for 12 months, no added fees.",
                            f"Fine. {d} a month, fixed for 12 months, no added fees."))
    offer(cid, p, clean)
    _check_offer(cid, p, clean)


def beat6(cid: str) -> None:
    s = _s()
    chat(cid, "system", "Beat 6 · Closing. Members reveal their sealed limits.")
    s.set_state(cid, "closing")
    secrets = ROOT / "members_secrets.json"
    if secrets.exists():
        _script("scripts/seed_members.py", "reveal", "--relay", RELAY_URL, "--coalition", cid)
    # Wait for reveals (simulated and real phones) to settle, at most 25 seconds.
    last, stable, start = -1, 0, time.time()
    while time.time() - start < 25 and stable < 3:
        time.sleep(1.5)
        now = s.count_type(cid, "REVEAL")
        stable = stable + 1 if now == last and now > 0 else 0
        last = now
    rows = s.log(cid)
    final = next((r for r in reversed(rows) if r["type"] == "OFFER"), None)
    price = final["body"]["price_cents"] if final else 5800
    t = compute_tally(rows, price, s.eligible_agents(cid))
    record_system(cid, "tally", offer_price_cents=price, accepted=t["accepted"], total=t["total"],
                  mismatched=t["mismatched"], not_revealed=t["not_revealed"])
    bus.publish(cid, "tally", {"accepted": t["accepted"], "total": t["total"], "revealed": t["revealed"]})
    s.set_state(cid, "closed")
    _remember_close(cid, price)
    chat(cid, "system", f"{t['accepted']} of {t['total']} members accept {dollars(price)}. "
                        f"Each saves {dollars(8500 - price)} a month. Check it yourself at /verify.html.")


def walkout(cid: str) -> None:
    """The coalition walks out on the vendor. Every member's phone shows the strike; the vendor caves.

    The vendor's concession is part of its published rules: a coalition that walks to a competitor
    gets WALKOUT_DISCOUNT_CENTS off the curve. It sticks for the rest of this run.
    """
    n = _s().counts(cid)["verified"]
    chat(cid, "system", "Walkout · The coalition takes its lines to a competitor.")
    chat(cid, "coalition", f"{n} verified members are taking their lines to a competitor. Strike.")
    bus.publish(cid, "strike", {"text": f"{n} members walked out on Northline Mobile", "members": n})
    record_system(cid, "walkout", members=n)
    time.sleep(STRIKE_SECONDS)  # let the room's phones sit on the strike screen
    _concessions[cid] = WALKOUT_DISCOUNT_CENTS
    price = quote(cid, n)
    chat(cid, "vendor", say("vendor", f"You sell monthly phone plans. {n} customers just walked out to a competitor. "
                                      f"Panic a little and beg them back with {dollars(price)} per line per month.",
                            f"Wait, wait! Don't go. {dollars(price)} a line, final answer."))
    offer(cid, price, f"Retention offer for {n} verified lines after walkout, 12-month term.")


BEATS = {1: beat1, 2: beat2, 3: beat3, 4: beat4, 5: beat5, 6: beat6, 7: walkout}


def _run(n: int, cid: str) -> None:
    try:
        BEATS[n](cid)
    except Exception as exc:  # a failed beat must say so on screen, never hang silently
        chat(cid, "system", f"Beat {n} failed: {type(exc).__name__}. Check the server log.")
        print(f"beat {n} on {cid} failed: {exc!r}", file=sys.stderr)


# One queue and one worker per coalition: beats on the same coalition run in the order they were pressed,
# and drills on other coalitions never block the demo.
_queues: dict[str, "queue.Queue[int]"] = {}
_queues_lock = threading.Lock()


def _worker(cid: str, q: "queue.Queue[int]") -> None:
    while True:
        n = q.get()
        _run(n, cid)
        q.task_done()


def _queue_for(cid: str) -> "queue.Queue[int]":
    with _queues_lock:
        q = _queues.get(cid)
        if q is None:
            q = _queues[cid] = queue.Queue()
            threading.Thread(target=_worker, args=(cid, q), daemon=True, name=f"beats-{cid}").start()
        return q


@router.post("/demo/beat/{n}")
def run_beat(n: int, c: str = DEMO_COALITION_ID):
    if n not in BEATS:
        raise HTTPException(404, "Beats are 1 to 7 (7 is the walkout).")
    if not _s().get_coalition(c):
        raise HTTPException(404, f"Unknown coalition {c}")
    q = _queue_for(c)
    ahead = q.unfinished_tasks
    q.put(n)
    return {"started": n, "coalition_id": c, "queued_behind": ahead}


# --- strike vote: the room decides to walk out --------------------------------------------------------
_strike_votes: dict[str, set[str]] = {}  # coalition_id -> real members who voted to strike this run


class VoteIn(BaseModel):
    coalition_id: str
    agent_id: str


def _votes_needed(cid: str) -> int:
    real = _s().counts(cid)["real"]
    return max(1, math.ceil(real * 0.4))  # 40% of the real people in the room


@router.post("/vote/strike")
def vote_strike(body: VoteIn):
    """A real member votes to walk out. When 40% of real members have voted, the walkout fires."""
    s = _s()
    member = s.get_member(body.coalition_id, body.agent_id)
    if not member or member["removed_reason"] or member["client"] not in ("web", "mcp"):
        raise HTTPException(403, "Only real members of this coalition can vote.")
    votes = _strike_votes.setdefault(body.coalition_id, set())
    votes.add(body.agent_id)
    needed = _votes_needed(body.coalition_id)
    bus.publish(body.coalition_id, "strike_votes", {"votes": len(votes), "needed": needed})
    fired = len(votes) >= needed
    if fired:
        record_system(body.coalition_id, "strike_vote", votes=len(votes), needed=needed)
        chat(body.coalition_id, "system", f"The room voted to strike: {len(votes)} of {needed} needed.")
        votes.clear()
        _queue_for(body.coalition_id).put(7)
    return {"votes": len(votes) if not fired else needed, "needed": needed, "fired": fired}


@router.post("/demo/reset")
def reset(c: str = DEMO_COALITION_ID, hard: int = 0):
    s = _s()
    if not s.get_coalition(c):
        s.create_coalition(DEMO_COALITION_NEED if c == DEMO_COALITION_ID else c, c)
    s.reset(c, hard=bool(hard))
    _concessions.pop(c, None)
    _strike_votes.pop(c, None)
    _remembered.pop(c, None)
    secrets = ROOT / "members_secrets.json"
    if secrets.exists():
        secrets.unlink()  # simulated members' secrets are stale once they're removed
    chat(c, "system", "Demo reset." + (" Everything wiped." if hard else " Real members kept."))
    return {"reset": c, "hard": bool(hard), "counts": s.counts(c)}
