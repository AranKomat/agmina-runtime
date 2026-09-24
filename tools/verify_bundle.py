"""Verify delivered files against MANIFEST.sha256. Run before edits/installing."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath

IGNORED = {".git", ".venv", ".pytest_cache", ".ruff_cache", "__pycache__", "build", "dist", "runs"}


def verify(root: Path) -> list[str]:
    expected = {}
    for line in (root/"MANIFEST.sha256").read_text(encoding="utf8").splitlines():
        sha, rel = line.split("  ", 1)
        path = PurePosixPath(rel)
        if (len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha)
                or path.is_absolute() or ".." in path.parts or rel in expected):
            raise ValueError("Malformed manifest")
        expected[rel] = sha
    errors = []
    for rel, sha in expected.items():
        path = root/rel
        if any((root/Path(*PurePosixPath(rel).parts[:i])).is_symlink()
               for i in range(1, len(PurePosixPath(rel).parts)+1)):
            errors.append("symlink: "+rel)
        elif not path.is_file():
            errors.append("missing: "+rel)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            errors.append("hash mismatch: "+rel)
    for path in root.rglob("*"):
        parts = path.relative_to(root).parts
        if any(p in IGNORED or p.endswith(".egg-info") for p in parts):
            continue
        if path.is_file() and path.relative_to(root).as_posix() not in {*expected, "MANIFEST.sha256"}:
            errors.append("unexpected: "+path.relative_to(root).as_posix())
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    failures = verify(Path(args.root).resolve())
    if failures:
        raise SystemExit("\n".join(failures))
    print("Delivered file hashes match. This is integrity checking, not publisher authentication.")
