# Open Union: Protocol Contract

This is the spec every part of Open Union builds against. Change it only by agreement, and update this file first.

## Idea

Personal agents (from any vendor) find others who need the same thing, form a coalition, and bargain with a vendor as one buyer. Each member's walk-away price is sealed with a hash commitment and revealed only at close, so anyone can re-check the tally. Only verified unique humans count toward the headcount.

## Coalition states

`open` → `closing` → `closed`. REVEAL is accepted only in `closing`. The tally is final at `closed`.

## Message envelope

Every message is one row in the public, append-only log.

```text
{ id, coalition_id, agent_id, type, body, ts }
```

- `id` and `ts` are set by the relay.
- `agent_id` is a random pseudonym chosen by the member's agent. No names, emails or prices go in the log before REVEAL.

## Message types

| type | sent by | body |
|---|---|---|
| `INTENT` | member agent | `{ need: str }`: one sentence, e.g. "phone plan under $60, Bay Area" |
| `JOIN` | member agent | `{ persona_inquiry_id: str or null, client: "web" or "mcp" or "firedrill" or "simulated-attack" }` |
| `COMMIT` | member agent | `{ commitment: str }` = lowercase hex `sha256("<price_cents>:<salt_hex>")` |
| `OFFER` | vendor agent | `{ price_cents: int, terms_text: str, senso_content_ids: [str], trap_checks: [{q: str, p: float}] }` |
| `RESPOND` | member agent | `{ offer_id: str, accept: bool }`: decided in the member's own code by comparing the offer to its own sealed price |
| `REVEAL` | member agent, in `closing` only | `{ price_cents: int, salt_hex: str }` |

## Relay API

| Method | Path | Does |
|---|---|---|
| POST | `/coalitions/match` | `{ need }` → `{ status: "joined" or "created" or "ask_user", coalition_id?, member_count? }` |
| POST | `/messages` | Validates and appends any protocol message, then publishes SSE events |
| GET | `/log?coalition_id=` | The full ordered public log |
| GET | `/stream?coalition_id=` | Server-Sent Events for screens |
| POST | `/demo/beat/{n}` | Presenter trigger for demo beats 1–6 |
| POST | `/demo/reset` | Clears simulated members, offers, chat and tally. Keeps real members (`web`, `mcp`). `?hard=1` wipes everything. |
| POST | `/persona/callback` | Marks a member verified once its Persona inquiry passed |

## SSE events

```text
member_joined   { agent_id, client, verified }
member_removed  { agent_id, reason }
offer           { offer_id, price_cents, terms_text }
trap_check      { questions: [{q, p}], verdict: "reject" | "pass" | "ask_member", senso: [{content_id, version_id, score}] }
chat            { who: "coalition" | "vendor" | "persona" | "system", text }
tally           { accepted, total, revealed: [{agent_id, price_cents, ok}] }
```

## Rules enforced in code, never by a model

1. Headcount for pricing counts only members whose Persona inquiry passed.
2. An offer passes the trap check only if every trap question has p < 0.30. If any p is between 0.30 and 0.70, the agent asks its human. Otherwise it rejects.
3. A member accepts only if `offer_price_cents ≤ its own sealed price_cents`, checked in the member's own agent.
4. At close, the tally counts only REVEALs whose `sha256("<price_cents>:<salt_hex>")` equals that agent's COMMIT. Mismatches are logged and excluded.
5. Vendor price = `85 − 27.1 × ln(1 + n/200)` dollars, n = verified members, floor $38. Models write the words only.
6. Every judgment (TypeSafe question + probability, Senso citation) is written to the log, so it's part of the audit trail.
7. Anything simulated or sandboxed is labeled as such in the log and the UI.

## Trust boundaries

- The relay never sees a member's price before REVEAL.
- Salts live only with the member: browser localStorage, `~/.open-union/secrets.json` for the MCP adapter, `members_secrets.json` for simulated members.
- Anyone can re-check the tally from `/log` alone (see `web/verify.html`).
