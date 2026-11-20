#!/usr/bin/env python3
"""Open Union MCP adapter: let any MCP client (Claude Desktop, Cursor) join a coalition.

Five tools over stdio, talking to the relay over HTTP per docs/CONTRACT.md:
union_find, union_join, union_status, union_respond, union_reveal.

Trust boundary (CONTRACT "Trust boundaries"): the walk-away price and its salt
live only in ~/.open-union/secrets.json on this machine. The relay never sees
them before REVEAL, and no tool ever returns the price to the model. The accept
decision in union_respond is computed here in code, never by the model.

    RELAY_URL=http://localhost:8077 python -m union_mcp.server
    python -m union_mcp.server --print-config   # claude_desktop_config.json snippet
"""
import hashlib
import json
import os
import secrets as secrets_mod
import sys
from pathlib import Path
from typing import Any

import httpx

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
except ModuleNotFoundError:  # mcp 1.x, where the same class is called FastMCP
    from mcp.server.fastmcp import FastMCP as _Server

DEFAULT_RELAY = "http://localhost:8077"
CLIENT = "mcp"
SECRETS_PATH = Path.home() / ".open-union" / "secrets.json"
TIMEOUT_SECONDS = 20.0

mcp = _Server("open-union")


def relay_url() -> str:
    return os.environ.get("RELAY_URL", DEFAULT_RELAY).rstrip("/")


def commitment_for(price_cents: int, salt_hex: str) -> str:
    """The sealed price: lowercase hex sha256("<price_cents>:<salt_hex>")."""
    return hashlib.sha256(f"{price_cents}:{salt_hex}".encode()).hexdigest()


# ---------------------------------------------------------------- local secrets

def _read_secrets() -> dict[str, Any]:
    try:
        return json.loads(SECRETS_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_secret(coalition_id: str, record: dict) -> None:
    SECRETS_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    data = _read_secrets()
    data[coalition_id] = record
    SECRETS_PATH.write_text(json.dumps(data, indent=2))
    SECRETS_PATH.chmod(0o600)


def _secret(coalition_id: str) -> dict | None:
    return _read_secrets().get(coalition_id)


# ------------------------------------------------------------------ relay calls

def _post(path: str, payload: dict) -> dict:
    response = httpx.post(f"{relay_url()}{path}", json=payload, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()

def _get(path: str, params: dict | None = None) -> Any:
    response = httpx.get(f"{relay_url()}{path}", params=params, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def _send(coalition_id: str, agent_id: str, msg_type: str, body: dict) -> dict:
    return _post("/messages", {"coalition_id": coalition_id, "agent_id": agent_id,
                               "type": msg_type, "body": body})


def _error(exc: Exception) -> dict:
    if isinstance(exc, httpx.HTTPStatusError):
        return {"error": f"relay returned {exc.response.status_code}: {exc.response.text[:300]}"}
    return {"error": f"could not reach the relay at {relay_url()}: {type(exc).__name__}"}


def _latest_offer(log: list[dict]) -> dict | None:
    offers = [row for row in log if row["type"] == "OFFER"]
    if not offers:
        return None
    row = offers[-1]
    return {"offer_id": row["id"], "price_cents": row["body"]["price_cents"],
            "terms_text": row["body"]["terms_text"]}


# ------------------------------------------------------------------------ tools

@mcp.tool()
def union_find(need: str) -> dict:
    """Find a buyers' coalition for what you want cheaper, e.g. "phone plan under $60"."""
    try:
        result = _post("/coalitions/match", {"need": need})
    except Exception as exc:  # the model needs the reason, not a traceback
        return _error(exc)
    if result.get("status") == "ask_user":
        return {"status": "ask_user",
                "message": "No clear match. Ask the person whether to start a new coalition for this need."}
    return {"status": result.get("status"), "coalition_id": result.get("coalition_id"),
            "member_count": result.get("member_count"),
            "next_step": "Call union_join with the person's maximum monthly price."}


@mcp.tool()
def union_join(coalition_id: str, max_monthly_price_usd: float) -> dict:
    """Join a coalition with a sealed walk-away price.

    The price and its salt are written only to ~/.open-union/secrets.json on this
    machine. Only the commitment hash is sent to the relay and returned here.
    """
    price_cents = int(round(max_monthly_price_usd * 100))
    if price_cents <= 0:
        return {"error": "max_monthly_price_usd must be greater than 0."}

    existing = _secret(coalition_id)
    if existing:
        return {"status": "already_joined", "coalition_id": coalition_id,
                "agent_id": existing["agent_id"], "commitment": existing["commitment"],
                "note": "A sealed price is already stored for this coalition and cannot be changed."}

    agent_id = f"mcp-{secrets_mod.token_hex(3)}"
    salt_hex = secrets_mod.token_hex(32)
    commitment = commitment_for(price_cents, salt_hex)
    try:
        _send(coalition_id, agent_id, "JOIN", {"persona_inquiry_id": None, "client": CLIENT})
        _send(coalition_id, agent_id, "COMMIT", {"commitment": commitment})
    except Exception as exc:
        return _error(exc)

    _write_secret(coalition_id, {"agent_id": agent_id, "price_cents": price_cents,
                                 "salt_hex": salt_hex, "commitment": commitment})
    return {"status": "joined", "coalition_id": coalition_id, "agent_id": agent_id,
            "client": CLIENT, "commitment": commitment,
            "note": "The price stays on this machine. The relay only has the commitment hash."}


@mcp.tool()
def union_status(coalition_id: str) -> dict:
    """The coalition's state and member counts, the latest offer, and this member's state."""
    try:
        coalition = _get(f"/coalitions/{coalition_id}")
        log = _get("/log", {"coalition_id": coalition_id})
    except Exception as exc:
        return _error(exc)

    secret = _secret(coalition_id)
    me: dict[str, Any] = {"joined": False}
    if secret:
        agent_id = secret["agent_id"]
        mine = [row["type"] for row in log if row["agent_id"] == agent_id]
        me = {"joined": True, "agent_id": agent_id, "client": CLIENT,
              "commitment": secret["commitment"], "committed": "COMMIT" in mine,
              "responded": "RESPOND" in mine, "revealed": "REVEAL" in mine}

    return {"coalition_id": coalition_id, "state": coalition.get("state"),
            "need": coalition.get("need"), "counts": coalition.get("counts"),
            "offer": _latest_offer(log), "me": me}


@mcp.tool()
def union_respond(coalition_id: str) -> dict:
    """Accept or decline the latest offer. The decision is a comparison in code, not a judgment call."""
    secret = _secret(coalition_id)
    if not secret:
        return {"error": "No sealed price stored for this coalition. Call union_join first."}
    try:
        offer = _latest_offer(_get("/log", {"coalition_id": coalition_id}))
    except Exception as exc:
        return _error(exc)
    if not offer:
        return {"status": "no_offer", "message": "The vendor has not made an offer yet."}

    accept = offer["price_cents"] <= secret["price_cents"]  # CONTRACT rule 3
    try:
        _send(coalition_id, secret["agent_id"], "RESPOND", {"offer_id": offer["offer_id"], "accept": accept})
    except Exception as exc:
        return _error(exc)
    return {"status": "responded", "offer_id": offer["offer_id"],
            "offer_price_cents": offer["price_cents"], "accept": accept,
            "reason": ("the offer is at or below the sealed limit" if accept
                       else "the offer is above the sealed limit")}


@mcp.tool()
def union_reveal(coalition_id: str) -> dict:
    """Reveal the sealed price so anyone can re-check the tally. Only works while the coalition is closing."""
    secret = _secret(coalition_id)
    if not secret:
        return {"error": "No sealed price stored for this coalition. Call union_join first."}
    try:
        state = _get(f"/coalitions/{coalition_id}").get("state")
    except Exception as exc:
        return _error(exc)
    if state != "closing":
        return {"status": "refused", "state": state,
                "message": "REVEAL is only accepted while the coalition is closing."}
    try:
        result = _send(coalition_id, secret["agent_id"], "REVEAL",
                       {"price_cents": secret["price_cents"], "salt_hex": secret["salt_hex"]})
    except Exception as exc:
        return _error(exc)
    return {"status": "revealed", "agent_id": secret["agent_id"],
            "commitment": secret["commitment"], "matches_commitment": result.get("ok")}


# ----------------------------------------------------------------------- config

def config_snippet() -> str:
    """The exact claude_desktop_config.json entry for this checkout."""
    entry = {
        "mcpServers": {
            "open-union": {
                "command": sys.executable,
                "args": [str(Path(__file__).resolve())],
                "env": {"RELAY_URL": relay_url()},
            }
        }
    }
    return json.dumps(entry, indent=2)


def main() -> None:
    if "--print-config" in sys.argv:
        print(config_snippet())
        return
    # stdout is the MCP transport, so the snippet goes to stderr.
    print("Add this to claude_desktop_config.json:\n" + config_snippet(), file=sys.stderr)
    print(f"open-union MCP server on stdio, relay {relay_url()}", file=sys.stderr)
    mcp.run("stdio")


if __name__ == "__main__":
    main()
