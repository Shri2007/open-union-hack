"""Persona identity check (P7 backend). Only members whose Persona inquiry passed count toward the headcount.

Flow: POST /persona/start (creates an inquiry, returns its hosted link) -> the person verifies on Persona ->
the page sends JOIN with the inquiry id -> POST /persona/callback re-checks the inquiry with Persona itself
(never trusting the browser) and marks the member verified.

Persona sandbox does not do real identity checks, and every log line says which environment it came from.
If Persona isn't configured, /persona/stub gives a clearly labeled stub so the demo still runs.
"""
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import bus, config
from app import relay
from app import store as store_module

router = APIRouter()

API = "https://api.withpersona.com/api/v1"
HOSTED_FLOW = "https://inquiry.withpersona.com/verify"
PASSED = {"completed", "approved"}  # Persona statuses that count as passed


class PersonaError(Exception):
    """Persona is unreachable, rejected our key, or isn't configured. Never treated as verified."""


def configured() -> bool:
    return bool(config.PERSONA_API_KEY and config.PERSONA_TEMPLATE_ID)


def environment() -> str:
    key = config.PERSONA_API_KEY
    if key.startswith("persona_sandbox"):
        return "sandbox"
    if key.startswith("persona_production"):
        return "production"
    return "unknown"


def _require_config() -> None:
    missing = [n for n, v in (("PERSONA_API_KEY", config.PERSONA_API_KEY),
                              ("PERSONA_TEMPLATE_ID", config.PERSONA_TEMPLATE_ID)) if not v]
    if missing:
        raise PersonaError(f"{' and '.join(missing)} missing: Persona is not configured")


def _call(method: str, path: str, **kw) -> dict:
    try:
        r = httpx.request(method, API + path, timeout=30,
                          headers={"Authorization": f"Bearer {config.PERSONA_API_KEY}"}, **kw)
    except httpx.HTTPError as exc:
        raise PersonaError(f"Persona request failed: {type(exc).__name__}")
    if r.status_code == 401:
        raise PersonaError("Persona rejected PERSONA_API_KEY (HTTP 401)")
    if r.status_code not in (200, 201):
        raise PersonaError(f"Persona returned HTTP {r.status_code}")
    return r.json()


def create_inquiry(coalition_id: str, agent_id: str) -> dict:
    """Returns {inquiry_id, url}. reference-id binds the inquiry to this one member."""
    _require_config()
    tmpl = config.PERSONA_TEMPLATE_ID
    attr = "inquiry-template-id" if tmpl.startswith("itmpl_") else "template-id"
    data = _call("POST", "/inquiries", json={
        "data": {"attributes": {attr: tmpl, "reference-id": f"{coalition_id}:{agent_id}"}},
        "meta": {"auto-create-one-time-link": True},
    })
    inquiry_id = data["data"]["id"]
    url = (data.get("meta") or {}).get("one-time-link") or f"{HOSTED_FLOW}?inquiry-id={inquiry_id}"
    return {"inquiry_id": inquiry_id, "url": url}


def get_inquiry(inquiry_id: str) -> dict:
    """Returns {status, reference_id} as Persona reports them."""
    _require_config()
    attrs = _call("GET", f"/inquiries/{inquiry_id}")["data"].get("attributes", {})
    return {"status": attrs.get("status"), "reference_id": attrs.get("reference-id")}


class StartIn(BaseModel):
    coalition_id: str
    agent_id: str


class CallbackIn(BaseModel):
    coalition_id: str
    agent_id: str
    inquiry_id: str


def _member_or_404(coalition_id: str, agent_id: str) -> dict:
    member = store_module.store.get_member(coalition_id, agent_id)
    if not member or member["removed_reason"]:
        raise HTTPException(404, "Unknown member. Send JOIN first.")
    return member


def _mark_verified(cid: str, agent_id: str, text: str, **log) -> None:
    store_module.store.set_verified(cid, agent_id, True)
    relay.record_system(cid, "persona_check", agent_id=agent_id, passed=True, **log)
    bus.publish(cid, "chat", {"who": "persona", "text": text})


@router.post("/persona/start")
def start(body: StartIn):
    if not store_module.store.get_coalition(body.coalition_id):
        raise HTTPException(404, f"Unknown coalition {body.coalition_id}")
    try:
        out = create_inquiry(body.coalition_id, body.agent_id)
    except PersonaError as exc:
        raise HTTPException(503, str(exc))
    return {**out, "environment": environment()}


@router.post("/persona/callback")
def callback(body: CallbackIn):
    cid, agent = body.coalition_id, body.agent_id
    _member_or_404(cid, agent)
    try:
        inquiry = get_inquiry(body.inquiry_id)
    except PersonaError as exc:
        raise HTTPException(503, str(exc))
    if inquiry["reference_id"] != f"{cid}:{agent}":
        raise HTTPException(403, "This inquiry belongs to a different member.")
    for row in store_module.store.log(cid):  # one inquiry, one member: stops one ID backing many accounts
        b = row["body"]
        if row["type"] == "SYSTEM" and b.get("kind") == "persona_check" and b.get("passed") \
                and b.get("inquiry_id") == body.inquiry_id and b.get("agent_id") != agent:
            raise HTTPException(409, "This inquiry already verified another member.")
    env = environment()
    if inquiry["status"] in PASSED:
        label = "Persona sandbox (no real identity check)" if env == "sandbox" else f"Persona {env}"
        _mark_verified(cid, agent, f"{label}: member verified.", inquiry_id=body.inquiry_id,
                       status=inquiry["status"], environment=env)
        return {"verified": True, "status": inquiry["status"]}
    relay.record_system(cid, "persona_check", agent_id=agent, passed=False, inquiry_id=body.inquiry_id,
                        status=inquiry["status"], environment=env)
    return {"verified": False, "status": inquiry["status"]}


@router.post("/persona/stub")
def stub(body: StartIn):
    """Clearly labeled stub for when Persona isn't set up. Refused if Persona is configured."""
    if configured():
        raise HTTPException(409, "Persona is configured: use the real flow.")
    _member_or_404(body.coalition_id, body.agent_id)
    _mark_verified(body.coalition_id, body.agent_id, "SANDBOX STUB (simulated): member marked verified.",
                   stub=True, simulated=True, environment="stub")
    return {"verified": True, "status": "stub"}
