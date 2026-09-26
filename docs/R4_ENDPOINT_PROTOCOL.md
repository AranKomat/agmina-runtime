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

For a retained real run, provider identity must be audited separately from the runtime report. The
metadata-only `tools/r4_audit_generations.py` command queries each successful provider generation ID
without making inference calls. `tools/r4_evaluate_endpoint_matrix.py --generation-audit PATH`
qualifies revision pinning when every dispatched attempt in the matrix has a successful record and
all records agree on provider and served model revision. A configured base model name may match a
provider's dated revision suffix, such as `z-ai/glm-5.3-flash` and
`z-ai/glm-5.3-flash-20260826`. This is identity/accounting evidence only; it is not semantic-quality
evidence and does not reconcile invoices by itself.

The first matrix can establish a scheduler-specific endpoint result only if all three conditions use
the same declared endpoint and have complete accounting. It does not establish a universal scheduler
winner. Follow-up load levels should reuse the same source/model and separately compare unloaded,
near-capacity, overloaded, bursty, and injected-delay/loss conditions. Cache, latest-only, placement,
and joint variants are separate ablations and must not be mixed into the scheduler-only result.

## Load-plan controls for isolated ablations

`LoadItem` exposes the runtime controls needed for those variants without changing the
application-facing `Job` contract:

- `cacheable: true` is permitted only for historical, non-policy work.
- `replace_key` requires `discardable: true`; replacement remains scoped to the same session,
  task revision, model, and operation.
- `observation_ids` is optional. Use it only when two jobs intentionally refer to the exact same
  retained evidence. Hashes, capture time, availability time, and source session still enter the
  cache key, so changing any of them must produce a miss.
- `operation` defaults to `paced_load` and can separate ablation families without changing the
  scheduler trace.

The controls are rejected for policy jobs so a load-plan cache/latest-only experiment cannot
silently drop a control action. A real cache comparison must first pass the corresponding mock
test, use duplicate historical queries with stable evidence IDs, and keep source evidence unchanged.

The first real latest-only probe used the source plan's 20-second deadline and correctly exposed
that the endpoint's conservative 19-second estimate left no feasible successor after a blocker.
The matched follow-up explicitly used a 60-second deadline and recorded the changed deadline in its
preparation manifest. This is the required pattern for interpreting the latest-only result; do not
silently widen deadlines inside a scheduler comparison.
