"""Open Union relay: one FastAPI app that serves the API and the web pages."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import config, db
from app.relay import router as relay_router

log = logging.getLogger("open_union")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    on = [k for k, v in config.INTEGRATIONS.items() if v]
    off = [k for k, v in config.INTEGRATIONS.items() if not v]
    log.info("integrations on: %s", ", ".join(on) or "none")
    log.info("integrations off: %s", ", ".join(off) or "none")
    try:
        db.create_tables()
        log.info("database tables ready")
    except Exception as exc:  # keep serving so /health can report the problem
        log.error("database setup failed: %s", type(exc).__name__)
    yield


app = FastAPI(title="Open Union", lifespan=lifespan)
app.include_router(relay_router)


@app.get("/health")
def health():
    return {"ok": True, "db": db.ping()}


# Mounted last so API routes win over static files.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
