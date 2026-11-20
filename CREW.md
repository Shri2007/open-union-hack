# Capy crew plan

Captain dispatches only the tasks below. Everything else in `docs/PROMPTS.md` is built locally by Shri. The full schedule is in `docs/WORKFLOW.md`.

| Wave | Task | Prompt | May touch only | Starts when |
|---|---|---|---|---|
| 1 | Stage screen | P2 | `web/stage.html` | Shri says "go wave 1" (after P0 is pushed, about 11:20) |
| 1 | Simulated members + sybil script | P6 | `scripts/seed_members.py`, `scripts/sybil_attack.py` | "go wave 1" |
| 1 | Public verifier page | P9 | `web/verify.html` | "go wave 1" |
| 1 | Coalition matching | P3 | `app/matching.py`, `tests/test_matching.py` | "go wave 1". Read `docs/API_NOTES.md` once it exists. |
| 2 | Join page + Persona | P7 | `web/join.html`, `app/persona.py` | "go wave 2" (about 12:30) |
| 2 | MCP adapter | P8 | `union_mcp/` | "go wave 2" |
| 2 | Presenter hotkeys | P11 | `web/stage.html` | "go wave 2", and only after P2 is merged |
| 3 | README for judges | P12 | `README.md` | "go P12" (after P8 is merged, about 2:30) |

Rules:
- At most 4 builder threads at once.
- Nothing starts before 11:00 AM PT on Nov 20, and nothing starts until Shri says go.
- Never edit `app/main.py`. Expose routes on an APIRouter, and Shri wires them in.
- No API keys are available to builders. Code against the contract and `docs/API_NOTES.md`, and use fakes in tests.
- Report the done-check result with every PR. Nothing is merged without Shri's OK.
