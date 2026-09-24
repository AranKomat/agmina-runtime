"""Exercise parent-side late-result and shutdown ownership with no model calls.

This uses the actual StreamBudget runtime and Physical Harness discovery worker.  The model
callbacks are bounded local fixtures; the campaign checks parent delivery/authority behavior, not
model quality or endpoint cancellation.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import subprocess
import sys
import threading
import time
from pathlib import Path


def add_parent_paths(streambudget_root: Path, physical_root: Path) -> None:
    sys.path.insert(0, str(streambudget_root / "src"))
    sys.path.insert(0, str(physical_root))


def git_head(root: Path) -> str:
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


def wait_for_completed(worker, timeout_s: float = 2.0) -> tuple:
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        values = worker.poll()
        if values:
            return values
        time.sleep(.005)
    raise TimeoutError("fixture worker did not produce a terminal result")


def physical_request(Basis, FrameRef, RegionRef, DiscoveryRequest, *, episode: str,
                     task_revision: str, submitted: float, deadline: float):
    raw = b"r1-fault-fixture-image"
    basis = Basis(episode, "obs-r1-fault", "source-r1-fault", 1.0, submitted, "head",
                  "frame-epoch", "geometry-1", 0, "robot-1", "calibration-1", ("evidence-1",))
    frame = FrameRef(basis, "asset-r1-fault", hashlib.sha256(raw).hexdigest(), "head", 1, 1, submitted)
    region = RegionRef("region-r1-fault", frame.asset_id, (0.1, 0.1, 0.9, 0.9))
    return DiscoveryRequest(
        "request-" + task_revision + "-" + episode,
        "Find the fixture object", task_revision, basis, (frame,), (region,), (), "inventory-0",
        submitted, deadline, ("initial_view",), "room_initial",
    ), raw


def semantic_response(request: object) -> dict:
    return {
        "request_id": request.id,
        "request_fingerprint": request.fingerprint,
        "updates": [{
            "local_id": "fixture-object",
            "frame_id": request.frames[0].asset_id,
            "region_id": request.regions[0].id,
            "box": None,
            "known_id": None,
            "description": "fixture object",
            "hypotheses": ["object"],
            "status": "hypothesis",
            "retention": "retain",
            "value": {"task": 1, "future": 0, "landmark": 0, "novelty": 1,
                      "uncertainty_value": 1, "redundancy": 0, "transience": 0},
            "needs_view": False,
        }],
        "attention": [],
        "scene_summary": "fixture",
    }


async def streambudget_shutdown(StreamConfig, StreamRuntime, Result, Watch, out: Path) -> dict:
    class SlowPool:
        def __init__(self):
            self.entered = asyncio.Event()
            self.cancelled = False

        async def call(self, role, request):
            self.entered.set()
            try:
                await asyncio.sleep(.2)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            return Result(json.dumps({"caption": "late", "facts": {}, "checks": []}), None, .2, "fixture")

        async def close(self):
            return None

    host = StreamRuntime(StreamConfig(), out / "streambudget-shutdown")
    pool = SlowPool()
    host.pool = pool
    try:
        host.register_watch(Watch(id="fixture", source="cam", goal="fixture object"))
        from PIL import Image
        image = Image.new("RGB", (8, 8), "white")
        image_buffer = io.BytesIO()
        image.save(image_buffer, format="JPEG")
        await host.ingest_frame("cam", 1.0, image_buffer.getvalue())
        await asyncio.wait_for(pool.entered.wait(), timeout=1)
        await host.close()
        return {"inflight_entered": True, "backend_cancelled": pool.cancelled,
                "alerts_after_close": len(host.alerts), "scheduler_closed": host.scheduler.closed}
    finally:
        if not host.closed:
            await host.close()


def physical_faults(Journal, AsyncDiscovery, SemanticInventory, SemanticKeyframes,
                    ExecutiveCadence, DiscoveryCoordinator, Basis, FrameRef, RegionRef,
                    DiscoveryRequest, out: Path) -> dict:
    late_journal = Journal(out / "physical-late.sqlite", "episode-late", max_microusd=0, max_calls=2)
    late_worker = None
    shutdown_journal = Journal(out / "physical-shutdown.sqlite", "episode-shutdown",
                                max_microusd=0, max_calls=2)
    shutdown_worker = None
    old_journal = Journal(out / "physical-old-task.sqlite", "episode-old", max_microusd=0, max_calls=2)
    old_worker = None
    try:
        submitted = time.monotonic()
        late_request, _ = physical_request(Basis, FrameRef, RegionRef, DiscoveryRequest,
                                            episode="episode-late", task_revision="task-v1",
                                            submitted=submitted, deadline=submitted + .03)

        def late_invoke(request, deadline):
            time.sleep(.06)
            return semantic_response(request)

        late_worker = AsyncDiscovery(journal=late_journal, invoke=late_invoke, model_name="fixture",
                                     enabled=True)
        late_worker.submit(late_request)
        late_completion = wait_for_completed(late_worker)[0]
        late_worker.close()

        entered = threading.Event()
        release = threading.Event()
        submitted = time.monotonic()
        shutdown_request, _ = physical_request(Basis, FrameRef, RegionRef, DiscoveryRequest,
                                                episode="episode-shutdown", task_revision="task-v1",
                                                submitted=submitted, deadline=submitted + 2)

        def blocked_invoke(request, deadline):
            entered.set()
            release.wait(2)
            return semantic_response(request)

        shutdown_worker = AsyncDiscovery(journal=shutdown_journal, invoke=blocked_invoke,
                                         model_name="fixture", enabled=True)
        shutdown_worker.submit(shutdown_request)
        if not entered.wait(1):
            raise TimeoutError("shutdown fixture never entered invoke")
        close_before_release = shutdown_worker.close(.01)
        release.set()
        close_after_release = shutdown_worker.close(1)

        submitted = time.monotonic()
        old_request, _ = physical_request(Basis, FrameRef, RegionRef, DiscoveryRequest,
                                          episode="episode-old", task_revision="old-task",
                                          submitted=submitted, deadline=submitted + 2)
        old_worker = AsyncDiscovery(journal=old_journal, invoke=lambda request, deadline: semantic_response(request),
                                    model_name="fixture", enabled=True)
        old_worker.submit(old_request)
        end = time.monotonic() + 2
        while not old_worker.completed and time.monotonic() < end:
            time.sleep(.005)
        if not old_worker.completed:
            raise TimeoutError("old-task fixture did not complete")
        inventory = SemanticInventory(old_journal)
        cadence = ExecutiveCadence()
        coordinator = DiscoveryCoordinator(journal=old_journal, keyframes=SemanticKeyframes(),
                                           worker=old_worker, inventory=inventory,
                                           executive_scheduler=cadence)
        delivered = coordinator.poll(current=old_request.current, now=time.monotonic(),
                                     task_revision="new-task")
        old_worker.close()
        return {
            "late": {"error_type": late_completion.error_type, "delivered_result": late_completion.result is not None},
            "shutdown": {"close_before_release": close_before_release,
                          "close_after_release": close_after_release,
                          "reserved_calls": len(shutdown_journal.records(AsyncDiscovery.KIND))},
            "old_task": {"delivered": len(delivered), "historical_only": bool(delivered and delivered[0].get("historical_only")),
                          "executive_pending": len(cadence.pending), "inventory_records": len(inventory.records)},
        }
    finally:
        release.set()
        for worker in (late_worker, shutdown_worker, old_worker):
            if worker is not None:
                worker.close(1)
        late_journal.close()
        shutdown_journal.close()
        old_journal.close()


async def run(args: argparse.Namespace) -> dict:
    add_parent_paths(args.streambudget_root, args.physical_root)
    from physical_harness.core.actions import Basis
    from physical_harness.integrations.experiment.journal import Journal
    from physical_harness.perception.contracts import DiscoveryRequest, FrameRef, RegionRef
    from physical_harness.perception.discovery import AsyncDiscovery
    from physical_harness.perception.discovery_coordinator import DiscoveryCoordinator
    from physical_harness.perception.keyframes import SemanticKeyframes
    from physical_harness.reasoning.executive import ExecutiveCadence
    from physical_harness.world.inventory import SemanticInventory
    from streambudget.backend import Result
    from streambudget.config import Config as StreamConfig
    from streambudget.runtime import Runtime as StreamRuntime
    from streambudget.types import Watch

    args.out.mkdir(parents=False, exist_ok=False)
    stream = await streambudget_shutdown(StreamConfig, StreamRuntime, Result, Watch, args.out)
    physical = physical_faults(Journal, AsyncDiscovery, SemanticInventory, SemanticKeyframes,
                               ExecutiveCadence, DiscoveryCoordinator, Basis, FrameRef, RegionRef,
                               DiscoveryRequest, args.out)
    result = {
        "protocol": "R1 parent fault and shutdown smoke",
        "streambudget_commit": git_head(args.streambudget_root),
        "physical_commit": git_head(args.physical_root),
        "paid_model_calls": 0,
        "gpu_calls": 0,
        "native_actions": 0,
        "streambudget": stream,
        "physical": physical,
    }
    if stream["alerts_after_close"] != 0 or not stream["scheduler_closed"]:
        raise AssertionError("StreamBudget delivered or retained an alert after shutdown")
    if physical["late"]["error_type"] != "TimeoutError" or physical["late"]["delivered_result"]:
        raise AssertionError("Late Physical Harness result was not rejected")
    if physical["shutdown"]["close_before_release"] or not physical["shutdown"]["close_after_release"]:
        raise AssertionError("Physical shutdown did not expose in-flight ambiguity")
    if not physical["old_task"]["historical_only"] or physical["old_task"]["executive_pending"]:
        raise AssertionError("Old-task result crossed the current executive boundary")
    (args.out / "report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--streambudget-root", type=Path, required=True)
    parser.add_argument("--physical-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), indent=2))


if __name__ == "__main__":
    main()
