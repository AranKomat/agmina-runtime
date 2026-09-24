from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
from pathlib import Path

from .config import Endpoint, Pool, RuntimeConfig
from .contracts import Job, ModelContract, Observation, ResultKind, canonical
from .replay import Trace, replay, synthetic_trace
from .runtime import Runtime
from .telemetry import summarize


def write_json(path, value):
    with Path(path).open("x", encoding="utf8") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def fresh_dir(value):
    path = Path(value)
    path.mkdir(parents=True, exist_ok=False)
    return path


def demo_config():
    models = tuple(ModelContract(alias=k, weights="synthetic-v1", preprocessing="fixture-v1",
                                 output_schema="fixture-json-v1", sampling="deterministic")
                   for k in ("policy", "semantic", "mapping"))
    endpoints = tuple(Endpoint(id=k+"-worker", model=k, pool="shared-device", site="local", kind="mock",
                               service_p95_ns=1_000_000, margin_ns=0) for k in ("policy", "semantic", "mapping"))
    return RuntimeConfig(pools=(Pool(id="shared-device"),), models=models, endpoints=endpoints,
                         campaign="synthetic-demo", max_attempts=20)


def fixture_job(session, now, *, jid, model="semantic", delay=.001, deadline_s=2., historical=False):
    blob = b"explicit fixture evidence"
    obs = Observation(id="obs-"+jid, source="fixture", sequence=0,
                      sha256=hashlib.sha256(blob).hexdigest(), capture_ns=now, available_ns=now)
    return Job(id=jid, tenant=session.tenant, session_id=session.id, epoch=session.epoch,
               task_revision=session.task_revision, clock_id=session.clock_id, model=model,
               operation="fixture", workload=model, result_kind=ResultKind.HISTORICAL if historical else
               (ResultKind.ACTION_PROPOSAL if model == "policy" else ResultKind.CURRENT), observations=(obs,),
               snapshot_ns=now, deadline_ns=now+int(deadline_s*1e9), max_age_ns=int(deadline_s*1e9),
               payload_json=canonical({"fixture_delay_s": delay, "fixture_output": {"fixture": True}}))


async def demo(out: Path):
    config = demo_config()
    write_json(out/"config.json", config.model_dump(mode="json"))
    runtime = Runtime(config, out/"ledger.sqlite")
    try:
        s = runtime.open_session("robot", "search-v1")
        video = runtime.open_session("camera", "watch-v1")
        now = runtime.clock.now_ns()
        # Nonpreemptive background is intentionally started first to expose blocking, not hide it.
        runtime.submit(fixture_job(video, now, jid="background", model="mapping", delay=.025))
        runtime.tick()
        runtime.submit(fixture_job(s, now, jid="policy", model="policy", delay=.002))
        runtime.submit(fixture_job(video, now, jid="inventory", delay=.005, historical=True))
        for jid in ("background", "policy", "inventory"):
            await runtime.wait(jid)
        runtime.consume("policy", consumer_id="native-shadow")
        runtime.record_outcome("policy", consumer_id="native-shadow", outcome="rejected",
                               evidence_ref="fixture:no-actuator")
        runtime.advance_session(video.id, expected_epoch=video.epoch, task_revision="watch-v2")
        try:
            runtime.consume("inventory", consumer_id="video")
        except PermissionError:
            runtime.store.event(runtime.clock.now_ns(), "fixture_old_epoch_rejection_confirmed")
        report = summarize(runtime)
        report.update(synthetic=True, models_loaded=False, native_actions=0, paid_api_calls=0)
        write_json(out/"report.json", report)
        with (out/"trace.jsonl").open("x") as f:
            for event in runtime.store.export_events():
                f.write(canonical(event)+"\n")
        write_json(out/"receipts.json", [r.model_dump(mode="json") for _, r in runtime.store.jobs(config.tenant)])
    finally:
        await runtime.close()
    return report


async def probe(args):
    """Bounded identical-input transport/latency test. NO model quality or task evaluation."""
    out = fresh_dir(args.out)
    cfg = RuntimeConfig.model_validate_json(Path(args.config).read_text())
    data = json.loads(Path(args.packet).read_text())
    if set(data) != {"payload", "observations"}:
        raise ValueError("Packet requires payload and observations")
    runtime = Runtime(cfg, out/"ledger.sqlite", allow_network=args.allow_network)
    try:
        s = runtime.open_session("probe", "frozen-input")
        for i in range(args.count):
            now = runtime.clock.now_ns()
            observations = tuple(Observation(id="input-"+str(j), source=o["source"], sequence=j,
                sha256=o["sha256"], capture_ns=now, available_ns=now) for j, o in enumerate(data["observations"]))
            # Each probe is a new capture-representation only for latency input replay; avoid identity collision.
            observations = tuple(o.model_copy(update={"id": f"input-{i}-{j}"}) for j,o in enumerate(observations))
            job = Job(id=f"probe-{i}", tenant=cfg.tenant, session_id=s.id, epoch=s.epoch,
                      task_revision=s.task_revision, clock_id=s.clock_id, model=args.model,
                      operation="frozen_input_probe", workload="query", result_kind=ResultKind.HISTORICAL,
                      observations=observations, snapshot_ns=now, deadline_ns=now+args.deadline_ms*1_000_000,
                      payload_json=canonical(data["payload"]))
            runtime.submit(job)
            r = await runtime.wait(job.id, timeout_s=args.deadline_ms/1000+5)
            if r.state.value == "succeeded":
                runtime.consume(job.id, consumer_id="probe")
            else:
                break  # Remaining declared calls not silently sent after a failure.
        write_json(out/"report.json", {**summarize(runtime), "input_replay_not_live_video": True,
                                      "cold_first_run_separate": True})
        write_json(out/"config.redacted.json", cfg.model_dump(mode="json"))
        with (out/"trace.jsonl").open("x") as f:
            for row in runtime.store.export_events():
                f.write(canonical(row)+"\n")
    finally:
        await runtime.close()
    print(out)


def bounded_deadline(text):
    value = int(text)
    if not 1 <= value <= 300000:
        raise argparse.ArgumentTypeError("deadline must be 1..300000 milliseconds")
    return value


def main():
    parser = argparse.ArgumentParser(description="Agmina continuous-inference runtime foundation")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="No network, credentials, models or GPU access")
    ledger_parser = sub.add_parser("ledger", help="Read existing accounting without resetting it")
    ledger_parser.add_argument("--database", required=True)
    d = sub.add_parser("demo", help="Synthetic async runtime demonstration")
    d.add_argument("--out", required=True)
    r = sub.add_parser("replay", help="Causal discrete-event comparison; not a robot/GPU benchmark")
    r.add_argument("--out", required=True)
    r.add_argument("--trace")
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--robots", type=int, default=2)
    r.add_argument("--cameras", type=int, default=4)
    r.add_argument("--seconds", type=int, default=5)
    r.add_argument("--profile-error", action="store_true")
    p = sub.add_parser("probe", help="Explicit bounded endpoint calls, never automatic retries")
    p.add_argument("--config", required=True)
    p.add_argument("--packet", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--count", type=int, default=1, choices=range(1, 21))
    p.add_argument("--deadline-ms", type=bounded_deadline, default=30000)
    p.add_argument("--allow-network", action="store_true")
    load_parser = sub.add_parser("load", help="Paced real/test endpoint load; source clock advances")
    load_parser.add_argument("--config", required=True)
    load_parser.add_argument("--plan", required=True)
    load_parser.add_argument("--out", required=True)
    load_parser.add_argument("--allow-network", action="store_true")
    s = sub.add_parser("serve", help="Single-tenant authenticated loopback sidecar")
    s.add_argument("--config", required=True)
    s.add_argument("--database", required=True)
    s.add_argument("--port", type=int, default=8766)
    s.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    if args.command == "doctor":
        print(json.dumps({"python": sys.version.split()[0], "platform": platform.system(),
                          "httpx": importlib.metadata.version("httpx"),
                          "pydantic": importlib.metadata.version("pydantic"),
                          "models_loaded": False, "network_probed": False,
                          "gpu_backends_qualified": [], "native_actions_enabled": False,
                          "next": "Run demo and replay; then explicit authorized endpoint probes."}, indent=2))
    elif args.command == "ledger":
        import sqlite3
        path = Path(args.database).resolve(strict=True)
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        cfg = json.loads(db.execute("SELECT value FROM meta WHERE key='budget'").fetchone()[0])
        rows = [dict(r) for r in db.execute("SELECT * FROM attempts")]
        quarantine = [dict(r) for r in db.execute("SELECT * FROM quarantines")]
        print(json.dumps({"caps":cfg,"attempts":rows,"quarantined_pools":quarantine},indent=2))
        db.close()
    elif args.command == "demo":
        out = fresh_dir(args.out)
        asyncio.run(demo(out))
        print(out)
    elif args.command == "replay":
        out = fresh_dir(args.out)
        trace = Trace.model_validate_json(Path(args.trace).read_text()) if args.trace else synthetic_trace(
            seed=args.seed, seconds=args.seconds, robots=args.robots, cameras=args.cameras,
            profile_error=args.profile_error)
        write_json(out/"input.json", trace.model_dump(mode="json"))
        reports = {}
        for mode in ("fifo", "edf", "slack"):
            result = replay(trace, mode)
            write_json(out/f"{mode}.json", result)
            reports[mode] = {k:v for k,v in result.items() if k != "records"}
        write_json(out/"comparison.json", reports)
        print(out)
    elif args.command == "probe":
        asyncio.run(probe(args))
    elif args.command == "load":
        from .load import LoadPlan, run_load
        cfg = RuntimeConfig.model_validate_json(Path(args.config).read_text())
        plan = LoadPlan.model_validate_json(Path(args.plan).read_text())
        asyncio.run(run_load(cfg, plan, Path(args.out), allow_network=args.allow_network))
        print(args.out)
    else:
        import uvicorn

        from .server import create_app
        cfg = RuntimeConfig.model_validate_json(Path(args.config).read_text())
        token = os.environ.get("AGMINA_TOKEN", "")
        if len(token) < 24:
            raise ValueError("Set AGMINA_TOKEN before launching the sidecar")
        runtime = Runtime(cfg, args.database, allow_network=args.allow_network)
        app = create_app(runtime, token)
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, workers=1)


if __name__ == "__main__":
    main()
