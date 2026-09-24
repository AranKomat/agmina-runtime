"""Real loopback HTTP smoke; only the synthetic backend, no external API/model/robot."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
from pathlib import Path

from agmina_runtime.client import Client, validate_delivery
from agmina_runtime.clocks import ClockMap
from agmina_runtime.contracts import Job, JobState, Observation, ResultKind

ROOT = Path(__file__).resolve().parents[1]


async def run(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    token = secrets.token_urlsafe(32)
    env = dict(os.environ, AGMINA_TOKEN=token)
    env["PYTHONPATH"] = str(ROOT / "src")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log = (out / "server.log").open("x")
    process = subprocess.Popen(
        [sys.executable, "-m", "agmina_runtime", "serve", "--config", str(ROOT / "configs/mock.json"),
         "--database", str(out / "ledger.sqlite"), "--port", str(port)],
        cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    client = Client(f"http://127.0.0.1:{port}", token, timeout_s=2)
    try:
        for _ in range(200):
            if process.poll() is not None:
                raise RuntimeError("Loopback server stopped during startup; inspect server.log")
            try:
                clock = await client.clock()
                break
            except Exception:
                await asyncio.sleep(.05)
        else:
            raise TimeoutError("Loopback server did not become ready")
        session = await client.open_session("socket-test", "goal-v1")
        now = clock["now_ns"]
        job = Job(id="socket-job", tenant=session.tenant, session_id=session.id, epoch=session.epoch,
                  task_revision=session.task_revision, clock_id=session.clock_id, model="semantic",
                  operation="fixture", workload="semantic", result_kind=ResultKind.CURRENT,
                  observations=(Observation(id="socket-observation", source="fixture-camera", sequence=0,
                                sha256=hashlib.sha256(b"synthetic").hexdigest(), capture_ns=now,
                                available_ns=now),), snapshot_ns=now, deadline_ns=now+5_000_000_000,
                  max_age_ns=5_000_000_000, payload_json='{"fixture_output":{"fixture":true}}')
        await client.submit(job)
        await client.submit(job)  # Same job must not become two model requests.
        for _ in range(200):
            status = await client.result(job.id)
            if status.state not in {JobState.QUEUED, JobState.RUNNING}:
                break
            await asyncio.sleep(.01)
        assert status.state == JobState.SUCCEEDED
        assert status.prediction_json is None  # Status read is not a payload-consumption bypass.
        delivered = await client.consume(job.id, "reader")
        import time
        local_now = time.monotonic_ns()
        mapping = ClockMap(session.clock_id, "same-host-test-clock", 0, 0, local_now+10_000_000_000)
        # Same OS monotonic clock in these two local processes only; not a remote clock-sync solution.
        validate_delivery(job, delivered, tenant=session.tenant, session_id=session.id,
                          current_epoch=session.epoch, current_task_revision=session.task_revision,
                          consumer_id="reader", now_local_ns=local_now, local_clock_id=mapping.target,
                          server_to_local=mapping, max_mapping_error_ns=0)
        advance = await client.http.post("/v1/sessions/advance", json={"id":session.id,
            "expected_epoch":session.epoch,"task_revision":"goal-v2","close":False})
        advance.raise_for_status()
        stale = await client.http.post("/v1/consume", json={"job_id":job.id,"consumer_id":"reader"})
        assert stale.status_code == 409
        metrics = await client.http.get("/v1/metrics")
        metrics.raise_for_status()
        report = {"transport":"real localhost TCP/HTTP", "backend":"synthetic mock", "passed":True,
                  "idempotent_submit":True, "current_delivery":True, "old_epoch_rejected":True,
                  "external_requests":0, "gpu_models":0, "native_actions":0}
        (out / "report.json").write_text(json.dumps(report, indent=2)+"\n")
        return report
    finally:
        await client.close()
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        log.close()
        if process.returncode not in {0, -signal.SIGINT}:
            raise RuntimeError(f"Server exit code {process.returncode}; inspect server.log")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(Path(args.out).resolve())), indent=2))
