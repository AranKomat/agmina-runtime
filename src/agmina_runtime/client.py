"""Sidecar SDK and mandatory post-network delivery fence.

Server-side acceptance alone cannot establish freshness at the robot/application.
Check again after receiving the response, against the CURRENT local epoch/task.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from .clocks import ClockMap
from .contracts import Job, JobState, Receipt, ResultKind


@dataclass(frozen=True)
class DeliveryCheck:
    job_id: str
    valid_until_local_ns: int
    checked_at_local_ns: int
    action_authorized: bool = False


def validate_delivery(job: Job, receipt: Receipt, *, tenant: str, session_id: str,
                      current_epoch: int, current_task_revision: str, consumer_id: str,
                      now_local_ns: int, local_clock_id: str, server_to_local: ClockMap,
                      max_mapping_error_ns: int, local_useful_until_ns: int | None = None) -> DeliveryCheck:
    if type(max_mapping_error_ns) is not int or max_mapping_error_ns < 0 or (
        local_useful_until_ns is not None and (type(local_useful_until_ns) is not int or local_useful_until_ns < 0)
    ):
        raise ValueError("Explicit integer clock bounds required")
    if receipt.request_fingerprint != job.fingerprint or receipt.job_id != job.id:
        raise PermissionError("Reply does not belong to the submitted job")
    if receipt.state != JobState.CONSUMED or receipt.consumed_by != consumer_id or receipt.prediction_json is None:
        raise PermissionError("Result has not been claimed by this consumer")
    if (job.tenant, job.session_id, job.epoch, job.task_revision) != (
        tenant, session_id, current_epoch, current_task_revision
    ):
        raise PermissionError("Local execution/task epoch changed while inference or network was in flight")
    if server_to_local.source != job.clock_id or server_to_local.error_ns > max_mapping_error_ns:
        raise PermissionError("Missing or too-uncertain delivery clock mapping")
    deadline, error = server_to_local.map(job.deadline_ns, target_clock=local_clock_id, now_ns=now_local_ns)
    latest = deadline-error
    if job.result_kind != ResultKind.HISTORICAL:
        for obs in job.observations:
            if obs.role == "current":
                capture, error = server_to_local.map(obs.capture_ns, target_clock=local_clock_id,
                                                     now_ns=now_local_ns)
                latest = min(latest, capture+job.max_age_ns-obs.uncertainty_ns-error)
    if job.workload == "policy":
        if local_useful_until_ns is None:
            raise PermissionError("Policy consumer must supply its current local useful-completion deadline")
        latest = min(latest, local_useful_until_ns)
    if now_local_ns >= latest:
        raise PermissionError("Result aged out during return transport")
    return DeliveryCheck(job.id, latest, now_local_ns)


class Client:
    def __init__(self, base_url: str, token: str, *, timeout_s=30, transport=None):
        from urllib.parse import urlparse
        p = urlparse(base_url)
        if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
            raise ValueError("Fixed HTTP(S) sidecar URL required")
        if p.scheme == "http" and p.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Use TLS or a local authenticated tunnel outside loopback")
        if len(token) < 24:
            raise ValueError("High-entropy bearer token required")
        self.http = httpx.AsyncClient(base_url=base_url.rstrip("/"),
            headers={"Authorization":"Bearer "+token}, timeout=timeout_s,
            transport=transport, follow_redirects=False, trust_env=False)

    async def close(self):
        await self.http.aclose()

    async def clock(self):
        r = await self.http.get("/v1/clock")
        r.raise_for_status()
        return r.json()

    async def open_session(self, sid, task_revision):
        from .contracts import Session
        r = await self.http.post("/v1/sessions", json={"id":sid,"task_revision":task_revision})
        r.raise_for_status()
        return Session.model_validate_json(r.text)

    async def submit(self, job: Job):
        r = await self.http.post("/v1/jobs", content=job.model_dump_json(),
                                 headers={"Content-Type":"application/json"})
        r.raise_for_status()
        return Receipt.model_validate_json(r.text)

    async def result(self, job_id):
        r = await self.http.get("/v1/result", params={"id":job_id})
        r.raise_for_status()
        return Receipt.model_validate_json(r.text)

    async def consume(self, job_id, consumer_id):
        r = await self.http.post("/v1/consume", json={"job_id":job_id,"consumer_id":consumer_id})
        r.raise_for_status()
        return Receipt.model_validate_json(r.text)

    async def cancel(self, job_id):
        r = await self.http.post("/v1/cancel", json={"job_id":job_id})
        r.raise_for_status()
        return Receipt.model_validate_json(r.text)
