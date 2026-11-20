# Rules for every agent working on Open Union

- The spec is `docs/CONTRACT.md`, and the build prompts are `docs/PROMPTS.md` (P0–P12). Follow them exactly. Don't redesign anything.
- The project is built during the event, from 11:00 AM PT on Nov 20, 2026. Commit after every done-check.
- Each task touches only the files its prompt names. If another file needs a change, stop and report back.
- If the contract seems wrong or incomplete, stop and report back. Never edit `docs/CONTRACT.md`.
- Never read, print, request or commit secrets. `.env` exists only on Shri's laptop. Tasks that need API keys (SingleStore, Arcee, Senso, TypeSafe, Persona) are built locally, not by cloud agents.
- Stack: Python 3.12, FastAPI, plain HTML + JS. No new frameworks, no build step.
- Label anything simulated or sandboxed as such in the UI and logs.
- Nothing is merged without Shri's OK.
