"""Prepare small real-endpoint R4 cache/latest-only conditions without dispatching calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agmina_runtime.config import RuntimeConfig
from agmina_runtime.load import LoadPlan


def prepare(base_config_path: Path, source_plan_path: Path, out: Path, cap_microusd: int,
            campaign_prefix: str, latest_deadline_ms: int | None) -> dict:
    if out.exists():
        raise FileExistsError(f"Output already exists: {out}")
    config = RuntimeConfig.model_validate_json(base_config_path.read_text(encoding="utf8"))
    source = LoadPlan.model_validate_json(source_plan_path.read_text(encoding="utf8"))
    if not source.jobs:
        raise ValueError("Source plan is empty")
    template = source.jobs[0]
    endpoint_models = [e for e in config.endpoints if e.model == template.model]
    if len(endpoint_models) != 1:
        raise ValueError("Expected exactly one endpoint for the source model")
    if not endpoint_models[0].externally_billed:
        raise ValueError("This preparation tool is for the declared real endpoint")
    if cap_microusd <= 0:
        raise ValueError("Positive per-condition cap required")

    cache_ids = ("r4-retained-evidence-0",)
    cache_items = (
        template.model_copy(update={
            "id": "cache-first", "release_ms": 0, "cacheable": True,
            "observation_ids": cache_ids,
        }),
        template.model_copy(update={
            "id": "cache-duplicate", "release_ms": 0, "cacheable": True,
            "observation_ids": cache_ids,
        }),
    )
    latest_update = {"deadline_after_ms": latest_deadline_ms} if latest_deadline_ms else {}
    latest_items = (
        template.model_copy(update={"id": "latest-blocker", "release_ms": 0,
                                    "operation": "blocker", **latest_update}),
        template.model_copy(update={"id": "latest-old", "release_ms": 0,
                                    "operation": "latest", "replace_key": "latest",
                                    "discardable": True, **latest_update}),
        template.model_copy(update={"id": "latest-new", "release_ms": 1,
                                    "operation": "latest", "replace_key": "latest",
                                    "discardable": True, **latest_update}),
    )
    baseline_items = tuple(item.model_copy(update={"replace_key": None, "discardable": False})
                           for item in latest_items)
    plans = {
        "cache": LoadPlan(
            provenance="R4 real cache-only ablation from one retained source item; no quality claim",
            synthetic_inputs=source.synthetic_inputs, jobs=cache_items),
        "latest": LoadPlan(
            provenance="R4 real latest-only ablation from one retained source item; no quality claim",
            synthetic_inputs=source.synthetic_inputs, jobs=latest_items),
        "baseline": LoadPlan(
            provenance="R4 matched no-replacement baseline from one retained source item; no quality claim",
            synthetic_inputs=source.synthetic_inputs, jobs=baseline_items),
    }
    out.mkdir(parents=True)
    conditions = []
    for name, plan in plans.items():
        condition = out / name
        condition.mkdir()
        variant = config.model_copy(update={
            "campaign": f"{campaign_prefix}-{name}",
            "max_attempts": len(plan.jobs),
            "max_microusd": cap_microusd,
            "cache_entries": 64 if name == "cache" else 0,
            "cache_bytes": 8_000_000 if name == "cache" else 0,
        })
        (condition / "config.json").write_text(variant.model_dump_json(indent=2) + "\n",
                                                  encoding="utf8")
        (condition / "plan.json").write_text(plan.model_dump_json(indent=2) + "\n",
                                                encoding="utf8")
        conditions.append({"name": name, "jobs": len(plan.jobs), "cap_microusd": cap_microusd,
                           "config": f"{name}/config.json", "plan": f"{name}/plan.json"})
    manifest = {
        "protocol": "R4 bounded real cache/latest-only preparation",
        "dispatches": 0,
        "paid_calls": 0,
        "native_actions": 0,
        "labels_read": False,
        "source_plan": str(source_plan_path),
        "source_model": template.model,
        "source_inputs_synthetic": source.synthetic_inputs,
        "no_retries": True,
        "provider_fallbacks": False,
        "quality_claim": False,
        "latest_deadline_after_ms": latest_deadline_ms,
        "conditions": conditions,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                                         encoding="utf8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-config", type=Path, required=True)
    parser.add_argument("--source-plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cap-microusd", type=int, default=8000)
    parser.add_argument("--campaign-prefix", default="r4-real-ablation")
    parser.add_argument("--latest-deadline-ms", type=int, default=None)
    args = parser.parse_args()
    print(json.dumps(prepare(args.base_config, args.source_plan, args.out, args.cap_microusd,
                             args.campaign_prefix, args.latest_deadline_ms), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
