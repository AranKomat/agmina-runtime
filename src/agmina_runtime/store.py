"""Single-coordinator SQLite journal and estimated-spend admission ledger.

Source payloads/results are sensitive durable data. Operational events contain
IDs/counts/hashes only. A crash never causes automatic inference replay.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from .contracts import Job, JobState, Receipt, Session, Usage, canonical


class Store:
    def __init__(self, path: str | Path, *, campaign: str, max_attempts: int, max_microusd: int):
        import fcntl
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = open(str(self.path) + ".lock", "a+", encoding="utf8")
        try:
            fcntl.flock(self._lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._lock.close()
            raise RuntimeError("This database already has a coordinator") from None
        self.db = sqlite3.connect(str(self.path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (tenant TEXT, id TEXT, body TEXT NOT NULL,
                                             PRIMARY KEY(tenant,id));
        CREATE TABLE IF NOT EXISTS jobs (tenant TEXT, id TEXT, body TEXT NOT NULL, receipt TEXT NOT NULL,
                                         state TEXT NOT NULL, PRIMARY KEY(tenant,id));
        CREATE TABLE IF NOT EXISTS observations (tenant TEXT, session TEXT, id TEXT, body TEXT NOT NULL,
                                                 PRIMARY KEY(tenant,session,id));
        CREATE TABLE IF NOT EXISTS attempts (tenant TEXT, job TEXT, pool TEXT, endpoint TEXT,
            quote INTEGER NOT NULL, actual INTEGER, disposition TEXT NOT NULL,
            PRIMARY KEY(tenant,job));
        CREATE TABLE IF NOT EXISTS quarantines (pool TEXT PRIMARY KEY, reason TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, at_ns INTEGER NOT NULL,
                                           kind TEXT NOT NULL, metadata TEXT NOT NULL);
        """)
        cfg = {"campaign": campaign, "max_attempts": max_attempts, "max_microusd": max_microusd}
        old = self.db.execute("SELECT value FROM meta WHERE key='budget'").fetchone()
        if old and json.loads(old[0]) != cfg:
            self.close()
            raise ValueError("Campaign/caps changed: use explicit offline budget extension, never reset holds")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO meta VALUES ('budget',?)", (canonical(cfg),))
        os.chmod(self.path, 0o600)

    def close(self):
        if getattr(self, "db", None) is not None:
            self.db.close()
            self.db = None
        if getattr(self, "_lock", None) is not None:
            self._lock.close()
            self._lock = None

    def bind_tenant(self, tenant: str):
        row = self.db.execute("SELECT value FROM meta WHERE key='tenant'").fetchone()
        if row and row[0] != tenant:
            raise PermissionError("A ledger belongs to one immutable tenant")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO meta VALUES ('tenant',?)", (tenant,))

    def event(self, at_ns: int, kind: str, **metadata):
        with self.db:
            self.db.execute("INSERT INTO events(at_ns,kind,metadata) VALUES (?,?,?)",
                            (at_ns, kind, canonical(metadata)))

    def session(self, tenant, sid) -> Session:
        row = self.db.execute("SELECT body FROM sessions WHERE tenant=? AND id=?", (tenant, sid)).fetchone()
        if row is None:
            raise KeyError("Unknown session")
        return Session.model_validate_json(row[0])

    def put_session(self, session: Session):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?)",
                            (session.tenant, session.id, canonical(session)))

    def job(self, tenant, jid) -> tuple[Job, Receipt]:
        row = self.db.execute("SELECT body,receipt FROM jobs WHERE tenant=? AND id=?", (tenant, jid)).fetchone()
        if row is None:
            raise KeyError("Unknown job")
        return Job.model_validate_json(row[0]), Receipt.model_validate_json(row[1])

    def jobs(self, tenant, states=()) -> list[tuple[Job, Receipt]]:
        query, args = "SELECT body,receipt FROM jobs WHERE tenant=?", [tenant]
        if states:
            query += " AND state IN (" + ",".join("?" for _ in states) + ")"
            args += [s.value for s in states]
        query += " ORDER BY rowid"
        return [(Job.model_validate_json(r[0]), Receipt.model_validate_json(r[1]))
                for r in self.db.execute(query, args).fetchall()]

    def add_job(self, job: Job, receipt: Receipt):
        # Original source IDs cannot acquire different pixels/times on resubmission.
        with self.db:
            for obs in job.observations:
                key = (job.tenant, job.session_id, obs.id)
                prev = self.db.execute("SELECT body FROM observations WHERE tenant=? AND session=? AND id=?",
                                       key).fetchone()
                body = canonical(obs.model_dump(mode="json", exclude={"role"}))
                if prev and prev[0] != body:
                    raise ValueError("Observation identity reused with different source/timestamp/content")
                self.db.execute("INSERT OR IGNORE INTO observations VALUES (?,?,?,?)", (*key, body))
            self.db.execute("INSERT INTO jobs VALUES (?,?,?,?,?)",
                            (job.tenant, job.id, canonical(job), canonical(receipt), receipt.state.value))

    def receipt(self, tenant, receipt: Receipt):
        with self.db:
            self.db.execute("UPDATE jobs SET receipt=?,state=? WHERE tenant=? AND id=?",
                            (canonical(receipt), receipt.state.value, tenant, receipt.job_id))

    def budget(self):
        cfg = json.loads(self.db.execute("SELECT value FROM meta WHERE key='budget'").fetchone()[0])
        rows = self.db.execute("SELECT * FROM attempts").fetchall()
        held = sum(r["quote"] for r in rows if r["actual"] is None)
        actual = sum(r["actual"] for r in rows if r["actual"] is not None)
        return {**cfg, "attempts": len(rows), "known_microusd": actual,
                "held_microusd": held, "admission_total_microusd": actual + held,
                "unknown_attempts": sum(r["disposition"] == "unknown" for r in rows),
                "over_ceiling": actual + held > cfg["max_microusd"],
                "note": "Estimated inference admission only; GPU rental/energy and invoices are separate."}

    def reserve(self, job: Job, endpoint, now_ns: int):
        with self.db:
            b = self.budget()
            if b["attempts"] >= b["max_attempts"] or (
                b["admission_total_microusd"] + endpoint.reserve_microusd > b["max_microusd"]
            ):
                raise PermissionError("attempt_or_cost_ceiling")
            self.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?)",
                            (job.tenant, job.id, endpoint.pool, endpoint.id,
                             endpoint.reserve_microusd, None, "reserved"))
            self.db.execute("INSERT INTO events(at_ns,kind,metadata) VALUES (?,?,?)",
                            (now_ns, "attempt_reserved", canonical({"job_id": job.id, "endpoint": endpoint.id,
                              "quote_microusd": endpoint.reserve_microusd})))

    def settle(self, job: Job, usage: Usage | None):
        value = usage.cost_microusd if usage else None
        with self.db:
            self.db.execute("UPDATE attempts SET actual=?,disposition=? WHERE tenant=? AND job=?",
                            (value, "settled" if value is not None else "unknown", job.tenant, job.id))

    def reconcile(self, tenant: str, jid: str, actual_microusd: int, evidence: str, now_ns: int):
        self.reconcile_many(tenant, ((jid, actual_microusd, evidence),), now_ns)

    def reconcile_many(self, tenant: str, entries, now_ns: int):
        """Atomically settle unresolved attempts from an explicit provider export.

        Validation happens before the transaction so a malformed or duplicate import cannot
        partially settle a batch. ``entries`` contains ``(job_id, actual_microusd,
        evidence_ref)`` tuples. The evidence reference is metadata only; the provider export
        itself remains outside the runtime ledger.
        """
        entries = tuple(entries)
        seen = set()
        for jid, actual_microusd, evidence in entries:
            if (type(jid) is not str or not jid or len(jid) > 256 or jid in seen or
                    type(actual_microusd) is not int or actual_microusd < 0 or
                    type(evidence) is not str or not evidence or len(evidence) > 1024):
                raise ValueError("Each reconciliation requires a unique job ID, nonnegative charge, "
                                 "and bounded evidence reference")
            seen.add(jid)
        for jid in seen:
            row = self.db.execute("SELECT * FROM attempts WHERE tenant=? AND job=?", (tenant, jid)).fetchone()
            if not row:
                raise ValueError(f"Unknown reconciliation job: {jid}")
            if row["actual"] is not None:
                raise ValueError(f"Attempt is already settled: {jid}")
        with self.db:
            for jid, actual_microusd, evidence in entries:
                updated = self.db.execute(
                    "UPDATE attempts SET actual=?,disposition='settled' "
                    "WHERE tenant=? AND job=? AND actual IS NULL",
                    (actual_microusd, tenant, jid),
                ).rowcount
                if updated != 1:
                    raise ValueError(f"Attempt changed before reconciliation: {jid}")
                self.db.execute(
                    "INSERT INTO events(at_ns,kind,metadata) VALUES (?,?,?)",
                    (now_ns, "charge_reconciled", canonical({"job_id": jid,
                        "actual_microusd": actual_microusd, "evidence_ref": evidence})),
                )

    def quarantine(self, pool: str, reason: str):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO quarantines VALUES (?,?)", (pool, reason))

    def quarantined(self) -> set[str]:
        return {r[0] for r in self.db.execute("SELECT pool FROM quarantines")}

    def release_pool(self, pool: str, evidence: str, now_ns: int):
        if not evidence:
            raise ValueError("Require evidence of backend termination/restart")
        with self.db:
            self.db.execute("DELETE FROM quarantines WHERE pool=?", (pool,))
        self.event(now_ns, "pool_released", pool=pool, evidence_ref=evidence)

    def recover(self, tenant: str, now_ns: int):
        for job, r in self.jobs(tenant, (JobState.QUEUED, JobState.RUNNING)):
            state = JobState.UNKNOWN if r.state == JobState.RUNNING else JobState.CANCELLED
            self.receipt(tenant, r.model_copy(update={"state": state, "reason": "coordinator_restart"}))
            if r.state == JobState.RUNNING:
                row = self.db.execute("SELECT pool FROM attempts WHERE tenant=? AND job=?",
                                      (tenant, job.id)).fetchone()
                if row:
                    self.quarantine(row[0], "restart_with_unconfirmed_remote_work")
                    self.settle(job, None)
            self.event(now_ns, "recovery_invalidated", job_id=job.id, state=state.value)
        # A cancelled/stale receipt can still have remote compute in flight. Also
        # cover crashes between reservation and persistent RUNNING transition.
        for row in self.db.execute(
            "SELECT job,pool FROM attempts WHERE tenant=? AND disposition='reserved'", (tenant,)
        ).fetchall():
            self.quarantine(row["pool"], "restart_with_unconfirmed_reserved_work")
            with self.db:
                self.db.execute("UPDATE attempts SET disposition='unknown' WHERE tenant=? AND job=?",
                                (tenant, row["job"]))
            self.event(now_ns, "recovery_unconfirmed_attempt", job_id=row["job"], pool=row["pool"])
        for row in self.db.execute("SELECT body FROM sessions WHERE tenant=?", (tenant,)).fetchall():
            s = Session.model_validate_json(row[0])
            self.put_session(s.model_copy(update={"state": "closed"}))

    def extend_budget(self, *, max_attempts: int, max_microusd: int, approval_ref: str, now_ns: int):
        old = self.budget()
        if (type(max_attempts) is not int or type(max_microusd) is not int or not approval_ref or
            max_attempts < old["max_attempts"] or max_microusd < old["max_microusd"]):
            raise ValueError("Explicit nondecreasing cumulative caps and an approval reference required")
        cfg = {"campaign": old["campaign"], "max_attempts": max_attempts, "max_microusd": max_microusd}
        with self.db:
            self.db.execute("UPDATE meta SET value=? WHERE key='budget'", (canonical(cfg),))
        self.event(now_ns, "budget_extended", approval_ref=approval_ref,
                   max_attempts=max_attempts, max_microusd=max_microusd)

    def export_events(self):
        return [{"seq": r["seq"], "at_ns": r["at_ns"], "kind": r["kind"], **json.loads(r["metadata"])}
                for r in self.db.execute("SELECT * FROM events ORDER BY seq")]
