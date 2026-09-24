"""Compare one direct chat call with the same call routed through Agmina.

This is a transport/accounting experiment, not a model-quality benchmark.  The direct and
coordinated paths use the same validated request body and source-bound packet.  The tool makes no
retries and stops on the first failed attempt in either path.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from pathlib import Path

from agmina_runtime.backends import HttpBackend, validate_chat
from agmina_runtime.config import RuntimeConfig
from agmina_runtime.contracts import Job, Observation, ResultKind, canonical, fingerprint
from agmina_runtime.runtime import Runtime


def fresh_dir(value: str | Path) -> Path:
    path = Path(value)
    path.mkdir(parents=False, exist_ok=False)
    return path


def read_packet(path: Path) -> tuple[dict, tuple[dict, ...]]:
    packet = json.loads(path.read_text(encoding="utf8"))
    if set(packet) != {"payload", "observations"}:
        raise ValueError("Packet requires payload and observations")
    if not isinstance(packet["observations"], list) or not packet["observations"]:
        raise ValueError("Packet requires nonempty observations")
    return packet["payload"], tuple(packet["observations"])


def make_job(runtime: Runtime, session, payload: dict, raw_observations: tuple[dict, ...], *, job_id: str,
             model: str, now: int) -> Job:
    observations = tuple(
        Observation(
            id=f"{job_id}-input-{index}",
            source=item["source"],
            sequence=index,
            sha256=item["sha256"],
            capture_ns=now,
            available_ns=now,
        )
        for index, item in enumerate(raw_observations)
    )
    return Job(
        id=job_id,
        tenant=runtime.config.tenant,
        session_id=session.id,
        epoch=session.epoch,
        task_revision=session.task_revision,
        clock_id=session.clock_id,
        model=model,
        operation="r2_transport_compare",
        workload="semantic",
        result_kind=ResultKind.HISTORICAL,
        observations=observations,
        snapshot_ns=now,
        deadline_ns=now + 300_000_000_000,
        payload_json=canonical(payload),
    )


async def run(args: argparse.Namespace) -> dict:
    out = fresh_dir(args.out)
    config = RuntimeConfig.model_validate_json(args.config.read_text(encoding="utf8"))
    payload, raw_observations = read_packet(args.packet)
    endpoints = [endpoint for endpoint in config.endpoints if endpoint.model == args.model]
    if len(endpoints) != 1:
        raise ValueError("R2 comparison requires exactly one endpoint for --model")
    endpoint = endpoints[0]
    model_contract = next(model for model in config.models if model.alias == args.model)

    # The fixture packet's payload is checked by the same validator used by Agmina's HTTP backend.
    # The placeholder model alias is replaced before validation so the job remains an ordinary
    # source-bound contract while the configured endpoint owns the served model name.
    config_payload = dict(payload)
    runtime = Runtime(config, out / "agmina.sqlite", allow_network=args.allow_network)
    direct_backend = None
    try:
        if args.preflight:
            session = runtime.open_session("r2-preflight", "frozen-packet")
            now = runtime.clock.now_ns()
            job = make_job(runtime, session, config_payload, raw_observations,
                           job_id="preflight", model=args.model, now=now)
            body = validate_chat(job, endpoint)
            extra = json.loads(endpoint.extra_body_json)
            provider = extra.get("provider", {}) if isinstance(extra, dict) else {}
            report = {
                "protocol": "R2 no-network transport preflight",
                "outcome": "preflight_passed",
                "network_calls": 0,
                "paid_calls": 0,
                "quality_claim": False,
                "model_alias": args.model,
                "model_contract_fingerprint": fingerprint(model_contract),
                "endpoint_id": endpoint.id,
                "endpoint_model_name": endpoint.model_name,
                "response_model_required": endpoint.response_model_required,
                "request_sha256": hashlib.sha256(canonical(body).encode()).hexdigest(),
                "request_body_valid": True,
                "provider_order": provider.get("order", []),
                "provider_fallbacks_allowed": provider.get("allow_fallbacks"),
                "declared_campaign": config.campaign,
                "declared_max_microusd": config.max_microusd,
                "endpoint_reservation_microusd": endpoint.reserve_microusd,
                "credential_env_name": endpoint.credential_env,
                "config": config.model_dump(mode="json"),
            }
            (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
            return report
        direct_backend = HttpBackend(runtime.clock, allow_network=args.allow_network)
        direct_session = runtime.open_session("r2-direct", "frozen-packet")
        agmina_session = runtime.open_session("r2-agmina", "frozen-packet")
        samples = []
        failure = None
        for index in range(args.count):
            now = runtime.clock.now_ns()
            direct_job = make_job(runtime, direct_session, config_payload, raw_observations,
                                  job_id=f"direct-{index}", model=args.model, now=now)
            agmina_job = make_job(runtime, agmina_session, config_payload, raw_observations,
                                  job_id=f"agmina-{index}", model=args.model, now=now)
            direct_body = validate_chat(direct_job, endpoint)
            agmina_body = validate_chat(agmina_job, endpoint)
            if canonical(direct_body) != canonical(agmina_body):
                raise AssertionError("Direct and Agmina request bodies differ")
            request_hash = hashlib.sha256(canonical(direct_body).encode()).hexdigest()

            direct_started = time.perf_counter_ns()
            try:
                direct_prediction = await direct_backend.infer(direct_job, endpoint)
            except Exception as exc:
                failure = {
                    "path": "direct",
                    "index": index,
                    "error": getattr(exc, "code", type(exc).__name__),
                    "termination_known": getattr(exc, "termination_known", None),
                    "elapsed_ns": time.perf_counter_ns() - direct_started,
                }
                break
            direct_elapsed = time.perf_counter_ns() - direct_started

            submitted = runtime.submit(agmina_job)
            if submitted.state.value != "queued":
                raise RuntimeError(f"Agmina rejected job: {submitted.reason}")
            agmina_started = time.perf_counter_ns()
            try:
                agmina_receipt = await runtime.wait(agmina_job.id, timeout_s=endpoint.timeout_s + 5)
            except Exception as exc:
                failure = {
                    "path": "agmina",
                    "index": index,
                    "error": getattr(exc, "code", type(exc).__name__),
                    "termination_known": getattr(exc, "termination_known", None),
                    "elapsed_ns": time.perf_counter_ns() - agmina_started,
                }
                break
            agmina_elapsed = time.perf_counter_ns() - agmina_started
            if agmina_receipt.state.value != "succeeded":
                failure = {
                    "path": "agmina",
                    "index": index,
                    "error": agmina_receipt.reason or agmina_receipt.state.value,
                    "state": agmina_receipt.state.value,
                    "elapsed_ns": agmina_elapsed,
                }
                break
            consumed = runtime.consume(agmina_job.id, consumer_id="r2-compare")
            samples.append({
                "index": index,
                "request_sha256": request_hash,
                "direct": {
                    "elapsed_ns": direct_elapsed,
                    "first_content_relative_ns": (
                        direct_prediction.first_content_ns - now
                        if direct_prediction.first_content_ns is not None else None
                    ),
                    "prediction_sha256": hashlib.sha256(
                        direct_prediction.payload_json.encode()).hexdigest(),
                    "usage": direct_prediction.usage.model_dump(mode="json"),
                },
                "agmina": {
                    "elapsed_ns": agmina_elapsed,
                    "queue_ns": (agmina_receipt.started_ns - agmina_receipt.submitted_ns
                                  if agmina_receipt.started_ns is not None else None),
                    "backend_roundtrip_ns": (agmina_receipt.completed_ns - agmina_receipt.started_ns
                                              if agmina_receipt.completed_ns is not None
                                              and agmina_receipt.started_ns is not None else None),
                    "first_content_relative_ns": (
                        agmina_receipt.first_content_ns - agmina_receipt.started_ns
                        if agmina_receipt.first_content_ns is not None
                        and agmina_receipt.started_ns is not None else None
                    ),
                    "prediction_sha256": hashlib.sha256(
                        (consumed.prediction_json or "").encode()).hexdigest(),
                    "usage": consumed.usage.model_dump(mode="json") if consumed.usage else None,
                    "state": consumed.state.value,
                    "endpoint": consumed.endpoint,
                },
            })
        report = {
            "protocol": "R2 direct-versus-Agmina transport comparison",
            "quality_claim": False,
            "model_alias": args.model,
            "model_contract_fingerprint": fingerprint(model_contract),
            "endpoint_id": endpoint.id,
            "endpoint_model_name": endpoint.model_name,
            "response_model_required": endpoint.response_model_required,
            "count": len(samples),
            "outcome": "passed" if len(samples) == args.count else "failed_or_incomplete",
            "no_retries": True,
            "paid_calls": args.allow_network and endpoint.externally_billed,
            "samples": samples,
            "failure": failure,
            "config": config.model_dump(mode="json"),
        }
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
        return report
    finally:
        if direct_backend is not None:
            await direct_backend.close()
        await runtime.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--count", type=int, choices=range(1, 7), default=1)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--preflight", action="store_true",
                        help="Validate config and packet without dispatching or making network calls")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), indent=2))


if __name__ == "__main__":
    main()
