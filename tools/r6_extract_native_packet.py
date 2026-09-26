"""Extract one retained native policy packet from a Behavior-Skill trace archive.

This is offline data preparation for R6. It reads one selected trace boundary and
the three referenced RGB assets, verifies their hashes, and emits the JSON packet
accepted by ``r6_native_policy_compare.py``. It does not run inference or motion
and must not be treated as a causal live-episode observation.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import tarfile
from pathlib import Path

from agmina_runtime.adapters.native_policy import POLICY_CAMERAS, validate_native_packet


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def fresh_dir(value: str | Path) -> Path:
    path = Path(value)
    path.mkdir(parents=False, exist_ok=False)
    return path


def load_row(trace: Path, index: int) -> tuple[dict, str]:
    if index < 0:
        raise ValueError("Trace index must be nonnegative")
    for current, line in enumerate(trace.read_text(encoding="utf8").splitlines()):
        if current == index:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("Trace row must be an object")
            return row, sha256(line.encode("utf8"))
    raise IndexError(f"Trace has no row {index}")


def find_member(archive: tarfile.TarFile, uri: str) -> tarfile.TarInfo:
    matches = [member for member in archive.getmembers()
               if member.isfile() and member.name.endswith("/" + uri)]
    if len(matches) != 1:
        raise ValueError(f"Expected one archived asset for {uri}, found {len(matches)}")
    return matches[0]


def image_envelope(raw: bytes) -> tuple[dict, dict]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Install the experiments extra for retained PNG decoding") from exc
    with Image.open(io.BytesIO(raw)) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        pixels = rgb.tobytes()
    return {
        "__ndarray__": base64.b64encode(pixels).decode("ascii"),
        "dtype": "uint8",
        "shape": [height, width, 3],
    }, {"width": width, "height": height, "bytes": len(pixels)}


def run(args: argparse.Namespace) -> dict:
    out = fresh_dir(args.out)
    row, trace_row_sha256 = load_row(args.trace, args.index)
    observation = row.get("observation")
    if not isinstance(observation, dict):
        raise ValueError("Selected trace row has no observation")
    if set(observation.get("rgb", {})) != set(POLICY_CAMERAS):
        raise ValueError("Selected observation does not contain the audited R1Pro camera set")
    if not isinstance(observation.get("proprio"), list) or len(observation["proprio"]) != 61:
        raise ValueError("Selected observation does not contain native 61-element proprioception")

    rgb = {}
    assets = {}
    with tarfile.open(args.archive, "r:*") as archive:
        for camera in POLICY_CAMERAS:
            evidence = observation["rgb"][camera]
            uri = evidence.get("uri")
            if not isinstance(uri, str) or not uri.endswith(".png"):
                raise ValueError(f"Missing PNG URI for {camera}")
            member = find_member(archive, uri)
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ValueError(f"Could not read archived member {member.name}")
            raw = extracted.read()
            digest = sha256(raw)
            if digest != uri[:-4]:
                raise ValueError(f"Archived PNG hash disagrees with URI for {camera}")
            rgb[camera], image_meta = image_envelope(raw)
            assets[camera] = {
                "uri": uri,
                "member": member.name,
                "png_sha256": digest,
                **image_meta,
            }

    packet = {
        "stamp": observation["stamp"],
        "instruction": row.get("instruction"),
        "proprio": observation["proprio"],
        "rgb": rgb,
    }
    packet = validate_native_packet(packet)
    trace_hash = sha256(args.trace.read_bytes())
    archive_hash = sha256(args.archive.read_bytes())
    report = {
        "protocol": "R6 retained native packet extraction",
        "outcome": "passed",
        "source_scope": "retained-offline-only",
        "trace": {"path": str(args.trace), "sha256": trace_hash,
                  "selected_index": args.index, "selected_row_sha256": trace_row_sha256},
        "archive": {"path": str(args.archive), "sha256": archive_hash},
        "packet_sha256": sha256(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()),
        "stamp": packet["stamp"],
        "assets": assets,
        "future_leakage_claim": False,
        "live_observation_claim": False,
        "inference_calls": 0,
        "native_actions": 0,
    }
    (out / "packet.json").write_text(json.dumps(packet, indent=2) + "\n", encoding="utf8")
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
