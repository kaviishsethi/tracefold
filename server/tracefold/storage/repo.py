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
    "target", "draft", "approver", "result",
    "public_discovery", "public_aliases", "profile", "plan", "file_names",
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

    def clients_with_prefix(self, prefix: str) -> list[dict]:
        rows = self.db.conn().execute("SELECT * FROM clients WHERE substr(name, 1, ?) = ?", (len(prefix), prefix))
        return [dict(r) for r in rows]

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

    def list_scans(self, ws_id: str, before: str | None, limit: int) -> list[dict]:
        q, args = "SELECT * FROM scans WHERE workspace_id=?", [ws_id]
        if before:
            q += " AND created_at < ?"
            args.append(before)
        q += " ORDER BY created_at DESC, id DESC LIMIT ?"
        args.append(limit)
        return [_decode(dict(r)) for r in self.db.conn().execute(q, args)]

    def get_client(self, client_id: str) -> dict | None:
        return _row(self.db.conn().execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone())

    def delete_scans(self, ws_id: str, scan_ids: list[str]) -> dict[str, int]:
        """Delete finished scans and everything only they produced. Findings still seen by another scan stay;
        findings left with no observation go, with their rechecks and actions."""
        if not scan_ids:
            return {"scans": 0, "findings": 0}
        with self.db.tx() as c:
            q = ",".join("?" * len(scan_ids))
            ids = [r[0] for r in c.execute(f"SELECT id FROM scans WHERE workspace_id=? AND id IN ({q})", (ws_id, *scan_ids))]
            if not ids:
                return {"scans": 0, "findings": 0}
            q = ",".join("?" * len(ids))
            touched = [r[0] for r in c.execute(f"SELECT DISTINCT finding_id FROM observations WHERE scan_id IN ({q})", ids)]
            snaps = [r[0] for r in c.execute(f"SELECT DISTINCT public_snapshot_id FROM scans WHERE id IN ({q}) AND public_snapshot_id IS NOT NULL", ids)]
            inputs = [r[0] for r in c.execute(f"SELECT DISTINCT input_id FROM scans WHERE id IN ({q})", ids)]
            runs = [r[0] for r in c.execute(f"SELECT id FROM discovery_runs WHERE scan_id IN ({q})", ids)]
            for table in ("observations", "evidence", "rechecks", "ledger", "discovery_sources"):
                c.execute(f"DELETE FROM {table} WHERE scan_id IN ({q})", ids)
            if runs:
                c.execute(f"DELETE FROM discovery_runs WHERE id IN ({','.join('?' * len(runs))})", runs)
            c.execute(f"DELETE FROM scans WHERE id IN ({q})", ids)
            orphans = [f for f in touched if c.execute("SELECT 1 FROM observations WHERE finding_id=? LIMIT 1", (f,)).fetchone() is None]
            for f in orphans:
                c.execute("DELETE FROM actions WHERE finding_id=?", (f,))
                c.execute("DELETE FROM rechecks WHERE finding_id=?", (f,))
                c.execute("DELETE FROM findings WHERE id=?", (f,))
            for s in snaps:
                if c.execute("SELECT 1 FROM scans WHERE public_snapshot_id=? LIMIT 1", (s,)).fetchone() is None:
                    c.execute("DELETE FROM public_snapshots WHERE id=? AND manifest_id LIKE 'discovery:%'", (s,))
            for i in inputs:
                if c.execute("SELECT 1 FROM scans WHERE input_id=? LIMIT 1", (i,)).fetchone() is None:
                    c.execute("DELETE FROM inputs WHERE id=?", (i,))
            return {"scans": len(ids), "findings": len(orphans)}

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

    # ---------------- company discovery ----------------
    def insert_profile_version(self, rec: dict) -> int:
        """Create a profile (version 1) or a new immutable version of an existing one."""
        with self.db.tx() as c:
            r = c.execute("SELECT MAX(version) FROM company_profiles WHERE id=? AND workspace_id=?",
                          (rec["id"], rec["workspace_id"])).fetchone()
            version = (r[0] or 0) + 1
            c.execute(
                "INSERT INTO company_profiles(id,workspace_id,version,display_name,official_domain,public_aliases,approved_by,"
                "approved_at,privacy_notice_version) VALUES (?,?,?,?,?,?,?,?,?)",
                (rec["id"], rec["workspace_id"], version, rec["display_name"], rec["official_domain"],
                 dumps(rec["public_aliases"]), rec["approved_by"], rec["approved_at"], rec["privacy_notice_version"]))
        return version

    def get_profile(self, ws_id: str, profile_id: str, version: int | None = None) -> dict | None:
        q = "SELECT * FROM company_profiles WHERE workspace_id=? AND id=?"
        args: list[Any] = [ws_id, profile_id]
        if version is not None:
            q += " AND version=?"
            args.append(version)
        q += " ORDER BY version DESC LIMIT 1"
        return _decode(_row(self.db.conn().execute(q, args).fetchone()))

    def list_profiles(self, ws_id: str) -> list[dict]:
        """Latest version of each approved profile in a workspace."""
        rows = self.db.conn().execute(
            "SELECT p.* FROM company_profiles p WHERE p.workspace_id=? AND p.version = "
            "(SELECT MAX(version) FROM company_profiles q WHERE q.id=p.id AND q.workspace_id=p.workspace_id) "
            "ORDER BY p.approved_at DESC", (ws_id,)).fetchall()
        return [_decode(dict(r)) for r in rows]

    def profile_exists(self, profile_id: str) -> bool:
        return self.db.conn().execute("SELECT 1 FROM company_profiles WHERE id=?", (profile_id,)).fetchone() is not None

    def insert_query_plan(self, rec: dict) -> None:
        with self.db.tx() as c:
            c.execute("INSERT INTO query_plans(id,workspace_id,profile_id,profile_version,profile,plan,created_by,created_at)"
                      " VALUES (?,?,?,?,?,?,?,?)",
                      (rec["id"], rec["workspace_id"], rec["profile_id"], rec["profile_version"], dumps(rec["profile"]),
                       dumps(rec["plan"]), rec["created_by"], rec["created_at"]))

    def get_query_plan(self, plan_id: str) -> dict | None:
        return _decode(_row(self.db.conn().execute("SELECT * FROM query_plans WHERE id=?", (plan_id,)).fetchone()))

    def list_query_plans(self, ws_id: str, after: str | None, limit: int) -> list[dict]:
        q, args = "SELECT * FROM query_plans WHERE workspace_id=?", [ws_id]
        if after:
            q += " AND id > ?"
            args.append(after)
        q += " ORDER BY id LIMIT ?"
        args.append(limit)
        return [_decode(dict(r)) for r in self.db.conn().execute(q, args)]

    def upsert_discovery_run(self, rec: dict) -> None:
        with self.db.tx() as c:
            c.execute(
                "INSERT INTO discovery_runs(id,workspace_id,scan_id,query_plan_id,profile_version,data,started_at,finished_at)"
                " VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data, finished_at=excluded.finished_at",
                (rec["id"], rec["workspace_id"], rec["scan_id"], rec["query_plan_id"], rec["profile_version"],
                 dumps(rec["data"]), rec["started_at"], rec.get("finished_at")))

    def discovery_run_for_scan(self, scan_id: str) -> dict | None:
        return _decode(_row(self.db.conn().execute("SELECT * FROM discovery_runs WHERE scan_id=?", (scan_id,)).fetchone()))

    def replace_discovery_sources(self, run_id: str, scan_id: str, sources: list[dict]) -> None:
        with self.db.tx() as c:
            c.execute("DELETE FROM discovery_sources WHERE run_id=?", (run_id,))
            for i, s in enumerate(sources):
                c.execute("INSERT INTO discovery_sources(run_id,scan_id,ordinal,source_id,data) VALUES (?,?,?,?,?)",
                          (run_id, scan_id, i, s["source_id"], dumps(s)))

    def discovery_sources(self, scan_id: str, after: int, limit: int) -> list[tuple[int, dict]]:
        rows = self.db.conn().execute(
            "SELECT ordinal, data FROM discovery_sources WHERE scan_id=? AND ordinal > ? ORDER BY ordinal LIMIT ?",
            (scan_id, after, limit)).fetchall()
        return [(r[0], loads(r[1])) for r in rows]

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

    # ---------------- remediation ----------------
    def put_remediation_profile(self, ws_id: str, company_name: str, reply_to: str) -> None:
        with self.db.tx() as c:
            c.execute("INSERT INTO remediation_profiles(workspace_id,company_name,reply_to,updated_at) VALUES (?,?,?,?) "
                      "ON CONFLICT(workspace_id) DO UPDATE SET company_name=excluded.company_name, "
                      "reply_to=excluded.reply_to, updated_at=excluded.updated_at", (ws_id, company_name, reply_to, iso(now())))

    def get_site_rules(self, ws_id: str) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {"always": [], "never": []}
        for r in self.db.conn().execute("SELECT kind, value FROM site_rules WHERE workspace_id=? ORDER BY created_at, value", (ws_id,)):
            out[r["kind"]].append(r["value"])
        return out

    def put_site_rules(self, ws_id: str, always: list[str], never: list[str]) -> None:
        with self.db.tx() as c:
            c.execute("DELETE FROM site_rules WHERE workspace_id=?", (ws_id,))
            ts = iso(now())
            c.executemany("INSERT INTO site_rules(workspace_id,kind,value,created_at) VALUES (?,?,?,?)",
                          [(ws_id, "always", v, ts) for v in always] + [(ws_id, "never", v, ts) for v in never])

    def set_industry(self, ws_id: str, industry: str | None) -> None:
        with self.db.tx() as c:
            c.execute("UPDATE workspaces SET industry=? WHERE id=?", (industry, ws_id))

    def remember_pages(self, ws_id: str, doc_key: str, rows: list[dict]) -> None:
        ts = iso(now())
        with self.db.tx() as c:
            c.executemany(
                "INSERT INTO page_memory(workspace_id,doc_key,url,provider,title,matched,last_seen_at) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(workspace_id,doc_key,url) DO UPDATE SET provider=excluded.provider, title=excluded.title, "
                "matched=excluded.matched, last_seen_at=excluded.last_seen_at",
                [(ws_id, doc_key, r["url"], r.get("provider"), r.get("title"), int(bool(r.get("matched"))), ts) for r in rows])

    def recall_pages(self, ws_id: str, doc_key: str) -> list[dict]:
        return [dict(r) for r in self.db.conn().execute(
            "SELECT url, provider, title, matched, last_seen_at FROM page_memory WHERE workspace_id=? AND doc_key=? "
            "ORDER BY matched DESC, last_seen_at DESC", (ws_id, doc_key))]

    def forget_pages(self, ws_id: str) -> None:
        with self.db.tx() as c:
            c.execute("DELETE FROM page_memory WHERE workspace_id=?", (ws_id,))

    def get_remediation_profile(self, ws_id: str) -> dict | None:
        return _row(self.db.conn().execute("SELECT * FROM remediation_profiles WHERE workspace_id=?", (ws_id,)).fetchone())

    def put_takedown_contact(self, ws_id: str, host: str, method: str, address: str) -> None:
        with self.db.tx() as c:
            c.execute("INSERT INTO takedown_contacts(workspace_id,host,method,address,updated_at) VALUES (?,?,?,?,?) "
                      "ON CONFLICT(workspace_id,host) DO UPDATE SET method=excluded.method, address=excluded.address, "
                      "updated_at=excluded.updated_at", (ws_id, host, method, address, iso(now())))

    def get_takedown_contact(self, ws_id: str, host: str) -> dict | None:
        return _row(self.db.conn().execute("SELECT * FROM takedown_contacts WHERE workspace_id=? AND host=?",
                                           (ws_id, host)).fetchone())

    def insert_action_if_absent(self, rec: dict) -> bool:
        cols = list(rec)
        vals = [dumps(rec[k]) if k in JSON_COLS and not isinstance(rec[k], str) else rec[k] for k in cols]
        with self.db.tx() as c:
            cur = c.execute(f"INSERT OR IGNORE INTO actions({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
            return cur.rowcount == 1

    def get_action(self, action_id: str) -> dict | None:
        return _decode(_row(self.db.conn().execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()))

    def list_actions(self, ws_id: str, status: str | None, finding_id: str | None, after: str | None, limit: int) -> list[dict]:
        q, args = "SELECT * FROM actions WHERE workspace_id=?", [ws_id]
        if status:
            q += " AND status=?"
            args.append(status)
        if finding_id:
            q += " AND finding_id=?"
            args.append(finding_id)
        if after:
            q += " AND id > ?"
            args.append(after)
        q += " ORDER BY id LIMIT ?"
        args.append(limit)
        return [_decode(dict(r)) for r in self.db.conn().execute(q, args)]

    def update_action(self, action_id: str, expected_version: int, **fields) -> bool:
        """Version-guarded update; bumps the version. Returns False if someone else changed the action first."""
        fields["updated_at"] = iso(now())
        sets = ", ".join(f"{k}=?" for k in fields)
        vals = [dumps(v) if k in JSON_COLS and not isinstance(v, str) else v for k, v in fields.items()]
        with self.db.tx() as c:
            cur = c.execute(f"UPDATE actions SET {sets}, version = version + 1 WHERE id=? AND version=?",
                            (*vals, action_id, expected_version))
            return cur.rowcount == 1

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
                c.execute("DELETE FROM discovery_sources WHERE scan_id=?", (sid,))
                c.execute("DELETE FROM discovery_runs WHERE scan_id=?", (sid,))
                c.execute("DELETE FROM scans WHERE id=?", (sid,))
            return len(ids)

    # ---------------- monitors (optional scheduled checks) ----------------
    def insert_monitor(self, m: dict) -> None:
        cols = list(m)
        vals = [dumps(v) if k in JSON_COLS and not isinstance(v, str) else v for k, v in m.items()]
        with self.db.tx() as c:
            c.execute(f"INSERT INTO monitors({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)

    def get_monitor(self, monitor_id: str) -> dict | None:
        return _decode(_row(self.db.conn().execute("SELECT * FROM monitors WHERE id=?", (monitor_id,)).fetchone()))

    def list_monitors(self, ws_id: str) -> list[dict]:
        return [_decode(dict(r)) for r in self.db.conn().execute(
            "SELECT * FROM monitors WHERE workspace_id=? ORDER BY created_at DESC", (ws_id,))]

    def due_monitors(self, at_iso: str) -> list[dict]:
        return [_decode(dict(r)) for r in self.db.conn().execute(
            "SELECT * FROM monitors WHERE enabled=1 AND next_run_at <= ? ORDER BY next_run_at", (at_iso,))]

    def update_monitor(self, monitor_id: str, **fields) -> None:
        sets = ", ".join(f"{k}=?" for k in fields)
        vals = [dumps(v) if k in JSON_COLS and not isinstance(v, str) else v for k, v in fields.items()]
        with self.db.tx() as c:
            c.execute(f"UPDATE monitors SET {sets} WHERE id=?", (*vals, monitor_id))

    def delete_monitor(self, monitor_id: str) -> None:
        with self.db.tx() as c:
            c.execute("DELETE FROM monitors WHERE id=?", (monitor_id,))
