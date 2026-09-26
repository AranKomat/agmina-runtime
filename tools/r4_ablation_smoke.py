"""Run the R4 cache/latest-only plumbing smoke against the deterministic mock backend.

This creates retained software evidence only. It never enables network access, reads labels,
uses a GPU, or authorizes native actions.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from agmina_runtime.config import RuntimeConfig
from agmina_runtime.contracts import ResultKind
from agmina_runtime.load import LoadItem, LoadPlan, run_load


def item(job_id: str, *, release_ms: int = 0, operation: str = "paced_load",
         delay: float = 0.001, **controls) -> LoadItem:
    return LoadItem(
        id=job_id, session="mock-camera", model="semantic", workload="semantic",
        release_ms=release_ms, deadline_after_ms=1000, result_kind=ResultKind.HISTORICAL,
        evidence_hashes=("0" * 64,), payload_json=json.dumps({"fixture_delay_s": delay}),
        operation=operation, **controls,
    )


def plans() -> dict[str, LoadPlan]:
    return {
        "cache": LoadPlan(
            provenance="R4 cache-only software ablation; identical retained evidence",
            synthetic_inputs=True,
            jobs=(
                item("cache-first", observation_ids=("retained-frame-0",), cacheable=True),
                item("cache-duplicate", observation_ids=("retained-frame-0",), cacheable=True),
            ),
        ),
        "latest": LoadPlan(
            provenance="R4 latest-only software ablation; queued semantic work",
            synthetic_inputs=True,
            jobs=(
                item("blocker", operation="blocker", delay=0.05),
                item("latest-old", release_ms=0, operation="latest", replace_key="latest",
                     discardable=True),
                item("latest-new", release_ms=1, operation="latest", replace_key="latest",
                     discardable=True),
            ),
        ),
    }


async def run(config_path: Path, out: Path) -> dict:
    if out.exists():
        raise FileExistsError(f"Output already exists: {out}")
    config = RuntimeConfig.model_validate_json(config_path.read_text(encoding="utf8"))
    out.mkdir(parents=True)
    reports = {}
    for name, plan in plans().items():
        reports[name] = await run_load(config, plan, out / name)
    result = {
        "protocol": "R4 zero-cost cache/latest-only load-control smoke",
        "config": str(config_path),
        "paid_calls": 0,
        "native_actions": 0,
        "labels_read": False,
        "network_enabled": False,
        "gpu_work": False,
        "quality_claim": False,
        "cache_hits": reports["cache"]["cache_hits"],
        "latest_states": reports["latest"]["states"],
        "reports": {name: f"{name}/report.json" for name in reports},
    }
    (out / "manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                                         encoding="utf8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/mock.json"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.config, args.out)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
