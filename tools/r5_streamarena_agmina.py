"""Run a bounded StreamBudget replay with every model call routed through Agmina.

Image calls become evidence-bound Agmina jobs. Planner and memory calls become explicit
text-only query jobs. The runner never reads evaluator labels and never claims an R5 quality
result. With a mock Agmina config it is a zero-cost bridge smoke; a real config requires
``--allow-network`` and its own operator-declared budget.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def add_path(root: Path) -> None:
    sys.path.insert(0, str(root / "src"))


def align_bridge_deadline(stream_config, endpoint_timeout_s: float):
    """Keep the parent scheduler alive until the Agmina bridge can finish or fail.

    StreamBudget normally owns its own model timeout. In this runner the model call is
    replaced by an Agmina wait, so the parent deadline must cover the configured Agmina
    endpoint timeout plus the bridge's five-second wait margin.
    """
    required = endpoint_timeout_s + 5.0
    scheduler = stream_config.scheduler
    if scheduler.deadline_s >= required and scheduler.drain_timeout_s >= required:
        return stream_config
    return stream_config.model_copy(update={
        "scheduler": scheduler.model_copy(update={
            "deadline_s": max(scheduler.deadline_s, required),
            "drain_timeout_s": max(scheduler.drain_timeout_s, required),
        })
    })


def source_receipt(dataset: Path, video_id: str | None, max_events: int | None):
    plan = json.loads((dataset / "plan.json").read_text(encoding="utf8"))
    entries = plan.get("videos")
    if not isinstance(entries, list) or not entries:
        raise ValueError("StreamArena plan has no videos")
    if video_id is not None:
        entries = [entry for entry in entries if entry.get("video_id") == video_id]
        if not entries:
            raise ValueError(f"Unknown video: {video_id}")
    videos, receipt = [], {"plan_sha256": sha256(dataset / "plan.json"), "videos": {}}
    for entry in entries:
        current_id = entry["video_id"]
        folder = (dataset / current_id).resolve()
        if not folder.is_relative_to(dataset.resolve()):
            raise ValueError("Video path escapes dataset")
        events_path, tasks_path = folder / "events.jsonl", folder / "tasks.jsonl"
        events = [json.loads(line) for line in events_path.read_text(encoding="utf8").splitlines() if line]
        tasks = [json.loads(line) for line in tasks_path.read_text(encoding="utf8").splitlines() if line]
        prep = json.loads((folder / "preparation.json").read_text(encoding="utf8"))
        if any(row.get("kind") != "frame" for row in events):
            raise ValueError(f"Non-frame event in {current_id}")
        if any(type(row.get("ts")) not in (int, float) or not 0 <= row["ts"] < 600
               for row in events):
            raise ValueError(f"Invalid source timestamp in {current_id}")
        if any(b["ts"] <= a["ts"] for a, b in zip(events, events[1:])):
            raise ValueError(f"Non-increasing source timestamps in {current_id}")
        if max_events is not None:
            if max_events < 1:
                raise ValueError("max-events must be positive")
            events = events[:max_events]
        end = events[-1]["ts"] if events else -1
        tasks = [task for task in tasks if task.get("at", -1) <= end]
        hashes = {row["file"]: row["sha256"] for row in prep.get("frame_hashes", [])}
        for event in events:
            frame = (folder / event["media"]).resolve()
            if not frame.is_relative_to(folder) or not frame.is_file():
                raise ValueError("Source frame escapes dataset or is missing")
            if hashes.get(event["media"]) != sha256(frame):
                raise ValueError(f"Frame hash mismatch: {current_id}/{event['media']}")
        videos.append({"video_id": current_id, "folder": folder, "events": events, "tasks": tasks})
        receipt["videos"][current_id] = {
            "events_sha256": sha256(events_path),
            "tasks_sha256": sha256(tasks_path),
            "preparation_sha256": sha256(folder / "preparation.json"),
            "selected_event_count": len(events),
            "task_count": len(tasks),
            "task_ids": [str(task["id"]) for task in tasks],
            "private_labels_present_but_unread": (folder / "labels-private.jsonl").exists(),
        }
    return videos, receipt


class AgminaPool:
    """Duck-typed StreamBudget ModelPool backed by one Agmina session."""

    def __init__(self, parent, coordinator, session, model_alias, *, result_kind, source_end_s):
        from agmina_runtime.clocks import ClockMap

        self.parent = parent
        self.coordinator = coordinator
        self.session = session
        self.model_alias = model_alias
        self.job_prefix = f"r5-sa-{session.id}"
        self.result_kind = result_kind
        self.config = parent.config
        self.allow_network = coordinator.allow_network
        self.calls: list[dict] = []
        self.counter = 0
        # One source frame can appear in many overlapping parent windows. Keep its mapped
        # observation identity stable across those jobs instead of rebasing it to each call's
        # wall time. The replay is historical, so place the source prefix just before the
        # coordinator's current time and never claim it is current/action evidence.
        anchor_ns = coordinator.clock.now_ns()
        source_horizon_ns = max(1, round(float(source_end_s) * 1_000_000_000))
        # This is a deliberately bounded historical replay window. The CPU-only full workload
        # can take longer than an hour, so the one-hour request default is not a valid mapping
        # lifetime for this campaign. It still expires rather than becoming an unbounded map.
        self.clock_map = ClockMap("streambudget-source", coordinator.clock.id,
                                  anchor_ns - source_horizon_ns, 0,
                                  anchor_ns + 86_400_000_000_000)

    async def call(self, role, request):
        from streambudget.backend import Result

        from agmina_runtime.adapters.hosts import streambudget_job, streambudget_text_job

        self.counter += 1
        call_id = self.counter
        started = time.monotonic_ns()
        phase = "prepare"
        row = {
            "call": call_id,
            "role": role,
            "operation": request.operation,
            "image_count": len(request.images),
        }
        try:
            strict_contracts = {
                "perceive": (
                    "Return exactly the three top-level keys caption, facts, and checks. "
                    "Do not return any other top-level key, note, explanation field, or metadata."
                ),
                "verify": (
                    "Return exactly the three top-level keys caption, facts, and checks. "
                    "Do not return any other top-level key, note, explanation field, or metadata."
                ),
                "plan": (
                    "Return exactly the two top-level keys tool and arguments. "
                    "Do not return any other top-level key or explanatory metadata."
                ),
                "compact": (
                    "Return exactly the one top-level key summary. "
                    "Do not return any other top-level key or explanatory metadata."
                ),
                "ocr": (
                    "Return exactly the one top-level key text. "
                    "Do not return any other top-level key or explanatory metadata."
                ),
            }
            contract = strict_contracts.get(request.operation)
            if request.operation in {"perceive", "verify"}:
                watches = request.context.get("watches")
                if isinstance(watches, list):
                    if watches:
                        watch_ids = [watch.get("id") for watch in watches if isinstance(watch, dict)]
                        contract = (contract or "") + (
                            " Every checks[].watch_id must exactly match one of these supplied watch IDs: "
                            + json.dumps(watch_ids)
                            + ". Do not invent sentinel IDs such as none or watches."
                        )
                    else:
                        contract = (contract or "") + (
                            " The supplied watches array is empty, so checks MUST be an empty array. "
                            "Do not emit a placeholder check or invent a sentinel watch ID."
                        )
            if contract:
                request = replace(request, system=request.system.rstrip() + "\n\n" + contract)
            model_alias = self.model_alias
            if request.operation in {"perceive", "verify"}:
                configured_aliases = {model.alias for model in self.coordinator.config.models}
                if "perception" in configured_aliases:
                    model_alias = "perception"
            now_ns = self.coordinator.clock.now_ns()
            source_as_of = request.context.get("as_of", self.parent.now)
            if type(source_as_of) not in (int, float) or source_as_of < 0:
                source_as_of = self.parent.now
            snapshot = self.parent.store.snapshot(float(source_as_of))
            common = {
                "session": self.session,
                "now_ns": now_ns,
                "snapshot_ns": now_ns,
                "deadline_ns": now_ns + round(self.coordinator.endpoints[
                    next(e.id for e in self.coordinator.config.endpoints if e.model == model_alias)
                ].timeout_s * 1_000_000_000),
                "model": model_alias,
                "result_kind": self.result_kind,
            }
            evidence = []
            if request.images:
                for image in request.images:
                    item = self.parent.store.get(image.evidence_id, snapshot)
                    if item.end != float(image.timestamp):
                        raise ValueError("Parent image timestamp differs from stored evidence")
                    if item.available_at > snapshot.as_of:
                        raise ValueError("Parent image was unavailable at the frozen snapshot")
                    evidence.append(item)
                job = streambudget_job(
                    request, clock_map=self.clock_map,
                    job_id=f"{self.job_prefix}-{call_id:06d}",
                    sequence_by_id={item.id: item.seq for item in evidence},
                    available_by_id={item.id: item.available_at for item in evidence}, **common,
                )
            else:
                job = streambudget_text_job(
                    request, job_id=f"{self.job_prefix}-{call_id:06d}", **common,
                )
            row.update({
                "job_id": job.id,
                "request_fingerprint": job.fingerprint,
                "observation_ids": [obs.id for obs in job.observations],
                "observation_hashes": [obs.sha256 for obs in job.observations],
            })
            phase = "submit"
            submitted = self.coordinator.submit(job)
            phase = "wait"
            completed = await self.coordinator.wait(job.id, timeout_s=self._timeout(job))
            row.update({
                "state_before_consume": completed.state.value,
                "submitted_ns": submitted.submitted_ns,
                "completed_ns": completed.completed_ns,
                "usage": completed.usage.model_dump(mode="json") if completed.usage else None,
                "provider_request_id": completed.provider_request_id,
            })
            if completed.state.value not in {"succeeded", "consumed"}:
                raise RuntimeError(f"Agmina call {job.id} ended in {completed.state.value}: {completed.reason}")
            phase = "consume"
            consumed = self.coordinator.consume(job.id, consumer_id="streambudget-agmina")
            self.coordinator.record_outcome(
                job.id, consumer_id="streambudget-agmina", outcome="unknown",
                evidence_ref="r5-independent-evaluation-pending",
            )
            row["state"] = consumed.state.value
            phase = "decode"
            payload = json.loads(consumed.prediction_json or "{}")
            text = payload.get("text")
            if not isinstance(text, str):
                raise RuntimeError("Agmina chat result did not contain text")
            usage = None
            if consumed.usage:
                usage = {
                    "prompt_tokens": consumed.usage.input_tokens,
                    "completion_tokens": consumed.usage.output_tokens,
                }
            row["wall_s"] = (time.monotonic_ns() - started) / 1e9
            self.calls.append(row)
            return Result(text, usage, row["wall_s"], job.id)
        except Exception as exc:
            row.update({
                "state": "failed",
                "error_phase": phase,
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:240],
                "wall_s": (time.monotonic_ns() - started) / 1e9,
            })
            self.calls.append(row)
            raise

    def _timeout(self, job):
        endpoint = next(e for e in self.coordinator.config.endpoints if e.model == job.model)
        return endpoint.timeout_s + 5

    async def close(self):
        return None


class MockAgminaBackend:
    """Valid JSON fixture for the bounded no-cost bridge smoke."""

    async def infer(self, job, endpoint):
        from agmina_runtime.contracts import Prediction, Usage, canonical

        if job.operation in {"perceive", "verify"}:
            value = {"caption": "Synthetic visual fixture.", "facts": {}, "checks": []}
        elif job.operation == "plan":
            value = {"tool": "answer", "arguments": {
                "text": "Insufficient evidence in the synthetic fixture.",
                "evidence_ids": [], "abstain": True}}
        elif job.operation == "compact":
            value = {"summary": "Synthetic evidence summary."}
        elif job.operation == "ocr":
            value = {"text": "Synthetic OCR fixture."}
        else:
            value = {"text": "Synthetic answer fixture."}
        return Prediction(payload_json=canonical({"text": json.dumps(value)}),
                          usage=Usage(cost_microusd=0))


async def run(args: argparse.Namespace) -> dict:
    add_path(args.streambudget_root)
    add_path(args.agmina_root)
    from streambudget.config import load_config
    from streambudget.replay import InputEvent, TaskEvent, local_media, read_jsonl
    from streambudget.runtime import Runtime as StreamRuntime

    from agmina_runtime.config import RuntimeConfig
    from agmina_runtime.contracts import ResultKind
    from agmina_runtime.runtime import Runtime

    videos, receipt = source_receipt(args.dataset, args.video, args.max_events)
    stream_config = load_config(args.streambudget_config)
    if stream_config.semantic_embeddings:
        raise ValueError("Disable semantic embeddings for this runner; embedding RPC is not implemented")
    agmina_config = RuntimeConfig.model_validate_json(args.agmina_config.read_text(encoding="utf8"))
    if args.model not in {model.alias for model in agmina_config.models}:
        raise ValueError(f"Agmina model alias is not registered: {args.model}")
    if not args.allow_network and any(e.kind != "mock" for e in agmina_config.endpoints):
        # Runtime will reject these jobs anyway; fail before touching the campaign output.
        raise ValueError("Real endpoints require --allow-network")
    if args.out.exists():
        raise ValueError("Output directory already exists")
    args.out.mkdir(parents=True)
    coordinator = Runtime(agmina_config, args.out / "agmina-ledger", allow_network=args.allow_network)
    endpoint_ids = [e.id for e in agmina_config.endpoints if e.model == args.model]
    if len(endpoint_ids) != 1:
        raise ValueError("Exactly one Agmina endpoint must serve the selected model")
    used_models = {args.model}
    if "perception" in {model.alias for model in agmina_config.models}:
        used_models.add("perception")
    bridge_timeouts = [e.timeout_s for e in agmina_config.endpoints if e.model in used_models]
    if not bridge_timeouts:
        raise ValueError("No Agmina endpoint timeout found for the selected bridge models")
    stream_config = align_bridge_deadline(stream_config, max(bridge_timeouts))
    if all(e.kind == "mock" for e in agmina_config.endpoints):
        coordinator.backends[endpoint_ids[0]] = MockAgminaBackend()
    predictions, all_calls = [], []
    try:
        for video in videos:
            events_path, tasks_path = video["folder"] / "events.jsonl", video["folder"] / "tasks.jsonl"
            inputs = [InputEvent.model_validate(row) for row in read_jsonl(events_path)]
            tasks = [TaskEvent.model_validate(row) for row in read_jsonl(tasks_path)]
            if args.max_events is not None:
                inputs = inputs[:args.max_events]
                end = inputs[-1].ts if inputs else -1
                tasks = [task for task in tasks if task.at <= end]
            work = args.out / video["video_id"]
            work.mkdir()
            parent = StreamRuntime(stream_config, work, allow_network=False)
            await parent.pool.close()
            session = coordinator.open_session("r5-streamarena-" + video["video_id"],
                                               "streamarena-agmina-v1")
            bridge = AgminaPool(parent, coordinator, session, args.model,
                                 result_kind=ResultKind.HISTORICAL,
                                 source_end_s=video["events"][-1]["ts"] if video["events"] else 0)
            parent.pool = bridge
            parent.specialists.pool = bridge
            parent.start()
            pending: set[asyncio.Task] = set()
            origin = time.monotonic()
            try:
                schedule = [(event.at, 1, index, event) for index, event in enumerate(inputs)]
                schedule += [(task.at, 0 if task.type == "watch" else 2, index, task)
                             for index, task in enumerate(tasks)]
                schedule.sort(key=lambda row: row[:3])

                async def ask(task):
                    try:
                        answer = await parent.ask(task.question, task.source, as_of=task.at,
                                                  question_id=task.id)
                        row = asdict(answer)
                    except Exception as exc:
                        row = {"question_id": task.id, "text": "", "status": "error",
                               "error_type": type(exc).__name__, "evidence_ids": [], "as_of": task.at}
                    row["video_id"] = video["video_id"]
                    row["delivered_at"] = max(parent.now, parent.timeline_clock()) if parent.timeline_clock else parent.now
                    predictions.append(row)
                    with (work / "predictions.jsonl").open("a", encoding="utf8") as handle:
                        handle.write(json.dumps(row) + "\n")

                for at, _, index, event in schedule:
                    parent.advance(at)
                    if isinstance(event, InputEvent):
                        if event.kind == "frame":
                            if not event.media:
                                raise ValueError("Frame event requires media")
                            data = local_media(events_path.parent, event.media).read_bytes()
                            await parent.ingest_frame(event.source, event.ts, data,
                                                      available_at=event.at, schedule=True)
                        else:
                            await parent.ingest_signal(event.source, event.ts, event.kind, event.text,
                                                       event.data, start=event.start,
                                                       available_at=event.at, schedule=True)
                    elif event.type == "watch":
                        from streambudget.types import Watch
                        parent.register_watch(Watch.model_validate({**event.watch, "id": event.id,
                                                                      "source": event.source,
                                                                      "created_at": event.at}))
                    elif event.type == "cancel":
                        parent.cancel_watch(event.id)
                    else:
                        await parent.drain()
                        task = asyncio.create_task(ask(event))
                        pending.add(task)
                        task.add_done_callback(pending.discard)
                    await parent.tick(at)
                    if args.deterministic:
                        await parent.drain()
                await parent.drain()
                if pending:
                    await asyncio.gather(*list(pending))
            finally:
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for call in bridge.calls:
                    call["video_id"] = video["video_id"]
                all_calls.extend(bridge.calls)
                parent_report = parent.report()
                parent_report.update({"video_id": video["video_id"],
                                      "elapsed_wall_s": time.monotonic() - origin,
                                      "agmina_call_count": len(bridge.calls),
                                      "agmina_backed": True})
                (work / "run.json").write_text(json.dumps(parent_report, indent=2) + "\n",
                                                encoding="utf8")
                await parent.close()
    finally:
        agmina_events = coordinator.store.export_events()
        agmina_budget = coordinator.store.budget()
        await coordinator.close()
    parent_job_failed = {
        parent["video_id"]: parent.get("trace_counts", {}).get("job_failed", 0)
        for parent in [
            json.loads((args.out / video["video_id"] / "run.json").read_text(encoding="utf8"))
            for video in videos
        ]
    }
    parent_job_failed_count = sum(parent_job_failed.values())
    report = {
        "protocol": "StreamArena full-workload replay with Agmina-backed image and query calls",
        "outcome": "transport_completed" if all_calls and all(
            call.get("state") == "consumed" for call in all_calls) and parent_job_failed_count == 0
            else "transport_incomplete",
        "dataset": str(args.dataset.resolve()),
        "source_receipt": receipt,
        "model": args.model,
        "video_count": len(videos),
        "model_call_count": len(all_calls),
        "calls_by_role": {role: sum(call["role"] == role for call in all_calls)
                           for role in sorted({call["role"] for call in all_calls})},
        "calls": all_calls,
        "parent_job_failed_count": parent_job_failed_count,
        "parent_job_failed_by_video": parent_job_failed,
        "predictions": predictions,
        "parent_reports": [
            json.loads((args.out / video["video_id"] / "run.json").read_text(encoding="utf8"))
            for video in videos
        ],
        "agmina_budget": agmina_budget,
        "agmina_event_count": len(agmina_events),
        "labels_read": False,
        "native_actions": 0,
        "r5_qualification": "not_qualified",
        "interpretation": [
            "This verifies full-workload request routing and accounting only.",
            "Independent labels were not opened and no quality score is reported.",
            "Real endpoint runs require charge reconciliation before any quality claim.",
        ],
    }
    (args.out / "source_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf8")
    (args.out / "agmina-events.json").write_text(json.dumps(agmina_events, indent=2) + "\n", encoding="utf8")
    (args.out / "agmina-config.json").write_text(agmina_config.model_dump_json(indent=2) + "\n",
                                                   encoding="utf8")
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--streambudget-root", type=Path, required=True)
    parser.add_argument("--streambudget-config", type=Path, required=True)
    parser.add_argument("--agmina-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--agmina-config", type=Path, required=True)
    parser.add_argument("--model", default="semantic")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--video")
    parser.add_argument("--max-events", type=int)
    parser.add_argument("--deterministic", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), indent=2))


if __name__ == "__main__":
    main()
