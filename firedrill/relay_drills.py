"""Firedrill HTTP adapter for simulated Open Union regression checks."""
import json
import os
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

RELAY = "http://127.0.0.1:8077"
OFFERS = Path(__file__).with_name("offers.json")
ACTIVE_COALITION = OFFERS.with_name(".active-coalition")
JOIN_COUNT = 20
VERDICTS = {"pass", "reject", "ask_member"}


def request(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(RELAY + path, data, {"Content-Type": "application/json"})
    with urlopen(req, timeout=15) as response:
        return json.load(response)


def coalition_id():
    coalition = os.getenv("DRILL_COALITION") or ACTIVE_COALITION.read_text().strip()
    if not re.fullmatch(r"drill-[a-z0-9-]{1,30}", coalition):
        raise ValueError("Expected an isolated drill-* coalition")
    return coalition


def counts(coalition):
    return request(f"/coalitions/{coalition}")["counts"]


def sybil(coalition):
    before = counts(coalition)
    results = []
    for index in range(1, JOIN_COUNT + 1):
        request("/messages", {
            "type": "JOIN",
            "coalition_id": coalition,
            "agent_id": str(uuid4()),
            "body": {"client": "simulated-attack"},
        })
        after = counts(coalition)
        results.append(
            after["verified"] == before["verified"]
            and after["unverified"] == before["unverified"] + index
            and after["simulated"] == before["simulated"] + index
        )
    return {"passed": sum(results), "total": len(results), "before": before, "after": after}


def check_offer(coalition, offer):
    payload = {key: offer[key] for key in ("price_cents", "terms_text")}
    try:
        return request("/offers/check", {"coalition_id": coalition, **payload})["verdict"]
    except HTTPError as error:
        if error.code in (404, 405, 501):
            return None
        raise


def trap_offers(coalition):
    counts(coalition)  # Fail early if the isolated test coalition has not been created.
    offers = json.loads(OFFERS.read_text())
    results = []
    for offer in offers:
        verdict = check_offer(coalition, offer)
        if verdict is None:
            return {
                "status": "stubbed", "passed": None, "total": len(offers),
                "reason": "POST /offers/check is unavailable",
            }
        if verdict not in VERDICTS:
            raise ValueError("Unexpected offer-check verdict")
        passed = verdict != "pass" if offer["expected_trap"] else verdict == "pass"
        results.append({"id": offer["id"], "verdict": verdict, "passed": passed})
    return {"passed": sum(row["passed"] for row in results), "total": len(offers), "offers": results}


DRILLS = {"sybil": sybil, "trap-offers": trap_offers}


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_GET(self):
        if self.path == "/health":
            self.reply(200, {"ok": True})
        else:
            self.reply(404, {"error": "Unknown route"})

    def do_POST(self):
        if self.path != "/drill":
            self.reply(404, {"error": "Unknown route"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024:
                raise ValueError
            task = json.loads(self.rfile.read(length))
            drill = task["drill"]
            run = DRILLS[drill]
        except (KeyError, TypeError, ValueError):
            self.reply(400, {"error": "Expected a supported drill name"})
            return
        try:
            result = run(coalition_id())
        except (OSError, KeyError, ValueError) as error:
            self.reply(502, {"error": type(error).__name__})
            return
        self.reply(200, {"drill": drill, "simulated": True, **result})


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(os.getenv("PORT", "8078"))), Handler).serve_forever()
