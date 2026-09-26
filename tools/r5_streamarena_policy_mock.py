"""Exercise StreamBudget's real replay policies with visual calls journaled by Agmina.

The parent replay and fixed/motion/adaptive selection logic are left unchanged. The parent
fixture creates a deterministic visual response, then the bridge submits that same response
through Agmina's zero-cost mock backend. This is an integration screen only: it is not model
quality, endpoint latency, or a benchmark result.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def add_path(root: Path) -> None:
    sys.path.insert(0, str(root / "src"))


def source_metadata(dataset: Path, video_id: str) -> dict:
    folder = (dataset / video_id).resolve()
    if not folder.is_relative_to(dataset.resolve()):
        raise ValueError("Video path escapes dataset")
    events_path = folder / "events.jsonl"
    tasks_path = folder / "tasks.jsonl"
    prep_path = folder / "preparation.json"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf8").splitlines() if line]
    tasks = [json.loads(line) for line in tasks_path.read_text(encoding="utf8").splitlines() if line]
    if len(events) != 1200 or any(row.get("kind") != "frame" for row in events):
        raise ValueError(f"Expected 1200 frame events for {video_id}")
    if any(float(row["ts"]) >= 600 for row in events):
        raise ValueError(f"Frame outside fixed 600-second prefix for {video_id}")
    return {
        "video_id": video_id,
        "events_sha256": sha256(events_path),
        "tasks_sha256": sha256(tasks_path),
        "preparation_sha256": sha256(prep_path),
        "frame_count": len(events),
        "task_count": len(tasks),
        "private_labels_present_but_unread": (folder / "labels-private.jsonl").exists(),
    }


@dataclass
class BridgeSettings:
    out: Path
    agmina_config: Path
    agmina_root: Path
    max_attempts: int


SETTINGS: BridgeSettings | None = None


class AgminaVisualBridge:
    """Parent ModelPool-compatible bridge for visual calls only."""

    def __init__(self, parent_config, parent_ledger, parent_trace, *, allow_network=False, transport=None):
        del allow_network, transport
        if SETTINGS is None:
            raise RuntimeError("Bridge settings were not initialized")
        from streambudget.backend import ModelPool

        from agmina_runtime.adapters.hosts import streambudget_job
        from agmina_runtime.clocks import ClockMap
        from agmina_runtime.config import RuntimeConfig
        from agmina_runtime.contracts import ResultKind, canonical
        from agmina_runtime.runtime import Runtime

        self._parent = ModelPool(parent_config, parent_ledger, parent_trace, allow_network=False)
        agmina_config = RuntimeConfig.model_validate_json(
            SETTINGS.agmina_config.read_text(encoding="utf8")
        )
        if agmina_config.max_attempts < SETTINGS.max_attempts:
            agmina_config = agmina_config.model_copy(update={"max_attempts": SETTINGS.max_attempts})
        self._agmina = Runtime(agmina_config, SETTINGS.out / "agmina" / "ledger.sqlite",
                               allow_network=False)
        self._session = self._agmina.open_session("r5-policy-bridge", "streamarena-policy-v1")
        self._job_count = 0
        self._visual_attempts = 0
        self._visual_count = 0
        self._errors = Counter()
        self._sequence_by_id = {}
        self._streambudget_job = streambudget_job
        self._clock_map = ClockMap
        self._result_kind = ResultKind.HISTORICAL
        self._canonical = canonical

    async def call(self, role, request):
        from streambudget.backend import Result

        # Planner/memory fixture calls are retained in the parent so this screen isolates the
        # visual serving boundary without inventing a provenance contract for text-only prompts.
        parent_result = await self._parent.call(role, request)
        if role not in {"perception", "verifier"} or not request.images:
            return parent_result

        self._visual_attempts += 1
        self._job_count += 1
        job_id = f"r5-policy-{self._job_count:05d}"
        try:
            output = parent_result.json()
            now_ns = self._agmina.clock.now_ns()
            # Evidence IDs recur across overlapping recent-frame windows. Their source sequence
            # must therefore be stable across requests, or the ledger correctly rejects identity
            # reuse with a different request-relative sequence.
            sequence = {}
            for image in request.images:
                if image.evidence_id not in self._sequence_by_id:
                    self._sequence_by_id[image.evidence_id] = len(self._sequence_by_id)
                sequence[image.evidence_id] = self._sequence_by_id[image.evidence_id]
            available = {image.evidence_id: image.timestamp for image in request.images}
            job = self._streambudget_job(
                request,
                session=self._session,
                clock_map=self._clock_map("streambudget-source", self._agmina.clock.id, 0, 0,
                                          now_ns + 3_600_000_000_000),
                now_ns=now_ns,
                snapshot_ns=now_ns,
                deadline_ns=now_ns + 60_000_000_000,
                model="semantic",
                job_id=job_id,
                sequence_by_id=sequence,
                available_by_id=available,
                result_kind=self._result_kind,
            )
            payload = job.payload()
            payload["fixture_output"] = output
            job = job.model_copy(update={"payload_json": self._canonical(payload)})
            receipt = self._agmina.submit(job)
            completed = await self._agmina.wait(job.id, timeout_s=10)
            if completed.state.value != "succeeded":
                raise RuntimeError(f"Agmina visual bridge did not succeed: {completed.state.value}")
            self._agmina.consume(job.id, consumer_id="r5-streamarena-policy-screen")
            self._agmina.record_outcome(
                job.id,
                consumer_id="r5-streamarena-policy-screen",
                outcome="rejected",
                evidence_ref="r5-policy-mock-pending-independent-evaluation",
            )
            self._visual_count += 1
            return Result(
                text=json.dumps(output, separators=(",", ":")),
                usage=parent_result.usage,
                latency_s=parent_result.latency_s,
                request_id=parent_result.request_id,
                routing={"bridge": "agmina-mock", "parent_request": receipt.request_fingerprint},
            )
        except Exception as exc:
            self._errors[type(exc).__name__] += 1
            raise

    async def close(self):
        await self._parent.close()
        await self._agmina.close()
        if SETTINGS is not None:
            bridge = {
                "protocol": "StreamBudget policy replay with Agmina visual mock bridge",
                "visual_attempts": self._visual_attempts,
                "visual_calls": self._visual_count,
                "agmina_jobs": self._job_count,
                "failed_visual_calls": self._visual_attempts - self._visual_count,
                "error_types": dict(self._errors),
                "paid_model_calls": 0,
                "native_actions": 0,
                "labels_read": False,
                "quality_qualified": False,
                "interpretation": "Selection-policy and ledger integration only; mock response path.",
            }
            (SETTINGS.out / "bridge.json").write_text(json.dumps(bridge, indent=2) + "\n",
                                                        encoding="utf8")


def mock_parent_config(path: Path, mode: str, namespace: str):
    from streambudget.config import load_config

    config = load_config(path)
    models = {
        role: model.model_copy(update={"kind": "mock", "model": "synthetic-policy-fixture"})
        for role, model in config.models.items()
    }
    return config.model_copy(update={
        "namespace": namespace,
        "models": models,
        "policy": config.policy.model_copy(update={"mode": mode}),
        "budget": config.budget.model_copy(update={"max_requests": 10000, "max_usd": None}),
    })


async def run_one(args: argparse.Namespace, video_id: str, mode: str, out: Path) -> dict:
    global SETTINGS
    out.mkdir(parents=True, exist_ok=False)
    metadata = source_metadata(args.dataset, video_id)
    add_path(args.agmina_root)
    add_path(args.streambudget_root)
    import streambudget.runtime as runtime_module
    from streambudget.replay import replay

    parent_config = mock_parent_config(args.parent_config, mode,
                                       f"agmina-r5-{mode}-{video_id}")
    SETTINGS = BridgeSettings(out, args.agmina_config, args.agmina_root, args.agmina_max_attempts)
    original_pool = runtime_module.ModelPool
    runtime_module.ModelPool = AgminaVisualBridge
    try:
        try:
            result = await replay(
                args.dataset / video_id / "events.jsonl",
                args.dataset / video_id / "tasks.jsonl",
                parent_config,
                out / "streambudget",
                timing="deterministic",
                speed=1,
                allow_network=False,
            )
        except BaseException as exc:
            bridge = json.loads((out / "bridge.json").read_text(encoding="utf8")) \
                if (out / "bridge.json").exists() else None
            partial = {
                "protocol": "StreamArena fixed-camera policy selection with Agmina visual mock bridge",
                "video_id": video_id,
                "policy_mode": mode,
                "source": metadata,
                "outcome": "incomplete",
                "error_type": type(exc).__name__,
                "agmina_bridge": bridge,
                "r5_qualification": "not_qualified",
                "paid_model_calls": 0,
                "native_actions": 0,
                "labels_read": False,
            }
            (out / "report.json").write_text(json.dumps(partial, indent=2) + "\n", encoding="utf8")
            raise
    finally:
        runtime_module.ModelPool = original_pool
    bridge = json.loads((out / "bridge.json").read_text(encoding="utf8"))
    report = {
        "protocol": "StreamArena fixed-camera policy selection with Agmina visual mock bridge",
        "video_id": video_id,
        "policy_mode": mode,
        "source": metadata,
        "parent_replay": result,
        "agmina_bridge": bridge,
        "r5_qualification": "not_qualified",
        "paid_model_calls": 0,
        "native_actions": 0,
        "labels_read": False,
        "next_required": [
            "run the same policy with a pinned real model",
            "preserve independent label custody",
            "score quality and latency under the frozen protocol",
        ],
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    if bridge["failed_visual_calls"]:
        raise RuntimeError(f"Bridge errors recorded in {out / 'bridge.json'}")
    return report


async def run(args: argparse.Namespace) -> list[dict]:
    plan = json.loads((args.dataset / "plan.json").read_text(encoding="utf8"))
    available = [entry["video_id"] for entry in plan["videos"]]
    videos = args.videos or available
    unknown = set(videos) - set(available)
    if unknown:
        raise ValueError("Unknown videos: " + ", ".join(sorted(unknown)))
    reports = []
    for video_id in videos:
        for mode in args.modes:
            out = args.out / f"{video_id}-{mode}"
            reports.append(await run_one(args, video_id, mode, out))
    (args.out / "campaign.json").write_text(json.dumps({
        "protocol": "StreamArena policy selection / Agmina mock bridge",
        "runs": [{"video_id": r["video_id"], "policy_mode": r["policy_mode"],
                  "visual_calls": r["agmina_bridge"]["visual_calls"]} for r in reports],
        "quality_qualified": False,
        "paid_model_calls": 0,
    }, indent=2) + "\n", encoding="utf8")
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--streambudget-root", type=Path, required=True)
    parser.add_argument("--agmina-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--parent-config", type=Path, required=True)
    parser.add_argument("--agmina-config", type=Path, required=True)
    parser.add_argument("--agmina-max-attempts", type=int, default=2000)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--videos", nargs="*", default=None)
    parser.add_argument("--modes", nargs="+", choices=("fixed", "motion", "adaptive"),
                        default=("fixed", "motion", "adaptive"))
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), indent=2))


if __name__ == "__main__":
    main()
