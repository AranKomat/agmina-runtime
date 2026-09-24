"""Reproduce local checks into a new directory; models/network not used.

Ruff is required by default. --allow-missing-ruff records it as NOT RUN instead;
that mode is useful in offline delivery environments and is not a lint pass.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--allow-missing-ruff", action="store_true")
    parser.add_argument("--loopback", action="store_true", help="Also run synthetic real localhost HTTP")
    args = parser.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, PYTHONPATH=str(ROOT/"src"))
    commands = [
        ("tests", [sys.executable, "-m", "pytest", "-q"]),
        ("compile", [sys.executable, "-m", "compileall", "-q", "src", "tests", "tools", "examples"]),
        ("repository", [sys.executable, "tools/check_repository.py"]),
        ("doctor", [sys.executable, "-m", "agmina_runtime", "doctor"]),
        ("demo", [sys.executable, "-m", "agmina_runtime", "demo", "--out", str(out/"demo")]),
        ("replay", [sys.executable, "-m", "agmina_runtime", "replay", "--seed", "7", "--profile-error",
                    "--out", str(out/"replay")]),
        ("load", [sys.executable, "-m", "agmina_runtime", "load", "--config", "configs/mock.json",
                  "--plan", "examples/mock_load.json", "--out", str(out/"load")]),
    ]
    results = []
    ruff_available = importlib.util.find_spec("ruff") is not None
    if ruff_available:
        commands.append(("ruff", [sys.executable, "-m", "ruff", "check", "."]))
    else:
        results.append({"check":"ruff", "status":"not_run_unavailable", "passed":None})
    if args.loopback:
        commands.append(("loopback", [sys.executable,"tools/loopback_smoke.py","--out",str(out/"loopback")]))
    for name, command in commands:
        started = time.monotonic()
        proc = subprocess.run(command, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=120)
        (out/f"{name}.log").write_text(proc.stdout, encoding="utf8")
        results.append({"check":name,"command":command,"exit_code":proc.returncode,
                        "passed":proc.returncode==0,"wall_s":time.monotonic()-started})
        print(f"{name}: {'PASS' if proc.returncode == 0 else 'FAIL'}", flush=True)
    report = {"python":sys.version, "checks":results, "model_calls":0, "native_actions":0,
              "all_executed_checks_pass":all(x["passed"] is not False for x in results),
              "ruff_passed":next((x["passed"] for x in results if x["check"]=="ruff"),None)}
    (out/"validation.json").write_text(json.dumps(report, indent=2)+"\n")
    if not report["all_executed_checks_pass"] or (not ruff_available and not args.allow_missing_ruff):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
