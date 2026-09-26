"""Run a no-network R1 workflow smoke against the two parent applications.

This is deliberately opt-in: the parent repositories are not dependencies of Agmina and are
loaded only when their source roots are supplied. The fixture backend returns schema-valid
responses; this checks request lineage, Agmina delivery, and the parent parsers, not model quality.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import subprocess
import sys
import time
from pathlib import Path


def add_parent_paths(streambudget_root: Path, physical_root: Path) -> None:
    sys.path.insert(0, str(streambudget_root / "src"))
    sys.path.insert(0, str(physical_root))


def git_state(root: Path) -> dict[str, object]:
    """Record Git provenance without rejecting a source snapshot with no .git metadata."""
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    if head.returncode:
        return {
            "commit": None,
            "dirty": None,
            "metadata": "unavailable",
            "reason": head.stderr.strip() or "not a Git checkout",
        }
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "commit": head.stdout.strip(),
        "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
        "metadata": "available" if status.returncode == 0 else "partial",
    }


async def run(args: argparse.Namespace) -> dict:
    add_parent_paths(args.streambudget_root, args.physical_root)

    from physical_harness.core.actions import Basis
    from physical_harness.integrations.experiment.journal import Journal
    from physical_harness.perception.contracts import FrameRef, RegionRef
    from physical_harness.perception.discovery import AsyncDiscovery, parse_response
    from physical_harness.perception.discovery_coordinator import DiscoveryCoordinator
    from physical_harness.perception.keyframes import SemanticKeyframes, ViewSample, thumbnail_descriptor
    from physical_harness.reasoning.executive import ExecutiveCadence
    from physical_harness.world.inventory import SemanticInventory
    from streambudget.backend import ImageInput, Request, Result
    from streambudget.backend import MockBackend as StreamMockBackend
    from streambudget.config import Config as StreamConfig
    from streambudget.runtime import Runtime as StreamRuntime
    from streambudget.trace import Trace
    from streambudget.types import Perception, Watch
    from streambudget.validation import validate_response

    from agmina_runtime.adapters.hosts import physical_observation, streambudget_job
    from agmina_runtime.clocks import ClockMap
    from agmina_runtime.config import Endpoint, Pool, RuntimeConfig
    from agmina_runtime.contracts import Job, ModelContract, ResultKind, Usage, canonical
    from agmina_runtime.runtime import Runtime

    args.out.mkdir(parents=False, exist_ok=False)
    raw = b"r1-authorized-fixture-image"
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

        # Run StreamBudget's actual watch scheduler twice on the same synthetic frame: once through
        # its native mock pool and once through an adapter that preserves its ledger/parser while
        # delegating inference coordination to Agmina.
        from PIL import Image, ImageDraw

        image_buffer = io.BytesIO()
        red_image = Image.new("RGB", (128, 128), "white")
        ImageDraw.Draw(red_image).rectangle((30, 30, 90, 90), fill="red")
        red_image.save(image_buffer, format="JPEG")
        red_jpeg = image_buffer.getvalue()

        async def run_stream_direct() -> dict:
            host = StreamRuntime(StreamConfig(), args.out / "streambudget-direct")
            try:
                host.register_watch(Watch(id="red", source="cam", goal="Red box visible"))
                await host.ingest_frame("cam", 1.0, red_jpeg)
                await host.drain()
                return {"alerts": len(host.alerts), "requests": host.ledger.requests,
                        "status": host.watches["red"].last_status}
            finally:
                await host.close()

        async def run_stream_agmina() -> dict:
            host = StreamRuntime(StreamConfig(), args.out / "streambudget-agmina")
            native_pool = host.pool
            agmina_session = runtime.open_session("streambudget-watch-r1", "watch-v1")
            payload_equivalent = []

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
                        agmina_now = runtime.clock.now_ns()
                        source_now = round(host.now * 1_000_000_000)
                        mapping = ClockMap("streambudget-watch", runtime.clock.id,
                                           agmina_now - source_now, 0, agmina_now + 60_000_000_000)
                        evidence = [host.store.get(image.evidence_id) for image in parent_request.images]
                        job = streambudget_job(
                            parent_request, session=agmina_session, clock_map=mapping, now_ns=agmina_now,
                            snapshot_ns=agmina_now, deadline_ns=agmina_now + 5_000_000_000,
                            model="fixture-model", job_id=f"r1-watch-{self.calls}",
                            sequence_by_id={item.id: item.seq for item in evidence},
                            available_by_id={item.id: item.available_at for item in evidence},
                            result_kind=ResultKind.CURRENT, max_age_ns=5_000_000_000,
                        )
                        native_body = native_pool._body(cfg, parent_request)
                        routed_body = job.payload()
                        equivalent = (native_body["messages"] == routed_body["messages"]
                                      and native_body.get("response_format")
                                      == routed_body.get("response_format"))
                        payload_equivalent.append(equivalent)
                        if not equivalent:
                            raise AssertionError("StreamBudget prompt/image payload changed at bridge")
                        fixture.outputs[job.id] = {"text": json.dumps(self.synthetic.generate(parent_request))}
                        runtime.submit(job)
                        await runtime.wait(job.id)
                        receipt = runtime.consume(job.id, consumer_id="streambudget-watch-r1")
                        status = "ok"
                        return Result(json.loads(receipt.prediction_json)["text"], None,
                                      time.monotonic() - started, job.id)
                    finally:
                        await host.ledger.settle(ticket, role=role, prices=cfg.prices, usage=None,
                                                 status=status, synthetic=True)

                async def close(self):
                    return None

            await native_pool.close()
            adapter = AgminaPool()
            host.pool = adapter
            try:
                host.register_watch(Watch(id="red", source="cam", goal="Red box visible"))
                await host.ingest_frame("cam", 1.0, red_jpeg)
                await host.drain()
                return {"alerts": len(host.alerts), "requests": host.ledger.requests,
                        "status": host.watches["red"].last_status,
                        "agmina_calls": adapter.calls,
                        "payload_equivalent": all(payload_equivalent) and bool(payload_equivalent)}
            finally:
                await host.close()

        direct_watch, agmina_watch = await asyncio.gather(run_stream_direct(), run_stream_agmina())
        if direct_watch != {"alerts": 1, "requests": 1, "status": "yes"}:
            raise AssertionError(f"Unexpected direct StreamBudget baseline: {direct_watch}")
        if {key: agmina_watch[key] for key in ("alerts", "requests", "status")} != direct_watch:
            raise AssertionError("Agmina-routed StreamBudget watch changed parent-visible behavior")
        if agmina_watch["agmina_calls"] != 1 or not agmina_watch["payload_equivalent"]:
            raise AssertionError("StreamBudget watch did not traverse the intended Agmina boundary")

        # Physical FrameRef -> Agmina observation -> existing discovery parser. No action path is
        # constructed, and the result remains a semantic hypothesis only.
        basis = Basis("ep-r1", "obs-1", "source-1", 0.0, 100.0, "local", "epoch-0",
                      "geo-0", 0, "robot", "calibration", ("entity-1",), "fixture")
        frame = FrameRef(basis, "asset-1", hashlib.sha256(red_jpeg).hexdigest(),
                         "head", 128, 128, 100.1)
        robot_map = ClockMap("robot", runtime.clock.id, 0, 0, now + 60_000_000_000)
        observation = physical_observation(frame, red_jpeg, sequence=3, clock_map=robot_map,
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

        # Exercise the parent-owned asynchronous discovery/journal/inventory path. The callback
        # creates its own Agmina coordinator inside the worker thread, avoiding cross-thread SQLite
        # access while preserving the physical application's existing reservation and writer flow.
        physical_journal = Journal(args.out / "physical-parent.sqlite", "ep-r1",
                                   max_microusd=0, max_calls=2)
        physical_worker = None
        physical_calls = []

        async def route_physical(parent_request) -> dict:
            call_root = args.out / f"physical-agmina-{len(physical_calls) + 1}"
            call_root.mkdir()
            coordinator = Runtime(config, call_root / "ledger.sqlite")
            try:
                call_now = coordinator.clock.now_ns()
                host_anchor = max(item.available_wall for item in parent_request.frames)
                mapping = ClockMap("physical-discovery", coordinator.clock.id,
                                   call_now - round(host_anchor * 1_000_000_000), 0,
                                   call_now + 60_000_000_000)
                session = coordinator.open_session("physical-discovery-r1", parent_request.task_revision)
                observations = tuple(
                    physical_observation(item, red_jpeg, sequence=index, clock_map=mapping,
                                         clock_id=coordinator.clock.id, now_ns=call_now)
                    for index, item in enumerate(parent_request.frames)
                )
                output = dict(discovery_payload,
                              request_id=parent_request.id,
                              request_fingerprint=parent_request.fingerprint)
                output["updates"] = [dict(discovery_payload["updates"][0],
                                          frame_id=parent_request.frames[-1].asset_id,
                                          region_id=parent_request.regions[-1].id)]
                job = Job(
                    id="r1-physical-async", tenant=session.tenant, session_id=session.id,
                    epoch=session.epoch, task_revision=session.task_revision, clock_id=session.clock_id,
                    model="fixture-model", operation="discovery", workload="semantic",
                    result_kind=ResultKind.HISTORICAL, observations=observations,
                    snapshot_ns=call_now, deadline_ns=call_now + 5_000_000_000,
                    payload_json=canonical({"fixture_delay_s": 0.001, "fixture_output": output}),
                )
                coordinator.submit(job)
                await coordinator.wait(job.id)
                receipt = coordinator.consume(job.id, consumer_id="physical-discovery-r1")
                physical_calls.append(job.id)
                return json.loads(receipt.prediction_json)
            finally:
                await coordinator.close()

        def physical_invoke(parent_request, deadline):
            if 100.2 >= deadline:
                raise TimeoutError("Physical discovery fixture expired before Agmina submission")
            return asyncio.run(route_physical(parent_request))

        try:
            physical_inventory = SemanticInventory(physical_journal)
            physical_cadence = ExecutiveCadence()
            physical_worker = AsyncDiscovery(
                journal=physical_journal, invoke=physical_invoke, model_name="agmina-fixture",
                enabled=True, clock=lambda: 100.2,
            )
            physical_coordinator = DiscoveryCoordinator(
                journal=physical_journal, keyframes=SemanticKeyframes(), worker=physical_worker,
                inventory=physical_inventory, executive_scheduler=physical_cadence,
            )
            async_request = physical_coordinator.observe(
                ViewSample(frame, thumbnail_descriptor(red_jpeg, frame)), now=100.2,
                task="Find a red radio", task_revision="task-v1", regions=(region,), room_id="room",
            )
            if async_request is None:
                raise AssertionError("Physical parent coordinator did not admit discovery")
            cutoff = time.monotonic() + 3
            while not physical_worker.completed and time.monotonic() < cutoff:
                await asyncio.sleep(0.005)
            delivered = physical_coordinator.poll(current=basis, now=100.3, task_revision="task-v1")
            physical_parent = {
                "calls": len(physical_calls), "delivered": len(delivered),
                "inventory_records": len(physical_inventory.records),
                "native_actions": sum(item.get("native_actions", 0) for item in delivered),
                "journal_roles": physical_journal.report()["roles"],
            }
            if physical_parent["calls"] != 1 or physical_parent["delivered"] != 1:
                raise AssertionError(f"Physical parent workflow failed: {physical_parent}")
            if physical_parent["inventory_records"] != 1 or physical_parent["native_actions"] != 0:
                raise AssertionError(f"Physical ownership boundary changed: {physical_parent}")
        finally:
            if physical_worker is not None and not physical_worker.close(1):
                raise RuntimeError("Physical parent discovery worker did not stop")
            physical_journal.close()

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
            "streambudget_parent": git_state(args.streambudget_root),
            "physical_contract": git_state(args.physical_root),
            "paid_model_calls": 0,
            "gpu_calls": 0,
            "native_actions": 0,
            "streambudget": {"job": stream_job.id, "state": stream_receipt.state.value,
                              "caption": parsed_stream.caption},
            "streambudget_watch": {"direct": direct_watch, "agmina": agmina_watch},
            "physical": {"job": physical_job.id, "state": physical_receipt.state.value,
                         "updates": len(parsed_discovery.updates),
                         "attention": len(parsed_discovery.attention),
                         "observation_source_time": observation.source_time},
            "physical_parent": physical_parent,
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
