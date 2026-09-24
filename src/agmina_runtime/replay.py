"""Causal discrete-event scheduler replay; not a robot simulator or ML evaluation.

Service durations are declared measured or synthetic. They are hidden from the
scheduler, which sees only profile estimates. Frozen durations do NOT model live
batching, thermal effects, action-dependent future observations, or GPU interference.
"""
from __future__ import annotations

import heapq
import random

from pydantic import Field, model_validator

from .contracts import Contract, Name, Ns, fingerprint
from .scheduling import Candidate, rank
from .telemetry import percentile


class ReplayRequest(Contract):
    id: Name
    session: Name
    workload: Name
    release_ns: Ns
    capture_ns: Ns
    deadline_ns: Ns
    profile_ns: Ns
    service_ns: Ns
    priority: int = Field(default=1, ge=0, le=3)
    max_age_ns: Ns

    @model_validator(mode="after")
    def ordered(self):
        if self.capture_ns > self.release_ns or self.deadline_ns <= self.release_ns or self.service_ns == 0:
            raise ValueError("Invalid trace ordering/service time")
        return self

    @property
    def latest_ns(self):
        return min(self.deadline_ns, self.capture_ns+self.max_age_ns)


class Trace(Contract):
    provenance: str = Field(min_length=1)
    synthetic: bool
    duration_ns: Ns
    slots: int = Field(default=1, ge=1, le=64)
    requests: tuple[ReplayRequest, ...] = Field(max_length=100000)

    @model_validator(mode="after")
    def unique(self):
        if len({r.id for r in self.requests}) != len(self.requests):
            raise ValueError("Duplicate trace request IDs")
        if any(r.release_ns > self.duration_ns for r in self.requests):
            raise ValueError("Release outside declared trace duration")
        return self


def replay(trace: Trace, mode: str):
    ordered = sorted(trace.requests, key=lambda r: (r.release_ns, r.id))
    queue, active, rows = [], [], {}
    now, cursor = 0, 0
    while cursor < len(ordered) or queue or active:
        while active and active[0][0] <= now:
            finish, jid = heapq.heappop(active)
            row = rows[jid]
            row["completed_ns"] = finish
            row["state"] = "completed_in_time" if finish < row["latest_ns"] else "completed_late"
        while cursor < len(ordered) and ordered[cursor].release_ns <= now:
            r = ordered[cursor]
            queue.append(r)
            rows[r.id] = {"id": r.id, "session": r.session, "workload": r.workload,
                          "release_ns": r.release_ns, "capture_ns": r.capture_ns, "latest_ns": r.latest_ns,
                          "started_ns": None, "completed_ns": None, "state": "queued"}
            cursor += 1
        for r in list(queue):
            if now >= r.latest_ns:
                rows[r.id]["state"] = "expired_before_dispatch"
                queue.remove(r)
        # Profile feasibility is identical for all comparators, independent of actual duration.
        eligible = [r for r in queue if now+r.profile_ns < r.latest_ns]
        eligible.sort(key=lambda r: rank(Candidate(r.id, r.release_ns, r.latest_ns,
                                                 r.profile_ns, r.priority), now, mode))
        while eligible and len(active) < trace.slots:
            r = eligible.pop(0)
            queue.remove(r)
            rows[r.id]["started_ns"] = now
            rows[r.id]["state"] = "running"
            heapq.heappush(active, (now+r.service_ns, r.id))
        next_times = [t for t in (
            ordered[cursor].release_ns if cursor < len(ordered) else None,
            active[0][0] if active else None,
            min((r.latest_ns for r in queue), default=None),
        ) if t is not None and t > now]
        if not next_times:
            break
        now = min(next_times)
    records = list(rows.values())
    by_workload = {}
    for row in records:
        g = by_workload.setdefault(row["workload"], {"offered": 0, "completed_in_time": 0,
                                  "completed_late": 0, "expired_before_dispatch": 0})
        g["offered"] += 1
        g[row["state"]] = g.get(row["state"], 0) + 1
    queue_ns = [r["started_ns"]-r["release_ns"] for r in records if r["started_ns"] is not None]
    age_ns = [r["completed_ns"]-r["capture_ns"] for r in records if r["completed_ns"] is not None]
    return {"kind": "discrete_event_replay", "synthetic": trace.synthetic, "provenance": trace.provenance,
            "trace_fingerprint": fingerprint(trace), "scheduler": mode, "offered": len(records),
            "by_workload": by_workload, "queue_p95_ns": percentile(queue_ns, .95),
            "completion_age_p95_ns": percentile(age_ns, .95), "elapsed_virtual_ns": now,
            "physical_task_success": None, "event_recall": None, "gpu_speedup": None,
            "records": records,
            "limits": ["No feedback-dependent future request generation.",
                       "Service times are schedule-invariant; no dynamic batching/preemption model.",
                       "A met deadline is not a correct perception result or safe robot action.",
                       "All offered work retained, including expired requests."]}


def synthetic_trace(*, seed=0, seconds=5, robots=2, cameras=4, slots=1, profile_error=False):
    if not 1 <= seconds <= 120 or not 0 <= robots <= 32 or not 0 <= cameras <= 128:
        raise ValueError("Fixture scale outside bound")
    rng = random.Random(seed)
    rows = []
    specs = [("policy", robots, 120, 32, 100, 0), ("semantic", cameras, 450, 85, 600, 1),
             ("mapping", 1, 380, 145, 1400, 3)]
    for workload, count, period, service, deadline, priority in specs:
        for s in range(count):
            i, start = 0, rng.randrange(max(1, period//2))
            while start < seconds*1000:
                jitter = rng.randrange(0, 15)
                actual = service*(3 if profile_error and rng.random() < .05 else 1) + jitter
                rows.append(ReplayRequest(id=f"{workload}-{s}-{i}", session=f"{workload}-{s}",
                    workload=workload, release_ns=start*1_000_000, capture_ns=max(0,start-5)*1_000_000,
                    deadline_ns=(start+deadline)*1_000_000, profile_ns=(service+10)*1_000_000,
                    service_ns=actual*1_000_000, priority=priority, max_age_ns=deadline*1_000_000))
                start += period
                i += 1
    return Trace(provenance=f"Synthetic independent request arrivals; seed={seed}; not hardware measurements",
                 synthetic=True, duration_ns=seconds*1_000_000_000, slots=slots, requests=tuple(rows))
