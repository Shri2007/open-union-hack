from threading import Event

from app import vendor


def test_price_uses_formula_and_floor():
    assert vendor.price_for(0) == 8500
    assert vendor.price_for(341) == 5803
    assert vendor.price_for(10**400) == 3800


def test_say_returns_exact_fallback_when_both_clients_raise(monkeypatch):
    calls = []

    def broken_client(name):
        def create(**kwargs):
            calls.append(name)
            raise RuntimeError("SDK failure")
        return create

    monkeypatch.setattr(vendor.config, "ARCEE_API_KEY", "test")
    monkeypatch.setattr(vendor.config, "ARCEE_MODEL_SMALL", "test")
    monkeypatch.setattr(vendor.config, "ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(vendor, "OpenAI", broken_client("arcee"))
    monkeypatch.setattr(vendor, "Anthropic", broken_client("anthropic"))

    fallback = "  Use this exact line.  "
    assert vendor.say("vendor", "List price is $85.", fallback) == fallback
    assert calls == ["arcee", "anthropic"]


def test_say_tries_haiku_after_arcee_deadline(monkeypatch):
    release = Event()
    monkeypatch.setattr(vendor, "_ARCEE_SECONDS", 0.02)
    monkeypatch.setattr(vendor, "_TOTAL_SECONDS", 1)
    monkeypatch.setattr(vendor, "_arcee", lambda *_: release.wait(2))
    monkeypatch.setattr(vendor, "_haiku", lambda *_: "The list price is $85.")

    try:
        assert vendor.say("vendor", "List price is $85.", "fallback") == "The list price is $85."
    finally:
        release.set()


def test_say_rejects_invented_numbers_and_multiline_output(monkeypatch):
    monkeypatch.setattr(vendor, "_arcee", lambda *_: "Try our $50 rate.")
    monkeypatch.setattr(vendor, "_haiku", lambda *_: "List price is $85.\nLet's talk.")
    assert vendor.say("coalition", "List price is $85.", "fallback") == "fallback"
