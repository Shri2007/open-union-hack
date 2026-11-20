"""Cognee vendor memory as a small local service, run in its own Python environment.

Cognee pins library versions the relay depends on, so it runs here, separately, and the relay talks to it
over HTTP (MEMORY_URL). If this service is down or slow, the relay simply has no memory; the demo goes on.

Run (from the repo root, inside the cognee environment, with the Cognee settings from PR #16 exported):
    python scripts/memory_service.py            # listens on 127.0.0.1:8766
"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app import memory  # noqa: E402  (in-process Cognee backend)

app = FastAPI(title="Open Union vendor memory (Cognee)")


class RememberIn(BaseModel):
    need: str
    walk_price_cents: int


class RecallIn(BaseModel):
    need: str


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/remember")
def remember(body: RememberIn) -> dict:
    # cognify can take a while, so store in the background and answer at once.
    threading.Thread(target=memory.remember_walkout, args=(body.need, body.walk_price_cents),
                     kwargs={"force": True}, daemon=True).start()
    return {"queued": True}


@app.post("/recall")
def recall(body: RecallIn) -> dict:
    return {"memory": memory.recall_walkout(body.need, force=True)}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8766, log_level="info")
