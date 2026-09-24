"""Non-preemptive request dispatch. No CUDA preemption or hard real-time guarantee.

FIFO/EDF/slack share freshness/admission rules. Service profiles are operator
estimates, not the future service time from a trace (no oracle scheduling).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    id: str
    submitted_ns: int
    latest_ns: int
    estimate_ns: int
    priority: int


def rank(job: Candidate, now_ns: int, mode: str):
    if mode == "fifo":
        return (job.submitted_ns, job.id)
    if mode == "edf":
        return (job.latest_ns, job.submitted_ns, job.id)
    if mode != "slack":
        raise ValueError("Unknown scheduling policy")
    # Urgency first; aging is a tie-break, not an asserted starvation guarantee.
    return (job.latest_ns - now_ns - job.estimate_ns, job.priority, job.submitted_ns, job.id)


def choose_endpoint(endpoints, *, now_ns: int, latest_ns: int, site_allowlist,
                    pool_slots, pool_use, endpoint_use, quarantined,
                    placement="fastest"):
    feasible = []
    for ep in endpoints:
        if ep.site not in site_allowlist or ep.pool in quarantined:
            continue
        if pool_use.get(ep.pool, 0) >= pool_slots[ep.pool] or endpoint_use.get(ep.id, 0) >= ep.max_inflight:
            continue
        if now_ns + ep.estimate_ns >= latest_ns:
            continue
        feasible.append(ep)
    if placement == "cheapest_feasible":
        def key(endpoint):
            return (endpoint.reserve_microusd, endpoint.estimate_ns, endpoint.id)
    else:
        def key(endpoint):
            return (endpoint.estimate_ns, endpoint.reserve_microusd, endpoint.id)
    return min(feasible, key=key) if feasible else None
