"""Offer check (P5): Senso finds the fine print, TypeSafe answers three trap questions, code decides.

The verdict is decided here, in plain code (docs/CONTRACT.md rule 2), never by a model.
Every Senso citation and every TypeSafe answer is written to the public log, so it's part of the audit trail.
Vendor offers are simulated in this demo, and every log entry says so.
"""
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import bus, config
from app import relay
from app import store as store_module

router = APIRouter()

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
TYPESAFE_MODEL = "jev-latest"
# Question ids are ours to name; TypeSafe returns answers under the same ids.
QUESTIONS = {
    "intro_price_jump": "Does `offer` raise the price after an introductory period?",
    "extra_fees": "Does `offer` add fees beyond the base monthly price?",
    "long_contract": "Does `offer` require a contract longer than 12 months?",
}
PASS_BELOW = 0.30
ASK_UP_TO = 0.70
SENSO_TOP_N = 3


class IntegrationError(Exception):
    """A key is missing or a service failed. Never treated as a pass."""


def search_senso(query: str) -> list[dict]:
    if not config.SENSO_API_KEY:
        raise IntegrationError("SENSO_API_KEY is missing")
    url = f"{config.SENSO_BASE_URL.rstrip('/')}/org/search/context"
    try:
        r = httpx.post(url, json={"query": query, "max_results": SENSO_TOP_N, "search_type": "hybrid"},
                       headers={"X-API-Key": config.SENSO_API_KEY}, timeout=30)
    except httpx.HTTPError as exc:
        raise IntegrationError(f"Senso request failed: {type(exc).__name__}")
    if r.status_code != 200:
        raise IntegrationError(f"Senso returned HTTP {r.status_code}")
    results = r.json().get("results") or []
    return [{"content_id": x.get("content_id"), "version_id": x.get("version_id"),
             "chunk_text": x.get("chunk_text") or "", "score": x.get("score"), "rank": x.get("rank")}
            for x in results[:SENSO_TOP_N]]


def ask_typesafe(price_cents: int, terms_text: str, plan_terms: list[str]) -> list[dict]:
    """One request, three Nouls. Returns [{id, q, p}] in QUESTIONS order."""
    if not config.TYPESAFE_API_KEY:
        raise IntegrationError("TYPESAFE_API_KEY is missing")
    body = {
        "model": TYPESAFE_MODEL,
        "state": {"offer": {"price": price_cents / 100, "terms_text": terms_text}, "plan_terms": plan_terms},
        "questions": {qid: {"type": "noul", "instructions": q} for qid, q in QUESTIONS.items()},
    }
    try:
        r = httpx.post(TYPESAFE_URL, json=body, timeout=30,
                       headers={"Authorization": f"Bearer {config.TYPESAFE_API_KEY}"})
    except httpx.HTTPError as exc:
        raise IntegrationError(f"TypeSafe request failed: {type(exc).__name__}")
    if r.status_code != 200:
        raise IntegrationError(f"TypeSafe returned HTTP {r.status_code}")
    answers = r.json().get("answers") or {}
    out = []
    for qid, q in QUESTIONS.items():
        p = (answers.get(qid) or {}).get("noul")
        if not isinstance(p, (int, float)) or not 0 <= p <= 1:
            raise IntegrationError(f"TypeSafe gave no probability for question {qid}")
        out.append({"id": qid, "q": q, "p": float(p)})
    return out


def decide(ps: list[float]) -> str:
    """CONTRACT rule 2. Pass only if every p < 0.30; else ask the member if any p is in 0.30-0.70; else reject."""
    if all(p < PASS_BELOW for p in ps):
        return "pass"
    if any(PASS_BELOW <= p <= ASK_UP_TO for p in ps):
        return "ask_member"
    return "reject"


def check_offer(cid: str, price_cents: int, terms_text: str, search=search_senso, ask=ask_typesafe) -> dict:
    """`search` and `ask` can be replaced with fakes in tests."""
    citations = search(terms_text)
    for c in citations:
        relay.record_system(cid, "senso_citation", simulated_vendor=True, **c)

    if not citations:
        relay.record_system(cid, "trap_check", simulated_vendor=True, verdict="ask_member",
                            note="no supporting context found")
        senso, questions, verdict = [], [], "ask_member"
    else:
        answers = ask(price_cents, terms_text, [c["chunk_text"] for c in citations])
        for a in answers:
            relay.record_system(cid, "trap_question", simulated_vendor=True, q=a["q"], p=a["p"])
        verdict = decide([a["p"] for a in answers])
        questions = [{"q": a["q"], "p": a["p"]} for a in answers]
        senso = [{"content_id": c["content_id"], "version_id": c["version_id"], "score": c["score"]}
                 for c in citations]
        relay.record_system(cid, "trap_check", simulated_vendor=True, verdict=verdict, questions=questions)

    bus.publish(cid, "trap_check", {"questions": questions, "verdict": verdict, "senso": senso})
    return {"verdict": verdict, "questions": questions, "senso": senso,
            "note": "" if citations else "no supporting context found"}


class OfferCheckIn(BaseModel):
    coalition_id: str
    price_cents: int = Field(gt=0)
    terms_text: str = Field(min_length=1)


@router.post("/offer-check")
def offer_check(body: OfferCheckIn):
    if not store_module.store.get_coalition(body.coalition_id):
        raise HTTPException(404, f"Unknown coalition {body.coalition_id}")
    try:
        return check_offer(body.coalition_id, body.price_cents, body.terms_text)
    except IntegrationError as exc:
        raise HTTPException(503, str(exc))
