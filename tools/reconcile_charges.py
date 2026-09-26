"""Preflight or apply an explicit provider charge export to an Agmina ledger.

Dry-run is the default. The input must be JSON/JSONL records with exact job IDs, actual charges in
micro-USD, and an evidence reference. This tool does not query a provider or infer missing charges.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

from agmina_runtime.reconciliation import reconcile_file
from agmina_runtime.store import Store


def open_existing(path: Path):
    if not path.is_file():
        raise ValueError(f"Ledger does not exist: {path}")
    db = sqlite3.connect(path)
    try:
        row = db.execute("SELECT value FROM meta WHERE key='budget'").fetchone()
        if row is None:
            raise ValueError("Ledger has no immutable budget metadata")
        budget = json.loads(row[0])
    finally:
        db.close()
    return Store(path, campaign=budget["campaign"], max_attempts=budget["max_attempts"],
                 max_microusd=budget["max_microusd"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="Commit settlements; default is read-only dry-run")
    parser.add_argument("--at-ns", type=int, help="Explicit monotonic event timestamp")
    args = parser.parse_args()
    if args.at_ns is not None and args.at_ns < 0:
        parser.error("--at-ns must be nonnegative")
    store = open_existing(args.database.resolve())
    try:
        report = reconcile_file(store, args.tenant, args.input.resolve(), apply=args.apply,
                                now_ns=args.at_ns if args.at_ns is not None else time.monotonic_ns())
    finally:
        store.close()
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
