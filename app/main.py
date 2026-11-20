"""Open Union relay: one FastAPI app that serves the API and the web pages."""
import io
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles

from app import config, db
from app.protocol import DEMO_COALITION_ID, DEMO_COALITION_NEED
from app.matching import router as matching_router
from app.negotiation import router as negotiation_router
from app.offer_check import router as offer_check_router
from app.persona import router as persona_router
from app.relay import router as relay_router
from app.store import store

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
        store.create_coalition(DEMO_COALITION_NEED, DEMO_COALITION_ID)
        store.backfill_embeddings()
        log.info("database tables ready, demo coalition %s", DEMO_COALITION_ID)
    except Exception as exc:  # keep serving so /health can report the problem
        log.error("database setup failed: %s", type(exc).__name__)
    yield


app = FastAPI(title="Open Union", lifespan=lifespan)
app.include_router(matching_router)  # before relay: /coalitions/match must win over /coalitions/{id}
app.include_router(relay_router)
app.include_router(negotiation_router)
app.include_router(persona_router)
app.include_router(offer_check_router)


@app.get("/health")
def health():
    return {"ok": True, "db": db.ping()}


def public_url() -> str:
    """The address phones can reach: PUBLIC_URL, else the tunnel link saved in demo/TUNNEL_URL.txt."""
    url = os.environ.get("PUBLIC_URL", "").strip()
    saved = Path(__file__).resolve().parent.parent / "demo" / "TUNNEL_URL.txt"
    if not url and saved.exists():
        url = saved.read_text().strip()
    return url.rstrip("/")


@app.get("/join-qr.svg")
def join_qr():
    """A QR code for the phone join page, so the whole room can scan it off the stage screen."""
    import qrcode
    import qrcode.image.svg
    base = public_url()
    if not base:
        return Response(status_code=404)
    img = qrcode.make(f"{base}/join.html", image_factory=qrcode.image.svg.SvgPathFillImage, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.get("/public-url")
def get_public_url():
    return {"url": public_url()}


# Mounted last so API routes win over static files.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
