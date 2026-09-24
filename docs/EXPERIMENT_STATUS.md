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
| R1 | **Partial: retained read-only integration** | Fixture/fault integration, retained lineage comparison, and clock-reset/generation fences pass; a broader cross-product fault matrix and real task/episode identity fields remain. |
| R2 | **Partial: endpoint handshake** | The first authorized OpenRouter trial exposed a provider response-model omission and later incomplete/timeout behavior; no direct/Agmina usable pair or charge reconciliation yet. |
| R3 | **Pending** | Run paced 1/2/4/8-session load against the selected real endpoint. |
| R4 | **Partial: synthetic only** | Deterministic scheduler replay and mock contention pass; real endpoint placement/cancellation study remains. |
| R5 | **Partial: development baseline only** | Retained and visual-QA provenance audits pass, and a prior GLM/Gemini status baseline is recorded; the data is not held out, so no quality claim. |
| R6 | **Pending** | Qualify a compatible stateless policy/simulator loop; preserve native action and safety gates. |
| R7 | **Pending** | Compare one additional compute/site class with model and precision differences disclosed. |
| R8 | **Pending** | Run one design-partner pilot and repeat the same protocol with a second partner. |

## Checklist

### R0 — Reproduce The Foundation

- [x] Install the package and development/server dependencies in a supported environment.
- [x] Run the complete local test suite: 138 passed in the current workspace.
- [x] Run compilation, repository/link checks, doctor, demo, replay, and synthetic paced load.
- [x] Run Ruff and the authenticated localhost sidecar/SDK smoke.
- [x] Build and import the wheel outside the source tree.
- [x] Verify zero paid model calls and zero native robot actions.
- [x] Preserve the deterministic replay's blocking-background negative control.

**R0 conclusion:** the coordinator's local software invariants are reproduced. This says nothing
about model quality, GPU performance, StreamBudget quality, or robot competence.

### R1 — Read-Only Application Bridges

- [x] Pin the StreamBudget interface commit used for the smoke: `076783012377d074b82efd7aaf296a8175b3a7f4`.
- [x] Record the Physical Harness contract checkout used for the smoke; current HEAD is
  `20f5c9baf42158bf3d37e122984c0f2d03794014`.
- [x] Run a no-network StreamBudget bridge smoke using its actual `Request` and `ImageInput` types.
- [x] Run a no-network physical bridge smoke using its actual `Basis` and `FrameRef` types.
- [x] Confirm source image hash, evidence sequence, capture/availability mapping, and simulator-time
  preservation in the returned contracts.
- [x] Deliver a fixture result through Agmina into StreamBudget's actual `Perception` validator.
- [x] Deliver a fixture semantic result through Agmina into the Physical Harness discovery parser.
- [x] Run the actual StreamBudget watch scheduler through both its native mock and Agmina-routed
  fixture paths; compare parent-visible alert, ledger-attempt, and status results.
- [x] Run the actual Physical Harness discovery coordinator, async worker, journal, and inventory
  writer with Agmina inside the read-only worker callback.
- [x] Compare fixture prompt/image message order and response-format payloads at the StreamBudget
  boundary, while preserving the parent ledger as the accounting owner.
- [x] Confirm invalid source bytes and a stale epoch are rejected after delivery.
- [x] Compare Agmina-generated source hash, image order/detail, prompt, cutoff, clock mapping,
  and accounting fields with the original retained StreamBudget requests; the report records that
  the parent request supplies no task/episode identity fields.
- [x] Run the StreamBudget bridge without changing watch, evidence-selection, parser, or ledger
  authority.
- [x] Record the live parent checkout state for each smoke (the current Physical Harness checkout is
  `20f5c9baf42158bf3d37e122984c0f2d03794014`; dirty state is reported rather than hidden).
- [x] Run the physical-harness bridge in discovery/shadow mode only.
- [ ] Exercise old-task results, late responses, epoch changes, invalid source hashes, and
  pending/in-flight shutdown in both bridge paths.
- [x] Run the actual parent fault smoke: StreamBudget in-flight shutdown, Physical Harness late
  response rejection, old-task historical-only delivery, and in-flight shutdown ambiguity.
- [x] Run a two-path clock-reset/generation-fence smoke covering stale consumption, target-clock
  mismatch, and expired mapping rejection.

**Gate:** source-bound requests round-trip without semantic or authority changes.

**Current evidence:** the workflow smoke `runs/r1-workflow-010` and fault campaign
`runs/r1-fault-006` passed with zero paid calls, zero
GPU work, and zero native actions. The fault campaign confirms StreamBudget does not publish an
alert after an in-flight shutdown; Physical Harness archives a late result as an error, delivers
an old-task result only as historical inventory without waking the current executive, and reports
that an in-flight callback cannot be declared stopped until it exits. The retained request
comparison `runs/r1-retained-004` verifies source hashes, image order/detail, prompt, cutoff, clock
mapping, and parent accounting; task/episode identity is absent from the StreamBudget request
contract. The clock-reset campaign `runs/r1-clock-005` rejects stale consumption, target-clock
mismatch, and expired mappings for both adapters. Parent checkout commit and dirty state are
retained in each report; the broader cross-product fault matrix remains open.

The retained replay `runs/r1-retained-004` adds six source PNGs from two video identities using the
receipt's original order, timestamps, sizes, and SHA-256 values. The native StreamBudget mock path
and the Agmina-routed path each produced five admitted requests and two parent-visible alerts; all
five routed request payloads were equivalent, and all reported lineage checks passed. This is
read-only lineage and parent-behavior evidence, not a hosted model or quality result.

### R2 — One Real Endpoint

- [x] Select one declared model and serving endpoint for the bounded transport trial: OpenRouter
  `z-ai/glm-5.3-flash`, with the synthetic vision packet and no quality claim.
- [x] Exercise the direct path and preserve provider-contract failures rather than silently retrying.
- [x] Run the no-network preflight for provider order, exact request body, fallback policy,
  reservation, and request fingerprint: `runs/r2-preflight-001`.
- [ ] Complete one successful direct/Agmina pair on a pinned endpoint.
- [ ] Record checkpoint/model revision, preprocessing, sampling, output schema, server revision,
  hardware, precision, routing, and declared budget before dispatch.
- [ ] Run the same authorized packet directly and through Agmina.
- [ ] Measure cold load/compile separately from warm first-content and complete-usable-output time.
- [ ] Reconcile charge receipts and unknown-charge holds by attempt ID.

**Gate:** valid native outputs, equivalent intended requests, complete accounting, and measured
timings. A transport pass is not a quality pass.

**Current evidence:** the local comparison harness passed against a loopback chat server and proved
identical validated request bodies and output fingerprints. The authorized hosted trial is not a
pass: the provider returned HTTP 200 without the response `model` field, which the default strict
binding rejected; an explicit `response_model_required=false` pin was then prepared, but the next
attempt did not produce a complete report within the endpoint/tool timeout. Failed and uncertain
attempts are retained under `runs/r2-transport-002` and `runs/r2-transport-003`; external charge
status remains unknown and must be reconciled before any claim. The next R2 action is a fresh,
operator-pinned endpoint or provider, not more blind retries of this route.

The no-network preflight `runs/r2-preflight-001` passed with zero network and paid calls. It
validated the exact outbound request body and fingerprint, the declared model contract, the `$0.25`
campaign ceiling, the `$0.05` endpoint reservation, and the requested provider order
`Together -> Fireworks -> Baseten -> CoreWeave` with fallbacks disabled. This is configuration and
transport-readiness evidence only; it does not establish provider availability, endpoint latency,
model quality, or a charge receipt.

**Next endpoint candidate:** `configs/openrouter-glm.template.json` pins the requested provider
preference order `Together -> Fireworks -> Baseten -> CoreWeave` with fallback disabled. Before a
new paid run, replace the model revision/profile placeholders, confirm the provider order is
supported by the account, and declare a fresh campaign cap. The route preference is not evidence
that any particular provider actually served a request.

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

The consolidated profile-error replay `runs/r4-synthetic-001` offered 539 requests across policy,
semantic, and mapping workloads under the same trace and compared FIFO, EDF, and least-slack. On
this trace FIFO protected mapping (26/26 completed in time) but admitted only 2/335 policy requests
in time; EDF admitted 108/335 policy requests in time while mapping fell to 7/26; least-slack was
intermediate but had the highest queue and completion-age p95 values. This is a synthetic workload
tradeoff, not an endpoint or quality result, and it reinforces the requirement to report outcomes by
workload rather than selecting a universal scheduler winner.

### R5 — StreamBudget Quality And Cost

- [x] Audit the retained six-frame campaign's receipt, frame hashes, timestamps, and video identities.
- [ ] Freeze a fixed-camera workload, event taxonomy, held-out labels, negative segments, and
  quality/latency constraints.
- [ ] Run fixed-rate VLM, tuned detector/motion refresh, and existing StreamBudget adaptive baselines.
- [ ] Add Agmina beneath the same selection policy to isolate serving effects.
- [ ] Measure event recall, false alerts per camera-hour, alert latency, evidence support, calls,
  tokens, bytes, GPU time where available, and cost per camera-hour.

**Gate:** cost/capacity improvement while meeting the predeclared quality and latency constraints.

The audit `runs/r5-audit-003` verifies all six retained-frame hashes and two video identities, but
records `r5_qualification: not_qualified`: the receipt says evaluator-only annotation/resolution
audit, `model_calls: 0`, and supplies no independent labels. The broader visual-QA audit
`runs/r5-audit-visual-001` verifies all six packet hashes and 1,107 packet frames; its six-case
label file is present, but the packet manifest explicitly says “Post-hoc development qualification,
not a held-out benchmark.” The receipt audit `runs/r5-dev-audit-002` records 12 completed
development trials (GLM and Gemini), 32 request attempts, and `$0.016686395` reported spend; all
12 abstention/answerability statuses matched the rubric, but this is only a development status
check, not answer-quality or held-out evidence. The next R5 step is to obtain or reserve an
untouched held-out split, then freeze the event/latency protocol before model comparison.

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
