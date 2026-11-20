# Open Union: Workflow for Nov 20

Who does what, when. Prompts are in `docs/PROMPTS.md`, the spec is `docs/CONTRACT.md`.

**Roles**
- **You (Claude Code, local):** the spine, plus reviewing, testing and merging everything
- **Codex (local, second terminal):** jobs that need your API keys
- **Capy:** Captain dispatches, up to **4 builders** at once, jobs that need only the contract. Builders never get keys.
- **Cursor:** quick visual fixes while you review

**The golden rules**
1. One owner per file. No two agents touch the same file at the same time.
2. Capy work only starts after the skeleton (P0) is pushed.
3. You merge everything, after its done-check passes. Commit after every merge.
4. Anything that needs a key gets tested on your laptop, never in the cloud.

---

## Schedule

| Time | You (Claude Code) | Codex (local) | Capy builder 1 | Capy builder 2 | Capy builder 3 | Capy builder 4 |
|---|---|---|---|---|---|---|
| 9:30–11:00 | Sponsor booths: Senso, TypeSafe, Arcee, Persona. **No code.** | — | — | — | — | — |
| **11:00–11:20** | **P0 skeleton.** Push, then tell Captain "go wave 1." | — | — | — | — | — |
| **11:20–12:30** wave 1 | **P1** protocol, log, live stream | **PA** API probes (TypeSafe + Senso), writes `docs/API_NOTES.md` | **P2** stage screen | **P6** simulated members + attack script | **P9** verifier page | **P3** coalition matching (uses `API_NOTES.md` once it's pushed) |
| 12:30 | **Merge wave 1.** Wire P3's router in. Test P3 with your TypeSafe key. Push, then tell Captain "go wave 2." | | | | | |
| **12:30–1:30** wave 2 | **P4** vendor, negotiation, beats 1–6, `/demo/reset` | **P5** Senso + TypeSafe trap check | **P7** join page + Persona (stub if no key) | **P8** MCP adapter | **P11** presenter hotkeys (stage screen is merged by now) | free: spare for fixes |
| **1:30–2:00** | **Lunch + first full run:** reset, seed 300, beats 1–4. Merge wave 2. **Walk the room with the join QR code:** real members stay through resets. | — | — | — | — | — |
| 2:00 checkpoint | **Plain Union works end to end?** If not, everything below is fixing the core. | | | | | |
| **2:00–3:00** | Wire P7's router in. Test Persona with your key. Test P8 in Claude Desktop. Fix integration bugs. | **P10** Firedrill drills (or the scripted fallback) | fixes from your testing | fixes from your testing | fixes from your testing | **P12** README (after P8 is merged, around 2:30) |
| 3:00 checkpoint | **MCP join works?** If not, cut it and pitch the protocol from the verifier page. | | | | | |
| **3:00–3:30** | Full demo runs (reset, beats 1–6) twice. Merge the README. | Pre-recording check prompt | — | — | — | — |
| **3:30** | **Feature freeze.** Bug fixes only. Rehearse twice with a timer. | | | | | |
| **3:45–4:10** | Record the video in one take (Tella or Screen Studio). Upload it and check the link in a private window. | | | | | |
| **4:10–4:25** | Repo opens logged out, then submit: repo, video link, tools list, names and emails. | | | | | |
| **4:30** | Deadline | | | | | |

---

## Real members from the room

- From about 1:30, the join page is live through the tunnel. Show the QR code to people at lunch and between checkpoints: "Scan, type what you want cheaper, set your max, 30 seconds."
- Collect nothing personal. Members are random pseudonyms. Tell people it's a demo, the vendor is simulated and nothing gets bought.
- **Start cloudflared once and never restart it.** A restart changes the link and kills every QR code already shown.
- `/demo/reset` keeps real members and only clears simulated ones. Never use `?hard=1` after 11:30.
- On stage: "300 are simulated. N are people in this room who joined from their phones today."

## What you tell Captain

- **11:20, after P0 is pushed:** "Go wave 1: P2, P6, P9, P3."
- **12:30, after wave 1 is merged:** "Go wave 2: P7, P8, P11."
- **About 2:30, after P8 is merged:** "Go P12."
- **Anytime a builder's PR fails its done-check:** "Fix: <paste the error>. Same file limits."

## File owners

| Files | Owner |
|---|---|
| `app/main.py`, `app/config.py`, `app/db.py`, `app/relay.py`, `app/protocol.py`, `tests/test_protocol.py` | You (P0, P1) |
| `app/vendor.py`, `app/negotiation.py` | You (P4) |
| `scripts/probe_apis.py`, `docs/API_NOTES.md` | Codex (PA) |
| `app/offer_check.py` | Codex (P5) |
| `firedrill/`, `scripts/drill.py` | Codex (P10) |
| `web/stage.html` | Capy P2, then Capy P11 |
| `scripts/seed_members.py`, `scripts/sybil_attack.py` | Capy P6 |
| `web/verify.html` | Capy P9 |
| `app/matching.py`, `tests/test_matching.py` | Capy P3 |
| `web/join.html`, `app/persona.py` | Capy P7 |
| `union_mcp/` | Capy P8 |
| `README.md` | Capy P12 |
| `docs/CONTRACT.md` | Nobody edits it without your OK |

## If you're behind

| At | If | Then |
|---|---|---|
| 12:30 | P1 isn't working | Pause wave 2 until it is. Everything depends on the log and the stream. |
| 2:00 | Beats 1–4 don't run | Stop all new work. Every builder fixes what you assign. |
| 3:00 | MCP join fails | Cut it. The verifier page carries the "open" story. |
| 3:00 | Persona sandbox fails | Keep the labeled stub. Say so on screen. |
| 3:30 | Anything is still half-done | Cut it. Freeze. |
