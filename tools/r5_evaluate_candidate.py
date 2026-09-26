"""Score an R5 candidate report after inference, outside the runtime process.

This evaluator reads private labels only after a completed transport run. It verifies that the
runtime did not read labels, binds the report and labels by hash and case ID, and scores the strict
multiple-choice response/citation contract. It never makes model calls and never qualifies R5 by
itself; independent custody and the frozen campaign thresholds remain external requirements.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

RESPONSE_KEYS = {"answer", "evidence_ids", "reason"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def prediction_value(prediction: object) -> tuple[dict | None, str | None]:
    if not isinstance(prediction, dict):
        return None, "prediction_not_object"
    if set(prediction) == RESPONSE_KEYS:
        return prediction, None
    text = prediction.get("text")
    if not isinstance(text, str) or not text:
        return None, "missing_text_payload"
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None, "text_not_strict_json"
    if not isinstance(value, dict):
        return None, "response_not_object"
    return value, None


def verify_label_audit(audit_path: Path, labels_path: Path) -> dict:
    audit = read_object(audit_path)
    labels = audit.get("labels")
    actual_hash = sha256(labels_path)
    if not isinstance(labels, dict) or labels.get("sha256") != actual_hash:
        raise ValueError("Private labels do not match the retained audit report hash")
    return {
        "audit_report_sha256": sha256(audit_path),
        "labels_sha256": actual_hash,
        "audit_held_out": labels.get("held_out"),
        "audit_case_count": labels.get("case_count"),
    }


def score_trial(trial: dict, case: dict, label: dict) -> dict:
    value, parse_error = prediction_value(trial.get("prediction"))
    allowed_answers = label.get("allowed_answers")
    if not isinstance(allowed_answers, list) or not allowed_answers or not all(
        isinstance(answer, str) for answer in allowed_answers
    ):
        raise ValueError(f"Invalid allowed answers for {trial['case_id']}")
    expected = label.get("answer")
    if expected not in allowed_answers:
        raise ValueError(f"Expected answer is not allowed for {trial['case_id']}")
    evidence = case.get("selected_frames")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"Missing selected-frame provenance for {trial['case_id']}")
    allowed_evidence = {row.get("evidence_id") for row in evidence}
    if None in allowed_evidence or len(allowed_evidence) != len(evidence):
        raise ValueError(f"Invalid evidence IDs for {trial['case_id']}")

    ids = value.get("evidence_ids") if value is not None else None
    schema_valid = bool(
        value is not None
        and set(value) == RESPONSE_KEYS
        and value.get("answer") in allowed_answers
        and isinstance(value.get("reason"), str)
        and bool(value["reason"].strip())
        and isinstance(ids, list)
        and all(isinstance(item, str) for item in ids)
    )
    citations_valid = bool(
        schema_valid
        and ids
        and len(ids) == len(set(ids))
        and set(ids) <= allowed_evidence
    )
    answer_correct = bool(schema_valid and value["answer"] == expected)
    return {
        "case_id": trial["case_id"],
        "transport_state": trial.get("state"),
        "parse_error": parse_error,
        "schema_valid": schema_valid,
        "citations_valid": citations_valid,
        "answer_correct": answer_correct,
        "cited_correct": answer_correct and citations_valid,
    }


def evaluate(report_path: Path, labels_path: Path, audit_path: Path) -> dict:
    report = read_object(report_path)
    labels = read_object(labels_path)
    label_audit = verify_label_audit(audit_path, labels_path)
    if report.get("labels_read") is not False:
        raise ValueError("Runtime report does not prove labels remained unread")
    if report.get("r5_qualification") != "not_qualified":
        raise ValueError("Evaluator expects an explicitly unqualified runtime report")
    provenance = report.get("input_provenance")
    if not isinstance(provenance, dict):
        raise ValueError("Runtime report lacks input provenance")
    cases = provenance.get("cases")
    trials = report.get("trials")
    if not isinstance(cases, list) or not isinstance(trials, list):
        raise ValueError("Runtime report lacks cases or trials")
    case_by_id = {row.get("case_id"): row for row in cases if isinstance(row, dict)}
    trial_by_id = {row.get("case_id"): row for row in trials if isinstance(row, dict)}
    if len(case_by_id) != len(cases) or len(trial_by_id) != len(trials):
        raise ValueError("Duplicate or malformed case IDs")
    if set(case_by_id) != set(trial_by_id) or not set(case_by_id) <= set(labels):
        raise ValueError("Report provenance, trials, and labels do not contain the same cases")

    rows = [score_trial(trial_by_id[case_id], case_by_id[case_id], labels[case_id])
            for case_id in case_by_id]
    total = len(rows)
    counts = {
        key: sum(bool(row[key]) for row in rows)
        for key in ("schema_valid", "citations_valid", "answer_correct", "cited_correct")
    }
    return {
        "protocol": "R5 candidate independent post-inference evaluation",
        "source_report_sha256": sha256(report_path),
        "private_labels_sha256": sha256(labels_path),
        "label_audit": label_audit,
        "labels_read_by_runtime": False,
        "labels_read_by_evaluator": True,
        "case_count": total,
        "transport_consumed": sum(row["transport_state"] == "consumed" for row in rows),
        "counts": counts,
        "rates": {key: value / total for key, value in counts.items()},
        "rows": rows,
        "r5_qualification": "not_qualified",
        "interpretation": (
            "Post-inference scoring artifact only. Qualification additionally requires independent "
            "label custody and the predeclared campaign quality, latency, cost, and charge gates."
        ),
        "model_calls": 0,
        "native_actions": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--audit-report", type=Path, required=True,
                        help="audit JSON that records the expected private-label hash")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(f"Refusing to overwrite evaluation: {args.out}")
    result = evaluate(args.report, args.labels, args.audit_report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
