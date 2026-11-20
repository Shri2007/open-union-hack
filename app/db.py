"""SingleStore connection and tables. The log table is the public, append-only record."""
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


def create_tables() -> None:
    with connect() as conn, conn.cursor() as cur:
        for ddl in TABLES:
            cur.execute(ddl)


def ping() -> bool:
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone()[0] == 1
    except Exception:
        return False
