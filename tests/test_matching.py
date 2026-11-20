"""Coalition matching decisions (docs/CONTRACT.md), against a fake store and a fake TypeSafe client."""
import uuid

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import matching
from app import store as store_module

PHONE = "phone-plan"
GYM = "gym-membership"


class FakeStore:
    def __init__(self):
        self.coalitions = {
            PHONE: {"id": PHONE, "need": "phone plan under $60", "state": "open"},
            GYM: {"id": GYM, "need": "gym membership under $30", "state": "open"},
        }
        self.rows = []

    def list_coalitions(self, limit=5):
        return list(self.coalitions.values())[:limit]

    def create_coalition(self, need, cid=None):
        cid = cid or str(uuid.uuid4())
        self.coalitions[cid] = {"id": cid, "need": need, "state": "open"}
        return cid

    def counts(self, cid):
        return {"verified": 2, "unverified": 1, "removed": 0, "real": 3, "simulated": 0}

    def append(self, cid, agent_id, msg_type, body):
        row = {"id": str(uuid.uuid4()), "coalition_id": cid, "agent_id": agent_id, "type": msg_type,
               "body": body, "ts": "t"}
        self.rows.append(row)
        return row


@pytest.fixture
def fake(monkeypatch):
    f = FakeStore()
    monkeypatch.setattr(store_module, "store", f)
    return f


@pytest.fixture
def client(fake):
    app = FastAPI()  # the real app wires this router in main.py; the test mounts it on its own
    app.include_router(matching.router)
    return TestClient(app)


def fake_typesafe(monkeypatch, probabilities):
    """Answer each candidate by its coalition need, so the order of candidates doesn't matter."""
    seen = []

    def _ask(state):
        seen.append(state)
        return probabilities[state["coalition"]["need"]]

    monkeypatch.setattr(matching, "ask_typesafe", _ask)
    return seen


def post(client, need):
    return client.post("/coalitions/match", json={"need": need})


def test_a_similar_need_joins_the_existing_coalition(client, monkeypatch, fake):
    fake_typesafe(monkeypatch, {"phone plan under $60": 0.92, "gym membership under $30": 0.04})
    r = post(client, "cheaper mobile plan, under $55")
    assert r.status_code == 200
    assert r.json() == {"status": "joined", "coalition_id": PHONE, "member_count": 3}


def test_a_middling_match_asks_the_user(client, monkeypatch, fake):
    fake_typesafe(monkeypatch, {"phone plan under $60": 0.55, "gym membership under $30": 0.04})
    r = post(client, "cheaper home internet")
    assert r.status_code == 200 and r.json() == {"status": "ask_user"}
    assert len(fake.coalitions) == 2  # nothing created while the user decides


def test_an_unrelated_need_creates_a_new_coalition(client, monkeypatch, fake):
    fake_typesafe(monkeypatch, {"phone plan under $60": 0.05, "gym membership under $30": 0.02})
    r = post(client, "cheaper car insurance")
    body = r.json()
    assert r.status_code == 200
    assert body["status"] == "created" and body["member_count"] == 0
    assert fake.coalitions[body["coalition_id"]]["need"] == "cheaper car insurance"


def test_every_question_and_probability_is_logged(client, monkeypatch, fake):
    fake_typesafe(monkeypatch, {"phone plan under $60": 0.92, "gym membership under $30": 0.04})
    post(client, "cheaper mobile plan, under $55")
    judgments = [r for r in fake.rows if r["type"] == "SYSTEM"]
    assert len(judgments) == 2
    first = judgments[0]
    assert first["agent_id"] == "system"
    assert first["body"]["kind"] == "match_question"
    assert first["body"]["question"] == matching.QUESTION
    assert first["body"]["state"] == {"member": {"need": "cheaper mobile plan, under $55"},
                                      "coalition": {"need": "phone plan under $60"}}
    assert first["body"]["p"] == 0.92


def test_a_failed_typesafe_call_is_an_error_not_a_new_coalition(client, monkeypatch, fake):
    def _down(state):
        raise HTTPException(502, "TypeSafe call failed: ConnectError")

    monkeypatch.setattr(matching, "ask_typesafe", _down)
    r = post(client, "cheaper mobile plan, under $55")
    assert r.status_code == 502
    assert len(fake.coalitions) == 2  # no coalition created on a failed judgment


def test_a_missing_key_is_an_error(client, monkeypatch, fake):
    monkeypatch.setattr(matching.config, "TYPESAFE_API_KEY", "")
    r = post(client, "cheaper mobile plan, under $55")
    assert r.status_code == 503
    assert len(fake.coalitions) == 2
