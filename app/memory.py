"""Vendor memory for walkouts, backed by Cognee (SIMULATED vendor "Northline Mobile" remembers a coalition).

remember_walkout(need, walk_price_cents) stores a sentence in Cognee (add + cognify).
recall_walkout(need) searches Cognee and returns {"walk_price_cents", "text"} or None.
Prices and decisions stay in code: memory only supplies the remembered number and a sentence for the chat.

Off unless COGNEE_MEMORY=1. Any Cognee failure is logged and becomes "no memory"; it never raises.
"""
import asyncio
import logging
import os
import re
import threading

log = logging.getLogger("open_union.memory")
DATASET = os.environ.get("COGNEE_DATASET", "open-union-demo")
_PRICE_RE = re.compile(r"walked at (\d+) cents")
_loop: asyncio.AbstractEventLoop | None = None
_lock = threading.Lock()


MEMORY_URL = os.environ.get("MEMORY_URL", "").rstrip("/")  # Cognee running as scripts/memory_service.py


def enabled() -> bool:
    return os.environ.get("COGNEE_MEMORY") == "1" or bool(MEMORY_URL)


def _remote(path: str, payload: dict, timeout: float) -> dict | None:
    """Call the separate Cognee memory service. Any failure means no memory, never an error."""
    import httpx
    try:
        r = httpx.post(f"{MEMORY_URL}{path}", json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        log.warning("memory service %s failed, continuing without memory: %r", path, exc)
        return None


def memory_sentence(need: str, walk_price_cents: int) -> str:
    return (f"Northline Mobile (simulated vendor) memory: the coalition that wanted '{need}' "
            f"walked at {walk_price_cents} cents a month (${walk_price_cents / 100:.0f}).")


class CogneeBackend:
    """Real Cognee: add -> cognify -> search(CHUNKS). Imported lazily so the app runs without cognee installed."""

    async def store(self, text: str) -> None:
        import cognee
        await cognee.add(text, dataset_name=DATASET)
        await cognee.cognify(datasets=[DATASET])

    async def search(self, query: str) -> list[str]:
        import cognee
        from cognee import SearchType
        results = await cognee.search(query_text=query, query_type=SearchType.CHUNKS, datasets=[DATASET], top_k=5)
        return [_text_of(r) for r in _flatten(results)]


def _flatten(x):
    if isinstance(x, (list, tuple)):
        for i in x:
            yield from _flatten(i)
    else:
        yield x


def _text_of(r) -> str:
    if isinstance(r, str):
        return r
    if isinstance(r, dict):
        sr = r.get("search_result")
        if sr is not None:
            return " ".join(_text_of(i) for i in _flatten(sr))
        return str(r.get("text") or r)
    return str(getattr(r, "text", r))


_backend = None


def set_backend(b) -> None:
    """Tests inject a fake backend here."""
    global _backend
    _backend = b


def _get_backend():
    global _backend
    if _backend is None:
        _backend = CogneeBackend()
    return _backend


def _run(coro):
    """Run a coroutine on one persistent loop (Cognee keeps async DB engines bound to a loop)."""
    global _loop
    with _lock:
        if _loop is None:
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, daemon=True, name="cognee-loop").start()
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout=float(os.environ.get("COGNEE_TIMEOUT", "180")))


def remember_walkout(need: str, walk_price_cents: int, force: bool = False) -> bool:
    if not (enabled() or force):
        return False
    if MEMORY_URL and not force:
        return bool(_remote("/remember", {"need": need, "walk_price_cents": walk_price_cents}, 5))
    try:
        _run(_get_backend().store(memory_sentence(need, walk_price_cents)))
        log.info("memory: stored walkout at %s cents for %r (Cognee, simulated vendor)", walk_price_cents, need)
        return True
    except Exception as exc:
        log.warning("memory: remember failed, continuing without memory: %r", exc)
        return False


def recall_walkout(need: str, force: bool = False) -> dict | None:
    if not (enabled() or force):
        return None
    if MEMORY_URL and not force:
        got = _remote("/recall", {"need": need}, float(os.environ.get("MEMORY_RECALL_TIMEOUT", "10")))
        return (got or {}).get("memory")
    try:
        for text in _run(_get_backend().search(need)):
            m = _PRICE_RE.search(text or "")
            if m:
                cents = int(m.group(1))
                return {"walk_price_cents": cents, "text": text.strip()}
        return None
    except Exception as exc:
        log.warning("memory: recall failed, continuing without memory: %r", exc)
        return None
