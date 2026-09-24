"""Audit a candidate StreamBudget dataset without making model calls.

The audit freezes provenance and labels metadata but deliberately does not promote development
footage to held-out R5 evidence. It accepts either the retained-frame receipt or a packet manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--labels", type=Path,
                        help="Optional independent-label file; presence is recorded, not treated as held-out")
    parser.add_argument("--run-receipt", type=Path,
                        help="Optional prior StreamBudget run receipt to summarize as development evidence")
    args = parser.parse_args()
    receipt_path = args.dataset / "receipt.json"
    manifest_path = args.dataset / "packets" / "manifest.json"
    if receipt_path.exists():
        metadata_path = receipt_path
        metadata = json.loads(receipt_path.read_text(encoding="utf8"))
        assets = []
        for entry in metadata.get("frames", []):
            path = args.dataset / entry["file"]
            data = path.read_bytes()
            observed = hashlib.sha256(data).hexdigest()
            assets.append({"file": entry["file"], "exists": True, "bytes": len(data),
                           "timestamp_s": entry["source_timestamp_s"],
                           "declared_sha256": entry["sha256"], "observed_sha256": observed,
                           "hash_matches": observed == entry["sha256"],
                           "video": entry.get("video")})
        asset_kind = "frames"
    elif manifest_path.exists():
        metadata_path = manifest_path
        metadata = json.loads(manifest_path.read_text(encoding="utf8"))
        assets = []
        for entry in metadata.get("packets", []):
            path = manifest_path.parent / entry["file"]
            data = path.read_bytes()
            observed = hashlib.sha256(data).hexdigest()
            assets.append({"id": entry["id"], "file": entry["file"], "exists": True,
                           "bytes": len(data), "declared_sha256": entry["sha256"],
                           "observed_sha256": observed, "hash_matches": observed == entry["sha256"],
                           "frames": entry.get("frames", 0), "captions": entry.get("captions", 0)})
        asset_kind = "packets"
    else:
        raise FileNotFoundError(f"Expected {receipt_path} or {manifest_path}")
    labels_path = args.labels or (args.dataset / "labels-private.json")
    labels = None
    label_obj = None
    if labels_path.exists():
        label_bytes = labels_path.read_bytes()
        label_obj = json.loads(label_bytes)
        labels = {"available": True, "held_out": False, "file": str(labels_path),
                  "sha256": hashlib.sha256(label_bytes).hexdigest(),
                  "case_count": len(label_obj.get("cases", {})) if isinstance(label_obj, dict) else None,
                  "reason": "labels are present, but this material is explicitly post-hoc development qualification"}
    else:
        labels = {"available": False, "held_out": False,
                  "reason": "no independent labels supplied"}
    development_run = None
    if args.run_receipt:
        run_receipt = json.loads(args.run_receipt.read_text(encoding="utf8"))
        trials = run_receipt.get("trials", [])
        comparisons = []
        for trial in trials:
            case_id = trial.get("case_id")
            expected = (label_obj.get("cases", {}).get(case_id, {}).get("expected")
                        if isinstance(label_obj, dict) else None)
            observed = trial.get("answer", {}).get("status")
            expected_status = "abstained" if expected == "abstained" else "ok" if expected else None
            comparisons.append({"model": trial.get("model"), "case_id": case_id,
                                "expected_answer": expected, "expected_status": expected_status,
                                "observed_status": observed,
                                "status_matches": expected_status is not None and expected_status == observed})
        development_run = {
            "receipt": str(args.run_receipt),
            "status": run_receipt.get("status"),
            "request_attempts": run_receipt.get("request_attempts"),
            "reported_usd": run_receipt.get("reported_usd"),
            "trial_count": len(trials),
            "models": sorted({row["model"] for row in comparisons if row["model"]}),
            "status_matches": sum(row["status_matches"] for row in comparisons),
            "status_match_all": bool(comparisons) and all(row["status_matches"] for row in comparisons),
            "quality_claim": False,
            "reason": "development run only; the rubric and labels were available during evaluation",
            "comparisons": comparisons,
        }
    frame_count = sum(row.get("frames", 0) for row in assets) if asset_kind == "packets" else len(assets)
    video_count = len({row.get("video") for row in assets if row.get("video") is not None})
    result = {
        "protocol": "R5 dataset audit",
        "dataset": str(args.dataset),
        "metadata_file": str(metadata_path),
        "purpose": metadata.get("purpose"),
        "status": metadata.get("status"),
        "model_calls": metadata.get("model_calls"),
        "full_archive_sha256_verified": metadata.get("full_archive_sha256_verified"),
        "asset_kind": asset_kind,
        "asset_count": len(assets),
        "frame_count": frame_count,
        "video_count": video_count,
        "all_hashes_match": bool(assets) and all(row["hash_matches"] for row in assets),
        "labels": labels,
        "development_run": development_run,
        "r5_qualification": "not_qualified",
        "next_required": ["freeze event taxonomy", "obtain an untouched held-out split",
                          "add held-out camera/view", "add negative segments",
                          "declare quality and latency thresholds"],
        "assets": assets,
    }
    args.out.mkdir(parents=False, exist_ok=False)
    (args.out / "report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
