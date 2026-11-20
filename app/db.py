"""SingleStore connection and tables. The log table is the public, append-only record."""
import threading

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


_local = threading.local()


def connect():
    if not config.SINGLESTORE_URL:
        raise RuntimeError("SINGLESTORE_URL is not set")
    return singlestoredb.connect(config.SINGLESTORE_URL, autocommit=True)


def shared():
    """One reused connection per thread. Opening a fresh one costs seconds on the shared tier."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _local.conn = connect()
    return conn


def reset_shared() -> None:
    conn = getattr(_local, "conn", None)
    _local.conn = None
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


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
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone()[0] == 1
    except Exception:
        return False
