"""Replay retained native policy queries through Agmina without inference or actuation.

The source directory must contain a result.json, queries.json, and query-NNN.npz files.
This tool verifies the retained tensor codec and source hashes, then returns each recorded
action chunk through a local Agmina backend. It does not execute the policy, simulator, or robot.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from agmina_runtime.config import Endpoint, Pool, RuntimeConfig
from agmina_runtime.contracts import Job, ModelContract, Observation, Prediction, ResultKind, Usage, canonical
from agmina_runtime.runtime import Runtime

QUERY_KEYS = {"image", "joint_position", "gripper_position", "actions"}


def fresh_dir(value: str | Path) -> Path:
    path = Path(value)
    path.mkdir(parents=False, exist_ok=False)
    return path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_recording(root: Path) -> tuple[dict, list[dict]]:
    result_path = root / "result.json"
    queries_path = root / "queries.json"
    result = json.loads(result_path.read_text(encoding="utf8"))
    query_metadata = json.loads(queries_path.read_text(encoding="utf8"))
    if not isinstance(query_metadata, list) or not query_metadata:
        raise ValueError("queries.json must contain a nonempty list")
    expected_resolution = tuple(result.get("metadata", {}).get("image_resolution", ()))
    if len(expected_resolution) != 2:
        raise ValueError("result.json must declare image_resolution")

    rows = []
    for offset, metadata in enumerate(query_metadata):
        if metadata.get("index") != offset:
            raise ValueError("Recorded query indices must be contiguous and ordered")
        path = root / f"query-{offset:03d}.npz"
        if not path.is_file():
            raise FileNotFoundError(path)
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != QUERY_KEYS:
                raise ValueError(f"Unexpected tensor keys in {path.name}")
            image = archive["image"]
            joints = archive["joint_position"]
            gripper = archive["gripper_position"]
            actions = archive["actions"]
            expected_image = (*expected_resolution, 3)
            if image.shape != expected_image or image.dtype != np.uint8:
                raise ValueError(f"Unexpected image codec in {path.name}")
            if joints.shape != (7,) or joints.dtype != np.float32:
                raise ValueError(f"Unexpected joint codec in {path.name}")
            if gripper.shape != (1,) or gripper.dtype != np.float32:
                raise ValueError(f"Unexpected gripper codec in {path.name}")
            if actions.shape != (32, 8) or actions.dtype != np.float32:
                raise ValueError(f"Unexpected action codec in {path.name}")
            if not all(np.isfinite(value).all() for value in (joints, gripper, actions)):
                raise ValueError(f"Nonfinite policy tensor in {path.name}")
            action_min = float(actions.min())
            action_max = float(actions.max())
            if not math.isclose(action_min, float(metadata["action_min"]), rel_tol=0, abs_tol=1e-7):
                raise ValueError(f"Action minimum disagrees with metadata in {path.name}")
            if not math.isclose(action_max, float(metadata["action_max"]), rel_tol=0, abs_tol=1e-7):
                raise ValueError(f"Action maximum disagrees with metadata in {path.name}")
            rows.append({
                "index": offset,
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "image_sha256": hashlib.sha256(image.tobytes(order="C")).hexdigest(),
                "joint_sha256": hashlib.sha256(joints.tobytes(order="C")).hexdigest(),
                "gripper_sha256": hashlib.sha256(gripper.tobytes(order="C")).hexdigest(),
                "action_sha256": hashlib.sha256(actions.tobytes(order="C")).hexdigest(),
                "action_min": action_min,
                "action_max": action_max,
                "actions": actions.tolist(),
            })
    return result, rows


class RecordedPolicyBackend:
    def __init__(self, rows: list[dict]):
        self.rows = {f"policy-{row['index']}": row for row in rows}
        self.calls: list[str] = []

    async def infer(self, job: Job, endpoint: Endpoint) -> Prediction:
        row = self.rows.get(job.id)
        if row is None:
            raise ValueError("Unknown recorded query")
        payload = job.payload()
        if payload != {
            "action_codec": {"datatype": "FP32", "shape": [32, 8]},
            "query_index": row["index"],
            "recording_sha256": row["sha256"],
        }:
            raise ValueError("Recorded replay payload changed")
        if len(job.observations) != 1 or job.observations[0].sha256 != row["sha256"]:
            raise ValueError("Recorded replay source binding changed")
        self.calls.append(job.id)
        return Prediction(
            payload_json=canonical({
                "actions": row["actions"],
                "datatype": "FP32",
                "shape": [32, 8],
            }),
            usage=Usage(cost_microusd=0),
        )


async def run(args: argparse.Namespace) -> dict:
    out = fresh_dir(args.out)
    result, rows = inspect_recording(args.recording)
    result_hash = sha256(args.recording / "result.json")
    queries_hash = sha256(args.recording / "queries.json")
    backend = RecordedPolicyBackend(rows)
    model = ModelContract(
        alias="recorded-policy",
        weights=f"operator-recording:{result_hash}",
        preprocessing="native-npz-v1:image-uint8-540x640x3,joints-fp32x7,gripper-fp32x1",
        output_schema="joint-position-chunk-fp32-32x8",
        sampling="recorded-output-no-inference",
    )
    endpoint = Endpoint(
        id="recorded-policy-backend",
        model=model.alias,
        pool="recorded-source",
        site="local",
        kind="mock",
        model_name="recorded-output",
        model_version=result_hash,
        service_p95_ns=10_000_000,
        margin_ns=1_000_000,
    )
    config = RuntimeConfig(
        campaign="r6-recorded-policy-replay",
        max_attempts=len(rows),
        max_microusd=0,
        max_queue=len(rows),
        max_jobs=len(rows),
        scheduler="fifo",
        cache_entries=0,
        cache_bytes=0,
        pools=(Pool(id="recorded-source"),),
        models=(model,),
        endpoints=(endpoint,),
    )
    runtime = Runtime(config, out / "ledger.sqlite", backends={endpoint.id: backend})
    replay_rows = []
    event_rows = []
    try:
        session = runtime.open_session("recorded-episode", "no-actuation-replay-v1")
        for row in rows:
            now = runtime.clock.now_ns()
            observation = Observation(
                id=f"recorded-query-{row['index']}",
                source="retained-native-policy-query",
                sequence=row["index"],
                sha256=row["sha256"],
                capture_ns=now,
                available_ns=now,
                source_time=f"recorded-query:{row['index']};capture-time-unavailable",
            )
            job = Job(
                id=f"policy-{row['index']}",
                tenant=config.tenant,
                session_id=session.id,
                epoch=session.epoch,
                task_revision=session.task_revision,
                clock_id=session.clock_id,
                model=model.alias,
                operation="recorded_policy_replay",
                workload="policy",
                result_kind=ResultKind.ACTION_PROPOSAL,
                observations=(observation,),
                snapshot_ns=now,
                deadline_ns=now + 10_000_000_000,
                max_age_ns=10_000_000_000,
                allowed_sites=("local",),
                payload_json=canonical({
                    "action_codec": {"datatype": "FP32", "shape": [32, 8]},
                    "query_index": row["index"],
                    "recording_sha256": row["sha256"],
                }),
            )
            submitted = runtime.submit(job)
            completed = await runtime.wait(job.id)
            consumed = runtime.consume(job.id, consumer_id="r6-shadow")
            runtime.record_outcome(
                job.id,
                consumer_id="r6-shadow",
                outcome="rejected",
                evidence_ref="recorded-replay:no-actuator",
            )
            prediction = json.loads(consumed.prediction_json or "{}")
            expected = {"actions": row["actions"], "datatype": "FP32", "shape": [32, 8]}
            replay_rows.append({
                "index": row["index"],
                "source_sha256": row["sha256"],
                "action_sha256": row["action_sha256"],
                "submitted_state": submitted.state.value,
                "completed_state": completed.state.value,
                "consumed_state": consumed.state.value,
                "prediction_exact": canonical(prediction) == canonical(expected),
                "endpoint": consumed.endpoint,
            })
        event_rows = runtime.store.export_events()
    finally:
        await runtime.close()

    action_flags = [row.get("action_authorized") for row in event_rows if row["kind"] == "consumed"]
    passed = (
        len(replay_rows) == len(rows)
        and backend.calls == [f"policy-{row['index']}" for row in rows]
        and all(row["prediction_exact"] for row in replay_rows)
        and action_flags == [False] * len(rows)
    )
    report = {
        "protocol": "R6 retained native-policy no-action replay",
        "outcome": "passed" if passed else "failed",
        "source_scope": result.get("scope"),
        "source_environment": result.get("environment"),
        "source_instruction": result.get("instruction"),
        "source_episode_success": bool(result.get("results")) and all(
            item.get("success") is True for item in result["results"]),
        "source_result_sha256": result_hash,
        "source_queries_sha256": queries_hash,
        "source_query_count": len(rows),
        "source_native_metadata": result.get("metadata"),
        "source_native_loop_timing": result.get("native_loop_timing"),
        "codec": {
            "image": {"shape": [540, 640, 3], "datatype": "UINT8"},
            "joint_position": {"shape": [7], "datatype": "FP32"},
            "gripper_position": {"shape": [1], "datatype": "FP32"},
            "actions": {"shape": [32, 8], "datatype": "FP32"},
            "action_space": result.get("metadata", {}).get("action_space"),
        },
        "model_inference_calls": 0,
        "network_calls": 0,
        "gpu_calls": 0,
        "native_actions": 0,
        "all_consumptions_action_authorized_false": action_flags == [False] * len(rows),
        "exact_action_roundtrips": sum(row["prediction_exact"] for row in replay_rows),
        "live_offload_qualified": False,
        "live_offload_blockers": [
            "exact checkpoint/server revision is not present in the retained receipt",
            "native metadata requires a session ID but reset/sequence semantics are not captured",
            "capture timestamps are unavailable for the retained queries",
            "this replay returns recorded outputs and does not execute the policy",
        ],
        "quality_claim": False,
        "task_success_claim": False,
        "queries": [{key: value for key, value in row.items() if key != "actions"} for row in rows],
        "replay": replay_rows,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    (out / "config.json").write_text(config.model_dump_json(indent=2) + "\n", encoding="utf8")
    with (out / "trace.jsonl").open("x", encoding="utf8") as stream:
        for row in event_rows:
            stream.write(canonical(row) + "\n")
    if not passed:
        raise RuntimeError("Recorded policy replay failed")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), indent=2))


if __name__ == "__main__":
    main()
