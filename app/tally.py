"""Recompute the close tally from /log rows alone (docs/CONTRACT.md rule 4).

Pure: no database, no network, no routes. The same arithmetic web/verify.html does in the
browser, so a judge can compare the two numbers.
"""
from app.protocol import SYSTEM_AGENT_ID, VENDOR_AGENT_ID, reveal_matches

NON_MEMBER_AGENTS = (VENDOR_AGENT_ID, SYSTEM_AGENT_ID)
AGENT_TYPES = ("JOIN", "COMMIT", "REVEAL", "INTENT", "RESPOND")


def compute_tally(rows: list[dict], offer_price_cents: int, eligible: set[str] | None = None) -> dict:
    """Count how many agents revealed a price that matches their commitment and accepts the offer.

    Each agent is judged on its first COMMIT and its latest REVEAL. A REVEAL that cannot be
    hashed (price_cents not an int, salt_hex not a str) or that has no commitment is a mismatch,
    never a silent skip, so a malformed reveal can never be counted as accepted.
    """
    agents: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        agent_id = row.get("agent_id")
        if not isinstance(agent_id, str) or agent_id in NON_MEMBER_AGENTS:
            continue
        if row.get("type") not in AGENT_TYPES:
            continue
        if eligible is not None and agent_id not in eligible:
            continue
        agent = agents.setdefault(agent_id, {"commitment": None, "reveal": None})
        body = row.get("body") if isinstance(row.get("body"), dict) else {}
        if row["type"] == "COMMIT" and agent["commitment"] is None:
            # First COMMIT wins: the relay allows only one, and a later one can't change a sealed price.
            commitment = body.get("commitment")
            if isinstance(commitment, str):
                agent["commitment"] = commitment
        if row["type"] == "REVEAL":
            agent["reveal"] = body

    accepted = mismatched = not_revealed = 0
    revealed: list[dict] = []
    for agent_id in sorted(agents):
        agent = agents[agent_id]
        reveal = agent["reveal"]
        if reveal is None:
            not_revealed += 1
            continue
        price_cents, salt_hex = reveal.get("price_cents"), reveal.get("salt_hex")
        malformed = (not isinstance(price_cents, int) or isinstance(price_cents, bool)
                     or not isinstance(salt_hex, str))
        ok = (not malformed
              and agent["commitment"] is not None
              and reveal_matches(agent["commitment"], price_cents, salt_hex))
        revealed.append({"agent_id": agent_id, "price_cents": price_cents if not malformed else None, "ok": ok})
        if ok and price_cents >= offer_price_cents:
            accepted += 1
        elif not ok:
            mismatched += 1

    return {
        "accepted": accepted,
        "total": len(agents),
        "mismatched": mismatched,
        "not_revealed": not_revealed,
        "revealed": revealed,
    }
