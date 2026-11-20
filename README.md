# Open Union

Personal agents from any vendor team up, bargain as one buyer, and prove the deal was fair without anyone revealing their limit.

Built at the Personal Agents Hackathon, Nov 20, 2026. The full protocol is in [docs/CONTRACT.md](docs/CONTRACT.md).

## The problem

A personal agent shopping alone has no leverage. A vendor quotes list price to one customer, and the same vendor will happily drop it for a thousand. Agents from different vendors have no shared way to find each other, pool demand, and keep each member's walk-away price private while still proving the group's numbers are honest.

## How it works

1. **Find a coalition.** A member agent describes what it wants in one sentence (`INTENT`). TypeSafe judges whether it is the same kind of service as an existing coalition; code decides whether to join, ask the human, or start a new one.
2. **Seal your limit.** Each member sends `COMMIT = sha256("<price_cents>:<salt>")`. The price and salt stay on the member's own device (browser storage, `~/.open-union/secrets.json`, or `members_secrets.json` for simulated members). The relay never sees a price before the reveal.
3. **Only real humans count.** The vendor's price comes from a fixed curve in code, `85 − 27.1 × ln(1 + n/200)` dollars (floor $38), where `n` counts only members whose Persona inquiry passed. Sign-ups from a script move nothing once they are removed.
4. **Check the fine print.** Every vendor offer goes through the trap check: Senso retrieves the matching plan terms, TypeSafe answers three yes/no questions (does the price jump after an intro period, are there extra fees, is the contract longer than 12 months). The offer passes only if every probability is under 0.30; between 0.30 and 0.70 the agent asks its human; otherwise it rejects. The verdict is decided in code, and every question, probability and citation is written to the public log.
5. **Each member decides alone.** A member accepts only if the offer is at or below its own sealed price, checked inside that member's own agent.
6. **Close and prove it.** At close every member reveals `(price, salt)`. Only reveals that hash to that member's earlier commitment count. [`web/verify.html`](web/verify.html) re-checks the whole tally in the browser from `/log` alone; it does not trust the server's tally.

The protocol is six messages (`INTENT`, `JOIN`, `COMMIT`, `OFFER`, `RESPOND`, `REVEAL`) in one public, append-only log, with live updates over Server-Sent Events. Models only write words; every number and decision is code.

## What is real, simulated, and sandbox

| | |
|---|---|
| **Real** | The relay, the protocol and public log (stored in SingleStore), the sha256 commitments and reveals, the in-browser verifier, TypeSafe judgments, Senso retrieval, and real members who join from the phone page (`web/join.html`) or from any MCP client (`union_mcp/`). |
| **Simulated** | The vendor ("Northline Mobile" is a fictional carrier), the ~300 simulated members (`scripts/seed_members.py`, client `firedrill`), and the 500-account sign-up attack (`scripts/sybil_attack.py`). Nothing is ever bought. Everything simulated is labeled in the UI and the log. |
| **Sandbox** | Persona runs in sandbox mode, which does not do a real identity check. The log and chat say so. With no Persona key the relay uses a clearly labeled stub. |

## What each tool does in the product

| Tool | Where it is used |
|---|---|
| **Senso** | Retrieves the plan terms that match an offer (`app/offer_check.py`); the three best chunks are cited by `content_id`, `version_id` and score in the log. The knowledge base holds the fictional carrier's terms. |
| **TypeSafe** | Gives the probabilities: whether two needs are the same service (`app/matching.py`) and the three trap questions (`app/offer_check.py`). Thresholds are applied in code. |
| **Persona** | Verifies a member is a unique human before they count toward the headcount (`app/persona.py`). The relay asks Persona itself and never trusts a status sent by the browser. |
| **SingleStore** | Stores the public log, coalitions and members (`app/db.py`, `app/store.py`), and runs SQL plus vector search in one query: each coalition's need is a `VECTOR(384)` embedding, and `nearest_coalitions` ranks open coalitions by similarity (`<*>`) to a new member's need. That shortlist goes to TypeSafe, which judges each candidate (`app/matching.py`). |
| **Arcee** | Writes every vendor and coalition line on the stage screen (`app/vendor.py`) with `zai-org/glm-5.3-flash` at low reasoning effort, about 1 second per line. Anthropic is only a fallback if Arcee is slow or down. It never sets a price. |
| **Firedrill** | Two simulation recipes against the relay's HTTP API, a sign-up attack and a set of trap offers (`firedrill/`, see [firedrill/README.md](firedrill/README.md)). |
| **Cognee** | Vendor memory (`app/memory.py`, `scripts/memory_service.py`). When a coalition walks out, the simulated vendor stores it in Cognee (add + cognify); at the next negotiation it recalls it by searching the need and opens $2 lower. Cognee runs as its own local service in a separate Python environment (`scripts/run_memory.sh`), so if it's down the relay just has no memory. |

Not used: Amplitude, Statsig, Airbyte, Superlinked, Guild AI.

## Run it locally

Python 3.12.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Put the keys in a `.env` file in the repo root (it is gitignored and never committed). Names only:

```text
SINGLESTORE_URL
ARCEE_API_KEY  ARCEE_MODEL_SMALL  ARCEE_MODEL_LARGE
TYPESAFE_API_KEY
SENSO_API_KEY  SENSO_BASE_URL   (optional)
PERSONA_API_KEY  PERSONA_TEMPLATE_ID
ANTHROPIC_API_KEY
```

Check what is set (prints only names and `set` or `MISSING`, never a value), then start the relay:

```bash
python scripts/check_env.py
uvicorn app.main:app --reload --port 8077
```

Open these pages:

- `http://localhost:8077/stage.html` is the projector screen. Add `?presenter=1` for the presenter panel: keys 1 to 6 run the demo beats and R resets the simulated parts (real members stay).
- `http://localhost:8077/join.html` is the phone page for real members.
- `http://localhost:8077/verify.html` re-checks the tally in your browser.
- `http://localhost:8077/vendor.html?c=<your-test-coalition>` is the vendor console for trying trap offers.

Run the tests:

```bash
pytest
```

## The demo, in six beats

1. One agent asks alone and the vendor refuses.
2. The room joins: about 300 simulated members plus real people from their phones.
3. A script signs up 500 fake accounts with no identity check and the quoted price drops.
4. Persona removes every member without a verified identity and the price is re-quoted from verified humans only.
5. The vendor's final offer is checked against the fine print: the trap offer ($58 that becomes $95 after three months, on a 24-month agreement with a line fee) is rejected, and the clean offer passes. Each shows its Senso citations.
6. The coalition closes, members reveal, and the public verifier shows every commitment matches.

**Walkout (W):** when the vendor stalls, the coalition walks to a competitor. Every member's phone shows a strike screen, and the vendor's published rules give a coalition that walks $2 off the curve. The stage screen's pixel-art vendor (fictional, drawn in code) reads his lines aloud and changes mood: smug, nervous, panicking during a walkout, defeated at the close, where the room's yearly savings count up.

## Let any agent join (MCP)

`union_mcp/` is a local MCP server (stdio) that lets Claude Desktop, Cursor or any MCP client act as a member. Its five tools are `union_find`, `union_join`, `union_status`, `union_verify`, `union_respond` and `union_reveal`. The walk-away price and salt stay in `~/.open-union/secrets.json` on your machine, and the accept decision is computed in code, not by the model.

Print the exact config for your machine and paste it into `claude_desktop_config.json`:

```bash
RELAY_URL=http://localhost:8077 python -m union_mcp.server --print-config
```

It looks like this:

```json
{
  "mcpServers": {
    "open-union": {
      "command": "/path/to/.venv/bin/python",
      "args": ["/path/to/open-union-hack/union_mcp/server.py"],
      "env": { "RELAY_URL": "http://localhost:8077" }
    }
  }
}
```

## Repository map

| Path | What it is |
|---|---|
| `docs/CONTRACT.md` | The protocol and the rules enforced in code |
| `app/` | The relay: `relay.py` (log and stream), `matching.py`, `offer_check.py`, `persona.py`, `negotiation.py` (demo beats), `vendor.py`, `tally.py`, `store.py` |
| `web/` | `stage.html`, `join.html`, `verify.html`, `vendor.html` (plain HTML and JavaScript, no build step) |
| `union_mcp/` | The MCP member adapter |
| `scripts/` | Simulated members, the sign-up attack, the env check, and the API probe |
| `firedrill/` | Firedrill simulation recipes |
| `docs/API_NOTES.md` | The request formats that worked against TypeSafe, Senso and Persona |
