# Agmina Runtime 0.1 — validation record

**Delivery date:** 2026-09-24. These are measurements of this new standalone repository,
not the full robot harness, StreamBudget, a model, an accelerator, or a production deployment.

## Executed checks

| Check | Observed result | Scope |
|---|---|---|
| Complete delivered Python test suite | **136 passed** | Contracts, scheduling, placement, source lineage, cache, deadlines, cancellation, accounting, recovery, transport and bridge-shape fixtures |
| Python compilation | Passed | Source, tests, examples and tooling |
| Source-boundary / local-link checker | Passed | No robot/model libraries or parent application imports; Markdown file destinations |
| `doctor` | Passed | CPU configuration inventory; no credential/model/network probe |
| Async runtime demo | Passed | Synthetic policy/semantic/mapping jobs, consumer claims, old-epoch rejection |
| FIFO / EDF / least-slack replay | Passed | Synthetic independent arrivals, fixed service times, profile errors; no GPU/robot model |
| Paced multi-session load | Passed | Real asyncio pacing with synthetic backends; all offered work retained |
| Localhost service + SDK | Passed | Real TCP/HTTP, authenticated API, idempotent submit, complete result, consumer fence, epoch change, shutdown |
| Wheel build | Passed | `setuptools.build_meta.build_wheel` |
| Wheel installation outside source tree | Passed | Installed package, all 17 submodules except command entry module, doctor/demo/replay; model libraries not imported |
| Extracted release integrity + tests | Passed | Manifest check, all 136 tests and local-link/source checks on extracted ZIP |
| Ruff | **Passed** | `ruff check .` under the publication revalidation environment |

Machine-readable receipts are in [results/local_validation.json](results/local_validation.json),
[results/loopback.json](results/loopback.json), and
[results/wheel_imports.json](results/wheel_imports.json). The synthetic examples are in
[results/synthetic_replay_seed7.json](results/synthetic_replay_seed7.json),
[results/synthetic_demo.json](results/synthetic_demo.json), and
[results/synthetic_load.json](results/synthetic_load.json).

## Environment

Linux, Python 3.13.5. Installed packages used: httpx 0.28.1, Pydantic 2.13.4,
pytest 9.0.2, pytest-asyncio 1.3.0, FastAPI 0.128.2, Uvicorn 0.48.0,
setuptools 82.0.1. Development dependency ranges are declared in `pyproject.toml`;
these observations are not a portable GPU lockfile.

The wheel was installed with `--no-deps` into a new virtual environment outside the source
checkout. Existing dependency packages from `/opt/pyvenv` were exposed through an explicit
`.pth` file after the initial smoke could not find Pydantic. Package imports came from the
installed wheel, not the source directory. This checks package inclusion and entry points;
it is **not** a clean-room dependency installation or Python 3.11 portability test.

## Defects corrected during local validation

- Evidence marked `current` in one request can become `context` in another without changing its
  immutable source identity. Dependency matching now uses source identity/time, not image hash alone.
- A pending newer job cannot supersede valid old work when its own source/snapshot is invalid.
- The coordinator rechecks time before dispatch and again before backend transmission.
- Invalid local outbound packets/absent credentials settle their reservation at zero when no send
  occurred; the attempt remains counted. Remote failures retain uncertainty.
- Restart now quarantines unconfirmed attempts even if a cancelled/stale receipt concealed the
  still-running work, including the reservation-to-running crash gap.
- A journal is pinned to one tenant. Epoch changes cannot be bypassed through a tenant change.
- Expected admission/validation errors have specific HTTP handlers rather than logging raw Pydantic
  input through generic server-error traceback handling.
- The initial localhost smoke had its own helper arguments reversed; that script was corrected and
  rerun successfully. There was no robot/API effect.

These corrections are covered where applicable by the delivered regression suite. Passing the
suite is not proof that every possible concurrency, storage, provider or deployment fault is handled.

## What has not been tested

No real VLM/VLA/SAM/GraspGenX model inference, hosted model call, AMD/NVIDIA/Jetson execution,
CUDA/ROCm kernel, model batching/preemption, actual RTSP camera, network impairment appliance,
robot actuation, BEHAVIOR episode, or task/event accuracy evaluation was run.
No weights, user credentials or private datasets were downloaded or bundled.
Remote GitHub Actions and Docker were not executed. A CI definition is supplied, not a CI pass.

The full current parent repositories could not be cloned in this environment. Integration tests use
shape-level fixtures based on read-only, pinned GitHub interfaces, not the parents' full suites.
The source review pins are documented in [docs/INTEGRATION.md](docs/INTEGRATION.md).

## Reproduce

```bash
python -m pip install -e '.[dev,server]'
python tools/verify_bundle.py
python tools/validate.py --out runs/validation-new --loopback
python -m build
```

Use a new output directory. On an offline machine without Ruff,
`--allow-missing-ruff` records it as unavailable; do not reinterpret that as lint passing.
The verifier should run before source edits. Installing/editing the code legitimately changes
files; keep the original archive and manifest as the reference.

## Publication revalidation

After the archive was extracted, the scheduler placement key was rewritten from assigned lambdas
to equivalent local functions so the declared Ruff policy passes. The manifest was refreshed for
that source change. A fresh run with CPython 3.13.7 and installed development/server dependencies
then passed all 136 tests, compilation, repository checks, doctor, demo, replay, synthetic load,
Ruff, the authenticated localhost sidecar/SDK smoke, and `python -m build`. It made zero paid
model calls and zero native robot actions. This is a local publication check; the hosted CI matrix
and remote integrations remain unexecuted.

## Claims deliberately not made

There is no claimed percent speedup, event-recall preservation, reduction in robotic failures,
commercial readiness, hard-real-time guarantee, or accelerator equivalence. The synthetic replay
keeps all expired/late/background work visible and leaves model quality, GPU speedup and physical
task success null. Its useful result is a reproducible way to test those hypotheses with actual
workloads next—not proof of them.
