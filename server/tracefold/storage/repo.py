"""Repositories. All SQL in the engine lives in this module and db.py."""
from __future__ import annotations

import sqlite3
from typing import Any

from ..util import dumps, iso, loads, new_id, now
from .db import Database


def _row(r: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(r) if r is not None else None


JSON_COLS = {
    "excludes", "capabilities", "sources", "files", "checks", "public_sources", "stages",
    "coverage", "budget", "versions", "errors", "summary", "data", "payload_summary",
}


def _decode(d: dict[str, Any] | None) -> dict[str, Any] | None:
    if d is None:
        return None
    for k in list(d):
        if k in JSON_COLS and isinstance(d[k], str):
            d[k] = loads(d[k])
    return d


class Repo:
    def __init__(self, db: Database):
        self.db = db

    # ---------------- workspaces / clients / grants ----------------
    def create_workspace(self, ws_id: str, name: str, source_type: str, root: str | None, excludes: list[str]) -> None:
        with self.db.tx() as c:
            c.execute(
                "INSERT INTO workspaces(id,name,source_type,root,excludes,created_at) VALUES (?,?,?,?,?,?)",
                (ws_id, name, source_type, root, dumps(excludes), iso(now())),
            )

    def get_workspace(self, ws_id: str) -> dict | None:
        return _decode(_row(self.db.conn().execute("SELECT * FROM workspaces WHERE id=?", (ws_id,)).fetchone()))

    def bump_revision(self, ws_id: str) -> int:
        with self.db.tx() as c:
            c.execute("UPDATE workspaces SET revision = revision + 1 WHERE id=?", (ws_id,))
            return c.execute("SELECT revision FROM workspaces WHERE id=?", (ws_id,)).fetchone()[0]

    def create_client(self, name: str, token_hash: str) -> str:
        cid = new_id("cl")
        with self.db.tx() as c:
            c.execute("INSERT INTO clients(id,name,token_hash,created_at) VALUES (?,?,?,?)", (cid, name, token_hash, iso(now())))
        return cid

    def client_by_token_hash(self, token_hash: str) -> dict | None:
        return _row(self.db.conn().execute(
            "SELECT * FROM clients WHERE token_hash=? AND revoked_at IS NULL", (token_hash,)).fetchone())

    def client_by_name(self, name: str) -> dict | None:
        return _row(self.db.conn().execute("SELECT * FROM clients WHERE name=?", (name,)).fetchone())

    def revoke_client(self, client_id: str) -> None:
        with self.db.tx() as c:
            c.execute("UPDATE clients SET revoked_at=? WHERE id=?", (iso(now()), client_id))

    def put_grant(self, client_id: str, ws_id: str, capabilities: list[str], disclosure: str) -> None:
        with self.db.tx() as c:
            c.execute(
                "INSERT INTO grants(client_id,workspace_id,capabilities,disclosure) VALUES (?,?,?,?) "
                "ON CONFLICT(client_id,workspace_id) DO UPDATE SET capabilities=excluded.capabilities, disclosure=excluded.disclosure",
                (client_id, ws_id, dumps(sorted(capabilities)), disclosure),
            )

    def grants_for(self, client_id: str) -> list[dict]:
        rows = self.db.conn().execute("SELECT * FROM grants WHERE client_id=?", (client_id,)).fetchall()
        return [_decode(dict(r)) for r in rows]

    # ---------------- manifests ----------------
    def put_manifest(self, ws_id: str, manifest_id: str, sources: list[dict]) -> int:
        with self.db.tx() as c:
            r = c.execute("SELECT version FROM manifests WHERE workspace_id=? AND id=?", (ws_id, manifest_id)).fetchone()
            version = (r[0] + 1) if r else 1
            c.execute(
                "INSERT INTO manifests(id,workspace_id,version,sources,created_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(workspace_id,id) DO UPDATE SET version=excluded.version, sources=excluded.sources",
                (manifest_id, ws_id, version, dumps(sources), iso(now())),
            )
        return version

    def get_manifest(self, ws_id: str, manifest_id: str) -> dict | None:
        return _decode(_row(self.db.conn().execute(
            "SELECT * FROM manifests WHERE workspace_id=? AND id=?", (ws_id, manifest_id)).fetchone()))

    def list_manifests(self, ws_id: str) -> list[str]:
        return [r[0] for r in self.db.conn().execute("SELECT id FROM manifests WHERE workspace_id=? ORDER BY id", (ws_id,))]

    # ---------------- inputs ----------------
    def insert_input(self, rec: dict) -> None:
        with self.db.tx() as c:
            c.execute(
                "INSERT INTO inputs(id,workspace_id,revision,source,manifest_digest,files,baseline,parser_version,created_by,created_at,expires_at)"
                " VALUES (:id,:workspace_id,:revision,:source,:manifest_digest,:files,:baseline,:parser_version,:created_by,:created_at,:expires_at)",
                {**rec, "files": dumps(rec["files"])},
            )

    def get_input(self, input_id: str) -> dict | None:
        return _decode(_row(self.db.conn().execute("SELECT * FROM inputs WHERE id=?", (input_id,)).fetchone()))

    # ---------------- scans ----------------
    def insert_scan(self, rec: dict) -> None:
        cols = list(rec)
        vals = [dumps(rec[k]) if k in JSON_COLS and not isinstance(rec[k], (str, type(None))) else rec[k] for k in cols]
        with self.db.tx() as c:
            c.execute(f"INSERT INTO scans({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)

    def get_scan(self, scan_id: str) -> dict | None:
        return _decode(_row(self.db.conn().execute("SELECT * FROM scans WHERE id=?", (scan_id,)).fetchone()))

    def find_idempotent(self, initiator: str, ws_id: str, key: str) -> dict | None:
        return _decode(_row(self.db.conn().execute(
            "SELECT * FROM scans WHERE initiator=? AND workspace_id=? AND idempotency_key=?", (initiator, ws_id, key)).fetchone()))

    def count_queued(self) -> int:
        return self.db.conn().execute("SELECT COUNT(*) FROM scans WHERE state='queued'").fetchone()[0]

    def update_scan(self, scan_id: str, **fields) -> None:
        sets, vals = [], []
        for k, v in fields.items():
            sets.append(f"{k}=?")
            vals.append(dumps(v) if k in JSON_COLS and not isinstance(v, (str, type(None))) else v)
        vals.append(scan_id)
        with self.db.tx() as c:
            c.execute(f"UPDATE scans SET {','.join(sets)} WHERE id=?", vals)

    def claim_next_scan(self) -> dict | None:
        """Atomically move the oldest queued scan to running."""
        with self.db.tx() as c:
            r = c.execute("SELECT id FROM scans WHERE state='queued' ORDER BY created_at, rowid LIMIT 1").fetchone()
            if not r:
                return None
            n = c.execute("UPDATE scans SET state='running', started_at=? WHERE id=? AND state='queued'", (iso(now()), r[0])).rowcount
            if n != 1:
                return None
        return self.get_scan(r[0])

    def request_cancel(self, scan_id: str) -> str:
        """Returns the resulting state. Queued scans cancel immediately; running scans cooperatively."""
        with self.db.tx() as c:
            st = c.execute("SELECT state FROM scans WHERE id=?", (scan_id,)).fetchone()[0]
            if st == "queued":
                c.execute("UPDATE scans SET state='cancelled', cancel_requested=1, finished_at=? WHERE id=?", (iso(now()), scan_id))
                return "cancelled"
            if st == "running":
                c.execute("UPDATE scans SET cancel_requested=1 WHERE id=?", (scan_id,))
            return st

    def cancel_requested(self, scan_id: str) -> bool:
        return bool(self.db.conn().execute("SELECT cancel_requested FROM scans WHERE id=?", (scan_id,)).fetchone()[0])

    def mark_running_interrupted(self) -> int:
        with self.db.tx() as c:
            return c.execute(
                "UPDATE scans SET state='interrupted', finished_at=?, errors=? WHERE state='running'",
                (iso(now()), dumps([{"code": "interrupted", "message": "The engine restarted while this scan was running.", "retryable": True}])),
            ).rowcount

    def queued_scans(self) -> list[dict]:
        return [_decode(dict(r)) for r in self.db.conn().execute("SELECT * FROM scans WHERE state='queued' ORDER BY created_at")]

    def active_input_ids(self) -> set[str]:
        return {r[0] for r in self.db.conn().execute("SELECT input_id FROM scans WHERE state IN ('queued','running')")}

    def scans_for_input(self, input_id: str) -> list[dict]:
        return [_decode(dict(r)) for r in self.db.conn().execute("SELECT * FROM scans WHERE input_id=?", (input_id,))]

    # ---------------- runner lock ----------------
    def acquire_runner(self, owner: str) -> bool:
        with self.db.tx() as c:
            r = c.execute("SELECT owner FROM runner_lock WHERE id=1").fetchone()
            if r and r[0] != owner:
                return False
            c.execute("INSERT OR REPLACE INTO runner_lock(id,owner,acquired_at) VALUES (1,?,?)", (owner, iso(now())))
            return True

    def release_runner(self, owner: str) -> None:
        with self.db.tx() as c:
            c.execute("DELETE FROM runner_lock WHERE id=1 AND owner=?", (owner,))

    def force_release_runner(self) -> None:
        with self.db.tx() as c:
            c.execute("DELETE FROM runner_lock")

    # ---------------- findings / observations / evidence ----------------
    def get_finding_by_key(self, ws_id: str, key: str) -> dict | None:
        return _row(self.db.conn().execute(
            "SELECT * FROM findings WHERE workspace_id=? AND correlation_key=?", (ws_id, key)).fetchone())

    def get_finding(self, finding_id: str) -> dict | None:
        return _row(self.db.conn().execute("SELECT * FROM findings WHERE id=?", (finding_id,)).fetchone())

    def insert_finding(self, rec: dict) -> None:
        cols = list(rec)
        with self.db.tx() as c:
            c.execute(f"INSERT INTO findings({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", [rec[k] for k in cols])

    def update_finding(self, finding_id: str, **fields) -> None:
        sets = ",".join(f"{k}=?" for k in fields)
        with self.db.tx() as c:
            c.execute(f"UPDATE findings SET {sets} WHERE id=?", [*fields.values(), finding_id])

    def update_finding_review(self, finding_id: str, state: str, reason: str | None, expected_version: int) -> bool:
        with self.db.tx() as c:
            n = c.execute(
                "UPDATE findings SET human_review=?, human_review_reason=?, version=version+1, updated_at=? WHERE id=? AND version=?",
                (state, reason, iso(now()), finding_id, expected_version),
            ).rowcount
        return n == 1

    def list_findings(self, ws_id: str, scan_id: str | None, after: str | None, limit: int) -> list[dict]:
        q = "SELECT f.* FROM findings f WHERE f.workspace_id=?"
        args: list[Any] = [ws_id]
        if scan_id:
            q += " AND EXISTS (SELECT 1 FROM observations o WHERE o.finding_id=f.id AND o.scan_id=?)"
            args.append(scan_id)
        if after:
            q += " AND f.id > ?"
            args.append(after)
        q += " ORDER BY f.id LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.db.conn().execute(q, args)]

    def open_findings(self, ws_id: str, kind: str | None = None) -> list[dict]:
        q = "SELECT * FROM findings WHERE workspace_id=? AND status='open'"
        args: list[Any] = [ws_id]
        if kind:
            q += " AND kind=?"
            args.append(kind)
        return [dict(r) for r in self.db.conn().execute(q, args)]

    def insert_observation(self, rec: dict) -> None:
        with self.db.tx() as c:
            c.execute(
                "INSERT INTO observations(id,finding_id,scan_id,input_id,revision,data,created_at) VALUES (?,?,?,?,?,?,?)",
                (rec["id"], rec["finding_id"], rec["scan_id"], rec["input_id"], rec["revision"], dumps(rec["data"]), rec["created_at"]),
            )

    def observations_for_finding(self, finding_id: str, scan_id: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM observations WHERE finding_id=?", [finding_id]
        if scan_id:
            q += " AND scan_id=?"
            args.append(scan_id)
        q += " ORDER BY created_at, rowid"
        return [_decode(dict(r)) for r in self.db.conn().execute(q, args)]

    def get_observation(self, obs_id: str) -> dict | None:
        return _decode(_row(self.db.conn().execute("SELECT * FROM observations WHERE id=?", (obs_id,)).fetchone()))

    def insert_evidence(self, rec: dict) -> None:
        with self.db.tx() as c:
            c.execute(
                "INSERT INTO evidence(id,workspace_id,scan_id,input_id,data) VALUES (?,?,?,?,?)",
                (rec["id"], rec["workspace_id"], rec["scan_id"], rec["input_id"], dumps(rec["data"])),
            )

    def get_evidence(self, ev_id: str) -> dict | None:
        return _decode(_row(self.db.conn().execute("SELECT * FROM evidence WHERE id=?", (ev_id,)).fetchone()))

    # ---------------- rechecks ----------------
    def insert_recheck(self, rec: dict) -> None:
        cols = list(rec)
        with self.db.tx() as c:
            c.execute(f"INSERT INTO rechecks({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", [rec[k] for k in cols])

    def update_recheck(self, recheck_id: str, outcome: str, reason: str | None) -> None:
        with self.db.tx() as c:
            c.execute("UPDATE rechecks SET outcome=?, reason=? WHERE id=?", (outcome, reason, recheck_id))

    def rechecks_for_finding(self, finding_id: str) -> list[dict]:
        return [dict(r) for r in self.db.conn().execute(
            "SELECT * FROM rechecks WHERE finding_id=? ORDER BY created_at, rowid", (finding_id,))]

    def get_recheck(self, recheck_id: str) -> dict | None:
        return _row(self.db.conn().execute("SELECT * FROM rechecks WHERE id=?", (recheck_id,)).fetchone())

    # ---------------- public snapshots ----------------
    def insert_snapshot(self, rec: dict) -> None:
        with self.db.tx() as c:
            c.execute(
                "INSERT INTO public_snapshots(id,workspace_id,manifest_id,manifest_version,sources,created_at) VALUES (?,?,?,?,?,?)",
                (rec["id"], rec["workspace_id"], rec["manifest_id"], rec["manifest_version"], dumps(rec["sources"]), rec["created_at"]),
            )

    def get_snapshot(self, snap_id: str) -> dict | None:
        return _decode(_row(self.db.conn().execute("SELECT * FROM public_snapshots WHERE id=?", (snap_id,)).fetchone()))

    def referenced_blob_hashes(self) -> set[str]:
        out: set[str] = set()
        for (s,) in self.db.conn().execute("SELECT sources FROM public_snapshots"):
            for src in loads(s, []):
                if src.get("content_hash"):
                    out.add(src["content_hash"])
        return out

    # ---------------- ledger ----------------
    def insert_ledger(self, events: list[dict]) -> None:
        if not events:
            return
        with self.db.tx() as c:
            for e in events:
                c.execute(
                    "INSERT INTO ledger(id,workspace_id,scan_id,destination_category,destination_host,purpose,source_id,status,payload_summary,at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (e.get("id") or new_id("ev"), e.get("workspace_id"), e.get("scan_id"), e["destination_category"],
                     e["destination_host"], e["purpose"], e.get("source_id"), e["status"], dumps(e.get("payload_summary", {})), e["at"]),
                )

    def ledger_for_scan(self, scan_id: str, after: str | None, limit: int) -> list[dict]:
        q, args = "SELECT * FROM ledger WHERE scan_id=?", [scan_id]
        if after:
            q += " AND id > ?"
            args.append(after)
        q += " ORDER BY id LIMIT ?"
        args.append(limit)
        return [_decode(dict(r)) for r in self.db.conn().execute(q, args)]

    def all_ledger(self) -> list[dict]:
        return [_decode(dict(r)) for r in self.db.conn().execute("SELECT * FROM ledger ORDER BY at")]

    # ---------------- retention ----------------
    def prune_scans(self, keep: int, older_than_iso: str) -> int:
        with self.db.tx() as c:
            ids = [r[0] for r in c.execute(
                "SELECT id FROM scans WHERE state NOT IN ('queued','running') AND "
                "(id NOT IN (SELECT id FROM scans ORDER BY created_at DESC LIMIT ?) OR created_at < ?) "
                "AND NOT EXISTS (SELECT 1 FROM observations o WHERE o.scan_id=scans.id) "
                "AND NOT EXISTS (SELECT 1 FROM rechecks r WHERE r.scan_id=scans.id)", (keep, older_than_iso))]
            for sid in ids:
                c.execute("DELETE FROM ledger WHERE scan_id=?", (sid,))
                c.execute("DELETE FROM scans WHERE id=?", (sid,))
            return len(ids)
