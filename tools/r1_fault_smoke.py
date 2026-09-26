"""Exercise parent-side late-result, generation, and shutdown ownership with no model calls.

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


def git_head(root: Path) -> str | None:
    """Return the parent revision when available; source snapshots may have no Git metadata."""
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def git_state(root: Path) -> dict[str, object]:
    """Record provenance without rejecting a parent source snapshot lacking .git metadata."""
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    if head.returncode:
        return {"commit": None, "dirty": None, "metadata": "unavailable"}
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


def fixture_jpeg() -> bytes:
    from PIL import Image

    image = Image.new("RGB", (8, 8), "white")
    image_buffer = io.BytesIO()
    image.save(image_buffer, format="JPEG")
    return image_buffer.getvalue()


async def streambudget_faults(StreamConfig, StreamRuntime, Result, Watch, out: Path) -> dict:
    class BlockingPool:
        def __init__(self):
            self.entered = asyncio.Event()
            self.cancelled = False
            self.calls = 0

        async def call(self, role, request):
            self.calls += 1
            self.entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise

        async def close(self):
            return None

    # One running observation and one queued observation are both terminated by shutdown.
    shutdown_host = StreamRuntime(
        StreamConfig(scheduler={"workers": 1, "deadline_s": 2, "drain_timeout_s": 1}),
        out / "streambudget-shutdown",
    )
    shutdown_pool = BlockingPool()
    shutdown_host.pool = shutdown_pool
    try:
        shutdown_host.register_watch(Watch(id="fixture-a", source="cam-a", goal="fixture object"))
        shutdown_host.register_watch(Watch(id="fixture-b", source="cam-b", goal="fixture object"))
        jpeg = fixture_jpeg()
        await shutdown_host.ingest_frame("cam-a", 1.0, jpeg)
        await asyncio.wait_for(shutdown_pool.entered.wait(), timeout=1)
        await shutdown_host.ingest_frame("cam-b", 1.0, jpeg)
        pending_before_close = len(shutdown_host.scheduler.pending)
        await shutdown_host.close()
        shutdown = {
            "inflight_entered": True,
            "backend_cancelled": shutdown_pool.cancelled,
            "backend_calls": shutdown_pool.calls,
            "pending_before_close": pending_before_close,
            "pending_after_close": len(shutdown_host.scheduler.pending),
            "alerts_after_close": len(shutdown_host.alerts),
            "scheduler_closed": shutdown_host.scheduler.closed,
        }
    finally:
        if not shutdown_host.closed:
            await shutdown_host.close()

    class ReleasedPool:
        def __init__(self):
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def call(self, role, request):
            self.entered.set()
            await self.release.wait()
            return Result(json.dumps({
                "caption": "fixture",
                "facts": {},
                "checks": [{"watch_id": "cancelled", "status": "yes",
                            "confidence": 1.0, "detail": "fixture"}],
            }), None, 0.0, "fixture")

        async def close(self):
            return None

    # A response for a cancelled watch cannot emit an alert.
    cancelled_host = StreamRuntime(
        StreamConfig(scheduler={"workers": 1, "deadline_s": 1, "drain_timeout_s": 1}),
        out / "streambudget-cancelled-watch",
    )
    cancelled_pool = ReleasedPool()
    cancelled_host.pool = cancelled_pool
    try:
        cancelled_host.register_watch(Watch(id="cancelled", source="cam", goal="fixture object"))
        await cancelled_host.ingest_frame("cam", 1.0, fixture_jpeg())
        await asyncio.wait_for(cancelled_pool.entered.wait(), timeout=1)
        cancelled_host.cancel_watch("cancelled")
        cancelled_pool.release.set()
        await cancelled_host.drain()
        cancelled_watch = {
            "alerts": len(cancelled_host.alerts),
            "watch_done": cancelled_host.watches["cancelled"].done,
            "watch_last_status": cancelled_host.watches["cancelled"].last_status,
        }
    finally:
        await cancelled_host.close()

    class TimeoutPool:
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
            return Result(json.dumps({"caption": "late", "facts": {}, "checks": []}),
                          None, .2, "fixture")

        async def close(self):
            return None

    # The parent deadline contains a slow response and prevents a late alert.
    timeout_host = StreamRuntime(
        StreamConfig(scheduler={"workers": 1, "deadline_s": .03, "drain_timeout_s": 1}),
        out / "streambudget-timeout",
    )
    timeout_pool = TimeoutPool()
    timeout_host.pool = timeout_pool
    try:
        timeout_host.register_watch(Watch(id="timeout", source="cam", goal="fixture object"))
        await timeout_host.ingest_frame("cam", 1.0, fixture_jpeg())
        await asyncio.wait_for(timeout_pool.entered.wait(), timeout=1)
        await timeout_host.drain()
        timeout = {
            "backend_cancelled": timeout_pool.cancelled,
            "alerts": len(timeout_host.alerts),
            "job_failed_events": timeout_host.trace.counts.get("job_failed", 0),
        }
    finally:
        await timeout_host.close()

    return {"shutdown": shutdown, "cancelled_watch": cancelled_watch, "timeout": timeout}


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

        invoked_request_ids = []

        def blocked_invoke(request, deadline):
            invoked_request_ids.append(request.id)
            entered.set()
            release.wait(2)
            return semantic_response(request)

        shutdown_worker = AsyncDiscovery(journal=shutdown_journal, invoke=blocked_invoke,
                                         model_name="fixture", enabled=True)
        shutdown_worker.submit(shutdown_request)
        if not entered.wait(1):
            raise TimeoutError("shutdown fixture never entered invoke")
        pending_request, _ = physical_request(
            Basis, FrameRef, RegionRef, DiscoveryRequest,
            episode="episode-shutdown", task_revision="task-v2",
            submitted=time.monotonic(), deadline=time.monotonic() + 2,
        )
        shutdown_worker.submit(pending_request)
        close_before_release = shutdown_worker.close(.01)
        release.set()
        close_after_release = shutdown_worker.close(1)
        shutdown_records = shutdown_journal.records(AsyncDiscovery.KIND)

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
                          "reserved_calls": sum(row["event"] == "reserved" for row in shutdown_records),
                          "cancelled_pending": any(row["event"] == "cancelled_before_call"
                                                   and row["request_id"] == pending_request.id
                                                   for row in shutdown_records),
                          "invoked_request_ids": invoked_request_ids},
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
    stream = await streambudget_faults(StreamConfig, StreamRuntime, Result, Watch, args.out)
    physical = physical_faults(Journal, AsyncDiscovery, SemanticInventory, SemanticKeyframes,
                               ExecutiveCadence, DiscoveryCoordinator, Basis, FrameRef, RegionRef,
                               DiscoveryRequest, args.out)
    result = {
        "protocol": "R1 parent fault and shutdown smoke",
        "streambudget_commit": git_head(args.streambudget_root),
        "physical_commit": git_head(args.physical_root),
        "parent_provenance": {
            "streambudget": git_state(args.streambudget_root),
            "physical": git_state(args.physical_root),
        },
        "paid_model_calls": 0,
        "gpu_calls": 0,
        "native_actions": 0,
        "streambudget": stream,
        "physical": physical,
    }
    if (stream["shutdown"]["alerts_after_close"] != 0
            or not stream["shutdown"]["scheduler_closed"]
            or not stream["shutdown"]["backend_cancelled"]
            or stream["shutdown"]["backend_calls"] != 1
            or stream["shutdown"]["pending_before_close"] != 2
            or stream["shutdown"]["pending_after_close"] != 0):
        raise AssertionError("StreamBudget delivered or retained an alert after shutdown")
    if (stream["cancelled_watch"]["alerts"] != 0
            or not stream["cancelled_watch"]["watch_done"]
            or stream["cancelled_watch"]["watch_last_status"] != "unknown"):
        raise AssertionError("StreamBudget cancelled-watch result crossed the cancellation boundary")
    if (not stream["timeout"]["backend_cancelled"] or stream["timeout"]["alerts"] != 0
            or stream["timeout"]["job_failed_events"] != 1):
        raise AssertionError("StreamBudget late call was not contained by its deadline")
    if physical["late"]["error_type"] != "TimeoutError" or physical["late"]["delivered_result"]:
        raise AssertionError("Late Physical Harness result was not rejected")
    if (physical["shutdown"]["close_before_release"]
            or not physical["shutdown"]["close_after_release"]
            or not physical["shutdown"]["cancelled_pending"]
            or physical["shutdown"]["reserved_calls"] != 2
            or len(physical["shutdown"]["invoked_request_ids"]) != 1):
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
