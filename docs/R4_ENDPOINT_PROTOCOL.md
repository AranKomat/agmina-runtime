# R4 Real Endpoint Protocol

**Status:** prepared, not yet dispatched. The first run is transport/scheduling evidence, not a
semantic-quality, GPU-time, or robot result.

## First Matrix

Use the retained `runs/r3-streamarena-glm-cohort-20260926-002/plan-s4.json` cohort and its matching
`config-s4.json` as the source. It contains 16 hash-verified jobs across four sessions, one endpoint
slot, 20-second freshness deadlines, and a 32,000 micro-USD per-condition admission cap. The matrix
holds model, provider order, endpoint, pool capacity, source frames, deadline semantics, and output
schema constant while changing only the scheduler:

```text
FIFO -> EDF -> least-slack
```

Prepare the fresh campaign directories without making calls:

```bash
.venv/bin/python tools/r4_prepare_endpoint_matrix.py \
  --base-config runs/r3-streamarena-glm-cohort-20260926-002/config-s4.json \
  --plan runs/r3-streamarena-glm-cohort-20260926-002/plan-s4.json \
  --out runs/r4-endpoint-matrix-prep-001
```

When the operator-pinned provider credential and endpoint are available, run each generated config
with the same plan through `agmina load`, using a fresh output directory per condition. Do not retry a
failed condition automatically. Reconcile every attempt before comparing cost or declaring a result.

## Measurements and Gate

Retain all offered, rejected, expired, cancelled, failed, late, and consumed jobs. Report useful
completion rate, queue/complete-output latency distributions, deadline misses, quarantine/recovery,
provider request IDs, and per-attempt charge status. Resource occupancy and GPU/energy telemetry are
unknown unless measured by the host.

The first matrix can establish a scheduler-specific endpoint result only if all three conditions use
the same declared endpoint and have complete accounting. It does not establish a universal scheduler
winner. Follow-up load levels should reuse the same source/model and separately compare unloaded,
near-capacity, overloaded, bursty, and injected-delay/loss conditions. Cache, latest-only, placement,
and joint variants are separate ablations and must not be mixed into the scheduler-only result.
