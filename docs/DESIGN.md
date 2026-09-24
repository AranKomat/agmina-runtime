# Design and invariants

## One responsibility boundary

Agmina coordinates **inference requests**, not robot actions or business decisions. The physical
harness and StreamBudget retain their source stores, state, memory, task/watch logic and verification.
A common inference coordinator need not merge their entity definitions or duplicate their databases.
SQLite here is a journal for sessions, requests, receipts and estimated charges, not a world model.

The implementation is deliberately a single-writer asyncio process. GPU libraries and robot packages
are not core dependencies. Operator-managed servers may use NVIDIA, AMD, or hosted infrastructure.
This is hardware-neutral at the RPC boundary, not evidence that every model runs on every device.

## Time is not a float named `timestamp`

All scheduling times are integer nanoseconds in one **named monotonic clock epoch**. Observations
have capture, availability, uncertainty and source identity. Historical simulator/video time can be
preserved as metadata but is never subtracted from runtime wall time.

A remote host must supply an explicit `ClockMap` with offset, uncertainty and validity duration. This
library does not assume clocks are synchronized. A coordinator restart changes clock ID, closes old
sessions and invalidates queued/in-flight work for new consumption. The budget survives.

For a current/action result, the latest useful time is the minimum of:

- the request's end-to-end deadline;
- every current observation's capture time plus allowed age, less clock uncertainty;
- an optional current policy-buffer deadline supplied by the host.

Context/history frames are not required to be fresh, but must be causally available at the declared
snapshot. The buffer timestamp is an advisory workload signal, not proof that continued motion is safe.

Validation occurs at submission, immediately before backend dispatch, after inference, at server
consumption, and again after transport through `client.validate_delivery`. The last check uses the
consumer's **current** epoch/task and (for a policy) local useful-completion deadline. A fresh server
reply can become stale in the network. None of these checks replaces the native ActionExecutor.

## Scheduling and resource accounting

`fifo`, `edf`, and `slack` share the same expiration/profile/admission rules. Least-slack orders by
`latest - now - estimated_service`, then priority and arrival. It is a transparent heuristic, not a
Kairos reproduction, optimal scheduler or hard-real-time guarantee. Fairness/starvation under overload
is an experiment, not a claimed property.

Endpoint profiles are static operator-supplied estimates. The sum of a service p95, transport p95 and
margin is a heuristic envelope; it is not generally the joint p95. Use held-out burst/jitter traces.
The simulator never exposes its actual future service time to the scheduling function.

All endpoints sharing one physical GPU should normally reference one pool. One slot means exclusive
**cooperative dispatch among participating workers**, not ownership of the GPU against other processes.
Increasing slots without measuring interference or resident memory is unsafe for performance claims.
Nothing unloads models, arbitrates VRAM, or preempts a running CUDA/ROCm kernel.

A long background request can block an urgent arrival even with the best queue order. The negative
control demonstrates that limitation. Later remedies require bounded background chunks, capacity
reservation or backend cooperation, not a more optimistic headline.

## Placement and model semantics

Each replica belongs to a configured ModelContract: weights/provenance, preprocessing, sampling and
output schema. Placement never swaps a model alias because it is cheaper. Sites are allowlisted per
request. `cheapest_feasible` minimizes a configured reservation estimate only among predicted-feasible
replicas; it is not an optimizer for total GPU rental or customer value.

The configured revision is an operator claim. Matching the returned HTTP model name does not prove
immutable hosted weights. Record provider routing, precision and actual revision when observable.
Unknown revision stays unknown. Downstream providers may route internally unless pinned there too.

Version 0.1 accepts stateless inference only. A SAM video tracker or temporal policy server that mutates
hidden state cannot be safely treated as a load-balanced stateless endpoint. Keep it host-owned or
explicitly supply and validate the complete history using its native recipe. Do not change that recipe
merely to fit this interface.

## Results, failures and cancellation

A successful inference result means only that a backend returned its transport/schema envelope. The
application parses the semantics and verifies the task. A policy tensor must pass its checkpoint codec
and native geometry/control checks. An output does not authorize a trajectory.

`consume()` records a claiming consumer; another consumer is rejected. Same-consumer retrieval is
idempotent but rechecks freshness. This is not exactly-once physical execution. The host must persist
its own action idempotency/epochs at the actual actuator boundary.

Cancelling queued work avoids a call. Cancelling in-flight work prevents delivery but keeps the slot
until the backend finishes. Transport timeout, coordinator cancellation or ambiguous backend error
quarantines the resource pool. The operator must confirm remote termination/restart before releasing it.
A cancelled HTTP client is not proof that billing or GPU work stopped.

On restart, queued work becomes cancelled; in-flight work becomes unknown; affected pools remain
quarantined. Old successful results remain audit records but cannot be consumed in a new clock/session.
No native controller restart or emergency stop is implemented here.

## Reuse and backpressure

Historical caching is opt-in and exact: same tenant, session, epoch, task, operation, model contract,
payload, evidence content/times and snapshot. New timestamps with identical pixels are not the same
observation. Different questions are not the same result. Actions and current perception are excluded.
A hit retains original computation time, uses a fresh delivery time and passes the same consumer fence.
Caching changes stochastic-sampling independence, so leave it off in model-quality comparisons.

Latest-only replacement can supersede a queued discardable job with a strictly newer snapshot for the
same session/epoch/task/model/operation/key. It never cancels an in-flight call or discards a queued
parent still needed by a dependent job. Do not use it for SAM frame sequences or policy history.
The source app should retain interesting transient frames and publish omission metrics.

Dependencies are scheduling barriers, not automatic prompt construction. Source lineage must be
included. The scheduler never splices an unavailable future result into a frozen prompt; host-side
follow-on reasoning should create a new request after its inputs actually exist.

## What is measured

Measured here: offered/admitted/expired/cancelled work, coordinator queue time, backend roundtrip,
first content when SSE supports it, complete prediction time, consumption age, provider token counts,
estimated/reconciled spend, exact historical cache hits, and externally reported consumption outcomes.

Not inferred: CUDA time, real-time factor, GPU energy, event recall, task success, contact safety, value
of a historical memory, or the correctness of a model's JSON. The summary leaves those fields null.
First content is not a complete decision. Error, stale, rejected and expired work stays in denominators.

## Additional limits on cost and dependency interpretation

`cheapest_feasible` orders endpoints by their configured reservation amount, then estimated latency.
It is not a total-cost-of-ownership optimizer; unpriced GPU rental and energy are not implicitly zero.
A local endpoint with zero provider charges can still have substantial infrastructure cost.

Evidence identity includes source, source ID, sequence, capture/availability times and uncertainty.
Identical image bytes do not substitute for that identity. The current/context role is request-local.
Dependencies gate execution and preserve declared input lineage; the runtime does not inject a
parent's model output into a child's immutable prompt. Submit a new, explicitly prepared request when
an application needs to consume newly generated output.
