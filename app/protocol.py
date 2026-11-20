"""The Open Union protocol: message envelope, body schemas and the commitment check (docs/CONTRACT.md)."""
import hashlib
import hmac
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

MessageType = Literal["INTENT", "JOIN", "COMMIT", "OFFER", "RESPOND", "REVEAL", "SYSTEM"]
Client = Literal["web", "mcp", "firedrill", "simulated-attack"]

HEX64 = r"^[0-9a-f]{64}$"
HEX = r"^[0-9a-f]{2,128}$"

DEMO_COALITION_ID = "demo-phone-plan"
DEMO_COALITION_NEED = "phone plan under $60"
VENDOR_AGENT_ID = "vendor"
SYSTEM_AGENT_ID = "system"
REAL_CLIENTS = ("web", "mcp")


class MessageIn(BaseModel):
    coalition_id: str = Field(min_length=1, max_length=36)
    agent_id: str = Field(min_length=1, max_length=64)
    type: MessageType
    body: dict[str, Any] = Field(default_factory=dict)


class IntentBody(BaseModel):
    need: str = Field(min_length=1, max_length=500)


class JoinBody(BaseModel):
    persona_inquiry_id: Optional[str] = None
    client: Client


class CommitBody(BaseModel):
    commitment: str = Field(pattern=HEX64)


class TrapCheck(BaseModel):
    q: str
    p: float = Field(ge=0, le=1)


class OfferBody(BaseModel):
    price_cents: int = Field(gt=0)
    terms_text: str = Field(min_length=1, max_length=4000)
    senso_content_ids: list[str] = Field(default_factory=list)
    trap_checks: list[TrapCheck] = Field(default_factory=list)


class RespondBody(BaseModel):
    offer_id: str = Field(min_length=1)
    accept: bool


class RevealBody(BaseModel):
    price_cents: int = Field(ge=0)
    salt_hex: str = Field(pattern=HEX)


class SystemBody(BaseModel):
    # Judgments and checks that belong in the audit trail (TypeSafe answers, Senso citations, reveal checks).
    kind: str = Field(min_length=1, max_length=64)
    model_config = {"extra": "allow"}


BODIES: dict[str, type[BaseModel]] = {
    "INTENT": IntentBody,
    "JOIN": JoinBody,
    "COMMIT": CommitBody,
    "OFFER": OfferBody,
    "RESPOND": RespondBody,
    "REVEAL": RevealBody,
    "SYSTEM": SystemBody,
}


def validate_body(msg_type: str, body: dict) -> BaseModel:
    return BODIES[msg_type].model_validate(body)


def commitment_for(price_cents: int, salt_hex: str) -> str:
    return hashlib.sha256(f"{price_cents}:{salt_hex}".encode()).hexdigest()


def reveal_matches(commitment: str, price_cents: int, salt_hex: str) -> bool:
    # Constant-time compare: nobody should learn partial matches from timing.
    return hmac.compare_digest(commitment, commitment_for(price_cents, salt_hex))
