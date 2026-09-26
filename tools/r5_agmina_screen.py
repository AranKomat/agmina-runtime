"""Run a candidate R5 packet set through the actual StreamBudget-to-Agmina boundary.

This runner never reads evaluator labels. With the repository mock config it is a zero-cost
transport/application smoke; with a real endpoint it requires ``--allow-network`` and the
operator-supplied config's own attempt and charge caps. Outputs are retained for independent
evaluation, but this tool never declares R5 quality or held-out success.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def task_spec_sha256(case: dict) -> str:
    """Hash only the runtime-visible task specification, not evaluator labels."""
    payload = {
        "id": case["id"],
        "category": case.get("category"),
        "question": case["question"],
        "options": case["options"],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf8")
    return hashlib.sha256(encoded).hexdigest()


def provenance(case: dict, manifest_sha256: str) -> dict:
    return {
        "case_id": case["id"],
        "video_sha256": case["video_sha256"],
        "task_spec_sha256": task_spec_sha256(case),
        "preparation_manifest_sha256": manifest_sha256,
        "selected_frames": [
            {
                "evidence_id": f"{case['id']}-f{row['index']}",
                "file": row["file"],
                "timestamp": row["timestamp"],
                "sha256": row["sha256"],
                "width": row["width"],
                "height": row["height"],
            }
            for row in case["frames"]
        ],
    }


def add_parent_path(root: Path) -> None:
    sys.path.insert(0, str(root / "src"))


def load_cases(root: Path, maximum: int, case_ids: set[str] | None = None) -> list[dict]:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf8"))
    if manifest.get("outcome") != "prepared_not_qualified":
        raise ValueError("Expected a prepared, not-yet-qualified candidate manifest")
    cases = manifest.get("packets")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 64:
        raise ValueError("Candidate manifest has an invalid packet count")
    selected = []
    selected_cases = [case for case in cases if case_ids is None or case["id"] in case_ids]
    if case_ids is not None and {case["id"] for case in selected_cases} != case_ids:
        missing = sorted(case_ids - {case["id"] for case in selected_cases})
        raise ValueError(f"Unknown candidate case ID(s): {', '.join(missing)}")
    for case in selected_cases[:maximum]:
        case_id = case["id"]
        video = root / "videos" / f"{case_id}.mp4"
        if sha256(video) != case["video_sha256"]:
            raise ValueError(f"Video hash mismatch for {case_id}")
        frames = []
        for index, row in enumerate(case["frames"]):
            path = (root / "packets" / case_id / row["file"]).resolve()
            if not path.is_relative_to((root / "packets" / case_id).resolve()):
                raise ValueError("Frame path escapes candidate packet")
            if sha256(path) != row["sha256"]:
                raise ValueError(f"Frame hash mismatch for {case_id}/{row['file']}")
            frames.append({"index": index, "path": path, **row})
        if not frames or any(b["timestamp"] <= a["timestamp"]
                             for a, b in zip(frames, frames[1:])):
            raise ValueError(f"Non-increasing frame timestamps for {case_id}")
        selected.append({**case, "video_path": video, "frames": frames})
    return selected


def question_text(case: dict) -> str:
    return case["question"] + "\n" + "\n".join(
        f"{key}. {value}" for key, value in case["options"].items()
    )


async def run(args: argparse.Namespace) -> dict:
    add_parent_path(args.streambudget_root)
    from streambudget.backend import ImageInput, Request
    from streambudget.benchmark_screen import SYSTEM

    from agmina_runtime.adapters.hosts import streambudget_job
    from agmina_runtime.clocks import ClockMap
    from agmina_runtime.config import RuntimeConfig
    from agmina_runtime.contracts import ResultKind
    from agmina_runtime.runtime import Runtime

    candidate_manifest = args.candidate / "manifest.json"
    candidate_manifest_sha256 = sha256(candidate_manifest)
    manifest = json.loads(candidate_manifest.read_text(encoding="utf8"))
    cases = load_cases(args.candidate, args.max_cases,
                       set(args.case_id) if args.case_id else None)
    input_provenance = {
        "candidate_manifest_sha256": candidate_manifest_sha256,
        "source": manifest.get("source"),
        "cases": [provenance(case, candidate_manifest_sha256) for case in cases],
    }
    config = RuntimeConfig.model_validate_json(args.config.read_text(encoding="utf8"))
    if args.model not in {model.alias for model in config.models}:
        raise ValueError(f"Model alias is not registered: {args.model}")
    args.out.mkdir(parents=False, exist_ok=False)
    runtime = Runtime(config, args.out / "ledger.sqlite", allow_network=args.allow_network)
    session = None
    trials = []
    try:
        session = runtime.open_session("r5-candidate", "r5-screen-v1")
        for case in cases:
            now_ns = runtime.clock.now_ns()
            images = [ImageInput(f"{case['id']}-f{row['index']}", row["timestamp"],
                                 row["path"].read_bytes()) for row in case["frames"]]
            sequence = {image.evidence_id: index for index, image in enumerate(images)}
            available = {image.evidence_id: image.timestamp for image in images}
            request = Request("benchmark_subset", SYSTEM, question_text(case), images)
            job = streambudget_job(
                request,
                session=session,
                clock_map=ClockMap("r5-video", runtime.clock.id, 0, 0, now_ns + 3_600_000_000_000),
                now_ns=now_ns,
                snapshot_ns=now_ns,
                deadline_ns=now_ns + round(args.timeout_s * 1_000_000_000),
                model=args.model,
                job_id="r5-" + case["id"],
                sequence_by_id=sequence,
                available_by_id=available,
                result_kind=ResultKind.HISTORICAL,
            )
            submitted = runtime.submit(job)
            completed = await runtime.wait(job.id, timeout_s=args.timeout_s + 5)
            row = {
                "case_id": case["id"],
                "request_fingerprint": job.fingerprint,
                "state": completed.state.value,
                "submitted_ns": submitted.submitted_ns,
                "completed_ns": completed.completed_ns,
                "usage": completed.usage.model_dump(mode="json") if completed.usage else None,
                "prediction": json.loads(completed.prediction_json) if completed.prediction_json else None,
            }
            if completed.state.value in {"succeeded", "consumed"}:
                runtime.consume(job.id, consumer_id="r5-independent-evaluator")
                runtime.record_outcome(job.id, consumer_id="r5-independent-evaluator",
                                       outcome="rejected", evidence_ref="r5-pending-independent-evaluation")
                row["state"] = runtime.result(job.id).state.value
            trials.append(row)
    finally:
        budget = runtime.store.budget()
        events = runtime.store.export_events()
        await runtime.close()
        (args.out / "events.json").write_text(json.dumps(events, indent=2) + "\n", encoding="utf8")
        external_endpoints = {endpoint.id for endpoint in config.endpoints if endpoint.externally_billed}
        reserved = [event for event in events if event["kind"] == "attempt_reserved"]
        report = {
            "protocol": "R5 candidate application/Agmina screen",
            "outcome": "transport_completed" if trials and all(
                row["state"] == "consumed" for row in trials
            ) else "transport_incomplete",
            "candidate": str(args.candidate),
            "config": str(args.config),
            "model": args.model,
            "case_count": len(trials),
            "input_provenance": input_provenance,
            "trials": trials,
            "labels_read": False,
            "r5_qualification": "not_qualified",
            "model_attempts": len(reserved),
            "paid_model_calls": sum(1 for event in reserved if event.get("endpoint") in external_endpoints),
            "budget": budget,
            "native_actions": 0,
            "next_required": ["preserve independent label custody",
                               "evaluate under the frozen quality/latency/cost protocol",
                               "reconcile every external charge attempt"],
        }
        (args.out / "config.json").write_text(config.model_dump_json(indent=2) + "\n", encoding="utf8")
        (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--streambudget-root", type=Path, required=True)
    parser.add_argument("--model", default="semantic")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-cases", type=int, default=6, choices=range(1, 7))
    parser.add_argument("--case-id", action="append",
                        help="Run only this candidate case ID; may be repeated")
    parser.add_argument("--timeout-s", type=float, default=60.0)
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), indent=2))


if __name__ == "__main__":
    main()
