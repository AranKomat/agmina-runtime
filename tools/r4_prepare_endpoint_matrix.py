"""Prepare a controlled real-endpoint R4 scheduler matrix without dispatching calls.

The generated directories contain one config per scheduler and a shared retained-input plan. This
tool never starts a runtime, contacts a provider, reads labels, or authorizes robot actions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from agmina_runtime.config import RuntimeConfig
from agmina_runtime.load import LoadPlan

SCHEDULERS = ("fifo", "edf", "slack")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(base_config: Path, plan_path: Path, out: Path, campaign_prefix: str) -> dict:
    if out.exists():
        raise FileExistsError(f"Output already exists: {out}")
    config = RuntimeConfig.model_validate_json(base_config.read_text(encoding="utf8"))
    plan = LoadPlan.model_validate_json(plan_path.read_text(encoding="utf8"))
    models = {item.model for item in plan.jobs}
    if len(models) != 1:
        raise ValueError("R4 matrix requires one model alias across the retained plan")
    model = next(iter(models))
    endpoints = [endpoint for endpoint in config.endpoints if endpoint.model == model]
    if len(endpoints) != 1:
        raise ValueError("R4 scheduler-only matrix requires exactly one matching endpoint")
    endpoint = endpoints[0]
    required_microusd = len(plan.jobs) * endpoint.reserve_microusd
    if config.max_attempts < len(plan.jobs) or config.max_microusd < required_microusd:
        raise ValueError("Base config cap is smaller than the retained plan")
    try:
        extra = json.loads(endpoint.extra_body_json)
    except json.JSONDecodeError as exc:
        raise ValueError("Endpoint extras are not valid JSON") from exc
    provider = extra.get("provider", {}) if isinstance(extra, dict) else {}
    if endpoint.externally_billed and provider.get("allow_fallbacks") is not False:
        raise ValueError("R4 real matrix requires provider fallbacks to be explicitly disabled")

    out.mkdir(parents=True)
    (out / "plan.json").write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf8")
    conditions = []
    for scheduler in SCHEDULERS:
        condition = f"{campaign_prefix}-{scheduler}"
        variant = config.model_copy(update={
            "campaign": condition,
            "max_attempts": len(plan.jobs),
            "max_microusd": config.max_microusd,
            "scheduler": scheduler,
        })
        path = out / f"config-{scheduler}.json"
        path.write_text(variant.model_dump_json(indent=2) + "\n", encoding="utf8")
        conditions.append({
            "name": scheduler,
            "campaign": condition,
            "config": path.name,
            "offered_jobs": len(plan.jobs),
            "max_attempts": variant.max_attempts,
            "max_microusd": variant.max_microusd,
            "endpoint": endpoint.id,
            "provider_order": provider.get("order", []),
            "fallbacks_allowed": provider.get("allow_fallbacks"),
        })
    manifest = {
        "protocol": "R4 controlled real-endpoint scheduler matrix preparation",
        "dispatches": 0,
        "paid_calls": 0,
        "native_actions": 0,
        "labels_read": False,
        "synthetic_inputs": plan.synthetic_inputs,
        "plan_sha256": sha256(out / "plan.json"),
        "source_plan": str(plan_path),
        "base_config": str(base_config),
        "same_model": model,
        "same_endpoint": endpoint.id,
        "same_pool_capacity": config.pools[[pool.id for pool in config.pools].index(endpoint.pool)].slots,
        "per_condition_admission_cap_microusd": config.max_microusd,
        "required_cap_for_offered_jobs_microusd": required_microusd,
        "no_retries": True,
        "conditions": conditions,
        "metrics": [
            "offered_and_terminal_counts",
            "useful_completion_rate",
            "queue_and_complete_output_latency",
            "deadline_misses_and_expiry",
            "pool_quarantine_and_recovery",
            "provider_request_id_and_charge_reconciliation",
        ],
        "quality_claim": False,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-config", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--campaign-prefix", default="r4-real-scheduler-20260926")
    args = parser.parse_args()
    print(json.dumps(prepare(args.base_config, args.plan, args.out, args.campaign_prefix), indent=2))


if __name__ == "__main__":
    main()
