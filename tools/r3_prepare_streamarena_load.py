"""Prepare bounded 1/2/4/8-session real-input load plans without reading labels."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(
    dataset: Path,
    video_id: str,
    base_config: Path,
    out: Path,
    sessions: list[int],
    jobs_per_session: int,
    release_period_ms: int,
    deadline_after_ms: int,
    campaign_prefix: str,
) -> dict:
    if out.exists():
        raise ValueError("Refusing to overwrite an existing cohort directory")
    if not sessions or any(value < 1 or value > 64 for value in sessions):
        raise ValueError("Session counts must be between 1 and 64")
    if jobs_per_session < 1 or jobs_per_session > 100:
        raise ValueError("jobs-per-session must be between 1 and 100")
    if release_period_ms < 1 or deadline_after_ms < 1:
        raise ValueError("Release period and deadline must be positive")

    folder = (dataset / video_id).resolve()
    if not folder.is_relative_to(dataset.resolve()):
        raise ValueError("Video path escapes the dataset")
    preparation_path = folder / "preparation.json"
    preparation = json.loads(preparation_path.read_text(encoding="utf8"))
    frame_rows = preparation.get("frame_hashes")
    if not isinstance(frame_rows, list) or len(frame_rows) < jobs_per_session:
        raise ValueError("Preparation record does not contain enough retained frames")

    # Spread the fixed input cohort across the retained clip without consulting task labels.
    selected = []
    for index in range(jobs_per_session):
        position = round((index + 1) * (len(frame_rows) - 1) / (jobs_per_session + 1))
        row = frame_rows[position]
        path = (folder / row["file"]).resolve()
        if not path.is_relative_to(folder) or not path.is_file():
            raise ValueError("Retained frame is missing or escapes the video directory")
        digest = sha256(path)
        if digest != row.get("sha256"):
            raise ValueError(f"Retained frame hash mismatch: {row['file']}")
        selected.append({"file": row["file"], "sha256": digest, "bytes": path.read_bytes()})

    original_config = json.loads(base_config.read_text(encoding="utf8"))
    models = [model for model in original_config["models"] if model["alias"] == "vision"]
    endpoints = [endpoint for endpoint in original_config["endpoints"] if endpoint["model"] == "vision"]
    if len(models) != 1 or len(endpoints) != 1:
        raise ValueError("Base config must contain exactly one vision model and endpoint")
    reserve_microusd = endpoints[0]["reserve_microusd"]
    if type(reserve_microusd) is not int or reserve_microusd < 0:
        raise ValueError("Endpoint reserve_microusd must be a nonnegative integer")

    out.mkdir(parents=True)
    reports = {}
    for session_count in sessions:
        jobs = []
        spacing_ms = max(1, release_period_ms // session_count)
        for step in range(jobs_per_session):
            frame = selected[step]
            image = "data:image/jpeg;base64," + base64.b64encode(frame["bytes"]).decode("ascii")
            for session_index in range(session_count):
                payload = {
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Return exactly one JSON object with one key, caption, whose value "
                                "is a concise string. This is a transport load measurement."
                            ),
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Describe the visible driving scene."},
                                {"type": "image_url", "image_url": {"url": image}},
                            ],
                        },
                    ],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "load_caption",
                            "strict": True,
                            "schema": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {"caption": {"type": "string"}},
                                "required": ["caption"],
                            },
                        },
                    },
                }
                jobs.append(
                    {
                        "id": f"s{session_count}-{session_index}-{step}",
                        "session": f"camera-{session_index}",
                        "model": "vision",
                        "workload": "semantic",
                        "release_ms": step * release_period_ms + session_index * spacing_ms,
                        "deadline_after_ms": deadline_after_ms,
                        "profile_capture_lag_ms": 0,
                        "result_kind": "historical",
                        "max_age_ms": None,
                        "evidence_hashes": [frame["sha256"]],
                        "payload_json": json.dumps(payload, separators=(",", ":")),
                    }
                )

        plan = {
            "provenance": (
                f"Retained StreamArena frame cohort from {video_id}; labels unread; "
                "prepared-input transport/capacity study, not semantic quality"
            ),
            "synthetic_inputs": False,
            "jobs": jobs,
        }
        config = {
            **original_config,
            "campaign": f"{campaign_prefix}-s{session_count}",
            "max_attempts": len(jobs),
            "max_microusd": len(jobs) * reserve_microusd,
            "max_queue": max(original_config.get("max_queue", 0), len(jobs)),
            "max_jobs": max(original_config.get("max_jobs", 0), len(jobs)),
            "models": models,
            "endpoints": endpoints,
        }
        plan_path = out / f"plan-s{session_count}.json"
        config_path = out / f"config-s{session_count}.json"
        plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf8")
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf8")
        reports[str(session_count)] = {
            "jobs": len(jobs),
            "max_microusd": config["max_microusd"],
            "plan_sha256": sha256(plan_path),
            "config_sha256": sha256(config_path),
        }

    manifest = {
        "protocol": "R3 paced retained-input load cohort",
        "dataset": str(dataset.resolve()),
        "dataset_plan_sha256": sha256(dataset / "plan.json"),
        "video_id": video_id,
        "preparation_sha256": sha256(preparation_path),
        "labels_read": False,
        "source_decode_included": False,
        "jobs_per_session": jobs_per_session,
        "release_period_ms_per_session": release_period_ms,
        "deadline_after_ms": deadline_after_ms,
        "selected_frames": [
            {"file": row["file"], "sha256": row["sha256"], "bytes": len(row["bytes"])}
            for row in selected
        ],
        "cohorts": reports,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--base-config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sessions", type=int, nargs="+", default=[1, 2, 4, 8])
    parser.add_argument("--jobs-per-session", type=int, default=4)
    parser.add_argument("--release-period-ms", type=int, default=6000)
    parser.add_argument("--deadline-after-ms", type=int, default=20000)
    parser.add_argument("--campaign-prefix", default="r3-streamarena-glm-20260926")
    args = parser.parse_args()
    result = prepare(
        args.dataset,
        args.video,
        args.base_config,
        args.out,
        args.sessions,
        args.jobs_per_session,
        args.release_period_ms,
        args.deadline_after_ms,
        args.campaign_prefix,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
