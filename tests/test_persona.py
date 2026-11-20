"""Persona verification: only Persona itself can verify a member (docs/CONTRACT.md rule 1)."""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import bus, config, persona
from app import store as store_module

CID = "ali-test"


class FakeStore:
    def __init__(self):
        self.members = {"a1", "a2"}
        self.verified = set()
        self.rows = []

    def get_coalition(self, cid):
        return {"id": cid, "need": "x", "state": "open"} if cid == CID else None

    def get_member(self, cid, agent_id):
        if agent_id not in self.members:
            return None
        return {"agent_id": agent_id, "client": "web", "verified": agent_id in self.verified, "removed_reason": None}

    def set_verified(self, cid, agent_id, verified):
        self.verified.add(agent_id)

    def append(self, cid, agent_id, msg_type, body):
        self.rows.append({"type": msg_type, "body": body})
        return {"id": str(len(self.rows)), "ts": "t"}

    def log(self, cid):
        return list(self.rows)


@pytest.fixture
def fake(monkeypatch):
    f = FakeStore()
    monkeypatch.setattr(store_module, "store", f)
    return f


@pytest.fixture
def chat(monkeypatch):
    lines = []
    monkeypatch.setattr(bus, "publish", lambda cid, ev, data: lines.append(data["text"]) if ev == "chat" else None)
    return lines


@pytest.fixture
def client(fake, chat):
    app = FastAPI()
    app.include_router(persona.router)
    return TestClient(app)


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(config, "PERSONA_API_KEY", "persona_sandbox_dummy")
    monkeypatch.setattr(config, "PERSONA_TEMPLATE_ID", "itmpl_dummy")


def inquiries(monkeypatch, table):
    """table: inquiry id -> (status, reference-id). Records which ids were asked about."""
    asked = []

    def _fetch(inquiry_id):
        asked.append(inquiry_id)
        if inquiry_id not in table:
            raise HTTPException(502, "Persona inquiry lookup failed: HTTPStatusError")
        status, ref = table[inquiry_id]
        return {"status": status, "reference_id": ref}
    monkeypatch.setattr(persona, "fetch_inquiry", _fetch)
    return asked


def callback(client, agent, inquiry, **extra):
    return client.post("/persona/callback", json={"coalition_id": CID, "agent_id": agent, "inquiry_id": inquiry, **extra})


def test_stub_mode_is_labeled(client, fake, chat, monkeypatch):
    monkeypatch.setattr(config, "PERSONA_API_KEY", "")
    monkeypatch.setattr(config, "PERSONA_TEMPLATE_ID", "")
    assert client.get("/persona/callback").json()["mode"] == "sandbox-stub"
    r = callback(client, "a1", None)
    assert r.json()["verified"] and r.json()["mode"] == "sandbox-stub" and "a1" in fake.verified
    assert "stub" in chat[-1] and fake.rows[-1]["body"]["environment"] == "stub"


def test_key_without_template_is_an_error_never_the_stub(client, fake, monkeypatch):
    monkeypatch.setattr(config, "PERSONA_API_KEY", "persona_sandbox_dummy")
    monkeypatch.setattr(config, "PERSONA_TEMPLATE_ID", "")
    r = client.get("/persona/callback")
    assert r.status_code == 503 and "PERSONA_TEMPLATE_ID" in r.text
    r = callback(client, "a1", "inq_1")  # the stub must not quietly verify anyone
    assert r.status_code == 503 and "a1" not in fake.verified


def test_passed_inquiry_verifies_and_says_sandbox(client, fake, chat, live, monkeypatch):
    inquiries(monkeypatch, {"inq_1": ("approved", f"{CID}:a1")})
    r = callback(client, "a1", "inq_1")
    assert r.json() == {"coalition_id": CID, "agent_id": "a1", "inquiry_id": "inq_1", "status": "approved",
                        "mode": "live", "verified": True}
    assert "a1" in fake.verified and fake.rows[-1]["body"]["environment"] == "sandbox"
    assert "sandbox" in chat[-1].lower()


def test_browser_cannot_claim_a_passed_status(client, fake, live, monkeypatch):
    asked = inquiries(monkeypatch, {"inq_1": ("created", f"{CID}:a1")})
    r = callback(client, "a1", "inq_1", status="approved")  # a forged status from the browser
    assert r.json()["verified"] is False and r.json()["status"] == "created"
    assert asked == ["inq_1"] and "a1" not in fake.verified


def test_inquiry_of_another_member_is_refused(client, fake, live, monkeypatch):
    inquiries(monkeypatch, {"inq_1": ("completed", f"{CID}:a1")})
    assert callback(client, "a2", "inq_1").status_code == 403
    assert "a2" not in fake.verified


def test_webhook_shape_is_checked_with_persona_not_trusted(client, fake, live, monkeypatch):
    asked = inquiries(monkeypatch, {"inq_9": ("created", f"{CID}:a1")})
    hook = {"data": {"attributes": {"name": "inquiry.completed", "status": "approved",
                                    "payload": {"data": {"type": "inquiry", "id": "inq_9",
                                                         "attributes": {"reference-id": f"{CID}:a1", "status": "approved"}}}}}}
    r = client.post("/persona/callback", json=hook)
    assert asked == ["inq_9"]  # it asked Persona, whatever the webhook body claimed
    assert r.json()["verified"] is False and "a1" not in fake.verified
    inquiries(monkeypatch, {"inq_9": ("approved", f"{CID}:a1")})
    assert client.post("/persona/callback", json=hook).json()["verified"] is True


@pytest.mark.parametrize("bad", ["../accounts/act_1", "inq_1/../../x", "inq_1?x=1", "inq_1#", "abc", "inq_"])
def test_inquiry_id_must_look_like_an_inquiry_id(client, fake, live, monkeypatch, bad):
    asked = inquiries(monkeypatch, {})
    assert callback(client, "a1", bad).status_code == 422
    assert asked == [] and "a1" not in fake.verified


def test_unconfirmed_environment_is_labeled(client, chat, live, monkeypatch):
    monkeypatch.setattr(config, "PERSONA_API_KEY", "bare-token-without-prefix")
    inquiries(monkeypatch, {"inq_1": ("approved", f"{CID}:a1")})
    callback(client, "a1", "inq_1")
    assert "unconfirmed" in chat[-1]


def test_persona_failure_is_never_a_pass(client, fake, live, monkeypatch):
    inquiries(monkeypatch, {})
    assert callback(client, "a1", "inq_missing").status_code == 502
    assert callback(client, "a1", None).status_code == 422
    assert "a1" not in fake.verified


def test_only_current_members_can_be_verified(client, live, monkeypatch):
    inquiries(monkeypatch, {"inq_1": ("completed", f"{CID}:ghost")})
    assert callback(client, "ghost", "inq_1").status_code == 403
