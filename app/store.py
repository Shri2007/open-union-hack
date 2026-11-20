"""All SingleStore reads and writes. Other modules use `store` (swappable with a fake in tests)."""
import json
import uuid
from datetime import datetime, timezone

from app import db


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _row(r) -> dict:
    body = r[4]
    if isinstance(body, (str, bytes)):
        body = json.loads(body)
    return {"id": r[0], "coalition_id": r[1], "agent_id": r[2], "type": r[3], "body": body,
            "ts": r[5].isoformat() + "Z"}


class Store:
    def _q(self, sql: str, args=(), fetch: str | None = None):
        for attempt in (1, 2):  # retry once on a dropped connection
            try:
                with db.shared().cursor() as cur:
                    cur.execute(sql, args)
                    if fetch == "one":
                        return cur.fetchone()
                    if fetch == "all":
                        return cur.fetchall()
                    return None
            except Exception:
                db.reset_shared()
                if attempt == 2:
                    raise

    # coalitions
    def get_coalition(self, cid: str) -> dict | None:
        r = self._q("SELECT id, need, state FROM coalitions WHERE id=%s", (cid,), "one")
        return {"id": r[0], "need": r[1], "state": r[2]} if r else None

    def list_coalitions(self, limit: int = 5) -> list[dict]:
        rows = self._q("SELECT id, need, state FROM coalitions ORDER BY created_at DESC LIMIT %s", (limit,), "all")
        return [{"id": r[0], "need": r[1], "state": r[2]} for r in rows]

    def create_coalition(self, need: str, cid: str | None = None) -> str:
        cid = cid or str(uuid.uuid4())
        self._q("INSERT IGNORE INTO coalitions (id, need, state, created_at) VALUES (%s, %s, 'open', %s)",
                (cid, need, _now()))
        return cid

    def set_state(self, cid: str, state: str) -> None:
        self._q("UPDATE coalitions SET state=%s WHERE id=%s", (state, cid))

    # members
    def upsert_member(self, cid: str, agent_id: str, client: str, verified: bool) -> None:
        self._q("INSERT INTO members (coalition_id, agent_id, client, verified, removed_reason, joined_at) "
                "VALUES (%s, %s, %s, %s, NULL, %s) "
                "ON DUPLICATE KEY UPDATE client=VALUES(client), verified=VALUES(verified), removed_reason=NULL",
                (cid, agent_id, client, verified, _now()))

    def get_member(self, cid: str, agent_id: str) -> dict | None:
        r = self._q("SELECT agent_id, client, verified, removed_reason FROM members "
                    "WHERE coalition_id=%s AND agent_id=%s", (cid, agent_id), "one")
        return {"agent_id": r[0], "client": r[1], "verified": bool(r[2]), "removed_reason": r[3]} if r else None

    def set_verified(self, cid: str, agent_id: str, verified: bool) -> None:
        self._q("UPDATE members SET verified=%s WHERE coalition_id=%s AND agent_id=%s", (verified, cid, agent_id))

    def remove_member(self, cid: str, agent_id: str, reason: str) -> None:
        self._q("UPDATE members SET removed_reason=%s WHERE coalition_id=%s AND agent_id=%s", (reason, cid, agent_id))

    def counts(self, cid: str) -> dict:
        r = self._q(
            "SELECT "
            " SUM(removed_reason IS NULL AND verified), "
            " SUM(removed_reason IS NULL AND NOT verified), "
            " SUM(removed_reason IS NOT NULL), "
            " SUM(removed_reason IS NULL AND client IN ('web','mcp')), "
            " SUM(removed_reason IS NULL AND client NOT IN ('web','mcp')) "
            "FROM members WHERE coalition_id=%s", (cid,), "one")
        keys = ["verified", "unverified", "removed", "real", "simulated"]
        return {k: int(v or 0) for k, v in zip(keys, r or [0] * 5)}

    # log
    def append(self, cid: str, agent_id: str, msg_type: str, body: dict) -> dict:
        row_id, ts = str(uuid.uuid4()), _now()
        self._q("INSERT INTO log (id, coalition_id, agent_id, type, body, ts) VALUES (%s, %s, %s, %s, %s, %s)",
                (row_id, cid, agent_id, msg_type, json.dumps(body), ts))
        return {"id": row_id, "coalition_id": cid, "agent_id": agent_id, "type": msg_type, "body": body,
                "ts": ts.isoformat() + "Z"}

    def log(self, cid: str) -> list[dict]:
        rows = self._q("SELECT id, coalition_id, agent_id, type, body, ts FROM log "
                       "WHERE coalition_id=%s ORDER BY ts, id", (cid,), "all")
        return [_row(r) for r in rows]

    def find_commit(self, cid: str, agent_id: str) -> str | None:
        r = self._q("SELECT body FROM log WHERE coalition_id=%s AND agent_id=%s AND type='COMMIT' "
                    "ORDER BY ts LIMIT 1", (cid, agent_id), "one")
        if not r:
            return None
        body = json.loads(r[0]) if isinstance(r[0], (str, bytes)) else r[0]
        return body["commitment"]

    def get_log_row(self, cid: str, row_id: str) -> dict | None:
        r = self._q("SELECT id, coalition_id, agent_id, type, body, ts FROM log WHERE coalition_id=%s AND id=%s",
                    (cid, row_id), "one")
        return _row(r) if r else None


store = Store()
