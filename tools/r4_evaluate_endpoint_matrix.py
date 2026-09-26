"""Evaluate a completed R4 scheduler matrix without making model calls."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEDULERS = ("fifo", "edf", "slack")


def read(path: Path):
    return json.loads(path.read_text(encoding="utf8"))


def semantic_digest(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def evaluate(prep: Path, runs: Path, out: Path) -> dict:
    expected_plan = read(prep / "plan.json")
    rows = []
    shared_endpoint = None
    shared_plan = True
    complete = True
    accounting_complete = True
    for scheduler in SCHEDULERS:
        root = runs / scheduler
        config = read(root / "config.json")
        report = read(root / "report.json")
        plan = read(root / "plan.json")
        plan_hash = semantic_digest(plan)
        states = report.get("states", {})
        terminal = sum(states.values()) == report.get("offered", -1)
        unknown = report.get("budget", {}).get("unknown_attempts")
        held = report.get("budget", {}).get("held_microusd")
        endpoint_ids = tuple(endpoint["id"] for endpoint in config.get("endpoints", []))
        if shared_endpoint is None:
            shared_endpoint = endpoint_ids
        shared_plan &= plan == expected_plan
        complete &= terminal and config.get("scheduler") == scheduler
        accounting_complete &= unknown == 0 and held == 0
        offered = report.get("offered", 0)
        consumed = states.get("consumed", 0)
        timing = report.get("timing", {})
        rows.append({
            "scheduler": scheduler,
            "offered": offered,
            "consumed": consumed,
            "expired": states.get("expired", 0),
            "other_states": {key: value for key, value in states.items()
                              if key not in {"consumed", "expired"}},
            "consumed_fraction": consumed / offered if offered else None,
            "attempts": report.get("budget", {}).get("attempts"),
            "known_microusd": report.get("budget", {}).get("known_microusd"),
            "unknown_attempts": unknown,
            "held_microusd": held,
            "queue_p50_ms": timing.get("queue", {}).get("p50_ns", 0) / 1e6,
            "queue_p95_ms": timing.get("queue", {}).get("p95_ns", 0) / 1e6,
            "complete_p50_ms": timing.get("submit_to_completion", {}).get("p50_ns", 0) / 1e6,
            "complete_p95_ms": timing.get("submit_to_completion", {}).get("p95_ns", 0) / 1e6,
            "endpoint_ids": endpoint_ids,
            "plan_sha256": plan_hash,
            "quarantined_pools": report.get("quarantined_pools", []),
        })
    endpoint_rows = read(runs / "fifo" / "config.json").get("endpoints", [])
    provider_revision_pinned = all(
        endpoint.get("model_version") and not str(endpoint["model_version"]).startswith("operator-record")
        for endpoint in endpoint_rows
    )
    result = {
        "protocol": "R4 bounded real-endpoint scheduler matrix evaluation",
        "status": "bounded_real_endpoint_observation" if complete and accounting_complete and shared_plan
        else "incomplete",
        "quality_claim": False,
        "native_actions": 0,
        "labels_read": False,
        "shared_plan": shared_plan,
        "canonical_plan_sha256": semantic_digest(expected_plan),
        "shared_endpoint": shared_endpoint is not None and all(row["endpoint_ids"] == shared_endpoint for row in rows),
        "terminal_reports": complete,
        "accounting_complete": accounting_complete,
        "served_provider_revision_pinned": provider_revision_pinned,
        "conditions": rows,
        "total_known_microusd": sum(row["known_microusd"] or 0 for row in rows),
        "total_unknown_attempts": sum(row["unknown_attempts"] or 0 for row in rows),
        "interpretation": [
            "The same retained plan was run once per scheduler on one externally served endpoint.",
            "This is transport/capacity evidence, not semantic quality or a universal scheduler ranking.",
            "The served provider revision is not pinned in the retained endpoint metadata.",
            "Replication at additional load levels is required before selecting a scheduler.",
        ],
    }
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prep", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.prep, args.runs, args.out), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
