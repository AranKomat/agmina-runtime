"""Run a no-network R1 workflow smoke against the two parent applications.

This is deliberately opt-in: the parent repositories are not dependencies of Agmina and are
loaded only when their source roots are supplied. The fixture backend returns schema-valid
responses; this checks request lineage, Agmina delivery, and the parent parsers, not model quality.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path


def add_parent_paths(streambudget_root: Path, physical_root: Path) -> None:
    sys.path.insert(0, str(streambudget_root / "src"))
    sys.path.insert(0, str(physical_root))


async def run(args: argparse.Namespace) -> dict:
    add_parent_paths(args.streambudget_root, args.physical_root)

    from physical_harness.core.actions import Basis
    from physical_harness.perception.contracts import FrameRef, RegionRef
    from physical_harness.perception.discovery import parse_response
    from streambudget.backend import ImageInput, Request, Result
    from streambudget.trace import Trace
    from streambudget.types import Perception
    from streambudget.validation import validate_response

    from agmina_runtime.adapters.hosts import physical_observation, streambudget_job
    from agmina_runtime.clocks import ClockMap
    from agmina_runtime.config import Endpoint, Pool, RuntimeConfig
    from agmina_runtime.contracts import Job, ModelContract, ResultKind, Usage, canonical
    from agmina_runtime.runtime import Runtime

    args.out.mkdir(parents=False, exist_ok=False)
    raw = b"r1-authorized-fixture-image"
    sha = hashlib.sha256(raw).hexdigest()
    config = RuntimeConfig(
        pools=(Pool(id="fixture-pool"),),
        models=(ModelContract(alias="fixture-model", weights="fixture-weights",
                              preprocessing="fixture-preprocessing", output_schema="fixture-json",
                              sampling="fixture-deterministic"),),
        endpoints=(Endpoint(id="fixture-endpoint", model="fixture-model", pool="fixture-pool",
                            site="local", kind="mock", service_p95_ns=1_000_000),),
        max_attempts=20,
    )

    class FixtureBackend:
        def __init__(self, runtime_clock):
            self.clock = runtime_clock
            self.outputs: dict[str, dict] = {}

        async def infer(self, job, endpoint):
            from agmina_runtime.contracts import Prediction

            return Prediction(payload_json=canonical(self.outputs[job.id]),
                              usage=Usage(cost_microusd=0),
                              first_content_ns=self.clock.now_ns())

    runtime = Runtime(config, args.out / "agmina", backends={})
    fixture = FixtureBackend(runtime.clock)
    runtime.backends["fixture-endpoint"] = fixture
    try:
        now = runtime.clock.now_ns()

        # StreamBudget request -> Agmina job -> StreamBudget's existing response validator.
        stream_session = runtime.open_session("streambudget-r1", "task-v1")
        image = ImageInput(evidence_id="frame-1", timestamp=1.0, jpeg=raw)
        request = Request("perceive", "system", "inspect the frame", [image], {})
        video_map = ClockMap("streambudget", runtime.clock.id, 0, 0, now + 60_000_000_000)
        stream_job = streambudget_job(
            request, session=stream_session, clock_map=video_map, now_ns=now,
            snapshot_ns=now, deadline_ns=now + 5_000_000_000,
            model="fixture-model", job_id="r1-streambudget", sequence_by_id={"frame-1": 7},
            available_by_id={"frame-1": 1.1}, result_kind=ResultKind.HISTORICAL,
        )
        fixture.outputs[stream_job.id] = {"text": json.dumps({
            "caption": "A fixture observation.", "facts": {"fixture": "true"}, "checks": []
        })}
        runtime.submit(stream_job)
        await runtime.wait(stream_job.id)
        stream_receipt = runtime.consume(stream_job.id, consumer_id="streambudget-r1")
        parsed_stream = validate_response(
            Perception,
            Result(json.loads(stream_receipt.prediction_json)["text"], None, 0.0, stream_job.id),
            Trace(args.out / "streambudget.trace.jsonl"),
            "r1-perceive",
        )

        # Physical FrameRef -> Agmina observation -> existing discovery parser. No action path is
        # constructed, and the result remains a semantic hypothesis only.
        basis = Basis("ep-r1", "obs-1", "source-1", 0.0, 100.0, "local", "epoch-0",
                      "geo-0", 0, "robot", "calibration", ("entity-1",), "fixture")
        frame = FrameRef(basis, "asset-1", sha, "head", 32, 24, 100.1)
        robot_map = ClockMap("robot", runtime.clock.id, 0, 0, now + 60_000_000_000)
        observation = physical_observation(frame, raw, sequence=3, clock_map=robot_map,
                                            clock_id=runtime.clock.id, now_ns=now)
        region = RegionRef("region-1", frame.asset_id, (0.1, 0.1, 0.8, 0.8))
        from physical_harness.perception.contracts import DiscoveryRequest

        discovery_request = DiscoveryRequest(
            "r1-discovery", "Find a red radio", "task-v1", basis, (frame,), (region,), (),
            "inventory-0", 100.2, 120.0, ("initial_view",),
        )
        physical_session = runtime.open_session("physical-r1", "task-v1")
        physical_job = Job(
            id="r1-physical", tenant=physical_session.tenant, session_id=physical_session.id,
            epoch=physical_session.epoch, task_revision=physical_session.task_revision,
            clock_id=physical_session.clock_id, model="fixture-model", operation="discovery",
            workload="semantic", result_kind=ResultKind.HISTORICAL, observations=(observation,),
            snapshot_ns=now, deadline_ns=now + 5_000_000_000,
            payload_json=canonical({"request_id": discovery_request.id,
                                    "request_fingerprint": discovery_request.fingerprint}),
        )
        discovery_payload = {
            "request_id": discovery_request.id,
            "request_fingerprint": discovery_request.fingerprint,
            "updates": [{"local_id": "radio-1", "frame_id": frame.asset_id,
                          "region_id": region.id, "box": None, "known_id": None,
                          "description": "red rectangular device", "hypotheses": ["radio"],
                          "status": "hypothesis", "retention": "retain",
                          "value": {"task": 3, "future": 1, "landmark": 0, "novelty": 1,
                                    "uncertainty_value": 2, "redundancy": 0, "transience": 0},
                          "needs_view": True}],
            "attention": [{"local_id": "radio-1", "reason": "possible target",
                           "significance": "high"}],
            "scene_summary": "A fixture room with a possible radio.",
        }
        fixture.outputs[physical_job.id] = discovery_payload
        runtime.submit(physical_job)
        await runtime.wait(physical_job.id)
        physical_receipt = runtime.consume(physical_job.id, consumer_id="physical-r1")
        parsed_discovery = parse_response(
            json.loads(physical_receipt.prediction_json), discovery_request,
            model="fixture-model", completed_wall=100.3,
        )

        # Negative lineage/freshness checks required for a read-only bridge.
        try:
            physical_observation(frame, b"wrong-bytes", sequence=3, clock_map=robot_map,
                                 clock_id=runtime.clock.id, now_ns=now)
        except PermissionError:
            invalid_source_rejected = True
        else:
            invalid_source_rejected = False

        stale_job = physical_job.model_copy(update={"id": "r1-stale", "deadline_ns": now + 10_000_000_000})
        fixture.outputs[stale_job.id] = discovery_payload
        runtime.submit(stale_job)
        runtime.advance_session("physical-r1", expected_epoch=0, task_revision="task-v2")
        stale_receipt = await runtime.wait(stale_job.id)
        try:
            runtime.consume(stale_job.id, consumer_id="physical-r1")
        except PermissionError:
            stale_delivery_rejected = True
        else:
            stale_delivery_rejected = False

        result = {
            "protocol": "R1 read-only parent workflow smoke",
            "streambudget_commit": "076783012377d074b82efd7aaf296a8175b3a7f4",
            "physical_contract_commit": "61bf0f500e4855ae00dd4c122b4ba0cbd7e42f4b",
            "paid_model_calls": 0,
            "gpu_calls": 0,
            "native_actions": 0,
            "streambudget": {"job": stream_job.id, "state": stream_receipt.state.value,
                              "caption": parsed_stream.caption},
            "physical": {"job": physical_job.id, "state": physical_receipt.state.value,
                         "updates": len(parsed_discovery.updates),
                         "attention": len(parsed_discovery.attention),
                         "observation_source_time": observation.source_time},
            "negative_checks": {"invalid_source_rejected": invalid_source_rejected,
                                 "stale_delivery_rejected": stale_delivery_rejected,
                                 "stale_state": stale_receipt.state.value},
        }
        if not invalid_source_rejected or not stale_delivery_rejected:
            raise AssertionError("R1 negative lineage/freshness check failed")
        (args.out / "report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
        return result
    finally:
        await runtime.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--streambudget-root", type=Path, required=True)
    parser.add_argument("--physical-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run(args))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
