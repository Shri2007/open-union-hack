#!/usr/bin/env python3
"""Simulated (firedrill) coalition members for Open Union demos.

Talks to the relay over HTTP only, per docs/CONTRACT.md. Every member here is
SIMULATED: it joins with client "firedrill" and a sandbox Persona inquiry id,
and the relay marks it verified only when it runs with SIMULATED_VERIFIED=1.

Each member's walk-away price and salt stay on this machine in
members_secrets.json and are never sent to the relay until REVEAL.

    python scripts/seed_members.py --relay http://localhost:8077 --coalition demo-phone-plan --n 300
    python scripts/seed_members.py reveal  --relay http://localhost:8077 --coalition demo-phone-plan
    python scripts/seed_members.py respond --relay http://localhost:8077 --coalition demo-phone-plan \
        --offer-id <id> --price-cents 5900
"""
import argparse
import asyncio
import hashlib
import json
import os
import random
import secrets
import sys

import httpx

CONCURRENCY = 20
PRICE_MIN_CENTS = 5000
PRICE_MAX_CENTS = 8000
CLIENT = "firedrill"
NEED = "phone plan under $60"
DEFAULT_RELAY = "http://localhost:8077"
DEFAULT_COALITION = "demo-phone-plan"
DEFAULT_SECRETS = "members_secrets.json"


def commitment_for(price_cents: int, salt_hex: str) -> str:
    """The sealed price: lowercase hex sha256("<price_cents>:<salt_hex>")."""
    return hashlib.sha256(f"{price_cents}:{salt_hex}".encode()).hexdigest()


def load_secrets(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save_secrets(path: str, data: dict) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(path, 0o600)


async def post_message(client: httpx.AsyncClient, relay: str, coalition: str,
                       agent_id: str, msg_type: str, body: dict) -> dict:
    r = await client.post(f"{relay.rstrip('/')}/messages", json={
        "coalition_id": coalition,
        "agent_id": agent_id,
        "type": msg_type,
        "body": body,
    })
    r.raise_for_status()
    return r.json()


async def coalition_counts(client: httpx.AsyncClient, relay: str, coalition: str) -> dict | None:
    try:
        r = await client.get(f"{relay.rstrip('/')}/coalitions/{coalition}")
        r.raise_for_status()
        return r.json().get("counts")
    except Exception:
        return None


async def run_capped(jobs) -> list:
    """Run coroutine factories with at most CONCURRENCY in flight."""
    sem = asyncio.Semaphore(CONCURRENCY)

    async def guarded(make):
        async with sem:
            try:
                return await make()
            except Exception as exc:  # a failed member must not stop the drill
                return exc

    return await asyncio.gather(*(guarded(make) for make in jobs))


async def seed(args) -> int:
    members = [{
        "agent_id": f"sim-{secrets.token_hex(5)}",
        "price_cents": random.randint(PRICE_MIN_CENTS, PRICE_MAX_CENTS),
        "salt_hex": secrets.token_hex(16),
        "persona_inquiry_id": f"sandbox-sim-{i + 1}",
    } for i in range(args.n)]

    # Saved before anything is sent: a member whose COMMIT lands but whose response is lost
    # still needs its salt, and the relay refuses a second commitment.
    store = load_secrets(args.secrets)
    store.setdefault(args.coalition, []).extend(members)
    save_secrets(args.secrets, store)

    async with httpx.AsyncClient(timeout=30.0) as client:
        async def send(m):
            await post_message(client, args.relay, args.coalition, m["agent_id"], "INTENT", {"need": args.need})
            await post_message(client, args.relay, args.coalition, m["agent_id"], "JOIN", {
                "persona_inquiry_id": m["persona_inquiry_id"], "client": CLIENT})
            await post_message(client, args.relay, args.coalition, m["agent_id"], "COMMIT", {
                "commitment": commitment_for(m["price_cents"], m["salt_hex"])})
            return m["agent_id"]

        results = await run_capped([lambda m=m: send(m) for m in members])
        counts = await coalition_counts(client, args.relay, args.coalition)

    failed = sum(1 for r in results if isinstance(r, Exception))

    # Verification is the relay's call (SIMULATED_VERIFIED on the server), so read it back.
    counts_note = (f"relay counts {counts['verified']} verified / {counts['unverified']} unverified"
                   if counts else "relay decides verification; its counts were unreadable")
    print(f"simulated (firedrill): seeded {args.n - failed}/{args.n} members, {failed} failed, "
          f"prices {PRICE_MIN_CENTS}-{PRICE_MAX_CENTS} cents sealed in {args.secrets}, "
          f"{counts_note}")
    return 1 if failed else 0


def members_for(args) -> list:
    members = load_secrets(args.secrets).get(args.coalition, [])
    if not members:
        print(f"simulated: no members for {args.coalition} in {args.secrets}; seed first", file=sys.stderr)
    return members


async def reveal(args) -> int:
    members = members_for(args)
    if not members:
        return 1

    async with httpx.AsyncClient(timeout=30.0) as client:
        async def send(m):
            return await post_message(client, args.relay, args.coalition, m["agent_id"], "REVEAL", {
                "price_cents": m["price_cents"], "salt_hex": m["salt_hex"]})

        results = await run_capped([lambda m=m: send(m) for m in members])

    sent = [r for r in results if not isinstance(r, Exception)]
    matched = sum(1 for r in sent if r.get("ok"))
    print(f"simulated (firedrill): revealed {len(sent)}/{len(members)} sealed prices, "
          f"{matched} matched their commitment, {len(members) - len(sent)} failed")
    return 1 if len(sent) != len(members) else 0


async def respond(args) -> int:
    """Each member decides in its own code: accept only if the offer is at or under its own price."""
    members = members_for(args)
    if not members:
        return 1

    async with httpx.AsyncClient(timeout=30.0) as client:
        async def send(m):
            accept = args.price_cents <= m["price_cents"]
            await post_message(client, args.relay, args.coalition, m["agent_id"], "RESPOND", {
                "offer_id": args.offer_id, "accept": accept})
            return accept

        results = await run_capped([lambda m=m: send(m) for m in members])

    sent = [r for r in results if not isinstance(r, Exception)]
    accepted = sum(1 for r in sent if r)
    print(f"simulated (firedrill): responded to offer {args.offer_id} at {args.price_cents} cents - "
          f"{accepted} accepted, {len(sent) - accepted} declined, {len(members) - len(sent)} failed")
    return 1 if len(sent) != len(members) else 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulated firedrill members for Open Union")
    subs = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--relay", default=DEFAULT_RELAY)
        p.add_argument("--coalition", default=DEFAULT_COALITION)
        p.add_argument("--secrets", default=DEFAULT_SECRETS)
        return p

    seed_p = common(subs.add_parser("seed", help="send INTENT, JOIN and COMMIT for n simulated members"))
    seed_p.add_argument("--n", type=int, default=300)
    seed_p.add_argument("--need", default=NEED)
    seed_p.set_defaults(func=seed)

    reveal_p = common(subs.add_parser("reveal", help="send REVEAL for every seeded member"))
    reveal_p.set_defaults(func=reveal)

    respond_p = common(subs.add_parser("respond", help="send RESPOND for every seeded member"))
    respond_p.add_argument("--offer-id", required=True)
    respond_p.add_argument("--price-cents", type=int, required=True)
    respond_p.set_defaults(func=respond)

    # No subcommand means seed, so the plain --relay/--coalition/--n form works.
    if not argv or argv[0].startswith("-"):
        argv = ["seed"] + argv
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv[1:])
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
