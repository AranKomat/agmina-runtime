"""Measured coordinator metrics. No fabricated GPU, semantic-quality or robot-success metrics."""
import math
from collections import Counter

from .contracts import JobState


def percentile(values, p):
    """Nearest-rank percentile (small-n values are descriptive, not tail guarantees)."""
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(p * len(values)) - 1)]


def summarize(runtime):
    rows = runtime.store.jobs(runtime.config.tenant)
    events = runtime.store.export_events()
    statuses = Counter(r.state.value for _, r in rows)
    queue, roundtrip, first, age, completion = [], [], [], [], []
    by_workload = {}
    grouped_latencies = {}
    usage_totals = {k: 0 for k in ("input_tokens", "output_tokens", "cached_input_tokens",
                                   "reasoning_output_tokens")}
    usage_missing = {k: 0 for k in usage_totals}
    for job, r in rows:
        g = by_workload.setdefault(job.workload, {"offered": 0, "usable_completion": 0, "consumed": 0})
        g["offered"] += 1
        g["usable_completion"] += r.state in {JobState.SUCCEEDED, JobState.CONSUMED}
        g["consumed"] += r.state == JobState.CONSUMED
        if r.started_ns is not None or r.cache_hit:
            for key in usage_totals:
                value = getattr(r.usage, key) if r.usage is not None else None
                if value is None:
                    usage_missing[key] += 1
                else:
                    usage_totals[key] += value
        for group in ("workload:"+job.workload, "endpoint:"+(r.endpoint or "not_dispatched")):
            g_times = grouped_latencies.setdefault(group, {"offered": 0, "roundtrip_ns": [], "queue_ns": []})
            g_times["offered"] += 1
            if r.started_ns is not None:
                g_times["queue_ns"].append(r.started_ns-r.submitted_ns)
                if r.completed_ns is not None:
                    g_times["roundtrip_ns"].append(r.completed_ns-r.started_ns)
        if r.started_ns is not None:
            queue.append(r.started_ns-r.submitted_ns)
        if r.completed_ns is not None:
            completion.append(r.completed_ns-r.submitted_ns)
            if r.started_ns is not None:
                roundtrip.append(r.completed_ns-r.started_ns)
        if r.first_content_ns is not None and r.started_ns is not None:
            first.append(r.first_content_ns-r.started_ns)
    for e in events:
        if e["kind"] == "consumed" and e.get("max_current_age_ns") is not None:
            age.append(e["max_current_age_ns"])
    timing = {}
    for name, series in (("queue", queue), ("backend_roundtrip", roundtrip), ("first_content", first),
                         ("submit_to_completion", completion), ("observation_age_at_consumption", age)):
        timing[name] = {"n": len(series), "p50_ns": percentile(series, .5), "p95_ns": percentile(series, .95),
                        "p99_ns": percentile(series, .99), "max_ns": max(series) if series else None}
    per_group = {}
    for group, raw in grouped_latencies.items():
        per_group[group] = {"offered": raw["offered"]}
        for kind in ("roundtrip_ns", "queue_ns"):
            values = raw[kind]
            per_group[group][kind] = {"n": len(values), "p50": percentile(values, .5),
                                     "p95": percentile(values, .95), "p99": percentile(values, .99)}
    return {"kind": "coordinator_measurements", "clock_id": runtime.clock.id, "offered": len(rows),
            "states": dict(statuses), "by_workload": by_workload, "timing": timing,
            "timing_groups": per_group,
            "tokens": {"known_totals": usage_totals, "missing_attempt_counts": usage_missing,
                       "reasoning_is_subset_of_output": True},
            "cache_hits": sum(r.cache_hit for _, r in rows), "budget": runtime.store.budget(),
            "quarantined_pools": sorted(runtime.store.quarantined()),
            "gpu_seconds": None, "device_energy_joules": None, "physical_task_success": None,
            "semantic_quality": None,
            "notes": ["Backend roundtrip includes unknown queue/network/compute/serialization components.",
                      "Do not infer GPU time from HTTP latency or infer task success from a consumed result.",
                      "All offered/rejected/expired work remains in the denominator.",
                      "First content is not a complete valid decision; nonstreamed calls have no TTFT metric.",
                      "Consumption age is measured at the coordinator, not after return-network delivery."]}
