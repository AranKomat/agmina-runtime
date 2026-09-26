"""Read-only builders for the inspected StreamBudget and physical-harness contracts.

The host supplies its causal cutoff, frame availability and an explicit clock
mapping. No timestamps are guessed, and no old app ledger is silently replaced.
"""
from __future__ import annotations

import base64
import hashlib
import math
from typing import Literal

from pydantic import Field, model_validator

from ..clocks import ClockMap
from ..contracts import Contract, Job, Name, Observation, ResultKind, Session, canonical


def _seconds_ns(seconds):
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
        raise ValueError("Finite nonnegative source time required")
    return round(seconds * 1_000_000_000)


def streambudget_job(request, *, session: Session, clock_map: ClockMap, now_ns: int,
                     snapshot_ns: int, deadline_ns: int, model: str, job_id: str,
                     sequence_by_id: dict, available_by_id: dict,
                     result_kind=ResultKind.HISTORICAL, max_age_ns=None):
    """Convert backend.Request, not Watch/MemoryStore. Availability map is mandatory.

    request.context is not appended: the inspected ModelPool._body sends system,
    text, and timestamped images. Keep prompt preparation in the host.
    """
    if not request.images:
        raise ValueError("This evidence bridge requires images; use explicit text-evidence jobs otherwise")
    content = [{"type": "text", "text": request.text}]
    observations = []
    for image in request.images:
        if image.evidence_id not in available_by_id or image.evidence_id not in sequence_by_id:
            raise ValueError("Source availability/sequence must come from the host evidence store")
        capture, error = clock_map.map(_seconds_ns(image.timestamp), target_clock=session.clock_id, now_ns=now_ns)
        available, _ = clock_map.map(_seconds_ns(available_by_id[image.evidence_id]),
                                    target_clock=session.clock_id, now_ns=now_ns)
        if type(image.jpeg) is not bytes:
            raise ValueError("Original JPEG bytes required")
        observations.append(Observation(id=image.evidence_id, source="streambudget", sequence=sequence_by_id[
            image.evidence_id], sha256=hashlib.sha256(image.jpeg).hexdigest(), capture_ns=capture,
            available_ns=available, uncertainty_ns=error, source_time=str(image.timestamp), role="current"))
        content.extend([{"type": "text", "text": f"Evidence {image.evidence_id}; t={image.timestamp:.6f}s"},
                        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," +
                         base64.b64encode(image.jpeg).decode(), "detail": "auto"}}])
    body = {"messages": [{"role": "system", "content": request.system}, {"role": "user", "content": content}],
            "response_format": {"type": "json_object"}}
    return Job(id=job_id, tenant=session.tenant, session_id=session.id, epoch=session.epoch,
               task_revision=session.task_revision, clock_id=session.clock_id, model=model,
               operation=request.operation, workload="semantic", result_kind=result_kind,
               observations=tuple(observations), snapshot_ns=snapshot_ns, deadline_ns=deadline_ns,
               max_age_ns=max_age_ns, max_uncertainty_ns=clock_map.error_ns, payload_json=canonical(body))


def streambudget_text_job(request, *, session: Session, now_ns: int, snapshot_ns: int,
                          deadline_ns: int, model: str, job_id: str,
                          result_kind=ResultKind.HISTORICAL):
    """Convert a text-only StreamBudget request into an explicit query job.

    Planner/memory requests carry their complete bounded prompt in the payload rather than
    pretending that a source image was observed. They remain task/session-bound, but are not
    evidence-bound; non-query jobs still require observations in the core contract.
    """
    if request.images:
        raise ValueError("Text bridge does not accept image inputs; use streambudget_job")
    body = {"messages": [{"role": "system", "content": request.system},
                         {"role": "user", "content": request.text}],
            "response_format": {"type": "json_object"}}
    return Job(id=job_id, tenant=session.tenant, session_id=session.id, epoch=session.epoch,
               task_revision=session.task_revision, clock_id=session.clock_id, model=model,
               operation=request.operation, workload="query", result_kind=result_kind,
               observations=(), snapshot_ns=snapshot_ns, deadline_ns=deadline_ns,
               max_uncertainty_ns=0, payload_json=canonical(body))


def physical_observation(frame, blob: bytes, *, sequence: int, clock_map: ClockMap,
                         clock_id: str, now_ns: int, role: Literal["current", "context"] = "current"):
    """Convert perception.contracts.FrameRef using monotonic wall, NEVER sim_time as wall."""
    frame.verify_bytes(blob)
    capture, error = clock_map.map(_seconds_ns(frame.basis.captured_wall), target_clock=clock_id, now_ns=now_ns)
    available, _ = clock_map.map(_seconds_ns(frame.available_wall), target_clock=clock_id, now_ns=now_ns)
    return Observation(id=frame.asset_id, source=frame.camera, sequence=sequence,
                       sha256=frame.content_sha256, capture_ns=capture, available_ns=available,
                       uncertainty_ns=error, role=role, source_time="sim:" + str(frame.basis.sim_time))


class ActionChunk(Contract):
    """Validated tensor envelope for a HOST-OWNED policy worker; not an actuator API.

    Joint names, units, period and normalization must match the checkpoint. No
    slicing/padding/re-timing or end-effector-to-joint conversion is performed.
    """
    codec_revision: Name
    action_names: tuple[Name, ...] = Field(min_length=1, max_length=128)
    units: tuple[str, ...]
    period_ns: int = Field(gt=0)
    normalized: bool
    actions: tuple[tuple[float, ...], ...] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def valid(self):
        if len(set(self.action_names)) != len(self.action_names) or len(self.units) != len(self.action_names):
            raise ValueError("Named axes and units must align uniquely")
        if any(not u or len(u) > 64 for u in self.units):
            raise ValueError("Explicit units required")
        if any(len(row) != len(self.action_names) or any(not math.isfinite(v) for v in row) for row in self.actions):
            raise ValueError("Finite rectangular action chunk required")
        return self

    def require_codec(self, *, revision, names, units, period_ns, normalized):
        if (self.codec_revision, self.action_names, self.units, self.period_ns, self.normalized) != (
            revision, names, units, period_ns, normalized
        ):
            raise PermissionError("Policy codec mismatch; do not coerce it into compatibility")
        return self
