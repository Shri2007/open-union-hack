# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Inferred from the repo and not yet confirmed by the owner: the join page is opened on a phone by a person in the room (a hackathon booth, lunch, a stage audience) who scanned a QR code. They have about 30 seconds and no account. Their job: say what they want cheaper in one sentence, set the most they would pay per month, prove they are a real person, and join a coalition. Judges may also open the same link on a laptop.

## Product Purpose

Open Union lets personal agents from any vendor team up and bargain with a vendor as one buyer. Each member's walk-away price is sealed with a hash, and only revealed at close, so anyone can re-check the tally. Only verified unique humans count toward the headcount. The join page is how a real person becomes a member.

## Positioning

The sealed price and the public proof. A member can join a group negotiation without telling anyone their limit, and the final tally can be re-checked by anyone from the public log in their own browser.

## Operating Context

- The phone page sits next to a projector screen (`stage.html`) that shows members joining, the price curve, the rejected trap offer and the sealed-tally proof.
- The price and a random salt are generated in the browser and kept in the browser's local storage only. The server only ever receives a sha256 commitment.
- Persona verification opens on Persona's hosted page and returns to the join page. The page must resume the member after that redirect.
- In the demo the vendor ("Northline Mobile") is fictional, about 300 members are simulated, and Persona runs in sandbox mode. These are labelled everywhere they show up.

## Capabilities and Constraints

- One file, `web/join.html`: plain HTML, CSS and JavaScript. No build step, no frameworks, no new dependencies (project rule in AGENTS.md). Any CDN stylesheet needs Shri's OK, and the page must still work on bad venue wifi, so it should not depend on one.
- The flow must keep working exactly: `POST /coalitions/match`, a 32-byte salt and sha256 commitment in the browser, `/persona/start` then the hosted flow, `JOIN` and `COMMIT` via `/messages`, `/persona/callback`, live updates, and the REVEAL step at close.
- Every element id, fetch call and localStorage key the script uses must stay as is.
- The price is never sent to the relay before close.
- Sandbox and stub states must be labelled in the UI (project rule): "Sandbox stub" when there is no Persona key, "Persona sandbox" otherwise.
- Not decided: the design rules the owner wrote in a local, git-ignored `FRONTEND_RULES.md`. They are not available to this session yet.

## Brand Commitments

The name is Open Union. The product's language is plain and exact: "sealed", "commitment", "verified unique human". No fabricated testimonials, customers or savings claims.

## Evidence on Hand

Real flow and copy in `web/join.html`, the protocol in `docs/CONTRACT.md`, the README in the repo root. There are no logos, photos or brand assets. Do not invent any.

## Product Principles

1. The person's limit stays theirs: the design should make the sealing feel safe and visible, never ask for it twice.
2. One thumb, one task, thirty seconds: every screen asks for one thing.
3. Say what is real, simulated and sandbox, in plain words, wherever it matters.
4. Show the proof, not a claim: the commitment hash and the verification state are real and visible.
5. Works first, looks great second: no change may break the flow.

## Accessibility & Inclusion

Not specified by the owner. Defaults: text contrast at least 4.5:1, tap targets at least 44px, visible keyboard focus, works at 320px width, respects reduced motion.
