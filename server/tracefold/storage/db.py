"""SQLite connection handling and schema migrations. Only storage code performs SQL."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

MIGRATIONS: list[str] = [
    # 1: core schema
    """
    CREATE TABLE workspaces (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        source_type TEXT NOT NULL,           -- local_dir | upload_only
        root TEXT,                           -- registered root (operator-provisioned only)
        excludes TEXT NOT NULL DEFAULT '[]',
        privacy_policy_version TEXT NOT NULL DEFAULT 'strict_private_v1',
        revision INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );
    CREATE TABLE clients (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        token_hash TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        revoked_at TEXT
    );
    CREATE TABLE grants (
        client_id TEXT NOT NULL REFERENCES clients(id),
        workspace_id TEXT NOT NULL REFERENCES workspaces(id),
        capabilities TEXT NOT NULL,
        disclosure TEXT NOT NULL,
        PRIMARY KEY (client_id, workspace_id)
    );
    CREATE TABLE manifests (
        id TEXT NOT NULL,
        workspace_id TEXT NOT NULL REFERENCES workspaces(id),
        version INTEGER NOT NULL,
        sources TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (workspace_id, id)
    );
    CREATE TABLE inputs (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        revision INTEGER NOT NULL,
        source TEXT NOT NULL,                -- upload | files | changes
        manifest_digest TEXT NOT NULL,
        files TEXT NOT NULL,                 -- metadata only: ids, paths, hashes, sizes, status
        baseline TEXT,
        parser_version TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    CREATE TABLE scans (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        input_id TEXT NOT NULL,
        revision INTEGER NOT NULL,
        checks TEXT NOT NULL,
        public_sources TEXT,
        public_snapshot_id TEXT,
        review_profile TEXT NOT NULL,
        model_review INTEGER NOT NULL,
        recheck_of TEXT,
        recheck_id TEXT,
        state TEXT NOT NULL,
        stages TEXT NOT NULL DEFAULT '[]',
        coverage TEXT NOT NULL DEFAULT '[]',
        budget TEXT NOT NULL DEFAULT '{}',
        versions TEXT NOT NULL DEFAULT '{}',
        errors TEXT NOT NULL DEFAULT '[]',
        summary TEXT NOT NULL DEFAULT '{}',
        cancel_requested INTEGER NOT NULL DEFAULT 0,
        initiator TEXT NOT NULL,
        idempotency_key TEXT,
        request_digest TEXT,
        created_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT,
        deadline_at TEXT
    );
    CREATE UNIQUE INDEX scans_idem ON scans(initiator, workspace_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
    CREATE INDEX scans_state ON scans(state, created_at);
    CREATE TABLE findings (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        check_id TEXT NOT NULL,
        rule_id TEXT,
        correlation_key TEXT NOT NULL,
        file_key TEXT NOT NULL,
        path TEXT,
        status TEXT NOT NULL,
        status_revision INTEGER NOT NULL,
        human_review TEXT NOT NULL DEFAULT 'unreviewed',
        human_review_reason TEXT,
        version INTEGER NOT NULL DEFAULT 1,
        first_seen_scan TEXT NOT NULL,
        last_seen_scan TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (workspace_id, correlation_key)
    );
    CREATE TABLE observations (
        id TEXT PRIMARY KEY,
        finding_id TEXT NOT NULL REFERENCES findings(id),
        scan_id TEXT NOT NULL,
        input_id TEXT NOT NULL,
        revision INTEGER NOT NULL,
        data TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE INDEX obs_scan ON observations(scan_id);
    CREATE INDEX obs_finding ON observations(finding_id, created_at);
    CREATE TABLE evidence (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        scan_id TEXT NOT NULL,
        input_id TEXT NOT NULL,
        data TEXT NOT NULL
    );
    CREATE TABLE rechecks (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        finding_id TEXT NOT NULL,
        observation_id TEXT NOT NULL,
        scan_id TEXT NOT NULL,
        outcome TEXT,
        reason TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE public_snapshots (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        manifest_id TEXT NOT NULL,
        manifest_version INTEGER NOT NULL,
        sources TEXT NOT NULL,               -- per-source url, status, hash, retrieved_at
        created_at TEXT NOT NULL
    );
    CREATE TABLE ledger (
        id TEXT PRIMARY KEY,
        workspace_id TEXT,
        scan_id TEXT,
        destination_category TEXT NOT NULL,
        destination_host TEXT NOT NULL,
        purpose TEXT NOT NULL,
        source_id TEXT,
        status TEXT NOT NULL,
        payload_summary TEXT NOT NULL,
        at TEXT NOT NULL
    );
    CREATE INDEX ledger_scan ON ledger(scan_id, at);
    CREATE TABLE runner_lock (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        owner TEXT NOT NULL,
        acquired_at TEXT NOT NULL
    );
    """,
    # 2: remediation (takedown requests, credential disabling) with human approval
    """
    CREATE TABLE remediation_profiles (
        workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id),
        company_name TEXT NOT NULL,
        reply_to TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE takedown_contacts (
        workspace_id TEXT NOT NULL REFERENCES workspaces(id),
        host TEXT NOT NULL,
        method TEXT NOT NULL,                -- email | form
        address TEXT NOT NULL,               -- abuse/legal email or form URL (operator-provided)
        updated_at TEXT NOT NULL,
        PRIMARY KEY (workspace_id, host)
    );
    CREATE TABLE actions (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        finding_id TEXT NOT NULL REFERENCES findings(id),
        kind TEXT NOT NULL,                  -- takedown_request | disable_aws_key
        status TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        target TEXT NOT NULL,                -- public URL/excerpt, or the AWS access key ID (an identifier, not the secret)
        draft TEXT NOT NULL DEFAULT '{}',
        approver TEXT,
        result TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        approved_at TEXT,
        executed_at TEXT,
        UNIQUE (finding_id, kind)
    );
    CREATE INDEX actions_ws ON actions(workspace_id, status, created_at);
    """,
    # 3: company-name discovery (approved public identity, immutable query plans, per-scan discovery runs)
    """
    CREATE TABLE company_profiles (
        id TEXT NOT NULL,
        workspace_id TEXT NOT NULL REFERENCES workspaces(id),
        version INTEGER NOT NULL,
        display_name TEXT NOT NULL,
        official_domain TEXT,
        public_aliases TEXT NOT NULL DEFAULT '[]',
        approved_by TEXT NOT NULL,
        approved_at TEXT NOT NULL,
        privacy_notice_version TEXT NOT NULL,
        PRIMARY KEY (id, version)
    );
    CREATE INDEX company_profiles_ws ON company_profiles(workspace_id, id, version);
    CREATE TABLE query_plans (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL REFERENCES workspaces(id),
        profile_id TEXT NOT NULL,
        profile_version INTEGER NOT NULL,
        profile TEXT NOT NULL,                -- immutable copy of the approved profile version
        plan TEXT NOT NULL,                   -- rendered searches, template version, scope, limits
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE INDEX query_plans_ws ON query_plans(workspace_id, created_at);
    CREATE TABLE discovery_runs (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        scan_id TEXT NOT NULL,
        query_plan_id TEXT NOT NULL,
        profile_version INTEGER NOT NULL,
        data TEXT NOT NULL,                   -- provider queries, errors, counts, candidates
        started_at TEXT NOT NULL,
        finished_at TEXT
    );
    CREATE UNIQUE INDEX discovery_runs_scan ON discovery_runs(scan_id);
    CREATE TABLE discovery_sources (
        run_id TEXT NOT NULL,
        scan_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL,
        source_id TEXT NOT NULL,
        data TEXT NOT NULL,
        PRIMARY KEY (run_id, ordinal)
    );
    CREATE INDEX discovery_sources_scan ON discovery_sources(scan_id, ordinal);
    ALTER TABLE scans ADD COLUMN public_discovery TEXT
    """,
    # 4: per-workspace site lists: pages checked in every public scan, hosts never fetched
    """
    CREATE TABLE site_rules (
        workspace_id TEXT NOT NULL REFERENCES workspaces(id),
        kind TEXT NOT NULL CHECK (kind IN ('always', 'never')),
        value TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (workspace_id, kind, value)
    )
    """,
    # 5: pages each document was compared against, so repeat scans can skip search and recheck known pages
    """
    CREATE TABLE page_memory (
        workspace_id TEXT NOT NULL REFERENCES workspaces(id),
        doc_key TEXT NOT NULL,
        url TEXT NOT NULL,
        provider TEXT,
        title TEXT,
        matched INTEGER NOT NULL DEFAULT 0,
        last_seen_at TEXT NOT NULL,
        PRIMARY KEY (workspace_id, doc_key, url)
    )
    """,
    # 6: the company's industry, which switches on industry-specific checks (financial, healthcare, ...)
    """
    ALTER TABLE workspaces ADD COLUMN industry TEXT
    """,
    # 7: optional scheduled checks (schedules). Off until someone adds one.
    """
    CREATE TABLE monitors (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL REFERENCES workspaces(id),
        client_id TEXT NOT NULL,
        name TEXT NOT NULL,
        source TEXT NOT NULL,                -- folder | files
        source_scan_id TEXT,                 -- files: the scan whose uploaded files are re-checked
        file_names TEXT NOT NULL DEFAULT '[]',
        every TEXT NOT NULL,                 -- hour | day | week
        public INTEGER NOT NULL DEFAULT 1,
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        next_run_at TEXT NOT NULL,
        last_run_at TEXT,
        last_scan_id TEXT,
        last_error TEXT,
        runs INTEGER NOT NULL DEFAULT 0
    )
    """,
    # 8: exact schedule intervals and a start time
    """
    ALTER TABLE monitors ADD COLUMN interval_seconds INTEGER;
    ALTER TABLE monitors ADD COLUMN start_at TEXT
    """,
]


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._local = threading.local()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = self._connect()
            self._local.conn = c
        return c

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """Short IMMEDIATE transaction; nested use joins the outer transaction."""
        c = self.conn()
        if c.in_transaction:
            yield c
            return
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise

    def migrate(self) -> int:
        c = self.conn()
        c.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)")
        applied = {r[0] for r in c.execute("SELECT version FROM schema_migrations")}
        for i, sql in enumerate(MIGRATIONS, start=1):
            if i in applied:
                continue
            with self.tx() as t:
                for stmt in [s for s in sql.split(";") if s.strip()]:
                    t.execute(stmt)
                t.execute("INSERT INTO schema_migrations(version) VALUES (?)", (i,))
        return len(MIGRATIONS)
