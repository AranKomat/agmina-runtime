"""Compare an ordered native policy RPC sequence directly and through Agmina.

This is a transport/offload campaign only. The policy server is reset by the host
once before each path, the same ordered JSON packet sequence is used for both calls,
and Agmina returns action proposals without authorizing or executing them. A real
run requires an operator-started loopback policy server and ``--allow-network``.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from pathlib import Path

from agmina_runtime.adapters.native_policy import (
    HttpNativePolicyTransport,
    NativePolicyBackend,
    validate_native_packet,
    validate_native_result,
)
from agmina_runtime.config import Endpoint, Pool, RuntimeConfig
from agmina_runtime.contracts import Job, ModelContract, Observation, ResultKind, canonical
from agmina_runtime.runtime import Runtime


def fresh_dir(value: str | Path) -> Path:
    path = Path(value)
    path.mkdir(parents=False, exist_ok=False)
    return path


def read_packet(path: Path) -> dict:
    packet = json.loads(path.read_text(encoding="utf8"))
    return validate_native_packet(packet)


def job_for(packet: dict, *, session, model: str, now_ns: int, deadline_ns: int) -> Job:
    packet_hash = hashlib.sha256(canonical(packet).encode()).hexdigest()
    observation = Observation(
        id="native-packet-" + packet_hash[:24],
        source="native-policy",
        sequence=packet["stamp"]["sequence"],
        sha256=packet_hash,
        capture_ns=now_ns,
        available_ns=now_ns,
        source_time="native-policy-packet",
    )
    return Job(
        id="agmina-native-policy-" + packet_hash[:16],
        tenant=session.tenant,
        session_id=session.id,
        epoch=session.epoch,
        task_revision=session.task_revision,
        clock_id=session.clock_id,
        model=model,
        operation="native_policy_infer",
        workload="policy",
        result_kind=ResultKind.ACTION_PROPOSAL,
        observations=(observation,),
        snapshot_ns=now_ns,
        deadline_ns=deadline_ns,
        max_age_ns=deadline_ns - now_ns,
        allowed_sites=("local",),
        payload_json=canonical(packet),
    )


def write_run_files(out: Path, report: dict, config: RuntimeConfig, events: list[dict]) -> None:
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    (out / "config.json").write_text(config.model_dump_json(indent=2) + "\n", encoding="utf8")
    with (out / "trace.jsonl").open("x", encoding="utf8") as stream:
        for event in events:
            stream.write(canonical(event) + "\n")


async def run(args: argparse.Namespace) -> dict:
    if not args.allow_network:
        raise SystemExit("Refusing native RPC without --allow-network")
    if not 0 < args.estimate_s <= args.timeout_s:
        raise ValueError("Scheduler estimate must be positive and no greater than the RPC timeout")
    out = fresh_dir(args.out)
    packets = [read_packet(path) for path in args.packet]
    if not packets:
        raise ValueError("At least one native packet is required")
    first_stamp = packets[0]["stamp"]
    previous_sequence = -1
    for packet in packets:
        stamp = packet["stamp"]
        if (stamp["session"], stamp["epoch"]) != (first_stamp["session"], first_stamp["epoch"]):
            raise ValueError("Native packet cohort crosses a policy session or epoch")
        if stamp["sequence"] <= previous_sequence:
            raise ValueError("Native packet cohort must have strictly increasing sequences")
        previous_sequence = stamp["sequence"]
    model = ModelContract(
        alias="native-policy",
        weights=args.weights,
        preprocessing=args.preprocessing,
        output_schema=args.output_schema,
        sampling=args.sampling,
    )
    endpoint = Endpoint(
        id="native-policy-loopback",
        model=model.alias,
        pool="native-policy",
        site="local",
        kind="worker",
        url=args.url + "/infer",
        model_name=args.model_name,
        model_version=args.model_version,
        timeout_s=args.timeout_s,
        service_p95_ns=round(args.estimate_s * 1_000_000_000),
        margin_ns=0,
    )
    config = RuntimeConfig(
        campaign="r6-native-policy-direct-vs-agmina",
        max_attempts=2 * len(packets),
        max_microusd=0,
        max_queue=len(packets),
        max_jobs=len(packets),
        scheduler="fifo",
        pools=(Pool(id=endpoint.pool),),
        models=(model,),
        endpoints=(endpoint,),
    )
    transport = HttpNativePolicyTransport(args.url, timeout_s=args.timeout_s)
    runtime = Runtime(config, out / "ledger.sqlite")
    runtime.backends[endpoint.id] = NativePolicyBackend(transport, clock=runtime.clock)
    direct = routed = None
    direct_elapsed = routed_elapsed = None
    submitted = completed = None
    error = None
    session = runtime.open_session(first_stamp["session"], "native-policy-transport-v1")
    try:
        reset_stamp = first_stamp
        await transport.reset(reset_stamp)
        direct = []
        direct_elapsed = []
        for packet in packets:
            direct_start = time.perf_counter_ns()
            direct.append(validate_native_result(await transport.infer(packet), packet["stamp"]))
            direct_elapsed.append(time.perf_counter_ns() - direct_start)

        await transport.reset(reset_stamp)
        routed = []
        routed_elapsed = []
        submitted = []
        completed = []
        for packet in packets:
            now_ns = runtime.clock.now_ns()
            job = job_for(packet, session=session, model=model.alias, now_ns=now_ns,
                          deadline_ns=now_ns + round(args.timeout_s * 1_000_000_000))
            routed_start = time.perf_counter_ns()
            submitted_receipt = runtime.submit(job)
            completed_receipt = await runtime.wait(job.id, timeout_s=args.timeout_s + 5)
            if completed_receipt.state.value != "succeeded":
                raise RuntimeError(f"Agmina policy job did not succeed: {completed_receipt.state.value}")
            routed_receipt = runtime.consume(job.id, consumer_id="r6-shadow")
            routed.append(json.loads(routed_receipt.prediction_json or "{}"))
            routed_elapsed.append(time.perf_counter_ns() - routed_start)
            submitted.append(submitted_receipt)
            completed.append(completed_receipt)
            runtime.record_outcome(job.id, consumer_id="r6-shadow", outcome="rejected",
                                   evidence_ref="r6-native-transport:no-actuation")
    except Exception as exc:
        error = repr(exc)
    finally:
        events = runtime.store.export_events()
        await runtime.close()
        await transport.close()

    if error is not None:
        report = {
            "protocol": "R6 native policy direct-versus-Agmina transport comparison",
            "outcome": "failed",
            "packet_sha256": [hashlib.sha256(canonical(packet).encode()).hexdigest()
                              for packet in packets],
            "stamps": [packet["stamp"] for packet in packets],
            "model": model.model_dump(mode="json"),
            "endpoint": endpoint.model_dump(mode="json"),
            "error": error,
            "direct_completed": len(direct or []),
            "routed_completed": len(routed or []),
            "native_actions": 0,
            "action_authorized": False,
            "paid_calls": 0,
            "closed_loop_qualified": False,
            "limitations": [
                "transport campaign did not complete; inspect error and retained ledger",
                "no simulator or actuator was connected",
            ],
        }
        write_run_files(out, report, config, events)
        raise RuntimeError(error)

    direct_json = [canonical(result) for result in direct]
    routed_json = [canonical(result) for result in routed]
    report = {
        "protocol": "R6 native policy direct-versus-Agmina transport comparison",
        "outcome": "passed" if direct_json == routed_json else "failed",
        "packet_sha256": [hashlib.sha256(canonical(packet).encode()).hexdigest()
                          for packet in packets],
        "packet_count": len(packets),
        "stamps": [packet["stamp"] for packet in packets],
        "model": model.model_dump(mode="json"),
        "endpoint": endpoint.model_dump(mode="json"),
        "direct": {"predictions": direct, "infer_elapsed_ns": direct_elapsed},
        "agmina": {"predictions": routed, "infer_and_runtime_elapsed_ns": routed_elapsed,
                    "submitted_states": [receipt.state.value for receipt in submitted],
                    "completed_states": [receipt.state.value for receipt in completed]},
        "predictions_exact": direct_json == routed_json,
        "native_actions": 0,
        "action_authorized": False,
        "paid_calls": 0,
        "gpu_calls": "server-dependent; not measured by Agmina",
        "closed_loop_qualified": False,
        "limitations": [
            "transport comparison only; no simulator or actuator was connected",
            "reset latency is excluded from direct and routed infer timings",
            "server checkpoint and hardware are operator-supplied metadata",
        ],
    }
    write_run_files(out, report, config, events)
    if report["outcome"] != "passed":
        raise RuntimeError("Direct and Agmina native policy predictions differ")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, action="append", required=True,
                        help="ordered native packet JSON; repeat for one episode cohort")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8011")
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--weights", required=True)
    parser.add_argument("--preprocessing", required=True)
    parser.add_argument("--output-schema", required=True)
    parser.add_argument("--sampling", required=True)
    parser.add_argument("--estimate-s", type=float, required=True,
                        help="operator-declared scheduler service estimate, separate from timeout")
    parser.add_argument("--timeout-s", type=float, default=180.0)
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), indent=2))


if __name__ == "__main__":
    main()
