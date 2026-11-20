"""SingleStore connection and tables. The log table is the public, append-only record."""
import os
import queue
import threading
from contextlib import contextmanager

import singlestoredb

from app import config

TABLES = [
    """
    CREATE TABLE IF NOT EXISTS log (
        id VARCHAR(36) NOT NULL,
        coalition_id VARCHAR(36) NOT NULL,
        agent_id VARCHAR(64) NOT NULL,
        type VARCHAR(16) NOT NULL,
        body JSON NOT NULL,
        ts DATETIME(6) NOT NULL,
        PRIMARY KEY (coalition_id, id),
        SORT KEY (ts)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS coalitions (
        id VARCHAR(36) NOT NULL,
        need TEXT NOT NULL,
        state VARCHAR(16) NOT NULL DEFAULT 'open',
        created_at DATETIME(6) NOT NULL,
        embedding VECTOR(384, F32) NULL,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS members (
        coalition_id VARCHAR(36) NOT NULL,
        agent_id VARCHAR(64) NOT NULL,
        client VARCHAR(32) NOT NULL,
        verified BOOL NOT NULL DEFAULT FALSE,
        removed_reason TEXT NULL,
        joined_at DATETIME(6) NOT NULL,
        PRIMARY KEY (coalition_id, agent_id)
    )
    """,
]


def connect():
    if not config.SINGLESTORE_URL:
        raise RuntimeError("SINGLESTORE_URL is not set")
    return singlestoredb.connect(config.SINGLESTORE_URL, autocommit=True)


# A small capped pool. The shared tier allows 100 connections per user across every machine using
# this database, so the relay never holds more than POOL_SIZE however many threads are busy.
POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "8"))
_idle: "queue.LifoQueue" = queue.LifoQueue()
_slots = threading.BoundedSemaphore(POOL_SIZE)


@contextmanager
def pooled():
    """Borrow a connection; return it on success, discard it on error."""
    if not _slots.acquire(timeout=30):
        raise RuntimeError("database pool exhausted")
    conn = None
    try:
        try:
            conn = _idle.get_nowait()
        except queue.Empty:
            conn = connect()
        yield conn
        _idle.put(conn)
        conn = None
    finally:
        if conn is not None:  # an error happened while borrowed: don't reuse a possibly broken connection
            try:
                conn.close()
            except Exception:
                pass
        _slots.release()


def create_tables() -> None:
    with connect() as conn, conn.cursor() as cur:
        for ddl in TABLES:
            cur.execute(ddl)
        # Tables made before vector search existed: add the column once.
        cur.execute("SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() AND table_name = 'coalitions' AND column_name = 'embedding'")
        if cur.fetchone()[0] == 0:
            cur.execute("ALTER TABLE coalitions ADD COLUMN embedding VECTOR(384, F32) NULL")


def ping() -> bool:
    try:
        with pooled() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone()[0] == 1
    except Exception:
        return False
