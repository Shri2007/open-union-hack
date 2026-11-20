"""Protocol rules from docs/CONTRACT.md, tested against an in-memory store (no database needed)."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app import store as store_module
from app.main import app
from app.protocol import commitment_for, reveal_matches

CID = "test-coalition"


class FakeStore:
    def __init__(self):
        self.coalitions = {CID: {"id": CID, "need": "phone plan under $60", "state": "open"}}
        self.members, self.rows = {}, []

    def get_coalition(self, cid):
        return self.coalitions.get(cid)

    def create_coalition(self, need, cid=None):
        cid = cid or str(uuid.uuid4())
        self.coalitions.setdefault(cid, {"id": cid, "need": need, "state": "open"})
        return cid

    def set_state(self, cid, state):
        self.coalitions[cid]["state"] = state

    def upsert_member(self, cid, agent_id, client, verified):
        self.members[(cid, agent_id)] = {"agent_id": agent_id, "client": client, "verified": verified,
                                         "removed_reason": None}

    def get_member(self, cid, agent_id):
        return self.members.get((cid, agent_id))

    def counts(self, cid):
        return {}

    def append(self, cid, agent_id, msg_type, body):
        row = {"id": str(uuid.uuid4()), "coalition_id": cid, "agent_id": agent_id, "type": msg_type,
               "body": body, "ts": "t"}
        self.rows.append(row)
        return row

    def log(self, cid):
        return [r for r in self.rows if r["coalition_id"] == cid]

    def find_commit(self, cid, agent_id):
        for r in self.rows:
            if r["coalition_id"] == cid and r["agent_id"] == agent_id and r["type"] == "COMMIT":
                return r["body"]["commitment"]
        return None

    def get_log_row(self, cid, row_id):
        return next((r for r in self.rows if r["id"] == row_id), None)


@pytest.fixture
def fake(monkeypatch):
    f = FakeStore()
    monkeypatch.setattr(store_module, "store", f)
    return f


@pytest.fixture
def client(fake):
    return TestClient(app)  # no `with`: skips startup, so no database connection


def send(client, agent, msg_type, body):
    return client.post("/messages", json={"coalition_id": CID, "agent_id": agent, "type": msg_type, "body": body})


def join_and_commit(client, agent, price_cents, salt):
    assert send(client, agent, "JOIN", {"client": "web", "persona_inquiry_id": None}).status_code == 200
    assert send(client, agent, "COMMIT", {"commitment": commitment_for(price_cents, salt)}).status_code == 200


def test_commitment_matches_only_the_same_price_and_salt():
    c = commitment_for(6200, "ab12")
    assert reveal_matches(c, 6200, "ab12")
    assert not reveal_matches(c, 6300, "ab12")
    assert not reveal_matches(c, 6200, "ab13")


def test_reveal_before_closing_is_refused(client, fake):
    join_and_commit(client, "alice", 6200, "ab12")
    r = send(client, "alice", "REVEAL", {"price_cents": 6200, "salt_hex": "ab12"})
    assert r.status_code == 409


def test_matching_reveal_is_counted(client, fake):
    join_and_commit(client, "alice", 6200, "ab12")
    fake.set_state(CID, "closing")
    r = send(client, "alice", "REVEAL", {"price_cents": 6200, "salt_hex": "ab12"})
    assert r.status_code == 200 and r.json()["ok"] is True
    check = [x for x in fake.rows if x["type"] == "SYSTEM"][-1]
    assert check["body"] == {"kind": "reveal_check", "agent_id": "alice", "ok": True, "reason": None}


def test_mismatched_reveal_is_logged_and_excluded(client, fake):
    join_and_commit(client, "bob", 5500, "cd34")
    fake.set_state(CID, "closing")
    r = send(client, "bob", "REVEAL", {"price_cents": 9900, "salt_hex": "cd34"})
    assert r.status_code == 200 and r.json()["ok"] is False
    assert any(x["type"] == "REVEAL" and x["agent_id"] == "bob" for x in fake.rows)  # logged, not dropped
    check = [x for x in fake.rows if x["type"] == "SYSTEM"][-1]
    assert check["body"]["ok"] is False and check["body"]["reason"] == "does not match commitment"


def test_second_commit_is_refused(client, fake):
    join_and_commit(client, "carol", 6000, "ef56")
    r = send(client, "carol", "COMMIT", {"commitment": commitment_for(9000, "ef56")})
    assert r.status_code == 409


def test_non_member_cannot_commit(client, fake):
    r = send(client, "mallory", "COMMIT", {"commitment": commitment_for(6000, "aa")})
    assert r.status_code == 403


def test_bad_commitment_format_is_rejected(client, fake):
    send(client, "dave", "JOIN", {"client": "web"})
    assert send(client, "dave", "COMMIT", {"commitment": "not-a-hash"}).status_code == 422


def test_unknown_coalition_is_404(client, fake):
    r = client.post("/messages", json={"coalition_id": "nope", "agent_id": "a", "type": "INTENT",
                                       "body": {"need": "x"}})
    assert r.status_code == 404
