"""Replay a retained StreamBudget frame campaign through native and Agmina paths.

This is a no-network, mock-backend R1 evidence check. It verifies that retained source bytes,
timestamps, order, and parent-visible scheduler results survive the bridge. It is not a model
quality or held-out benchmark.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path


def add_paths(streambudget_root: Path) -> None:
    sys.path.insert(0, str(streambudget_root / "src"))


def prompt_text(body: dict) -> list[tuple[str, object]]:
    values = []
    for message in body.get("messages", []):
        content = message.get("content")
        if isinstance(content, str):
            values.append((message.get("role"), content))
        else:
            values.append((message.get("role"), tuple(
                item.get("text") for item in content
                if item.get("type") == "text"
            )))
    return values


def image_details(body: dict) -> list[object]:
    return [item.get("image_url", {}).get("detail")
            for message in body.get("messages", [])
            for item in (message.get("content") if isinstance(message.get("content"), list) else [])
            if item.get("type") == "image_url"]


def retained_frames(root: Path) -> list[dict]:
    receipt = json.loads((root / "receipt.json").read_text(encoding="utf8"))
    if receipt.get("status") != "complete" or receipt.get("model_calls") != 0:
        raise AssertionError("retained receipt is not a completed zero-call campaign")
    rows = []
    from PIL import Image

    for entry in receipt.get("frames", []):
        path = root / entry["file"]
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise AssertionError(f"retained hash mismatch: {path.name}")
        with Image.open(path) as image:
            if list(image.size) != entry["native_size"]:
                raise AssertionError(f"retained size mismatch: {path.name}")
        rows.append({"file": entry["file"], "sha256": entry["sha256"],
                     "timestamp_s": entry["source_timestamp_s"], "bytes": len(data),
                     "data": data})
    if not rows:
        raise AssertionError("retained receipt has no frames")
    return rows


async def run(args: argparse.Namespace) -> dict:
    frames = retained_frames(args.retained_dir)
    add_paths(args.streambudget_root)

    from streambudget.backend import MockBackend as StreamMockBackend
    from streambudget.backend import Result
    from streambudget.config import Config as StreamConfig
    from streambudget.runtime import Runtime as StreamRuntime
    from streambudget.types import Watch

    from agmina_runtime.adapters.hosts import streambudget_job
    from agmina_runtime.clocks import ClockMap
    from agmina_runtime.config import Endpoint, Pool, RuntimeConfig
    from agmina_runtime.contracts import ModelContract, ResultKind, Usage, canonical
    from agmina_runtime.runtime import Runtime

    config = RuntimeConfig(
        pools=(Pool(id="fixture-pool"),),
        models=(ModelContract(alias="fixture-model", weights="fixture-weights",
                              preprocessing="fixture-preprocessing", output_schema="fixture-json",
                              sampling="fixture-deterministic"),),
        endpoints=(Endpoint(id="fixture-endpoint", model="fixture-model", pool="fixture-pool",
                            site="local", kind="mock", service_p95_ns=1_000_000),),
        max_attempts=40,
    )
    coordinator = Runtime(config, args.out / "agmina")

    async def run_parent(*, routed: bool) -> dict:
        host = StreamRuntime(StreamConfig(), args.out / ("streambudget-agmina" if routed
                                                         else "streambudget-direct"))
        native_pool = host.pool
        calls: list[dict] = []
        fixture_backend = _FixtureBackend(coordinator)
        if routed:
            coordinator.backends["fixture-endpoint"] = fixture_backend

        class AgminaPool:
            def __init__(self):
                self.calls = 0
                self.synthetic = StreamMockBackend()

            async def call(self, role, parent_request):
                started = time.monotonic()
                cfg = host.config.role(role)
                ticket = await host.ledger.reserve(0.0)
                status = "error"
                try:
                    self.calls += 1
                    agmina_now = coordinator.clock.now_ns()
                    source_now = round(host.now * 1_000_000_000)
                    mapping = ClockMap("streambudget-retained", coordinator.clock.id,
                                       agmina_now - source_now, 0, agmina_now + 600_000_000_000)
                    session = coordinator.open_session(f"streambudget-retained-{self.calls}", "retained-v1")
                    evidence = [host.store.get(item.evidence_id) for item in parent_request.images]
                    job = streambudget_job(
                        parent_request, session=session, clock_map=mapping, now_ns=agmina_now,
                        snapshot_ns=agmina_now, deadline_ns=agmina_now + 600_000_000_000,
                        model="fixture-model", job_id=f"retained-{self.calls}",
                        sequence_by_id={item.id: item.seq for item in evidence},
                        available_by_id={item.id: item.available_at for item in evidence},
                        result_kind=ResultKind.CURRENT, max_age_ns=600_000_000_000,
                    )
                    native_body = native_pool._body(cfg, parent_request)
                    routed_body = job.payload()
                    equivalent = (native_body["messages"] == routed_body["messages"]
                                  and native_body.get("response_format")
                                  == routed_body.get("response_format"))
                    expected_capture = [round(item.timestamp * 1_000_000_000) + mapping.offset_ns
                                        for item in parent_request.images]
                    expected_available = [round(item.available_at * 1_000_000_000) + mapping.offset_ns
                                         for item in evidence]
                    observations = list(job.observations)
                    lineage = {
                        "source_hash_equal": len(observations) == len(parent_request.images)
                        and all(obs.sha256 == hashlib.sha256(item.jpeg).hexdigest()
                                for obs, item in zip(observations, parent_request.images)),
                        "image_order_equal": [obs.id for obs in observations]
                        == [item.evidence_id for item in parent_request.images],
                        "image_detail_equal": image_details(native_body) == image_details(routed_body),
                        "prompt_equal": prompt_text(native_body) == prompt_text(routed_body),
                        "cutoff_covers_availability": max((obs.available_ns for obs in observations),
                                                           default=0) <= job.snapshot_ns,
                        "clock_mapping_equal": len(observations) == len(expected_capture)
                        and [obs.capture_ns for obs in observations] == expected_capture
                        and [obs.available_ns for obs in observations] == expected_available
                        and all(obs.source_time == str(item.timestamp)
                                for obs, item in zip(observations, parent_request.images)),
                        "task_episode_identity": {
                            "task": parent_request.context.get("task"),
                            "episode": parent_request.context.get("episode"),
                            "supplied_by_parent": bool(parent_request.context.get("task")
                                                         or parent_request.context.get("episode")),
                        },
                    }
                    calls.append({"job": job.id, "request_fingerprint": job.fingerprint,
                                  "payload_equivalent": equivalent,
                                  "source_ids": [item.id for item in evidence],
                                  "lineage": lineage})
                    if not equivalent:
                        raise AssertionError("retained StreamBudget payload changed at bridge")
                    prediction = self.synthetic.generate(parent_request)
                    fixture_backend.outputs[job.id] = prediction
                    coordinator.submit(job)
                    await coordinator.wait(job.id)
                    receipt = coordinator.consume(job.id, consumer_id="streambudget-retained")
                    status = "ok"
                    return Result(json.loads(receipt.prediction_json)["text"], None,
                                  time.monotonic() - started, job.id)
                finally:
                    await host.ledger.settle(ticket, role=role, prices=cfg.prices,
                                             usage=None, status=status, synthetic=True)

            async def close(self):
                return None

        try:
            if routed:
                await native_pool.close()
                host.pool = AgminaPool()
            host.register_watch(Watch(id="retained", source="cam",
                                      goal="Is the red box visible?", repeat=True,
                                      cooldown_seconds=0, max_observation_gap=60))
            for frame in frames:
                await host.ingest_frame("cam", frame["timestamp_s"], frame["data"])
            await host.drain()
            report = host.report()
            report["parent_alerts"] = host.alerts
            report["requests"] = host.ledger.requests
            if routed:
                report["agmina_calls"] = host.pool.calls
                report["bridge_calls"] = calls
            return report
        finally:
            await host.close()

    class _FixtureBackend:
        def __init__(self, runtime):
            self.runtime = runtime
            self.outputs: dict[str, dict] = {}

        async def infer(self, job, endpoint):
            from agmina_runtime.contracts import Prediction
            return Prediction(payload_json=canonical({"text": json.dumps(self.outputs[job.id])}),
                              usage=Usage(cost_microusd=0),
                              first_content_ns=self.runtime.clock.now_ns())

    try:
        direct, routed = await asyncio.gather(run_parent(routed=False), run_parent(routed=True))
        direct_shape = {key: direct[key] for key in ("alerts", "requests", "now")}
        routed_shape = {key: routed[key] for key in ("alerts", "requests", "now")}
        if direct_shape != routed_shape:
            raise AssertionError(f"parent-visible retained replay differs: {direct_shape} != {routed_shape}")
        if not all(call["payload_equivalent"] for call in routed["bridge_calls"]):
            raise AssertionError("one or more retained requests changed at the Agmina boundary")
        if not all(all(call["lineage"][key] for key in
                       ("source_hash_equal", "image_order_equal", "image_detail_equal",
                        "prompt_equal", "cutoff_covers_availability", "clock_mapping_equal"))
                   for call in routed["bridge_calls"]):
            raise AssertionError("one or more retained lineage invariants failed")
        lineage_checks = [call["lineage"] for call in routed["bridge_calls"]]
        result = {
            "protocol": "R1 retained StreamBudget replay",
            "paid_model_calls": 0,
            "gpu_calls": 0,
            "native_actions": 0,
            "retained_dir": str(args.retained_dir),
            "frames": [{key: row[key] for key in ("file", "sha256", "timestamp_s", "bytes")}
                       for row in frames],
            "direct": direct_shape,
            "agmina": routed_shape | {"agmina_calls": routed["agmina_calls"],
                                       "payload_equivalent": True,
                                       "accounting_equal": direct["requests"] == routed["requests"]},
            "lineage_checks": lineage_checks,
            "warning": "Mock replay verifies lineage and parent behavior only; it is not R5 quality evidence.",
        }
        (args.out / "report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
        return result
    finally:
        await coordinator.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--streambudget-root", type=Path, required=True)
    parser.add_argument("--retained-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=False, exist_ok=False)
    print(json.dumps(asyncio.run(run(args)), indent=2))


if __name__ == "__main__":
    main()
