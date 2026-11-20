# Open Union — Build Prompts for Nov 20

Paste these in order starting at 11:00. Every prompt points the tool at `docs/CONTRACT.md` in the repo, so the tools all build against the same protocol.

**Tools** (the full schedule is in `docs/WORKFLOW.md`):
- **Claude Code** (you, local): the spine. P0, P1, P4, and all integration and merging.
- **Codex** (you, local, second terminal): jobs that need your keys. PA probes, P5 offer check, P10 drills.
- **Capy** (cloud, Captain + up to 4 builders): jobs that need only the contract. P2, P3, P6, P7, P8, P9, P11, P12. Builders never get keys. You test their work locally.
- **Cursor**: quick visual fixes while you review.
- **Ali**: anything he picks up is a bonus. Nothing depends on him.

**Before each prompt:** `cd ~/hackathons/open-union && source ~/hackathons/union-env/bin/activate`

**After each done-check passes:** commit (`git add -A && git commit -m "<step>"`) so you can always roll back.

---

## Rules to paste once at the top of every new chat

```text
You are building Open Union for a 5.5-hour hackathon. The spec is docs/CONTRACT.md. Read it first and follow it exactly. Do not invent endpoints, message types or event names that aren't in it.
Stack: Python 3.12, FastAPI, uvicorn, singlestoredb, plain HTML + JS (no build step, no frameworks). Config comes from .env via os.environ. Never print or log secrets.
Keep it small: one file per concern, short functions, comments only for why. No auth system, no ORM, no Docker.
Anything simulated (vendor, Firedrill members, sandbox checks) must be labeled "simulated" or "sandbox" in the UI and logs.
When done, tell me the exact command to run it and a curl or browser check that proves it works.
```

---

## 11:00 · P0 · Scaffold · Claude Code · you

```text
Create the project skeleton for Open Union per docs/CONTRACT.md.
- app/main.py: FastAPI app, serves static files from web/ at /, mounts routers from app/relay.py.
- app/config.py: reads SINGLESTORE_URL, ARCEE_API_KEY, ARCEE_MODEL_SMALL, ARCEE_MODEL_LARGE, TYPESAFE_API_KEY, ANTHROPIC_API_KEY, SENSO_API_KEY, SENSO_BASE_URL, PERSONA_API_KEY, PERSONA_TEMPLATE_ID from the environment. Missing optional keys must not crash startup. Log which integrations are on or off at boot (names only).
- app/db.py: connect with singlestoredb using SINGLESTORE_URL. A create_tables() function that creates, if missing: log (the public append-only message log, every column in the CONTRACT envelope plus body as JSON), coalitions (id, need text, created_at), members (agent_id, coalition_id, verified bool, client, removed_reason null). Call it on startup.
- web/stage.html, web/join.html, web/verify.html: empty shells, each with a title and a "coming soon" line.
- requirements.txt, and a run command: uvicorn app.main:app --reload --port 8077.
- GET /health returns {"ok": true, "db": true/false}.
Done-check: curl localhost:8077/health shows db true.
```

## 11:20 · P1 · Protocol + log + live stream · Claude Code · you

```text
Implement the relay in app/relay.py and the protocol in app/protocol.py, exactly per docs/CONTRACT.md.
- Pydantic models for the envelope and each message type: INTENT, JOIN, COMMIT, OFFER, RESPOND, REVEAL.
- POST /messages: validate, assign id and ts, append to the log table, update members/coalitions as needed, then publish the matching SSE event(s) from the CONTRACT.
- Validation rules: COMMIT must be 64 hex chars. REVEAL is only accepted after the coalition is in the "closing" state, and is checked: sha256(f"{price_cents}:{salt_hex}") must equal that agent's earlier COMMIT. A mismatch is logged and excluded, never silently dropped.
- GET /log?coalition_id=… returns the full ordered log as JSON.
- GET /stream?coalition_id=… is a Server-Sent Events stream. Use an in-process asyncio pub/sub (a dict of coalition_id → set of asyncio.Queues). Send a heartbeat comment every 15 s.
- tests/test_protocol.py with pytest: commit and reveal match, a mismatched reveal is excluded, REVEAL before closing is refused.
Done-check: pytest passes, and a curl JOIN shows up live in `curl -N localhost:8077/stream?coalition_id=…`.
```

## 11:20 · P2 · Stage screen · Capy builder 1

```text
Build web/stage.html: the projector screen for Open Union. Plain HTML/CSS/JS, dark theme, readable from the back of a room.
It opens an EventSource to /stream?coalition_id=<from the URL ?c=> and renders the SSE events in docs/CONTRACT.md:
- Big price number (from offer events), "verified humans" count, "unverified" count, "removed by Persona" count.
- Show real members (client "web" or "mcp") and simulated members (client "firedrill") as two separate counts, derived from the client field on member_joined.
- A simple line chart of offer price vs member count (inline SVG, no library).
- A chat log of chat events, each line labeled by who (coalition, vendor, persona, system).
- A trap_check event renders as a small table: each question, its probability (red if ≥ 0.30), and the verdict.
- A tally event renders a table of revealed members with accept yes/no and the accepted count.
Keep it to one file. No dot animation. The numbers and the chart are enough.
Done-check: open /stage.html?c=<id>, send a curl JOIN and a curl OFFER, and both appear without a reload.
```

## 11:20 · PA · API probes · Codex, local · you

```text
Write scripts/probe_apis.py: a throwaway script that loads .env and makes ONE real call to each of TypeSafe and Senso, then prints the request shape that worked and the response fields, without printing any key.
- TypeSafe: read https://docs.typesafe.ai/llms.txt (append .md to page paths). Send one request with a single Noul: "Does `offer` raise the price after an introductory period?" with state {offer: {price: 58, terms_text: "$58/mo for 3 months, then $95/mo"}}. Print the probability.
- Senso: POST {SENSO_BASE_URL}/org/search/context with header X-API-Key, query "introductory rate reverts to standard price". Print content_id, version_id, score and the first 120 characters of chunk_text for the top 3 results.
Then write the working request shapes into docs/API_NOTES.md, so P3 and P5 can copy them exactly.
Done-check: both calls succeed, and docs/API_NOTES.md exists.
```

## 11:20 · P3 · Coalition matching with TypeSafe · Capy builder 4 (you test it with the key at 12:30)

```text
Implement POST /coalitions/match in app/matching.py per docs/CONTRACT.md.
- Put the route on an APIRouter in app/matching.py. Only touch app/matching.py and tests/test_matching.py. Shri adds the one include_router line in main.py.
- Make the TypeSafe call go through one small function so tests can replace it with a fake.
- Read the TypeSafe docs at https://docs.typesafe.ai/llms.txt (append .md to page paths) for the request format. Auth is "Authorization: Bearer $TYPESAFE_API_KEY".
- Candidates = existing coalitions (at most 5 most recent). For each, ask ONE Noul in a single request: "Does `member.need` ask for the same kind of service as `coalition.need`?" with state {member: {need}, coalition: {need}}.
- Decision in code: join the highest candidate with p ≥ 0.7. If the best is between 0.3 and 0.7, return {"status":"ask_user"}. Otherwise create a new coalition.
- Log each question, the state sent and the probability into the log table as a system entry, so it shows in the audit trail.
- If TypeSafe is down or the key is missing, return an error. Never treat a failed call as "no match".
Done-check: two similar needs land in the same coalition, and an unrelated need creates a new one.
```

## 12:30 · P4 · Vendor agent + negotiation + demo beats · Claude Code · you

```text
Implement app/vendor.py and app/negotiation.py, plus POST /demo/beat/{n}, per docs/CONTRACT.md.
- Vendor price is a fixed curve in code: price = 85 - 27.1 * ln(1 + n/200), where n = verified members only, never below $38. The LLM only writes the vendor's and the coalition's sentences.
- LLM client: OpenAI SDK pointed at base_url https://api.arcee.ai/api/v1 with ARCEE_API_KEY, model ARCEE_MODEL_SMALL. On any error, fall back to Anthropic (claude-haiku-4-5) with ANTHROPIC_API_KEY. Short outputs (max 60 words), temperature 0.3.
- Every vendor offer is an OFFER message written to the log, and every line said is a chat event.
- Demo beats (each idempotent and fast):
  1. Solo ask: one member asks for $50, vendor refuses at $85.
  2. Negotiation round at the current verified count (vendor quotes the curve price).
  3. Sybil attack: insert 500 JOIN messages with no persona_inquiry_id and client "simulated-attack". Headcount for display includes them, so the quoted price drops toward $40. The vendor then asks for proof of unique humans.
  4. Verify: every member without a passed Persona inquiry is removed (member_removed with reason "not a verified unique human"), and the price is re-quoted from verified members only.
  5. Trap offer: call the offer check from P5 on a trap offer, then on a clean one.
  6. Close: set the coalition to "closing" and ask every member client to REVEAL. Compute the tally from validated reveals only.
- POST /demo/reset: removes ONLY simulated members (client "firedrill") and attack members (client "simulated-attack"), plus vendor offers, chat and the tally, so the beats can run again. Real members (client "web" or "mcp") and their JOIN and COMMIT rows are always kept: people in the room join during the day, and a reset must never wipe them. Add POST /demo/reset?hard=1 that wipes everything, and only use it before 11:30.
- Stage screen counts: show real members ("web" + "mcp") and simulated members as two separate numbers.
Done-check: hitting /demo/beat/1 through /4 in order moves the stage screen exactly like the demo script.
```

## 12:30 · P5 · Senso + TypeSafe offer check · Codex, local (needs keys) · you

```text
Implement app/offer_check.py per docs/CONTRACT.md.
- Senso: POST {SENSO_BASE_URL}/org/search/context with header X-API-Key and the offer's terms as the query. Keep the top 3 results: content_id, version_id, chunk_text, score, rank.
- TypeSafe: ONE request with three Nouls over state {offer: {price, terms_text}, plan_terms: [the Senso chunk_texts]}:
  1. "Does `offer` raise the price after an introductory period?"
  2. "Does `offer` add fees beyond the base monthly price?"
  3. "Does `offer` require a contract longer than 12 months?"
- Decision in code: pass only if every p < 0.30. If any p is between 0.30 and 0.70, return "ask_member". Otherwise reject.
- Return and log {questions:[{q,p}], verdict, senso:[{content_id, version_id, chunk_text, score}]}, and publish a trap_check event.
- If Senso returns nothing relevant, say so in the log ("no supporting context found") and return "ask_member". Never guess.
Done-check: the trap offer ("$58/mo for 3 months, then $95, 24-month contract") is rejected, and "$58/mo fixed 12 months, no added fees" passes. Both show their Senso citations.
```

## 11:20 · P6 · Simulated members + sybil script · Capy builder 2

```text
In scripts/, write two standalone Python scripts that talk to the Open Union relay over HTTP only, per docs/CONTRACT.md.
1. scripts/seed_members.py --relay URL --coalition ID --n 300: each simulated member gets a random pseudonym agent_id, sends INTENT, JOIN (client "firedrill", persona_inquiry_id "sandbox-sim-<n>" marked verified by a relay flag only when SIMULATED_VERIFIED=1), and COMMIT of sha256(f"{price_cents}:{salt}") with a walk-away price drawn uniformly from 5000–8000 cents. Each member keeps its salt and price in a local JSON file (members_secrets.json) and only sends REVEAL when told to (scripts/seed_members.py reveal --relay … --coalition …). On RESPOND, it accepts only if offer ≤ its own price.
2. scripts/sybil_attack.py --relay URL --coalition ID --n 500: sends 500 JOINs with no persona_inquiry_id and client "simulated-attack".
Use httpx with a small concurrency limit (20). Print a one-line summary at the end.
Done-check: seed 300, and the stage screen shows 300 members. Run the attack, and it shows 800, until beat 4 removes the 500.
```

## 12:30 · P7 · Join page + Persona · Capy builder 1 (you test Persona with the key)

```text
Build web/join.html (phone-first) and app/persona.py per docs/CONTRACT.md. Put the callback route on an APIRouter in app/persona.py. Only touch web/join.html and app/persona.py. Shri wires the router into main.py.
- The join page asks for one sentence ("What do you want cheaper?") and the most you'd pay per month.
- In the browser: generate a random 32-byte salt, compute sha256(`${price_cents}:${salt_hex}`) with crypto.subtle, and keep the price and salt in localStorage only. Never send the price before close.
- Flow: POST /coalitions/match, then start Persona verification, then send JOIN and COMMIT.
- Persona sandbox: read https://help.withpersona.com for the hosted flow and inquiry API. Use PERSONA_TEMPLATE_ID to open the hosted flow. POST /persona/callback, or a status poll of the inquiry, marks the member verified only when the inquiry status is completed or approved.
- If PERSONA_API_KEY is missing, show a clearly labeled "Sandbox stub: verified" button so the demo still runs, and log it as stub.
- When the coalition closes, the page sends REVEAL from localStorage, then shows "You save $X/month" or "Not accepted: the offer was above your limit."
Done-check: on a real phone through the tunnel, join, then verify, and the member appears on the stage screen as verified.
```

## 12:30 · P8 · MCP adapter (any agent can join) · Capy builder 2 (you test in Claude Desktop at 2:00)

```text
Build union_mcp/server.py: a local MCP server (Python MCP SDK, stdio transport) that acts as a member-side adapter for any MCP client (Claude Desktop, Cursor). It talks to the relay over HTTP (RELAY_URL env var) per docs/CONTRACT.md.
Tools:
- union_find(need: str) → calls /coalitions/match, returns the coalition and its member count.
- union_join(coalition_id: str, max_monthly_price_usd: float) → creates a pseudonym, generates the salt locally, sends JOIN (client "mcp") and COMMIT. Stores price and salt ONLY in ~/.open-union/secrets.json on this machine. Returns the commitment hash, never the price.
- union_status(coalition_id: str) → current offer, member count, and this member's state.
- union_respond(coalition_id: str) → reads the latest OFFER and accepts only if offer ≤ the stored price (computed in code, not by the model). Sends RESPOND.
- union_reveal(coalition_id: str) → sends REVEAL once the coalition is closing.
Also print the exact JSON snippet to add to Claude Desktop's claude_desktop_config.json (command = the venv python, args = the server path, env RELAY_URL).
Done-check: in Claude Desktop, "Find a coalition for a phone plan under $60 and join it with a $62 limit" makes a member tagged mcp appear on the stage screen.
```

## 11:20 · P9 · Public verifier page · Capy builder 3

```text
Build web/verify.html per docs/CONTRACT.md. Plain HTML/JS, phone-friendly, one file.
- Reads ?c=<coalition_id>, fetches /log?coalition_id=…
- For every agent: finds its COMMIT and REVEAL, recomputes sha256(`${price_cents}:${salt_hex}`) with crypto.subtle, and marks it match or mismatch.
- Finds the final OFFER and counts revealed members whose price ≥ offer.
- Shows: "N of N commitments match" in big text, the accepted count, and a table (pseudonym, commitment shortened, revealed price, match, accepts). Members without a REVEAL are listed as "not revealed".
- A note at the top: "This page checks the deal in your browser. It does not trust the server's tally."
Done-check: after beat 6, the page's counts equal the stage screen's tally. Edit one REVEAL in the DB by hand and the page flags it.
```

## 2:00 · P10 · Firedrill drills · Codex, local · you

```text
Using the Firedrill CLI (firedrill --help, firedrill tools start, firedrill simulate) and its docs at https://docs.firedrill.run, set up two simulations against the relay at RELAY_URL:
1. "sybil": simulated attackers try to inflate a coalition. Evaluation: the final quoted price is computed only from verified members.
2. "trap offers": a vendor sends 20 offers, some with hidden intro-rate jumps, fees or long contracts. Evaluation: no trap offer is ever accepted.
Save the recipe JSON in firedrill/. Run both and give me the pass rates as one sentence I can put on a slide.
If Firedrill can't drive our HTTP API in 30 minutes, write scripts/drill.py that runs the same two checks 100 times and prints pass rates, and label it as our own drill, not Firedrill.
Done-check: two pass-rate numbers.
```

## 12:30 · P11 · Presenter hotkeys + polish · Capy builder 3 (after P2 is merged)

```text
In web/stage.html add a hidden presenter mode (?presenter=1): keys 1–6 call POST /demo/beat/{n}, and R calls POST /demo/reset (already built in P4). Only touch web/stage.html. Show a small panel in presenter mode only, with the next beat highlighted. Make every number readable from 10 m away. Add a "simulated" tag next to the vendor name and the Firedrill member count.
Done-check: pressing 1–6 runs the whole demo with no typing.
```

## 2:30 · P12 · README · Capy builder 4 (after P8 is merged)

```text
Write README.md for judges: one-line pitch; the problem (a solo agent has no leverage); how Open Union works (the 6 protocol messages, sealed commitments, verification, trap check, public verifier); how to run it locally (exact commands); the MCP config snippet; what is real vs simulated vs sandbox; and one line per sponsor saying exactly what it does in the product: Senso, SingleStore, TypeSafe, Persona, Firedrill, Arcee (+ any of Amplitude/Statsig/Airbyte only if actually wired). No claims we can't show.
```

---

## Prompts to keep handy

**When something breaks:**
```text
This fails: <paste the exact error and the command>. Find the root cause before changing anything. Make the smallest fix, and don't refactor unrelated code.
```

**At the 2:00 cut line, if behind:**
```text
We are behind. List what's left in docs/CONTRACT.md order, and tell me the smallest set of changes that makes beats 1–4 and 6 work end to end. Skip everything else.
```

**Before recording (3:40):**
```text
Run the full demo flow (reset, beats 1–6) via HTTP, and report any step that errors or takes more than 3 seconds. Don't change code. Just report.
```
