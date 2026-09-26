"""Strict provider-charge import and preflight helpers.

Provider exports are evidence supplied by an operator. They never become an implicit zero-cost
result, and an import cannot settle a job unless its exact Agmina job ID is present and unresolved.
"""
from __future__ import annotations

import json
from pathlib import Path

from .store import Store

MAX_IMPORT_BYTES = 8_000_000
MAX_RECORDS = 10_000
RECORD_KEYS = {"job_id", "actual_microusd", "evidence_ref"}


def _record(value, *, source: str):
    if not isinstance(value, dict) or set(value) != RECORD_KEYS:
        raise ValueError(f"{source}: record must contain exactly job_id, actual_microusd, evidence_ref")
    job_id = value["job_id"]
    actual = value["actual_microusd"]
    evidence = value["evidence_ref"]
    if type(job_id) is not str or not job_id or len(job_id) > 256:
        raise ValueError(f"{source}: invalid job_id")
    if type(actual) is not int or actual < 0:
        raise ValueError(f"{source}: actual_microusd must be a nonnegative integer")
    if type(evidence) is not str or not evidence or len(evidence) > 1024 or "\n" in evidence:
        raise ValueError(f"{source}: invalid evidence_ref")
    return job_id, actual, evidence


def load_records(path: str | Path):
    """Load a bounded JSON array/object or JSONL provider export."""
    path = Path(path)
    raw = path.read_bytes()
    if len(raw) > MAX_IMPORT_BYTES:
        raise ValueError("Reconciliation import exceeds byte bound")
    text = raw.decode("utf8")
    stripped = text.strip()
    if not stripped:
        raise ValueError("Reconciliation import is empty")
    records = []
    parsed = None
    jsonl = not (stripped.startswith("[") or stripped.startswith("{"))
    if not jsonl:
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            if stripped.startswith("{") and "Extra data" in exc.msg:
                jsonl = True
            else:
                raise ValueError("Malformed reconciliation JSON") from exc
    if not jsonl:
        if isinstance(parsed, dict):
            if set(parsed) != {"records"} or not isinstance(parsed["records"], list):
                raise ValueError("JSON import must be an array or an object with a records array")
            parsed = parsed["records"]
        if not isinstance(parsed, list):
            raise ValueError("JSON import must be an array")
        for index, value in enumerate(parsed, 1):
            records.append(_record(value, source=f"record {index}"))
    else:
        for line_no, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_no}: malformed JSON") from exc
            records.append(_record(value, source=f"line {line_no}"))
    if not records:
        raise ValueError("Reconciliation import has no records")
    if len(records) > MAX_RECORDS:
        raise ValueError("Reconciliation import exceeds record bound")
    if len({row[0] for row in records}) != len(records):
        raise ValueError("Reconciliation import contains duplicate job IDs")
    return tuple(records)


def preflight(store: Store, tenant: str, records):
    """Validate exact unresolved-job mapping without writing ledger state."""
    if type(tenant) is not str or not tenant:
        raise ValueError("A tenant is required")
    records = tuple(records)
    if len({row[0] for row in records}) != len(records):
        raise ValueError("Reconciliation import contains duplicate job IDs")
    for jid, _actual, _evidence in records:
        row = store.db.execute("SELECT actual FROM attempts WHERE tenant=? AND job=?", (tenant, jid)).fetchone()
        if row is None:
            raise ValueError(f"Unknown reconciliation job: {jid}")
        if row["actual"] is not None:
            raise ValueError(f"Attempt is already settled: {jid}")
    return {"records": len(records), "charge_microusd": sum(row[1] for row in records),
            "job_ids": [row[0] for row in records]}


def reconcile_file(store: Store, tenant: str, path: str | Path, *, apply: bool, now_ns: int):
    records = load_records(path)
    preview = preflight(store, tenant, records)
    before = store.budget()
    if apply:
        store.reconcile_many(tenant, records, now_ns)
    after = store.budget()
    return {"mode": "apply" if apply else "dry-run", **preview,
            "before": before, "after": after}
