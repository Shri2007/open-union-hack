#!/usr/bin/env python3
"""Simulated sybil attack on an Open Union coalition.

SIMULATED / SANDBOX only: floods the relay with JOINs that carry no Persona
inquiry id, using client "simulated-attack" per docs/CONTRACT.md, so the demo
can show that unverified headcount never counts toward pricing. HTTP only.

    python scripts/sybil_attack.py --relay http://localhost:8077 --coalition demo-phone-plan --n 500
"""
import argparse
import asyncio
import secrets
import sys

import httpx

CONCURRENCY = 20
CLIENT = "simulated-attack"
DEFAULT_RELAY = "http://localhost:8077"
DEFAULT_COALITION = "demo-phone-plan"


async def run_capped(jobs) -> list:
    """Run coroutine factories with at most CONCURRENCY in flight."""
    sem = asyncio.Semaphore(CONCURRENCY)

    async def guarded(make):
        async with sem:
            try:
                return await make()
            except Exception as exc:
                return exc

    return await asyncio.gather(*(guarded(make) for make in jobs))


async def attack(args) -> int:
    agent_ids = [f"atk-{secrets.token_hex(5)}" for _ in range(args.n)]

    async with httpx.AsyncClient(timeout=30.0) as client:
        async def join(agent_id):
            r = await client.post(f"{args.relay.rstrip('/')}/messages", json={
                "coalition_id": args.coalition,
                "agent_id": agent_id,
                "type": "JOIN",
                "body": {"persona_inquiry_id": None, "client": CLIENT},
            })
            r.raise_for_status()
            return r.json()

        results = await run_capped([lambda a=a: join(a) for a in agent_ids])

    sent = sum(1 for r in results if not isinstance(r, Exception))
    print(f"simulated attack (sandbox): sent {sent}/{args.n} unverified JOINs as client "
          f"'{CLIENT}' to {args.coalition}, {args.n - sent} failed")
    return 1 if sent != args.n else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulated sybil attack (sandbox) for Open Union")
    parser.add_argument("--relay", default=DEFAULT_RELAY)
    parser.add_argument("--coalition", default=DEFAULT_COALITION)
    parser.add_argument("--n", type=int, default=500)
    args = parser.parse_args(sys.argv[1:])
    return asyncio.run(attack(args))


if __name__ == "__main__":
    raise SystemExit(main())
