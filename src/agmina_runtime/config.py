"""Operator-only configuration: pin contracts, resources and charge estimates."""
from __future__ import annotations

from urllib.parse import urlparse

from pydantic import Field, model_validator

from .contracts import Contract, ModelContract, Name, Ns


class Pool(Contract):
    id: Name
    slots: int = Field(default=1, ge=1, le=64)
    # A cooperative semaphore, NOT GPU memory/SM isolation. Default is exclusive.


class Endpoint(Contract):
    id: Name
    model: Name
    pool: Name
    site: Name
    kind: str = Field(pattern=r"^(mock|chat|triton|worker)$")
    url: str | None = None
    credential_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    model_name: str = "fixture"
    model_version: str | None = None
    service_p95_ns: Ns = 100_000_000
    transport_p95_ns: Ns = 0
    margin_ns: Ns = 5_000_000
    timeout_s: float = Field(default=30.0, gt=0, le=300)
    max_inflight: int = Field(default=1, ge=1, le=64)
    reserve_microusd: Ns = 0
    externally_billed: bool = False
    input_per_million_microusd: Ns | None = None
    cached_per_million_microusd: Ns | None = None
    output_per_million_microusd: Ns | None = None
    stream: bool = False
    max_output_tokens: int = Field(default=256, ge=1, le=65536)
    max_response_bytes: int = Field(default=2_000_000, ge=256, le=32_000_000)
    # API routing/sampling supplied here, never guessed from the model name.
    extra_body_json: str = "{}"

    @model_validator(mode="after")
    def fixed_url(self):
        if self.kind != "mock":
            parsed = urlparse(self.url or "")
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("Trusted fixed HTTP(S) endpoint required")
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("Credentials, queries and fragments do not belong in endpoint URL")
            if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError("Use HTTPS off loopback (or an authenticated local tunnel)")
        if self.externally_billed and self.reserve_microusd == 0:
            raise ValueError("Paid endpoints require a positive charge reservation")
        from .contracts import strict_json
        extra = strict_json(self.extra_body_json, max_bytes=8192)
        if set(extra) & {"model", "messages", "stream", "max_tokens", "max_completion_tokens"}:
            raise ValueError("Endpoint extras cannot override canonical request limits/model")
        return self

    @property
    def estimate_ns(self):
        # Conservative heuristic sum, not a calibrated joint p95 or hard guarantee.
        return self.service_p95_ns + self.transport_p95_ns + self.margin_ns


class RuntimeConfig(Contract):
    tenant: Name = "local"
    campaign: Name = "local-research"
    max_attempts: int = Field(default=100, ge=0, le=1_000_000)
    max_microusd: Ns = 0
    max_queue: int = Field(default=128, ge=1, le=10000)
    max_jobs: int = Field(default=10000, ge=1, le=1_000_000)
    scheduler: str = Field(default="slack", pattern=r"^(fifo|edf|slack)$")
    placement: str = Field(default="fastest", pattern=r"^(fastest|cheapest_feasible)$")
    cache_entries: int = Field(default=64, ge=0, le=10000)
    cache_bytes: int = Field(default=8_000_000, ge=0, le=128_000_000)
    cache_ttl_ns: Ns = 60_000_000_000
    pools: tuple[Pool, ...]
    models: tuple[ModelContract, ...]
    endpoints: tuple[Endpoint, ...]

    @model_validator(mode="after")
    def references(self):
        for values in (self.pools, self.models, self.endpoints):
            ids = [getattr(x, "id", getattr(x, "alias", None)) for x in values]
            if not ids or len(ids) != len(set(ids)):
                raise ValueError("Nonempty unique configured registries required")
        models = {m.alias for m in self.models}
        pools = {p.id for p in self.pools}
        if any(e.pool not in pools or e.model not in models for e in self.endpoints):
            raise ValueError("Endpoint references unknown pool/model")
        if models != {e.model for e in self.endpoints}:
            raise ValueError("Every model contract needs a configured endpoint")
        return self
