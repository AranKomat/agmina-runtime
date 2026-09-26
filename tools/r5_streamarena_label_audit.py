"""Create a hash-only audit for the private StreamArena labels.

This command is run by the evaluator/operator before inference. It records no answers or
references, so the resulting audit can accompany a runtime campaign without exposing labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line]


def audit(dataset: Path, videos: list[str] | None) -> dict:
    plan_path = dataset / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf8"))
    selected = [item["video_id"] for item in plan["videos"]]
    if videos is not None:
        unknown = set(videos) - set(selected)
        if unknown:
            raise ValueError("Unknown video: " + ", ".join(sorted(unknown)))
        selected = videos
    result = {
        "protocol": "R5 StreamArena private-label hash audit",
        "dataset_plan_sha256": sha256(plan_path),
        "videos": {},
        "answers_included": False,
        "custody_claim": "operator-created hash record; labels remain outside runtime",
    }
    for video_id in selected:
        folder = (dataset / video_id).resolve()
        if not folder.is_relative_to(dataset.resolve()):
            raise ValueError("Video path escapes dataset")
        tasks_path = folder / "tasks.jsonl"
        labels_path = folder / "labels-private.jsonl"
        tasks, labels = rows(tasks_path), rows(labels_path)
        task_ids = {str(row["id"]) for row in tasks}
        label_ids = {str(row["qid"]) for row in labels}
        if task_ids != label_ids:
            raise ValueError(f"Task/label IDs differ for {video_id}")
        result["videos"][video_id] = {
            "tasks_sha256": sha256(tasks_path),
            "labels_sha256": sha256(labels_path),
            "task_count": len(tasks),
            "label_count": len(labels),
            "label_ids": sorted(label_ids),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--video", action="append", dest="videos")
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError("Refusing to overwrite a label audit")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result = audit(args.dataset, args.videos)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"out": str(args.out), "video_count": len(result["videos"]),
                      "answers_included": False}, indent=2))


if __name__ == "__main__":
    main()
