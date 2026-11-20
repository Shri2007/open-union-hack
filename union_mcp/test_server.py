"""Exercise the five MCP tools against a fake in-process relay, and the stdio handshake.

    python -m pytest union_mcp/test_server.py -q
"""
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from union_mcp import server

COALITION = "demo-phone-plan"


class FakeRelay(BaseHTTPRequestHandler):
    """The smallest relay that answers the paths the adapter uses, per docs/CONTRACT.md."""

    state = {"state": "open", "log": [], "next_id": 1}

    def log_message(self, *args):  # keep pytest output clean
        pass

    def _send(self, code: int, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/log":
            cid = parse_qs(url.query)["coalition_id"][0]
            return self._send(200, [r for r in self.state["log"] if r["coalition_id"] == cid])
        if url.path.startswith("/coalitions/"):
            return self._send(200, {"id": COALITION, "need": "phone plan under $60",
                                    "state": self.state["state"],
                                    "counts": {"verified": 2, "unverified": 1, "removed": 0,
                                               "real": 1, "simulated": 2}})
        return self._send(404, {"detail": "not found"})

    def do_POST(self):
        url = urlparse(self.path)
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if url.path == "/coalitions/match":
            return self._send(200, {"status": "joined", "coalition_id": COALITION, "member_count": 3})
        if url.path == "/messages":
            if payload["type"] == "REVEAL" and self.state["state"] != "closing":
                return self._send(409, {"detail": "REVEAL is only accepted while the coalition is closing."})
            row_id = f"row-{self.state['next_id']}"
            self.state["next_id"] += 1
            self.state["log"].append({"id": row_id, "coalition_id": payload["coalition_id"],
                                      "agent_id": payload["agent_id"], "type": payload["type"],
                                      "body": payload["body"], "ts": "2026-11-20T20:00:00Z"})
            extra = {"ok": True} if payload["type"] == "REVEAL" else {}
            return self._send(200, {"id": row_id, "ts": "2026-11-20T20:00:00Z", **extra})
        return self._send(404, {"detail": "not found"})


@pytest.fixture()
def relay(monkeypatch, tmp_path):
    FakeRelay.state = {"state": "open", "log": [], "next_id": 1}
    httpd = HTTPServer(("127.0.0.1", 0), FakeRelay)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv("RELAY_URL", f"http://127.0.0.1:{httpd.server_address[1]}")
    monkeypatch.setattr(server, "SECRETS_PATH", tmp_path / ".open-union" / "secrets.json")
    yield FakeRelay.state
    httpd.shutdown()


def add_offer(state, price_cents: int) -> str:
    row_id = f"offer-{price_cents}"
    state["log"].append({"id": row_id, "coalition_id": COALITION, "agent_id": "vendor", "type": "OFFER",
                         "body": {"price_cents": price_cents, "terms_text": "simulated vendor offer",
                                  "senso_content_ids": [], "trap_checks": []},
                         "ts": "2026-11-20T20:05:00Z"})
    return row_id


def test_find_returns_the_coalition(relay):
    result = server.union_find("phone plan under $60")
    assert result["status"] == "joined" and result["coalition_id"] == COALITION


def test_join_seals_the_price_locally(relay):
    result = server.union_join(COALITION, 62.0)
    assert result["status"] == "joined" and result["client"] == "mcp"
    assert result["commitment"] == server.commitment_for(6200, server._secret(COALITION)["salt_hex"])
    assert "price_cents" not in json.dumps(result)  # the price never leaves this machine

    sent = {row["type"]: row["body"] for row in relay["log"]}
    assert sent["JOIN"] == {"persona_inquiry_id": None, "client": "mcp"}
    assert sent["COMMIT"] == {"commitment": result["commitment"]}
    assert "price_cents" not in json.dumps(sent)

    stored = json.loads(server.SECRETS_PATH.read_text())[server._key(COALITION)]
    assert stored["price_cents"] == 6200 and "pending" not in stored
    assert server.SECRETS_PATH.stat().st_mode & 0o777 == 0o600


def test_a_lost_commit_reply_keeps_the_salt_and_the_retry_reuses_it(relay):
    real_send = server._send

    def drop_the_reply(*args):
        raise httpx.ReadTimeout("reply lost")

    server._send = drop_the_reply
    try:
        failed = server.union_join(COALITION, 62.0)
    finally:
        server._send = real_send
    assert "error" in failed and failed["commitment"]
    assert json.loads(server.SECRETS_PATH.read_text())[server._key(COALITION)]["pending"] is True

    retried = server.union_join(COALITION, 62.0)
    assert retried["status"] == "joined"
    assert retried["agent_id"] == failed["agent_id"]  # the same member, not a second one
    assert retried["commitment"] == failed["commitment"]


def test_an_unfinished_join_blocks_respond_and_reveal(relay):
    """A pending record means the relay may hold no commitment, so never publish the price."""
    real_send = server._send
    server._send = lambda *args: (_ for _ in ()).throw(httpx.ReadTimeout("reply lost"))
    try:
        server.union_join(COALITION, 62.0)
    finally:
        server._send = real_send

    add_offer(relay, 5900)
    relay["state"] = "closing"
    assert "error" in server.union_respond(COALITION)
    assert "error" in server.union_reveal(COALITION)
    assert not [row for row in relay["log"] if row["type"] in ("RESPOND", "REVEAL")]
    assert server.union_status(COALITION)["me"]["join_unfinished"] is True


def test_secrets_are_namespaced_by_relay(relay, monkeypatch):
    first_relay = server.relay_url()
    first = server.union_join(COALITION, 62.0)
    monkeypatch.setenv("RELAY_URL", "http://127.0.0.1:1")  # same coalition id, another relay
    assert server._secret(COALITION) is None
    stored = json.loads(server.SECRETS_PATH.read_text())
    assert list(stored) == [f"{first_relay}|{COALITION}"]
    assert stored[f"{first_relay}|{COALITION}"]["agent_id"] == first["agent_id"]


def test_status_reports_state_offer_and_me(relay):
    server.union_join(COALITION, 62.0)
    add_offer(relay, 5900)
    status = server.union_status(COALITION)
    assert status["state"] == "open"
    assert status["offer"]["price_cents"] == 5900
    assert status["me"]["joined"] and status["me"]["committed"] and not status["me"]["revealed"]
    assert "price_cents" not in json.dumps(status["me"])


def test_respond_accepts_at_or_below_the_sealed_price(relay):
    server.union_join(COALITION, 62.0)
    add_offer(relay, 6200)
    result = server.union_respond(COALITION)
    assert result["accept"] is True
    assert relay["log"][-1]["body"] == {"offer_id": "offer-6200", "accept": True}


def test_respond_declines_above_the_sealed_price(relay):
    server.union_join(COALITION, 62.0)
    add_offer(relay, 6500)
    result = server.union_respond(COALITION)
    assert result["accept"] is False
    assert relay["log"][-1]["body"] == {"offer_id": "offer-6500", "accept": False}


def test_reveal_is_refused_before_closing(relay):
    server.union_join(COALITION, 62.0)
    result = server.union_reveal(COALITION)
    assert result["status"] == "refused" and result["state"] == "open"
    assert not [row for row in relay["log"] if row["type"] == "REVEAL"]


def test_reveal_sends_price_and_salt_once_closing(relay):
    server.union_join(COALITION, 62.0)
    relay["state"] = "closing"
    result = server.union_reveal(COALITION)
    assert result["status"] == "revealed" and result["matches_commitment"] is True
    reveal = [row for row in relay["log"] if row["type"] == "REVEAL"][-1]["body"]
    assert reveal["price_cents"] == 6200
    assert server.commitment_for(reveal["price_cents"], reveal["salt_hex"]) == result["commitment"]


def test_stdio_server_lists_its_five_tools():
    """Start the server as Claude Desktop would and read the tool list off stdio."""
    proc = subprocess.Popen(
        [sys.executable, str(Path(server.__file__).resolve())],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, cwd=str(Path(server.__file__).resolve().parents[1]))

    def send(message: dict) -> None:
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "done-check", "version": "0"}}})
        assert json.loads(proc.stdout.readline())["result"]["serverInfo"]["name"] == "open-union"
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = json.loads(proc.stdout.readline())["result"]["tools"]
    finally:
        proc.kill()
    assert sorted(t["name"] for t in tools) == [
        "union_find", "union_join", "union_respond", "union_reveal", "union_status"]
    assert "claude_desktop_config.json" in proc.stderr.read()
