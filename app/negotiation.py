"""Demo beats 1–6 and reset (prompt P4). Each beat runs in the background so the presenter's key press returns at once.

Pieces built by others plug in here:
- app/vendor.py (Codex): price_for(n) and say(who, situation, fallback)
- app/tally.py (Capy): compute_tally(rows, offer_price_cents, eligible)
- app/offer_check.py (Ali): check_offer(cid, price_cents, terms_text) -> {"verdict": "pass"|"reject"|"ask_member", ...}
Until each lands, the local fallbacks below keep the demo running.
"""
import math
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

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
_running = threading.Lock()

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
    have = _s().counts(cid)["simulated"]
    proc = _script("scripts/seed_members.py", "--relay", RELAY_URL, "--coalition", cid,
                   "--n", str(max(0, SEED_TARGET - have))) if have < SEED_TARGET else None
    last = -1
    while True:
        n = _s().counts(cid)["verified"]
        if n != last and n > 0 and (n - last >= 60 or (proc and proc.poll() is not None)):
            offer(cid, price_for(n), f"Volume quote for {n} verified lines, 12-month term.")
            last = n
        if not proc or proc.poll() is not None:
            break
        time.sleep(1.5)
    n = _s().counts(cid)["verified"]
    if n != last:
        offer(cid, price_for(n), f"Volume quote for {n} verified lines, 12-month term.")
    chat(cid, "coalition", say("coalition", f"{n} verified members want a phone plan under $60. Ask for a volume price.",
                               f"{n} verified members want a plan under $60. What's your volume price?"))
    chat(cid, "vendor", say("vendor", f"You sell monthly phone plans. Quote {dollars(price_for(n))} per phone line per month "
                                      f"for {n} verified people, 12-month term.",
                            f"For {n} verified lines, {dollars(price_for(n))} a month on a 12-month term."))


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
    offer(cid, price_for(n), f"Volume quote for {n} verified lines, 12-month term.")
    chat(cid, "vendor", say("vendor", f"You sell monthly phone plans. Accept that {n} verified people each want one phone line; "
                                      f"your quote stays {dollars(price_for(n))} per line per month.",
                            f"{n} verified lines. {dollars(price_for(n))} stands."))
    chat(cid, "system", "Fakes removed. The price is back where real people put it.")


def beat5(cid: str) -> None:
    chat(cid, "system", "Beat 5 · The vendor's final offer, checked against the fine print.")
    chat(cid, "vendor", say("vendor", "Present a final offer of $58 a month, sounding generous. Don't mention the fine print.",
                            "Final offer: $58 a month. You won't find better."))
    offer(cid, 5800, TRAP_TERMS)
    result = _check_offer(cid, 5800, TRAP_TERMS)
    if result.get("verdict") == "pass":
        chat(cid, "system", "Offer check passed the trap offer. Review the trap questions.")
        return
    chat(cid, "coalition", "Rejected. $58 that becomes $95 after 3 months, plus fees, is not $58. "
                           "We need $58 fixed for 12 months, no added fees.")
    time.sleep(TRAP_PAUSE_SECONDS)  # keep the rejected trap check on screen long enough for the room to read it
    chat(cid, "vendor", say("vendor", "Grudgingly agree to $58 a month fixed for 12 months with no added fees.",
                            "Fine. $58 a month, fixed for 12 months, no added fees."))
    offer(cid, 5800, CLEAN_TERMS)
    _check_offer(cid, 5800, CLEAN_TERMS)


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
    chat(cid, "system", f"{t['accepted']} of {t['total']} members accept {dollars(price)}. "
                        f"Each saves {dollars(8500 - price)} a month. Check it yourself at /verify.html.")


BEATS = {1: beat1, 2: beat2, 3: beat3, 4: beat4, 5: beat5, 6: beat6}


def _run(n: int, cid: str) -> None:
    try:
        BEATS[n](cid)
    except Exception as exc:  # a failed beat must say so on screen, never hang silently
        chat(cid, "system", f"Beat {n} failed: {type(exc).__name__}. Check the server log.")
        raise
    finally:
        _running.release()


@router.post("/demo/beat/{n}")
def run_beat(n: int, c: str = DEMO_COALITION_ID):
    if n not in BEATS:
        raise HTTPException(404, "Beats are 1 to 6.")
    if not _s().get_coalition(c):
        raise HTTPException(404, f"Unknown coalition {c}")
    if not _running.acquire(blocking=False):
        raise HTTPException(409, "Another beat is still running.")
    threading.Thread(target=_run, args=(n, c), daemon=True).start()
    return {"started": n, "coalition_id": c}


@router.post("/demo/reset")
def reset(c: str = DEMO_COALITION_ID, hard: int = 0):
    s = _s()
    if not s.get_coalition(c):
        s.create_coalition(DEMO_COALITION_NEED if c == DEMO_COALITION_ID else c, c)
    s.reset(c, hard=bool(hard))
    secrets = ROOT / "members_secrets.json"
    if secrets.exists():
        secrets.unlink()  # simulated members' secrets are stale once they're removed
    chat(c, "system", "Demo reset." + (" Everything wiped." if hard else " Real members kept."))
    return {"reset": c, "hard": bool(hard), "counts": s.counts(c)}
