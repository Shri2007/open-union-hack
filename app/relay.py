"""Relay routes: append protocol messages to the public log and stream live events (docs/CONTRACT.md)."""
import asyncio
import json
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app import bus
from app import store as store_module
from app.protocol import (DEMO_COALITION_ID, SYSTEM_AGENT_ID, MessageIn, reveal_matches, validate_body)

router = APIRouter()
HEARTBEAT_SECONDS = 15


def _store():
    # Looked up at call time so tests can swap in a fake store.
    return store_module.store


def record_system(cid: str, kind: str, **data) -> dict:
    """Write a judgment or check into the public log, so it's part of the audit trail."""
    return _store().append(cid, SYSTEM_AGENT_ID, "SYSTEM", {"kind": kind, **data})


def _simulated_verified(client: str) -> bool:
    return client == "firedrill" and os.environ.get("SIMULATED_VERIFIED") == "1"


@router.post("/messages")
def post_message(msg: MessageIn):
    s = _store()
    coalition = s.get_coalition(msg.coalition_id)
    if not coalition:
        raise HTTPException(404, f"Unknown coalition {msg.coalition_id}")
    try:
        body = validate_body(msg.type, msg.body)
    except ValidationError as exc:
        raise HTTPException(422, json.loads(exc.json()))

    cid, agent = msg.coalition_id, msg.agent_id
    member = s.get_member(cid, agent)

    if msg.type == "JOIN":
        verified = _simulated_verified(body.client)
        row = s.append(cid, agent, "JOIN", body.model_dump())
        s.upsert_member(cid, agent, body.client, verified)
        bus.publish(cid, "member_joined", {"agent_id": agent, "client": body.client, "verified": verified})
        return {"id": row["id"], "ts": row["ts"]}

    if msg.type in ("COMMIT", "RESPOND", "REVEAL"):
        if not member or member["removed_reason"]:
            raise HTTPException(403, "Only current members can send this message. Send JOIN first.")

    if msg.type == "COMMIT":
        if s.find_commit(cid, agent):
            # One commitment per member: a limit can't be changed after offers arrive.
            raise HTTPException(409, "This member already committed a sealed price.")

    if msg.type == "RESPOND":
        offer = s.get_log_row(cid, body.offer_id)
        if not offer or offer["type"] != "OFFER":
            raise HTTPException(404, "offer_id does not match an OFFER in this coalition.")

    if msg.type == "REVEAL":
        if coalition["state"] != "closing":
            raise HTTPException(409, "REVEAL is only accepted while the coalition is closing.")
        commitment = s.find_commit(cid, agent)
        ok = bool(commitment) and reveal_matches(commitment, body.price_cents, body.salt_hex)
        row = s.append(cid, agent, "REVEAL", body.model_dump())
        record_system(cid, "reveal_check", agent_id=agent, ok=ok,
                      reason=None if ok else ("no commitment" if not commitment else "does not match commitment"))
        return {"id": row["id"], "ts": row["ts"], "ok": ok}

    row = s.append(cid, agent, msg.type, body.model_dump())

    if msg.type == "OFFER":
        bus.publish(cid, "offer", {"offer_id": row["id"], "price_cents": body.price_cents,
                                   "terms_text": body.terms_text})
    return {"id": row["id"], "ts": row["ts"]}


@router.get("/log")
def get_log(coalition_id: str = DEMO_COALITION_ID):
    return _store().log(coalition_id)


@router.get("/coalitions/{coalition_id}")
def get_coalition(coalition_id: str):
    s = _store()
    coalition = s.get_coalition(coalition_id)
    if not coalition:
        raise HTTPException(404, f"Unknown coalition {coalition_id}")
    return {**coalition, "counts": s.counts(coalition_id)}


@router.get("/stream")
async def stream(request: Request, coalition_id: str = DEMO_COALITION_ID):
    q = bus.subscribe(coalition_id)

    async def events():
        try:
            yield ": connected\n\n"
            while not await request.is_disconnected():
                try:
                    event, data = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_SECONDS)
                    yield f"event: {event}\ndata: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            bus.unsubscribe(coalition_id, q)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
