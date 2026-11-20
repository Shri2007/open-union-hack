"""Persona verification: only a verified unique human counts toward the headcount (docs/CONTRACT.md).

The join page opens Persona's hosted flow with PERSONA_TEMPLATE_ID and then posts here; Persona's own
webhook can post here too. Either way a member is marked verified only when its inquiry is completed
or approved. With no PERSONA_API_KEY the relay runs a clearly labeled sandbox stub instead.

In live mode the relay never trusts a status sent by the browser or a webhook body: it asks Persona itself
for the inquiry, and the inquiry's reference-id must be this member's "<coalition>:<agent>". Persona, not
this code, decides who is a unique human: turn on duplicate detection in the Persona template.
"""
import logging
import re
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import bus, config, relay
from app import store as store_module

router = APIRouter()
log = logging.getLogger("open_union.persona")

PERSONA_API = "https://withpersona.com/api/v1/inquiries"
PERSONA_VERSION = "2023-01-05"
HOSTED_FLOW_URL = "https://withpersona.com/verify"
TIMEOUT_SECONDS = 15.0
PASSED_STATUSES = ("completed", "approved")
STUB_MODE = "sandbox-stub"
LIVE_MODE = "live"


class CallbackIn(BaseModel):
    """Our join page's shape. A Persona webhook posts its own JSON, parsed out of `extra`."""
    coalition_id: str | None = Field(default=None, max_length=36)
    agent_id: str | None = Field(default=None, max_length=64)
    inquiry_id: str | None = Field(default=None, max_length=128)
    status: str | None = Field(default=None, max_length=64)
    model_config = {"extra": "allow"}


INQUIRY_ID = re.compile(r"inq_[A-Za-z0-9]{1,64}")  # goes into a URL path next to our API key


def _mode() -> str:
    return LIVE_MODE if config.PERSONA_API_KEY else STUB_MODE


def _environment() -> str:
    """Persona sandbox does no real identity check, so the log and chat must say which one this is."""
    key = config.PERSONA_API_KEY
    return "sandbox" if key.startswith("persona_sandbox") else "production" if key.startswith("persona_production") else "unknown"


def _inquiry_id(body: "CallbackIn") -> Any:
    """From our join page's field, or from a Persona webhook (data.attributes.payload.data.id)."""
    if body.inquiry_id:
        return body.inquiry_id
    found = _dig(body.model_extra or {}, "inquiry-id", "inquiry_id", "inquiryId")
    if found:
        return found
    node: Any = body.model_extra or {}
    for key in ("data", "attributes", "payload", "data"):
        node = node.get(key) if isinstance(node, dict) else None
    return node.get("id") if isinstance(node, dict) and str(node.get("id", "")).startswith("inq_") else None


def _dig(value: Any, *keys: str) -> Any:
    """First value found under any of `keys`, at any depth of a webhook payload."""
    if isinstance(value, dict):
        for key in keys:
            if value.get(key) is not None and not isinstance(value.get(key), (dict, list)):
                return value[key]
        for nested in value.values():
            found = _dig(nested, *keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _dig(nested, *keys)
            if found is not None:
                return found
    return None


def _reference(body: CallbackIn) -> tuple[str | None, str | None]:
    """coalition_id and agent_id, from our own fields or from the inquiry's reference-id."""
    if body.coalition_id and body.agent_id:
        return body.coalition_id, body.agent_id
    raw = _dig(body.model_extra or {}, "reference-id", "reference_id", "referenceId")
    if isinstance(raw, str) and ":" in raw:
        cid, _, agent = raw.partition(":")
        return cid or None, agent or None
    return body.coalition_id, body.agent_id


def fetch_inquiry(inquiry_id: str) -> dict:
    """Ask Persona itself for the inquiry: {status, reference_id}. Tests replace this function with a fake."""
    try:
        response = httpx.get(
            f"{PERSONA_API}/{inquiry_id}",
            headers={"Authorization": f"Bearer {config.PERSONA_API_KEY}",
                     "Persona-Version": PERSONA_VERSION,
                     "Key-Inflection": "kebab"},
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code == 401:
            raise HTTPException(502, "Persona rejected PERSONA_API_KEY (HTTP 401)")
        response.raise_for_status()
        attrs = response.json()["data"]["attributes"]
        return {"status": str(attrs["status"]).lower(), "reference_id": attrs.get("reference-id")}
    except HTTPException:
        raise
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(502, f"Persona inquiry lookup failed: {type(exc).__name__}") from exc


class StartIn(BaseModel):
    coalition_id: str = Field(max_length=36)
    agent_id: str = Field(max_length=64)


def _persona_headers() -> dict:
    return {"Authorization": f"Bearer {config.PERSONA_API_KEY}", "Persona-Version": PERSONA_VERSION,
            "Key-Inflection": "camel", "Content-Type": "application/json"}


@router.post("/persona/start")
def persona_start(body: StartIn) -> dict:
    """Create the inquiry server-side and return a one-time hosted link.

    This sidesteps the hosted flow's template, environment and redirect-domain settings: the link already
    points at the right sandbox inquiry, and the person comes back to the join page themselves.
    """
    if _mode() != LIVE_MODE or not config.PERSONA_TEMPLATE_ID:
        raise HTTPException(409, "Persona isn't configured on this relay. Use the sandbox stub.")
    try:
        created = httpx.post(PERSONA_API, headers=_persona_headers(), timeout=TIMEOUT_SECONDS, json={
            "data": {"attributes": {"inquiryTemplateId": config.PERSONA_TEMPLATE_ID,
                                    "referenceId": f"{body.coalition_id}:{body.agent_id}"}}})
        created.raise_for_status()
        inquiry_id = created.json()["data"]["id"]
        link = httpx.post(f"{PERSONA_API}/{inquiry_id}/generate-one-time-link", headers=_persona_headers(),
                          timeout=TIMEOUT_SECONDS, json={})
        link.raise_for_status()
        meta = link.json().get("meta") or {}
        url = meta.get("oneTimeLink") or meta.get("one-time-link")
        if not url:
            raise KeyError("oneTimeLink")
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(502, f"Persona could not start an inquiry: {type(exc).__name__}") from exc
    log.info("persona inquiry started agent=%s", body.agent_id)
    return {"inquiry_id": inquiry_id, "url": url}


@router.get("/persona/callback")
def persona_config() -> dict:
    """What the join page needs to start verification: live hosted flow, or the sandbox stub."""
    return {"mode": _mode(),
            "template_id": config.PERSONA_TEMPLATE_ID or None,
            "hosted_flow_url": HOSTED_FLOW_URL}


@router.post("/persona/callback")
def persona_callback(body: CallbackIn) -> dict:
    """Mark a member verified once its Persona inquiry passed. Every outcome goes in the public log."""
    store = store_module.store
    cid, agent_id = _reference(body)
    inquiry_id = _inquiry_id(body)
    if not cid or not agent_id:
        raise HTTPException(422, "coalition_id and agent_id are required (or a reference-id of '<coalition_id>:<agent_id>').")
    if not store.get_coalition(cid):
        raise HTTPException(404, f"Unknown coalition {cid}")
    member = store.get_member(cid, agent_id)
    if not member or member["removed_reason"]:
        raise HTTPException(403, "Only current members can be verified. Send JOIN first.")

    mode = _mode()
    if mode == STUB_MODE:
        # No Persona key on this relay: label the stub everywhere it shows up.
        status, inquiry_id = STUB_MODE, inquiry_id or STUB_MODE
    else:
        # Never trust a status sent by the browser or a webhook body: ask Persona itself, every time.
        if not inquiry_id:
            raise HTTPException(422, "inquiry_id is required when Persona is configured.")
        if not INQUIRY_ID.fullmatch(str(inquiry_id)):
            raise HTTPException(422, "inquiry_id must look like inq_xxxxxxxx.")
        inquiry = fetch_inquiry(str(inquiry_id))
        status = inquiry["status"]
        if inquiry["reference_id"] != f"{cid}:{agent_id}":
            raise HTTPException(403, "This inquiry belongs to a different member.")

    verified = mode == STUB_MODE or status in PASSED_STATUSES
    if verified:
        store.set_verified(cid, agent_id, True)
    env = "stub" if mode == STUB_MODE else _environment()
    relay.record_system(cid, "persona_check", agent_id=agent_id, inquiry_id=inquiry_id,
                        status=status, mode=mode, environment=env, verified=verified)
    label = (" (sandbox stub, not a real identity check)" if mode == STUB_MODE
             else "" if env == "production"
             else " (Persona sandbox, not a real identity check)" if env == "sandbox"
             else " (Persona environment unconfirmed)")
    bus.publish(cid, "chat", {"who": "persona",
                              "text": (f"{agent_id} is a verified unique human{label}." if verified
                                       else f"{agent_id} is not verified: inquiry {status}.")})
    log.info("persona check mode=%s verified=%s agent=%s", mode, verified, agent_id)
    return {"coalition_id": cid, "agent_id": agent_id, "inquiry_id": inquiry_id,
            "status": status, "mode": mode, "verified": verified}
