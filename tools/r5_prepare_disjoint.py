"""Prepare a fresh, disjoint R5 packet candidate without making model calls.

The runtime manifest deliberately excludes evaluator answers. This is data preparation only:
the resulting split is not an R5 quality result until an authorized Agmina-backed model run is
performed and the evaluator labels are applied independently.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
from collections import defaultdict
from pathlib import Path

import av
import httpx

MMVU_REVISION = "b937f414a87e9012acba49d95669020b24fa9ee9"
SEED = "agmina-r5-heldout-20260925-v1"
FRAME_COUNT = 16
MAX_SIDE = 768


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf8")
    temporary.replace(path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_rows(url: str) -> list[dict]:
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        rows = response.json()
    result = []
    for row in rows:
        if row.get("question_type") != "multiple-choice":
            continue
        options = {key: value for key, value in row["choices"].items() if value}
        if row["answer"] not in options:
            raise ValueError("Source answer is not an offered option")
        result.append({
            "id": "MMVU-" + row["id"],
            "source_id": row["id"],
            "category": row["metadata"]["subject"],
            "video_key": row["video"],
            "video_url": row["video"].replace("/resolve/main/", f"/resolve/{MMVU_REVISION}/"),
            "question": row["question"],
            "options": options,
            "answer": row["answer"],
        })
    return result


def excluded_ids(manifest: Path) -> set[str]:
    data = json.loads(manifest.read_text(encoding="utf8"))
    return {str(row["id"]) for row in data.get("packets", []) if row.get("id") != "probe"}


def choose(rows: list[dict], excluded: set[str], count: int) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["id"] not in excluded:
            groups[row["category"]].append(row)
    for values in groups.values():
        values.sort(key=lambda row: hashlib.sha256(f"{SEED}|{row['id']}".encode()).hexdigest())
    categories = sorted(groups, key=lambda value: hashlib.sha256(f"{SEED}|{value}".encode()).hexdigest())
    selected: list[dict] = []
    used_videos: set[str] = set()
    while len(selected) < count:
        before = len(selected)
        for category in categories:
            while groups[category] and groups[category][0]["video_key"] in used_videos:
                groups[category].pop(0)
            if groups[category]:
                row = groups[category].pop(0)
                selected.append(row)
                used_videos.add(row["video_key"])
                if len(selected) == count:
                    return selected
        if len(selected) == before:
            raise ValueError("Not enough disjoint source cases")
    return selected


def download(url: str, destination: Path) -> str:
    temporary = destination.with_suffix(destination.suffix + ".partial")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, timeout=300, follow_redirects=True) as response:
        response.raise_for_status()
        with temporary.open("wb") as stream:
            for chunk in response.iter_bytes(1024 * 1024):
                stream.write(chunk)
    temporary.replace(destination)
    return digest(destination)


def sample_video(video: Path, folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    with av.open(str(video)) as container:
        stream = container.streams.video[0]
        first = next(container.decode(stream))
        if first.pts is None:
            raise ValueError("Video has no presentation timestamps")
        start = float(first.pts * stream.time_base)
        duration = (float(stream.duration * stream.time_base) if stream.duration
                    else float(container.duration / av.time_base))
        rate = float(stream.average_rate or 30)
        end = max(start, start + duration - 1 / rate)
        frames = []
        for index in range(FRAME_COUNT):
            target = start + (end - start) * index / (FRAME_COUNT - 1)
            container.seek(int(target / stream.time_base), stream=stream, backward=True)
            chosen = None
            for frame in container.decode(stream):
                if frame.pts is None:
                    raise ValueError("Sampled frame has no presentation timestamp")
                chosen = frame
                if float(frame.pts * stream.time_base) + 1e-7 >= target:
                    break
            if chosen is None:
                raise ValueError("No frame available at sample target")
            timestamp = float(chosen.pts * stream.time_base) - start
            image = chosen.to_image().convert("RGB")
            image.thumbnail((MAX_SIDE, MAX_SIDE))
            content = io.BytesIO()
            image.save(content, format="JPEG", quality=85)
            name = f"{index:04}.jpg"
            (folder / name).write_bytes(content.getvalue())
            frames.append({"file": name, "timestamp": timestamp,
                           "sha256": hashlib.sha256(content.getvalue()).hexdigest(),
                           "width": image.width, "height": image.height})
    return {"duration_s": duration, "frames": frames, "sampling": "uniform video PTS"}


def prepare(args: argparse.Namespace) -> dict:
    out = args.out
    out.mkdir(parents=False, exist_ok=False)
    evaluator = out / "evaluator"
    evaluator.mkdir()
    excluded = excluded_ids(args.exclude_manifest)
    rows = fetch_rows(args.metadata_url)
    selected = choose(rows, excluded, args.count)
    save(evaluator / "selection-private.json", selected)
    save(evaluator / "labels-private.json", {
        row["id"]: {"answer": row["answer"], "allowed_answers": list(row["options"])}
        for row in selected
    })

    packets = []
    acquired = []
    for row in selected:
        video = out / "videos" / f"{row['id']}.mp4"
        started = time.monotonic()
        video_sha = download(row["video_url"], video)
        packet = sample_video(video, out / "packets" / row["id"])
        packet["id"] = row["id"]
        save(out / "packets" / row["id"] / "frames.json", packet)
        packets.append({"id": row["id"], "category": row["category"],
                        "question": row["question"], "options": row["options"],
                        "video_sha256": video_sha, "frames": packet["frames"]})
        acquired.append({"id": row["id"], "video_sha256": video_sha,
                         "bytes": video.stat().st_size,
                         "elapsed_s": time.monotonic() - started})
    manifest = {
        "protocol": "R5 fresh disjoint held-out candidate preparation",
        "outcome": "prepared_not_qualified",
        "model_calls": 0,
        "source": {"dataset": "MMVU", "revision": MMVU_REVISION,
                    "metadata_url": args.metadata_url, "selection_seed": SEED,
                    "excluded_manifest": str(args.exclude_manifest),
                    "excluded_manifest_sha256": digest(args.exclude_manifest),
                    "excluded_case_count": len(excluded)},
        "packet_count": len(packets),
        "packets": packets,
        "evaluator_labels_outside_runtime_manifest": True,
        "next_required": ["independent label custody", "Agmina-backed model run",
                           "fixed latency/cost thresholds", "quality evaluation"],
    }
    save(out / "manifest.json", manifest)
    save(out / "acquisition.json", {"status": "complete", "packets": acquired,
                                    "evaluator_labels_sha256": digest(evaluator / "labels-private.json")})
    return {"out": str(out), "packet_count": len(packets), "excluded_case_count": len(excluded),
            "ids": [row["id"] for row in selected], "model_calls": 0,
            "outcome": "prepared_not_qualified"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--exclude-manifest", type=Path, required=True)
    parser.add_argument("--metadata-url", default=(
        f"https://huggingface.co/datasets/yale-nlp/MMVU/resolve/{MMVU_REVISION}/validation.json"))
    parser.add_argument("--count", type=int, default=6, choices=range(1, 13))
    parser.add_argument("--academic-use-confirmed", action="store_true")
    args = parser.parse_args()
    if not args.academic_use_confirmed:
        parser.error("Explicit local research-use confirmation is required")
    print(json.dumps(prepare(args), indent=2))


if __name__ == "__main__":
    main()
