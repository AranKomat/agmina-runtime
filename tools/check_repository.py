"""Small repository integrity check; not a substitute for Ruff or a security audit."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]


def check() -> list[str]:
    errors = []
    forbidden = {"torch", "tensorflow", "rclpy", "physical_harness", "streambudget", "cupy"}
    for path in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf8"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [name.name for name in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                if module.split(".")[0] in forbidden:
                    errors.append(f"{path.relative_to(ROOT)}:{node.lineno}: runtime depends on {module}")
    for path in sorted(ROOT.rglob("*.md")):
        if any(part.startswith(".") or part in {"build", "dist"} for part in path.relative_to(ROOT).parts):
            continue
        for destination in re.findall(r"\]\(([^\s)]+)\)", path.read_text(encoding="utf8")):
            if urlparse(destination).scheme or destination.startswith("#"):
                continue
            target = unquote(destination.split("#", 1)[0])
            if target and not (path.parent / target).exists():
                errors.append(f"{path.relative_to(ROOT)}: missing local link: {destination}")
    return errors


if __name__ == "__main__":
    failures = check()
    if failures:
        raise SystemExit("\n".join(failures))
    print("Source boundaries and local file links pass. This is not a security sandbox or Ruff.")
