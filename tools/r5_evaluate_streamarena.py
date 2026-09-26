"""Evaluate a completed Agmina-backed StreamArena replay without exposing labels to runtime.

The evaluator requires a hash-only label audit created before inference. It emits task-level
booleans and aggregate metrics, but does not copy reference answers or candidate text into the
output. Exact text scoring is deliberately conservative; custom semantic judging is a separate
development experiment and is not silently substituted here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line]


def normalized(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(re.sub(r"[^\w\s]", " ", value.casefold()).split())


def audit_binding(report: dict, audit: dict, dataset: Path) -> dict:
    source = report.get("source_receipt")
    if not isinstance(source, dict) or source.get("plan_sha256") != audit.get("dataset_plan_sha256"):
        raise ValueError("Runtime source receipt does not match the label audit plan hash")
    bound = {}
    source_videos = source.get("videos", {})
    for video_id, actual_source in source_videos.items():
        expected = audit.get("videos", {}).get(video_id)
        if not expected:
            raise ValueError(f"Runtime video is absent from the label audit: {video_id}")
        folder = (dataset / video_id).resolve()
        if not folder.is_relative_to(dataset.resolve()):
            raise ValueError("Video path escapes dataset")
        if actual_source.get("tasks_sha256") != expected.get("tasks_sha256"):
            raise ValueError(f"Runtime task provenance does not match label audit: {video_id}")
        labels = folder / "labels-private.jsonl"
        tasks = folder / "tasks.jsonl"
        if sha256(labels) != expected.get("labels_sha256") or sha256(tasks) != expected.get("tasks_sha256"):
            raise ValueError(f"Dataset changed since label audit: {video_id}")
        bound[video_id] = {"labels": labels, "tasks": tasks, "expected": expected}
    if set(bound) != set(source_videos):
        raise ValueError("Label audit and runtime source videos differ")
    return bound


def score(report: dict, audit: dict, dataset: Path) -> dict:
    if report.get("labels_read") is not False:
        raise ValueError("Runtime report does not prove labels remained unread")
    if report.get("outcome") != "transport_completed":
        raise ValueError("Score only a transport-completed run; retain incomplete runs as negative evidence")
    bound = audit_binding(report, audit, dataset)
    predictions = {(str(row.get("video_id")), str(row.get("question_id"))): row
                   for row in report.get("predictions", [])}
    parent_reports = {str(row["video_id"]): row for row in report.get("parent_reports", [])}
    rows = []
    for video_id, paths in bound.items():
        labels = {str(row["qid"]): row for row in read_jsonl(paths["labels"])}
        tasks = {str(row["id"]): row for row in read_jsonl(paths["tasks"])}
        if set(labels) != set(tasks):
            raise ValueError(f"Task/label IDs differ at evaluation: {video_id}")
        alerts = (parent_reports.get(video_id) or {}).get("alerts_detail", [])
        for qid, label in labels.items():
            qtype = str(label.get("qtype", "unknown"))
            row = {"video_id": video_id, "question_id": qid, "qtype": qtype,
                   "censored": False, "semantic_correct": None, "emitted": False,
                   "timing_ok": None, "status": "missing"}
            if qtype == "Pro":
                ref = label.get("ref_sec")
                row["censored"] = isinstance(ref, (int, float)) and ref >= 600
                candidates = [alert for alert in alerts
                              if str(alert.get("watch_id")) in {qid, "q" + qid}]
                alert = candidates[0] if candidates else None
                row["emitted"] = alert is not None
                if alert is not None:
                    row["status"] = "emitted"
                    row["semantic_correct"] = normalized(alert.get("text")) == normalized(label.get("answer"))
                    if not row["censored"] and isinstance(ref, (int, float)):
                        delivered = alert.get("delivered_at")
                        row["timing_ok"] = (isinstance(delivered, (int, float))
                                             and ref - 0.5 <= delivered <= ref + 2)
                else:
                    row["status"] = "missing"
            else:
                prediction = predictions.get((video_id, qid))
                if prediction is not None:
                    row["status"] = prediction.get("status", "unknown")
                    actual = prediction.get("text", "")
                    row["semantic_correct"] = (
                        row["status"] not in {"error", "dropped", "step_limit", "no_evidence", "abstained"}
                        and normalized(actual) == normalized(label.get("answer"))
                    )
            rows.append(row)
    eligible = [row for row in rows if not row["censored"]]
    by_type = {}
    for qtype in sorted({row["qtype"] for row in rows}):
        subset = [row for row in rows if row["qtype"] == qtype and not row["censored"]]
        by_type[qtype] = {
            "count": len(subset),
            "semantic_correct": sum(row["semantic_correct"] is True for row in subset),
            "strict_correct": sum(row["semantic_correct"] is True and row["timing_ok"] is not False
                                   for row in subset),
            "emitted": sum(row["emitted"] for row in subset),
        }
    complete = all(
        report["source_receipt"]["videos"][video_id].get("task_count") == expected["label_count"]
        for video_id, data in bound.items()
        for expected in [data["expected"]]
    )
    return {
        "protocol": "R5 StreamArena independent exact-text/event evaluation",
        "outcome": "scored_complete" if complete else "scored_incomplete",
        "r5_qualification": "not_qualified",
        "label_audit_sha256": sha256(Path(audit["_path"])),
        "labels_read_by_runtime": False,
        "labels_read_by_evaluator": True,
        "task_count": len(rows),
        "eligible_count": len(eligible),
        "censored_count": len(rows) - len(eligible),
        "semantic_correct": sum(row["semantic_correct"] is True for row in eligible),
        "strict_correct": sum(row["semantic_correct"] is True and row["timing_ok"] is not False
                               for row in eligible),
        "by_type": by_type,
        "statuses": dict(Counter(row["status"] for row in rows)),
        "rows": rows,
        "scoring_note": "Conservative exact normalized text and fixed timing window; not an official score.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = read_json(args.report)
    audit_data = read_json(args.audit)
    audit_data["_path"] = str(args.audit)
    result = score(report, audit_data, args.dataset)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(json.dumps({key: result[key] for key in
                      ("outcome", "task_count", "eligible_count", "semantic_correct",
                       "strict_correct", "r5_qualification")}, indent=2))


if __name__ == "__main__":
    main()
