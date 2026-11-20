"""The close tally recomputed from log rows alone (docs/CONTRACT.md rule 4)."""
from app.protocol import commitment_for
from app.tally import compute_tally

OFFER_CENTS = 5000


def join(agent_id, client="web"):
    return {"id": f"j-{agent_id}", "coalition_id": "c", "agent_id": agent_id, "type": "JOIN",
            "body": {"persona_inquiry_id": None, "client": client}, "ts": "2026-11-20T19:00:00Z"}


def commit(agent_id, commitment):
    return {"id": f"c-{agent_id}", "coalition_id": "c", "agent_id": agent_id, "type": "COMMIT",
            "body": {"commitment": commitment}, "ts": "2026-11-20T19:01:00Z"}


def reveal(agent_id, body):
    return {"id": f"r-{agent_id}", "coalition_id": "c", "agent_id": agent_id, "type": "REVEAL",
            "body": body, "ts": "2026-11-20T19:02:00Z"}


def member(agent_id, price_cents, salt_hex="ab12", reveal_price=None, reveal_salt=None):
    """JOIN + COMMIT + REVEAL for one agent; pass reveal_* to reveal something else than it sealed."""
    revealed = {"price_cents": price_cents if reveal_price is None else reveal_price,
                "salt_hex": salt_hex if reveal_salt is None else reveal_salt}
    return [join(agent_id), commit(agent_id, commitment_for(price_cents, salt_hex)), reveal(agent_id, revealed)]


def test_matching_reveal_above_the_offer_is_accepted():
    out = compute_tally(member("alice", 6000), OFFER_CENTS)
    assert out == {"accepted": 1, "total": 1, "mismatched": 0, "not_revealed": 0,
                   "revealed": [{"agent_id": "alice", "price_cents": 6000, "ok": True}]}


def test_mismatched_reveal_is_counted_as_mismatch_not_accepted():
    out = compute_tally(member("mallory", 6000, reveal_price=4000), OFFER_CENTS)
    assert out["accepted"] == 0
    assert out["mismatched"] == 1
    assert out["revealed"] == [{"agent_id": "mallory", "price_cents": 4000, "ok": False}]


def test_agent_with_no_reveal_is_not_revealed():
    rows = [join("quiet"), commit("quiet", commitment_for(6000, "ab12"))]
    out = compute_tally(rows, OFFER_CENTS)
    assert out == {"accepted": 0, "total": 1, "mismatched": 0, "not_revealed": 1, "revealed": []}


def test_revealed_price_below_the_offer_is_not_accepted():
    out = compute_tally(member("thrifty", 4000), OFFER_CENTS)
    assert out["accepted"] == 0
    assert out["mismatched"] == 0
    assert out["revealed"] == [{"agent_id": "thrifty", "price_cents": 4000, "ok": True}]


def test_eligible_limits_the_agents_considered():
    rows = member("alice", 6000) + member("bob", 7000)
    out = compute_tally(rows, OFFER_CENTS, eligible={"alice"})
    assert out["total"] == 1
    assert out["accepted"] == 1
    assert [r["agent_id"] for r in out["revealed"]] == ["alice"]


def test_malformed_reveal_is_a_mismatch_never_accepted():
    sealed = commitment_for(6000, "ab12")
    rows = [join("bad-types"), commit("bad-types", sealed), reveal("bad-types", {"price_cents": "6000", "salt_hex": "ab12"}),
            join("no-salt"), commit("no-salt", sealed), reveal("no-salt", {"price_cents": 6000, "salt_hex": None})]
    out = compute_tally(rows, OFFER_CENTS)
    assert out["accepted"] == 0
    assert out["mismatched"] == 2
    assert all(r["ok"] is False and r["price_cents"] is None for r in out["revealed"])


def test_reveal_without_a_commitment_is_a_mismatch():
    out = compute_tally([join("sneaky"), reveal("sneaky", {"price_cents": 9000, "salt_hex": "ab12"})], OFFER_CENTS)
    assert out["accepted"] == 0
    assert out["mismatched"] == 1


def test_vendor_and_system_rows_are_not_agents():
    rows = member("alice", 6000) + [
        {"id": "o1", "coalition_id": "c", "agent_id": "vendor", "type": "OFFER",
         "body": {"price_cents": OFFER_CENTS, "terms_text": "12 months"}, "ts": "2026-11-20T19:03:00Z"},
        {"id": "s1", "coalition_id": "c", "agent_id": "system", "type": "SYSTEM",
         "body": {"kind": "reveal_check"}, "ts": "2026-11-20T19:04:00Z"}]
    out = compute_tally(rows, OFFER_CENTS)
    assert out["total"] == 1
    assert [r["agent_id"] for r in out["revealed"]] == ["alice"]


def test_first_commit_and_latest_reveal_win():
    rows = [join("alice"), commit("alice", commitment_for(6000, "ab12")), commit("alice", commitment_for(100, "ab12")),
            reveal("alice", {"price_cents": 100, "salt_hex": "ab12"}),
            reveal("alice", {"price_cents": 6000, "salt_hex": "ab12"})]
    out = compute_tally(rows, OFFER_CENTS)
    assert out["revealed"] == [{"agent_id": "alice", "price_cents": 6000, "ok": True}]
    assert out["accepted"] == 1
