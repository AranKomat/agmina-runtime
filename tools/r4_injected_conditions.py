"""Retain zero-cost R4 injected-delay and unconfirmed-loss controls."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from agmina_runtime.config import RuntimeConfig
from agmina_runtime.load import LoadItem, LoadPlan, run_load


def load_item(job_id: str, payload: dict) -> LoadItem:
    return LoadItem(
        id=job_id, session="r4-mock", model="semantic", workload="semantic", release_ms=0,
        deadline_after_ms=1000, evidence_hashes=("0" * 64,), payload_json=json.dumps(payload),
    )


async def run(config_path: Path, out: Path) -> dict:
    if out.exists():
        raise FileExistsError(f"Output already exists: {out}")
    config = RuntimeConfig.model_validate_json(config_path.read_text(encoding="utf8"))
    out.mkdir(parents=True)
    plans = {
        "delay": LoadPlan(
            provenance="R4 injected-delay control; deterministic mock backend",
            synthetic_inputs=True,
            jobs=tuple(load_item(f"delay-{i}", {"fixture_delay_s": delay})
                       for i, delay in enumerate((0.001, 0.01, 0.03, 0.05))),
        ),
        "loss": LoadPlan(
            provenance="R4 unconfirmed-loss control; deterministic mock backend",
            synthetic_inputs=True,
            jobs=(load_item("loss", {"fixture_unknown": True}),),
        ),
    }
    reports = {}
    for name, plan in plans.items():
        reports[name] = await run_load(config, plan, out / name)
    result = {
        "protocol": "R4 zero-cost injected delay/loss controls",
        "config": str(config_path),
        "paid_calls": 0,
        "native_actions": 0,
        "labels_read": False,
        "network_enabled": False,
        "gpu_work": False,
        "quality_claim": False,
        "delay_states": reports["delay"]["states"],
        "loss_states": reports["loss"]["states"],
        "loss_unknown_attempts": reports["loss"]["budget"]["unknown_attempts"],
        "loss_quarantined_pools": reports["loss"]["quarantined_pools"],
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
