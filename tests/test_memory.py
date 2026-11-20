"""Vendor memory (SIMULATED) with a fake backend: no network, no Cognee."""
import asyncio

import pytest

from app import memory


@pytest.fixture(autouse=True)
def no_memory_service(monkeypatch):
    # A developer's .env may point MEMORY_URL at a running Cognee service; these tests are offline.
    monkeypatch.setattr(memory, "MEMORY_URL", "")


class FakeBackend:
    def __init__(self, fail=False):
        self.texts, self.fail = [], fail

    async def store(self, text):
        if self.fail:
            raise RuntimeError("boom")
        self.texts.append(text)

    async def search(self, query):
        if self.fail:
            raise RuntimeError("boom")
        return list(self.texts)


def setup_function(_):
    memory.set_backend(None)


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("COGNEE_MEMORY", raising=False)
    fake = FakeBackend()
    memory.set_backend(fake)
    assert memory.remember_walkout("phone plan", 6000) is False
    assert memory.recall_walkout("phone plan") is None
    assert fake.texts == []


def test_roundtrip(monkeypatch):
    monkeypatch.setenv("COGNEE_MEMORY", "1")
    memory.set_backend(FakeBackend())
    assert memory.recall_walkout("phone plan") is None
    assert memory.remember_walkout("phone plan under $60, Bay Area", 6000) is True
    got = memory.recall_walkout("cheap cell plan")
    assert got["walk_price_cents"] == 6000 and "simulated" in got["text"]


def test_failure_never_raises(monkeypatch):
    monkeypatch.setenv("COGNEE_MEMORY", "1")
    memory.set_backend(FakeBackend(fail=True))
    assert memory.remember_walkout("x", 1) is False
    assert memory.recall_walkout("x") is None


def test_no_price_in_results_is_none(monkeypatch):
    monkeypatch.setenv("COGNEE_MEMORY", "1")
    fake = FakeBackend()
    fake.texts = ["unrelated text"]
    memory.set_backend(fake)
    assert memory.recall_walkout("x") is None
