# Agmina Runtime Experiment Status

**Protocol:** R0-R8 in [EXPERIMENTS.md](EXPERIMENTS.md)  
**Repository:** `AranKomat/agmina-runtime`  
**Last updated:** 2026-09-25

This is the working checklist for the Agmina Runtime experiment program. The R-series definitions
and acceptance criteria remain in `docs/EXPERIMENTS.md`; this file records what has actually been
run. A synthetic or shape-level check must not be promoted to an endpoint, application-quality,
hardware, or physical-task result.

## Status At A Glance

| Stage | Status | Current evidence / next gate |
|---|---|---|
| R0 | **Complete** | Local software reproduction and validation passed; see `VALIDATION.md`. |
| R1 | **Pending** | Add one read-only StreamBudget bridge, then one physical-harness bridge, against pinned application commits. |
| R2 | **Pending** | Run one authorized real endpoint with direct-call equivalence, complete-output timing, and charge receipts. |
| R3 | **Pending** | Run paced 1/2/4/8-session load against the selected real endpoint. |
| R4 | **Partial: synthetic only** | Deterministic scheduler replay and mock contention pass; real endpoint placement/cancellation study remains. |
| R5 | **Pending** | Run fixed-camera StreamBudget quality/cost evaluation with held-out labels. |
| R6 | **Pending** | Qualify a compatible stateless policy/simulator loop; preserve native action and safety gates. |
| R7 | **Pending** | Compare one additional compute/site class with model and precision differences disclosed. |
| R8 | **Pending** | Run one design-partner pilot and repeat the same protocol with a second partner. |

## Checklist

### R0 — Reproduce The Foundation

- [x] Install the package and development/server dependencies in a supported environment.
- [x] Run the complete local test suite: 136 passed at publication validation.
- [x] Run compilation, repository/link checks, doctor, demo, replay, and synthetic paced load.
- [x] Run Ruff and the authenticated localhost sidecar/SDK smoke.
- [x] Build and import the wheel outside the source tree.
- [x] Verify zero paid model calls and zero native robot actions.
- [x] Preserve the deterministic replay's blocking-background negative control.

**R0 conclusion:** the coordinator's local software invariants are reproduced. This says nothing
about model quality, GPU performance, StreamBudget quality, or robot competence.

### R1 — Read-Only Application Bridges

- [ ] Pin the StreamBudget application commit and retained-evidence campaign.
- [ ] Compare Agmina-generated source hash, image order/detail, prompt, cutoff, clock mapping,
  task/episode identity, and accounting fields with the original StreamBudget request.
- [ ] Run the StreamBudget bridge without changing watch, evidence-selection, parser, or ledger
  authority.
- [ ] Pin the Physical Agent Harness commit and retained FrameRef campaign.
- [ ] Run the physical-harness bridge in discovery/shadow mode only.
- [ ] Exercise old-task results, late responses, epoch changes, invalid source hashes, and
  pending/in-flight shutdown in both bridge paths.

**Gate:** source-bound requests round-trip without semantic or authority changes.

### R2 — One Real Endpoint

- [ ] Select one model and one serving endpoint already useful for the chosen workload.
- [ ] Record checkpoint/model revision, preprocessing, sampling, output schema, server revision,
  hardware, precision, routing, and declared budget before dispatch.
- [ ] Run the same authorized packet directly and through Agmina.
- [ ] Measure cold load/compile separately from warm first-content and complete-usable-output time.
- [ ] Reconcile charge receipts and unknown-charge holds by attempt ID.

**Gate:** valid native outputs, equivalent intended requests, complete accounting, and measured
timings. A transport pass is not a quality pass.

### R3 — Paced Multi-Session Load

- [ ] Prepare a retained, authorized workload plan with declared arrival times and deadlines.
- [ ] Run one, two, four, and eight sessions within a predeclared cap.
- [ ] Keep offered, rejected, expired, cancelled, late, and completed work in the denominator.
- [ ] Check no duplicate dispatch, cross-epoch consumption, or unbounded queue growth.
- [ ] Record endpoint response distributions and resident resource telemetry.

**Gate:** useful completions remain within the declared freshness and capacity constraints.

### R4 — Scheduling, Placement, And Cancellation

- [x] Run deterministic FIFO/EDF/least-slack replay on a shared synthetic trace.
- [x] Exercise synthetic profile error, blocking background work, expiry, and pool recovery.
- [ ] Repeat on the real endpoint while holding model, precision, source data, server batching,
  pool capacity, and deadline semantics fixed.
- [ ] Compare scheduler-only, cache-only, latest-only, placement-only, and joint variants.
- [ ] Measure unloaded, near-capacity, overloaded, bursty, and injected-delay/loss conditions.

**Current limitation:** synthetic replay is evidence for coordinator behavior only, not endpoint
throughput or semantic quality.

### R5 — StreamBudget Quality And Cost

- [ ] Freeze a fixed-camera workload, event taxonomy, held-out labels, negative segments, and
  quality/latency constraints.
- [ ] Run fixed-rate VLM, tuned detector/motion refresh, and existing StreamBudget adaptive baselines.
- [ ] Add Agmina beneath the same selection policy to isolate serving effects.
- [ ] Measure event recall, false alerts per camera-hour, alert latency, evidence support, calls,
  tokens, bytes, GPU time where available, and cost per camera-hour.

**Gate:** cost/capacity improvement while meeting the predeclared quality and latency constraints.

### R6 — Policy/Simulator Closed Loop

- [ ] Choose a compatible policy/simulator recipe with a native observation/action codec.
- [ ] Replay recorded policy inputs with no actions first.
- [ ] Compare direct server and Agmina paths under the identical recipe.
- [ ] Keep local control, emergency behavior, action admission, verification, and recovery in the
  application host.
- [ ] Exercise epoch changes, stale catalogs, clock uncertainty, target movement, network stalls,
  and buffer exhaustion.
- [ ] Record task/progress outcomes, prediction age, idle/stall intervals, corrections, and action
  counts; independently verify outcomes.

**Gate:** native gates and closed-loop outcome evidence pass. A timer fixture or open-loop replay is
not sufficient.

### R7 — Heterogeneous Compute

- [ ] Add one additional endpoint or device class after R2-R4 are stable.
- [ ] Freeze the model and precision where comparable, and disclose changed kernels/sampling.
- [ ] Record actual device telemetry; do not infer Jetson or AMD results from another host.
- [ ] Keep operator-owned NVIDIA-only perception/control dependencies on qualified NVIDIA hosts.

**Gate:** comparison is reproducible and does not hide model, precision, hardware, or drop-rate
differences.

### R8 — Design-Partner Validation

- [ ] Select one initial buyer/workload and obtain an authorized current trace.
- [ ] Run one repeatable read-only integration with an explicit ownership boundary.
- [ ] Measure a concrete value signal: capacity, predictability, reduced intervention, or integration.
- [ ] Repeat the same coordinator/protocol with a second partner without forking the runtime.

**Gate:** evidence of reusable value, or a deliberate narrowing of the product boundary.

## Resource Plan

### Can run locally without GPU or paid calls

- R0, including all delivered software checks.
- R1 request-shape and bridge tests using retained synthetic/fixture evidence.
- R4 deterministic replay and coordinator fault-injection tests.
- Documentation, manifests, source review, and report tooling.

### Requires an operator-authorized endpoint or application environment

- R1 full parent-repository bridge execution.
- R2 real model/provider or local model server.
- R3 and real R4 endpoint load.
- R5 StreamBudget retained footage and independent labels.
- R6 compatible policy/simulator and, if applicable, a GPU.
- R7 additional hardware/device class.
- R8 partner data and authorization.

Do not rent or provision a GPU for R0/R1 contract work. Before any paid call or GPU rental, pin the
workload, cap, model/endpoint, retention policy, and primary metric. Preserve failed and uncertain
work; do not retry automatically or treat an uncharged result as proof of zero cost.

## Evidence Naming

Use fresh output directories and names such as `runs/r2-transport-001` or
`runs/r5-streambudget-001`. Each campaign should retain:

- code/config/model/hardware/data pins and input hashes;
- arrival, capture, availability, dispatch, first-content, complete, and consume times;
- offered, rejected, expired, cancelled, failed, late, and completed counts;
- charge receipts or explicit unknown-charge holds;
- quality labels and independent outcome references where applicable.

Never report synthetic replay as model quality, hosted wall time as GPU time, or a met deadline as
robot competence.
