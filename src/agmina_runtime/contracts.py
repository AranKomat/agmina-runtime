"""Wire contracts. All scheduling timestamps are in ONE named monotonic clock.

The runtime cannot infer remote clock offsets, physical safety, model quality, or
which observations a caller secretly used. Host applications remain authorities.
"""
from __future__ import annotations

import hashlib
import json
import math
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Name = Annotated[str, Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]*$")]
Sha = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Ns = Annotated[int, Field(ge=0, le=2**63 - 1)]


def strict_json(value: str, *, max_bytes: int = 8_000_000) -> dict:
    if not isinstance(value, str) or len(value.encode()) > max_bytes:
        raise ValueError("JSON object exceeds byte bound")

    def pairs(items):
        out = {}
        for key, val in items:
            if key in out:
                raise ValueError("Duplicate JSON key")
            out[key] = val
        return out

    def constant(_):
        raise ValueError("Nonfinite JSON number")

    try:
        parsed = json.loads(value, object_pairs_hook=pairs, parse_constant=constant)
    except (RecursionError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("JSON must be an object")

    def check(obj, depth=0):
        if depth > 32:
            raise ValueError("JSON nesting exceeds limit")
        if isinstance(obj, float) and not math.isfinite(obj):
            raise ValueError("Nonfinite JSON number")
        if isinstance(obj, (list, dict)):
            for child in obj.values() if isinstance(obj, dict) else obj:
                check(child, depth + 1)
    check(parsed)
    return parsed


def canonical(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ResultKind(str, Enum):
    CURRENT = "current"
    HISTORICAL = "historical"
    ACTION_PROPOSAL = "action_proposal"


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    CONSUMED = "consumed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    STALE = "stale"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class Observation(Contract):
    id: Name
    source: Name
    sequence: Ns
    sha256: Sha
    capture_ns: Ns
    available_ns: Ns
    uncertainty_ns: Ns = 0
    role: Literal["current", "context"] = "current"
    # Optional source-domain value retained as metadata, never subtracted from monotonic time.
    source_time: str | None = Field(default=None, max_length=160)

    @property
    def source_fingerprint(self):
        """Evidence identity excludes the job-local current/context role."""
        return fingerprint(self.model_dump(mode="json", exclude={"role"}))

    @model_validator(mode="after")
    def ordered(self):
        if self.available_ns < self.capture_ns:
            raise ValueError("Availability precedes mapped capture")
        return self


class Session(Contract):
    tenant: Name
    id: Name
    epoch: Ns
    task_revision: Name
    clock_id: Name
    state: Literal["active", "closed"] = "active"
    updated_ns: Ns
    buffer_until_ns: Ns | None = None
    # Advisory scheduling input, not a safety-certified execution commitment.


class Job(Contract):
    id: Name
    tenant: Name
    session_id: Name
    epoch: Ns
    task_revision: Name
    clock_id: Name
    model: Name  # Operator-configured model CONTRACT alias, never an arbitrary URL.
    operation: Name
    workload: Literal["policy", "segmentation", "semantic", "mapping", "query"]
    result_kind: ResultKind
    observations: tuple[Observation, ...] = Field(min_length=0, max_length=32)
    snapshot_ns: Ns
    deadline_ns: Ns
    max_age_ns: Ns | None = None
    max_uncertainty_ns: Ns = 0
    priority: int = Field(default=1, ge=0, le=3)  # Smaller is more urgent, trusted caller only.
    allowed_sites: tuple[Name, ...] = ("local", "site", "cloud")
    dependencies: tuple[Name, ...] = Field(default=(), max_length=32)
    payload_json: str
    replace_key: Name | None = None
    discardable: bool = False
    cacheable: bool = False

    @field_validator("payload_json")
    @classmethod
    def payload_object(cls, value):
        return canonical(strict_json(value))

    @model_validator(mode="after")
    def valid(self):
        if not self.observations and self.workload != "query":
            raise ValueError("Evidence-bound jobs require at least one observation")
        if self.deadline_ns <= self.snapshot_ns:
            raise ValueError("Deadline must follow evidence cutoff")
        if len({o.id for o in self.observations}) != len(self.observations):
            raise ValueError("Repeated observation ID")
        if any(o.available_ns > self.snapshot_ns for o in self.observations):
            raise ValueError("Evidence unavailable at snapshot")
        if any(o.uncertainty_ns > self.max_uncertainty_ns for o in self.observations):
            raise ValueError("Capture clock uncertainty exceeds operator bound")
        if self.result_kind != ResultKind.HISTORICAL:
            if self.max_age_ns is None or not any(o.role == "current" for o in self.observations):
                raise ValueError("Current/action results require current evidence and an age bound")
        if self.replace_key and not self.discardable:
            raise ValueError("Latest-only replacement requires explicit discard permission")
        if self.workload == "policy" and (self.discardable or self.cacheable):
            raise ValueError("Policy jobs cannot be implicitly dropped or result-cached")
        if self.cacheable and self.result_kind != ResultKind.HISTORICAL:
            raise ValueError("Only exact historical queries may reuse completed results")
        if not self.allowed_sites or len(set(self.allowed_sites)) != len(self.allowed_sites):
            raise ValueError("Explicit unique allowed sites required")
        if self.id in self.dependencies or len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("Invalid dependency set")
        return self

    @property
    def fingerprint(self):
        return fingerprint(self)

    def payload(self):
        return strict_json(self.payload_json)

    def latest_ns(self, session: Session) -> int:
        latest = self.deadline_ns
        if self.result_kind != ResultKind.HISTORICAL:
            latest = min(latest, *(o.capture_ns + self.max_age_ns - o.uncertainty_ns
                                   for o in self.observations if o.role == "current"))
        if self.workload == "policy" and session.buffer_until_ns is not None:
            latest = min(latest, session.buffer_until_ns)
        return latest

    def invalid_reason(self, session: Session, now_ns: int, clock_id: str) -> str | None:
        if self.clock_id != clock_id or session.clock_id != clock_id:
            return "clock_epoch_mismatch"
        if (self.tenant, self.session_id, self.epoch, self.task_revision) != (
            session.tenant, session.id, session.epoch, session.task_revision
        ) or session.state != "active":
            return "session_epoch_mismatch"
        if self.snapshot_ns > now_ns:
            return "future_snapshot"
        if now_ns >= self.latest_ns(session):
            return "deadline_or_freshness_expired"
        return None


class ModelContract(Contract):
    alias: Name
    weights: str = Field(min_length=1, max_length=256)
    preprocessing: str = Field(min_length=1, max_length=256)
    output_schema: str = Field(min_length=1, max_length=256)
    sampling: str = Field(min_length=1, max_length=256)
    stateful: bool = False
    # Stateful model sessions are deliberately NOT migrated/served by v0.1.
    @model_validator(mode="after")
    def no_stateful(self):
        if self.stateful:
            raise ValueError("Keep stateful SAM/policy workers host-owned until reset/sequence RPC is qualified")
        return self

    @property
    def fingerprint(self):
        return fingerprint(self)


class Usage(Contract):
    input_tokens: Ns | None = None
    output_tokens: Ns | None = None
    cached_input_tokens: Ns | None = None
    reasoning_output_tokens: Ns | None = None
    cost_microusd: Ns | None = None
    # Reasoning tokens are a subset of output_tokens in this normalized contract.
    @model_validator(mode="after")
    def subsets(self):
        if self.cached_input_tokens is not None and (
            self.input_tokens is None or self.cached_input_tokens > self.input_tokens
        ):
            raise ValueError("Cached tokens exceed total input")
        if self.reasoning_output_tokens is not None and (
            self.output_tokens is None or self.reasoning_output_tokens > self.output_tokens
        ):
            raise ValueError("Reasoning must be a documented subset of output")
        return self


class Prediction(Contract):
    payload_json: str
    usage: Usage = Usage()
    first_content_ns: Ns | None = None
    # Provider-generation ID only; never store response text or credentials here.
    provider_request_id: str | None = Field(default=None, max_length=256)
    @field_validator("payload_json")
    @classmethod
    def valid_payload(cls, value):
        return canonical(strict_json(value))


class Receipt(Contract):
    job_id: Name
    request_fingerprint: Sha
    state: JobState
    endpoint: Name | None = None
    reason: str | None = None
    submitted_ns: Ns
    started_ns: Ns | None = None
    completed_ns: Ns | None = None
    computed_ns: Ns | None = None
    first_content_ns: Ns | None = None
    prediction_json: str | None = None
    usage: Usage | None = None
    provider_request_id: str | None = Field(default=None, max_length=256)
    cache_hit: bool = False
    consumed_by: Name | None = None
    consumed_ns: Ns | None = None
    # Passing this receipt is NOT robot action admission or semantic verification.
