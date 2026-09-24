"""Exercise source-clock reset and task-generation fences on both parent adapters.

This is a local contract campaign: actual parent request/frame types are converted into Agmina
jobs, then a generation change makes the in-flight result non-consumable. No model, GPU, or action
is used. It checks mapping mismatch/expiry separately so a stale result cannot be hidden by a
successful transport fixture.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path


def add_paths(streambudget_root: Path, physical_root: Path) -> None:
    sys.path.insert(0, str(streambudget_root / "src"))
    sys.path.insert(0, str(physical_root))


def expect_value_error(fn) -> bool:
    try:
        fn()
    except (TypeError, ValueError):
        return True
    return False


async def run(args: argparse.Namespace) -> dict:
    add_paths(args.streambudget_root, args.physical_root)
    from physical_harness.core.actions import Basis
    from physical_harness.perception.contracts import FrameRef
    from streambudget.backend import ImageInput, Request

    from agmina_runtime.adapters.hosts import physical_observation, streambudget_job
    from agmina_runtime.clocks import ClockMap, ManualClock
    from agmina_runtime.config import Endpoint, Pool, RuntimeConfig
    from agmina_runtime.contracts import Job, ModelContract, ResultKind, canonical
    from agmina_runtime.runtime import Runtime

    clock = ManualClock(1_000_000_000_000, "clock-before-reset")
    config = RuntimeConfig(
        pools=(Pool(id="fixture-pool"),),
        models=(ModelContract(alias="fixture-model", weights="fixture-weights",
                              preprocessing="fixture-preprocessing", output_schema="fixture-json",
                              sampling="fixture-deterministic"),),
        endpoints=(Endpoint(id="fixture-endpoint", model="fixture-model", pool="fixture-pool",
                            site="local", kind="mock", service_p95_ns=1_000_000),),
        max_attempts=8,
    )
    runtime = Runtime(config, args.out / "agmina", clock=clock)
    raw = b"r1-clock-reset-image"
    now = clock.now_ns()
    # Freeze the target snapshot at source availability 10.1s; capture at 10.0s remains older.
    offset = now - 10_100_000_000
    valid = ClockMap("streambudget", clock.id, offset, 0, now + 60_000_000_000)
    expired = ClockMap("streambudget", clock.id, offset, 0, now - 1)
    wrong_target = ClockMap("streambudget", "clock-after-reset", offset, 0,
                           now + 60_000_000_000)
    results = {}
    try:
        stream_session = runtime.open_session("clock-stream", "task-v1")
        request = Request("perceive", "system", "inspect", [ImageInput("frame-1", 10.0, raw)], {})
        stream_job = streambudget_job(
            request, session=stream_session, clock_map=valid, now_ns=now, snapshot_ns=now,
            deadline_ns=now + 30_000_000_000, model="fixture-model", job_id="clock-stream-job",
            sequence_by_id={"frame-1": 1}, available_by_id={"frame-1": 10.1},
            result_kind=ResultKind.CURRENT, max_age_ns=30_000_000_000,
        )
        runtime.submit(stream_job)
        runtime.advance_session("clock-stream", expected_epoch=0, task_revision="task-v2")
        stale_stream = await runtime.wait(stream_job.id)
        try:
            runtime.consume(stream_job.id, consumer_id="clock-test")
        except PermissionError:
            stream_consume_rejected = True
        else:
            stream_consume_rejected = False
        results["streambudget"] = {
            "stale_state": stale_stream.state.value,
            "stale_consume_rejected": stream_consume_rejected,
            "mapping_target_mismatch_rejected": expect_value_error(lambda: streambudget_job(
                request, session=stream_session, clock_map=wrong_target, now_ns=now,
                snapshot_ns=now, deadline_ns=now + 30_000_000_000, model="fixture-model",
                job_id="clock-stream-wrong-target", sequence_by_id={"frame-1": 1},
                available_by_id={"frame-1": 10.1}, result_kind=ResultKind.CURRENT,
                max_age_ns=30_000_000_000)),
            "mapping_expiry_rejected": expect_value_error(lambda: streambudget_job(
                request, session=stream_session, clock_map=expired, now_ns=now,
                snapshot_ns=now, deadline_ns=now + 30_000_000_000, model="fixture-model",
                job_id="clock-stream-expired", sequence_by_id={"frame-1": 1},
                available_by_id={"frame-1": 10.1}, result_kind=ResultKind.CURRENT,
                max_age_ns=30_000_000_000)),
        }

        basis = Basis("episode-clock", "obs-clock", "source-clock", 1.0, 100.0, "head",
                      "epoch-before-reset", "geometry-1", 0, "robot", "calibration", ("entity-clock",))
        frame = FrameRef(basis, "asset-clock", hashlib.sha256(raw).hexdigest(), "head", 8, 8, 100.1)
        physical_map = ClockMap("robot", clock.id, now - 100_100_000_000, 0,
                                now + 60_000_000_000)
        observation = physical_observation(frame, raw, sequence=1, clock_map=physical_map,
                                           clock_id=clock.id, now_ns=now)
        physical_session = runtime.open_session("clock-physical", "task-v1")
        physical_job = Job(
            id="clock-physical-job", tenant=physical_session.tenant, session_id=physical_session.id,
            epoch=physical_session.epoch, task_revision=physical_session.task_revision,
            clock_id=physical_session.clock_id, model="fixture-model", operation="discovery",
            workload="semantic", result_kind=ResultKind.CURRENT, observations=(observation,),
            snapshot_ns=now, deadline_ns=now + 30_000_000_000, max_age_ns=30_000_000_000,
            payload_json=canonical({"fixture_output": {"fixture": True}}),
        )
        runtime.submit(physical_job)
        runtime.advance_session("clock-physical", expected_epoch=0, task_revision="task-v2")
        stale_physical = await runtime.wait(physical_job.id)
        try:
            runtime.consume(physical_job.id, consumer_id="clock-test")
        except PermissionError:
            physical_consume_rejected = True
        else:
            physical_consume_rejected = False
        results["physical"] = {
            "stale_state": stale_physical.state.value,
            "stale_consume_rejected": physical_consume_rejected,
            "mapping_target_mismatch_rejected": expect_value_error(lambda: physical_observation(
                frame, raw, sequence=1, clock_map=physical_map, clock_id="clock-after-reset",
                now_ns=now)),
        }
        result = {"protocol": "R1 clock reset and generation-fence smoke",
                  "paid_model_calls": 0, "gpu_calls": 0, "native_actions": 0,
                  "results": results}
        checks = [results["streambudget"][key] for key in
                  ("stale_consume_rejected", "mapping_target_mismatch_rejected", "mapping_expiry_rejected")]
        checks += [results["physical"][key] for key in
                   ("stale_consume_rejected", "mapping_target_mismatch_rejected")]
        if not all(checks) or results["streambudget"]["stale_state"] not in {"stale", "expired"} \
                or results["physical"]["stale_state"] not in {"stale", "expired"}:
            raise AssertionError("clock reset or generation fence was not enforced")
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
    args.out.mkdir(parents=False, exist_ok=False)
    print(json.dumps(asyncio.run(run(args)), indent=2))


if __name__ == "__main__":
    main()
