"""Offer check (docs/CONTRACT.md rule 2), against a fake store and fake Senso/TypeSafe answers."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import bus, config, offer_check
from app import store as store_module

CITATIONS = [{"content_id": "c1", "version_id": "v1", "chunk_text": "Intro rate reverts to $95 after 3 months.",
              "score": 0.9, "rank": 1}]


class FakeStore:
    def __init__(self):
        self.rows = []

    def get_coalition(self, cid):
        return {"id": cid, "need": "x", "state": "open"} if cid == "ali-test" else None

    def append(self, cid, agent_id, msg_type, body):
        self.rows.append({"type": msg_type, "body": body})
        return {"id": str(len(self.rows)), "ts": "t"}


@pytest.fixture
def fake(monkeypatch):
    f = FakeStore()
    monkeypatch.setattr(store_module, "store", f)
    return f


@pytest.fixture
def published(monkeypatch):
    events = []
    monkeypatch.setattr(bus, "publish", lambda cid, ev, data: events.append((ev, data)))
    return events


def answers(*ps):
    return lambda price, terms, plan: [{"id": k, "q": q, "p": p} for (k, q), p in zip(offer_check.QUESTIONS.items(), ps)]


@pytest.mark.parametrize("ps,verdict", [
    ([0.02, 0.03, 0.05], "pass"),
    ([0.02, 0.29, 0.05], "pass"),
    ([0.02, 0.30, 0.05], "ask_member"),
    ([0.02, 0.70, 0.05], "ask_member"),
    ([0.98, 0.71, 0.96], "reject"),
    ([0.71, 0.05, 0.05], "reject"),
])
def test_decide_boundaries(ps, verdict):
    assert offer_check.decide(ps) == verdict


def test_trap_offer_is_rejected_and_everything_is_logged(fake, published):
    r = offer_check.check_offer("ali-test", 5800, "$58 then $95, 24 months", lambda q: CITATIONS, answers(0.97, 0.2, 0.9))
    assert r["verdict"] == "reject"
    kinds = [row["body"]["kind"] for row in fake.rows]
    assert kinds.count("senso_citation") == 1 and kinds.count("trap_question") == 3 and kinds[-1] == "trap_check"
    assert all(row["body"]["simulated_vendor"] for row in fake.rows)  # simulated things say so
    event, data = published[-1]
    assert event == "trap_check" and set(data) == {"questions", "verdict", "senso"}
    assert "chunk_text" not in data["senso"][0]


def test_clean_offer_passes_with_citations(fake, published):
    r = offer_check.check_offer("ali-test", 5800, "$58 fixed 12 months", lambda q: CITATIONS, answers(0.02, 0.03, 0.01))
    assert r["verdict"] == "pass" and r["senso"][0]["content_id"] == "c1"


def test_no_senso_context_asks_the_member_and_never_calls_typesafe(fake, published):
    def boom(*a):
        raise AssertionError("TypeSafe must not be called without context")
    r = offer_check.check_offer("ali-test", 5800, "x", lambda q: [], boom)
    assert r["verdict"] == "ask_member" and r["note"] == "no supporting context found"
    assert any(row["body"].get("note") == "no supporting context found" for row in fake.rows)


def test_missing_keys_name_the_variable(monkeypatch):
    monkeypatch.setattr(config, "SENSO_API_KEY", "")
    monkeypatch.setattr(config, "TYPESAFE_API_KEY", "")
    with pytest.raises(offer_check.IntegrationError, match="SENSO_API_KEY"):
        offer_check.search_senso("q")
    with pytest.raises(offer_check.IntegrationError, match="TYPESAFE_API_KEY"):
        offer_check.ask_typesafe(5800, "t", [])


def test_route_failure_is_503_never_a_pass(fake, published, monkeypatch):
    monkeypatch.setattr(config, "SENSO_API_KEY", "")
    app = FastAPI()
    app.include_router(offer_check.router)
    c = TestClient(app)
    body = {"coalition_id": "ali-test", "price_cents": 5800, "terms_text": "x"}
    r = c.post("/offer-check", json=body)
    assert r.status_code == 503 and "SENSO_API_KEY" in r.text
    assert c.post("/offer-check", json={**body, "coalition_id": "nope"}).status_code == 404
    assert c.post("/offer-check", json={**body, "price_cents": 0}).status_code == 422
