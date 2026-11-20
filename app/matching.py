"""POST /coalitions/match: join an existing coalition or start one (docs/CONTRACT.md).

The judgment comes from TypeSafe as a probability; the decision is made here in code.
"""
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import config, relay
from app import store as store_module

router = APIRouter()

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
TYPESAFE_MODEL = "jev-latest"
TIMEOUT_SECONDS = 20.0

QUESTION = "Does `member.need` ask for the same kind of service as `coalition.need`?"
QUESTION_ID = "same_service"
JOIN_AT = 0.7
ASK_USER_AT = 0.3
MAX_CANDIDATES = 5


class MatchIn(BaseModel):
    need: str = Field(min_length=1, max_length=500)


def ask_typesafe(state: dict) -> float:
    """One TypeSafe request with one Noul. Tests replace this function with a fake.

    Returns the probability that the two needs are for the same kind of service.
    A missing key or a failed call raises: a failure is never a "no match".
    """
    key = config.TYPESAFE_API_KEY
    if not key:
        raise HTTPException(503, "TypeSafe is not configured: TYPESAFE_API_KEY is missing.")
    payload = {
        "state": state,
        "model": TYPESAFE_MODEL,
        "questions": {QUESTION_ID: {"type": "noul", "instructions": QUESTION}},
    }
    try:
        response = httpx.post(
            TYPESAFE_URL,
            json=payload,
            headers={"Authorization": f"Bearer {key}"},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return float(response.json()["answers"][QUESTION_ID]["noul"])
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(502, f"TypeSafe call failed: {type(exc).__name__}") from exc


@router.post("/coalitions/match")
def match(body: MatchIn) -> dict:
    store = store_module.store
    need = body.need.strip()

    best_id, best_p = None, 0.0
    for candidate in store.list_coalitions(MAX_CANDIDATES):
        state = {"member": {"need": need}, "coalition": {"need": candidate["need"]}}
        p = ask_typesafe(state)
        relay.record_system(candidate["id"], "match_question", question=QUESTION, state=state, p=p)
        if p > best_p:
            best_id, best_p = candidate["id"], p

    if best_id and best_p >= JOIN_AT:
        return {"status": "joined", "coalition_id": best_id, "member_count": _member_count(store, best_id)}
    if best_p >= ASK_USER_AT:
        return {"status": "ask_user"}

    cid = store.create_coalition(need)
    return {"status": "created", "coalition_id": cid, "member_count": 0}


def _member_count(store, cid: str) -> int:
    counts = store.counts(cid)
    return int(counts.get("verified", 0)) + int(counts.get("unverified", 0))
