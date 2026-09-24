# Agmina Runtime 0.1 — self-contained research-agent handoff

**Prepared:** 2026-09-24. **Delivery:** a new standalone repository, `agmina-runtime`.
**Mission:** establish a useful common inference boundary for continuous-video applications and
physical-agent workloads without merging or rewriting the two existing application repositories.

No prior conversation is needed to use this document. The package is a tested research foundation,
not a hosted service, trained model, deployed robot controller, or demonstrated speedup.

## 1. Why this repository exists

There are already two research applications:

1. **Physical Agent Harness** owns embodied reasoning, geometry, persistent physical identity,
   maps, capability graphs, action admission, native control, verification and recovery.
2. **StreamBudget** owns standing video objectives, frame/evidence selection, semantic memory,
   retrospective investigation, event detection and their quality evaluation.

Both need to submit asynchronous model work, choose where it runs, bound queues and costs, retain
provenance and refuse stale results. That shared compute boundary is the purpose of Agmina Runtime.
It does not create a third world model, planner, video evidence database or robot-control framework.

Technical scope is **continuous, evidence-bound inference with different urgency/freshness needs**.
It is not limited to robot policies and is not a universal multimodal model server. The first two
reference workloads are video semantic inference and robot/policy inference. It is compatible with
using existing vendor/OpenAI-compatible servers; it does not replace their kernels or GPU batchers.

## 2. Delivery and source-review baseline

The existing repositories were read through GitHub at:

- `AranKomat/streambudget`: `076783012377d074b82efd7aaf296a8175b3a7f4`.
- `AranKomat/physical-agent-harness`: `cc03d4ed1ecb1664d9c1d04f6adc13786385f6d5`.

The reviewed StreamBudget `backend.Request`, `ImageInput`, `Result` and physical
`perception.contracts.FrameRef` fields inform the thin bridge helpers. Full checkouts could not be
cloned from this environment. No current upstream suite or native application was executed here.
The new repository is complete in its own right; the bridge tests use declared interface-shape
fixtures, not undocumented assumptions that either full application has been integrated.

No GitHub files were edited or pushed. Do not reapply old V1/V2/V3 installers. Put this beside the
other repositories and connect it through an optional library dependency or authenticated sidecar.
No source from either repository is copied into this package.

## 3. Architectural ownership

```text
APPLICATIONS
  StreamBudget: watch/query, evidence, relevance, semantic output quality
  Physical harness: task/world state, identity, candidates, actions, verification
       |
       | immutable source-bound inference request
       v
AGMINA RUNTIME
  session/epoch + named monotonic clock
  compatible endpoint registry + cooperative resource pools
  queue policy + deadlines + placement + exact historical cache
  attempt/spend journal + recovery + complete result delivery
       |
       +--> chat-compatible VLM endpoint
       +--> Triton V2 tensor endpoint
       +--> stateless native-model worker adapter
       |
       v
APPLICATION CONSUMER
  current local epoch/freshness check AFTER network delivery
  domain parser / evidence publication / independent native action admission
```

The runtime **never** calls a motor, invokes an inspection action, writes authoritative geometry,
changes a policy's codec, or marks task success. GPT remains the physical application's recurrent
embodied executive; GLM remains its read-only discovery worker. This delivery does not decide how
often either should reason. The applications retain those policies.

## 4. What is actually implemented

### Sessions and clocks

Requests identify tenant, session, execution epoch, task revision and clock ID. Observations have
source ID, sequence, byte hash, capture time, availability and uncertainty. Current views and
historical context are separate. A remote clock requires an explicit mapping; simulator time is
never treated as wall time. Restart changes coordinator clock epoch and closes old sessions.

### Scheduling and placement

FIFO, earliest-deadline and least-slack request ordering are executable. They use the same
admission/freshness rules. Placement chooses a configured compatible replica by estimated finish
or lowest reservation estimate that fits. The backend model contract contains weights/provenance,
preprocessing, sampling and output-schema references. There is no automatic model substitution.

Pools have cooperative slot counts; default one concurrent call on a shared GPU pool. This limits
only work submitted through this coordinator. It is not GPU memory partitioning or preemption.
Profiles are operator-supplied, not self-calibrated hard bounds. The sum of service/transport p95s
and margin is a heuristic, not proof of a joint p95.

### Freshness and consumption

Requests are checked at ingress, dispatch, immediately before calling a backend, after completion,
at server consumption and again by the client-side delivery fence. A task/epoch change invalidates
old work. A result that expires during the network return is rejected. Policy consumers also supply
their current local useful-completion deadline. Passing these checks still does not authorize motion.

### Budget and lifecycle

SQLite/WAL records original requests, receipts, attempts and metadata-only events. Estimated charge
reservations and call ceilings are cumulative across restart. Unknown charges stay held; usage is
not fabricated as zero. Explicit reconciliation and cumulative cap extension require operator
references. A provider-side spending cap is still necessary for invoices.

No automatic retries are performed. Cancelling an in-flight consumer does not pretend to cancel GPU
work: its slot remains occupied until completion. An unconfirmed timeout or shutdown quarantines
the pool. Restart does not reissue queued or in-flight inference. Pool release requires an operator
confirmation of actual worker termination/restart. Physical exactly-once execution remains the host's job.

### Reuse and bounded work

Exact completed-result caching is supported only for opt-in historical queries with the same complete
evidence, session/epoch/task, operation, payload and model contract. It is bounded by entries, bytes
and TTL. It is not a learned semantic cache or encoder/KV feature cache.

Latest-only replacement applies only to explicitly discardable queued work with a newer snapshot.
It does not drop in-flight work, necessary dependencies, stateful tracker frames or policy history.
The host must preserve potentially relevant transient frames. A full queue can still reject work;
this prototype offers no hard admission or starvation guarantee.

### Backends and measurement

Chat-compatible HTTP sends source-hashed inline images to a fixed endpoint, assembles complete SSE
responses, records first-content time and normalizes usage. Partial/truncated outputs are not delivered
as complete decisions. It does not expose partial JSON to physical control.

The Triton adapter sends/validates finite typed JSON tensors and checks returned model/version fields.
The generic worker adapter binds job ID and epoch in the response. A synthetic worker server is
included as an example—not as a SAM/VLA implementation.

Telemetry records offered/rejected/expired/cancelled requests, queue/backend roundtrip, first content,
complete prediction and consumption age. GPU time, energy, semantic quality and physical task success
are left null. An external outcome reference is a consumer report, not independent verification.

## 5. What is deliberately NOT implemented

- No model weights, paid provider calls, GPU kernels, CUDA/ROCm workers or Jetson tests.
- No GPU-level batching, preemption, SM partitioning, memory-residency manager or neural feature reuse.
- No automatic migration of recurrent model state. `stateful=True` is rejected. Keep SAM video
  tracking and temporal policy queues host-owned until reset/sequence protocols are qualified.
- No direct vla.cpp/FluxVLA native-protocol adapter; their exact interfaces still need a pinned wrapper.
- No ROS, Microsoft lifecycle, DeepStream, Holoscan, RTSP/video decode or native audio deployment.
- No semantic frame-selection replacement, model routing by quality, policy training or distillation.
- No production multi-tenant IAM, safety certification, robot rental/operation or customer integration.
- No measured cost/quality advantage, event-recall result, GPU speedup or robot-success gain.

These are boundaries, not hidden TODOs behind successful mock results. They are enumerated so the
research agent does not mistake a generic worker interface for qualified native behavior.

## 6. Start locally

Python 3.11+; Linux/macOS are intended. File locking uses Unix `fcntl`.

```bash
cd agmina-runtime
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,server]'
agmina doctor
agmina demo --out runs/demo-001
agmina replay --out runs/replay-001
agmina load --config configs/mock.json --plan examples/mock_load.json --out runs/load-001
python tools/validate.py --out runs/validation-001
```

All default examples are local synthetic tests, with zero paid calls and zero native actions. Reusing
an output directory fails. The validator reports every command and unavailable tool explicitly.
Read `VALIDATION.md` for what was actually run during delivery; do not invent a new full-suite count.

The replay compares three policies on the **same** arrival/service trace, with future service times
hidden from scheduling. It includes a negative case where a long running background job blocks all
policies. Its measurements are virtual trace results, not GPU or robot measurements.

The paced load driver is different: source arrivals continue while asynchronous endpoint calls run.
It records arrival lag and offered work. Prepared-input replay excludes source capture and decoding.
That distinction must remain visible in reports.

## 7. Run a real VLM endpoint

Choose one model already useful on your application. Use a separate model-serving environment and
edit `configs/local-chat.template.json`:

- real served model ID;
- exact checkpoint/preprocessing/sampling revision, or explicitly unknown hosted revision;
- fixed endpoint URL;
- measured service/transport profile and margin;
- output/response limits;
- credential environment-variable name, if needed;
- positive per-attempt reservation and separately authorized cumulative budget for billed endpoints.

```bash
agmina probe --config configs/local-chat.template.json \
  --packet examples/vision_packet.json --model vision --count 3 \
  --out runs/endpoint-001 --allow-network

agmina load --config configs/local-chat.template.json \
  --plan examples/vision_load.json --out runs/endpoint-load-001 --allow-network
```

The included packet is a generated red square and the included real-endpoint load plan has four
requests. They test transport and timing, not real vision quality. Replace them with authorized
retained inputs only after that works. Model name validation does not attest immutable weights or
provider routing; record those separately. Keep strong serving-engine batching baselines enabled.

Do not use an existing exhausted project call ceiling. Agmina's ledger is not permission to spend.
The parent application's approvals remain authoritative. Reconcile one actual provider charge once,
while correlating all additional guard ledgers by attempt ID.

## 8. Sidecar and host integration

```bash
export AGMINA_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
agmina serve --config configs/mock.json --database runs/sidecar/ledger.sqlite --port 8766
```

The sidecar binds loopback and requires a bearer token. It exposes clock, session, epoch advance,
heartbeat, submit, result status, consume, cancel and metrics. It accepts no arbitrary endpoint URLs,
remote image URLs, model installation or robot commands. Use TLS/authenticated tunnels outside
loopback; production security needs further work.

**StreamBudget integration:** keep ModelPool prompt preparation and downstream parser semantics.
Build a source-bound Job using `streambudget_job()` with source availability from the evidence store.
Map video/replay time to the runtime clock explicitly. Submit only the selected work; do not rebuild
its watch scheduler inside Agmina. Return the chat text to the original Result/parser and reconcile
its original campaign ledger. Compare exact outgoing image order/detail and prompts before benchmarking.

**Physical harness integration:** start read-only at discovery/shadow inference. Convert FrameRef using
`physical_observation()`; verify original bytes; map captured_wall and available_wall rather than
sim_time. Keep live SAM state, policy queue/history, full native codec and execution ownership in the
host. A returned policy proposal goes through client freshness, native codec and fresh action-catalog
review. Use `ActionChunk.require_codec()` to reject rather than coerce embodiment mismatches.

For either app, validate the returned Receipt against the submitted Job and CURRENT local task/epoch
**after transport**, using `validate_delivery()`. The host's native execution and event permissions
still apply. A consumed result is not a physical execution receipt.

Detailed ownership and adapter limits are in `docs/INTEGRATION.md`; all commands above are complete
for the delivered local examples, while real application wiring requires a reviewed optional bridge.

## 9. Experiment sequence after delivery

Use these R-series names to avoid confusing this work with BEHAVIOR phases.

| Stage | Experiment | Required evidence / gate |
|---|---|---|
| R0 | Reproduce software, replay, mock load, wheel and lint | Invariants pass; no external model/robot calls |
| R1 | Retained read-only bridge into each existing application | Exact source/prompt/time/ledger correspondence; no authority changes |
| R2 | One actual endpoint on one GPU/provider | Native output validity, direct-call equivalence, cold/warm timings and charge receipts |
| R3 | Paced 1/2/4/8-session inference load | Bound queues, all offered work counted, no stale delivery, measured response distributions |
| R4 | FIFO/EDF/slack plus placement under contention/jitter | Same inputs/checkpoint/batching/hardware/caps; gains replicated without hiding drops |
| R5 | Fixed-camera StreamBudget quality/cost study | Held-out event recall, false alerts, latency and evidence quality at a predeclared cost target |
| R6 | Compatible policy/simulator closed loop | Same native recipe, consumer fences, actual task/progress outcomes and independent verification |
| R7 | AMD/NVIDIA/site/embedded comparisons | Model/precision differences disclosed; actual hardware telemetry; Jetson claims only with Jetson |
| R8 | One design-partner pilot, then repeatability on a second | Paid-value signal and reuse without rewriting the partner's control stack |

R0/R1 proceed without GPU calls. R2/R3 can use the available local/NVIDIA/AMD resources without solving
BEHAVIOR. R5 is likely the fastest application-level evidence. R6 can use a simpler compatible robot
benchmark while the difficult BEHAVIOR hardware/sensing qualification continues independently.

The detailed predeclared metrics, controls and stop rules are in `docs/EXPERIMENTS.md`. Keep model
quality, application selection policy, scheduling and hardware changes as separate ablations before
claiming a combined gain. Fixed-arrival trace replay cannot measure action-dependent robot success.

## 10. Recommended next work, in concrete order

1. Put this repo alongside the two current projects; do not merge their sources.
2. Reproduce R0, including Ruff in the normal development environment and an independent wheel import.
3. Add one StreamBudget read-only bridge, preserving its source store and call authorization.
4. Profile one currently useful VLM endpoint directly and through Agmina. Run the same payload before
   changing prompts, frame selection or caching. Record complete usable-response time, not only TTFT.
5. Produce a realistic multi-session load from retained camera/robot requests and run R3/R4.
6. Make the first application-quality comparison on fixed-camera video with strong cheap-CV baselines.
7. Add a stateless policy or tensor worker with its native codec; do not migrate SAM/policy state yet.
8. Only then consider backend-specific microbatching/encoder experiments that generic APIs cannot expose.

Do not begin by porting every NVIDIA robotics component to AMD, buying an entire robotics lab,
recreating a video recorder, or training a new policy. The immediate question is whether coordination
of already-useful inference produces measurable benefits at a reusable interface.

## 11. Operational safeguards and acceptance criteria

No silent retries, favorable-start selection, hidden fallback, stale-frame retimestamping, or source
label leakage. No model confidence becomes current geometry or task truth. Unknown space/stopping
and native qualification rules in the physical harness remain unchanged.

Every experiment retains source/config pins, raw input hashes, arrival/capture times, output/charge
receipts, failures, rejects, expiry and source timing omissions. Separate cold compile from warm
inference. No inference HTTP duration becomes GPU time. No met deadline becomes robot competence.
Use actual device profiling for GPU/energy claims and held-out semantic labels for quality claims.

The database contains sensitive payloads even though operational trace events do not. Protect and
retain it deliberately; do not commit actual customer footage or credentials. Freeze or archive a
campaign when its configured capacity is reached. Explicitly reconcile unknown remote work and
charges rather than clearing them to unblock tests.

Success for the MVP is not a large feature list. It is one repeated result of the form:

> On this declared workload, model and hardware, with the same quality/freshness constraints, the
> application completes more useful work or spends less on inference, and a second integration uses
> the same protocol and coordinator rather than another custom stack.

## 12. Primary sources and what they support

The two inspected repository interfaces are linked above by exact commit in
`docs/REFERENCES.md`. Triton's batching and cancellation documentation informed the split between
application request scheduling and backend execution; vLLM's multimodal documentation informed the
explicit boundary around encoder/KV state; Microsoft's offloading overview motivates measuring the
whole inference path rather than assuming cloud placement is faster.

- https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/batcher.html
- https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/request_cancellation.html
- https://docs.vllm.ai/en/latest/features/multimodal_inputs/
- https://www.microsoft.com/en-us/research/blog/offloaded-inference-for-real-world-physical-ai-robotics/

None of those sources establishes a performance result for this code. No upstream model/code/assets
are bundled. The original implementation is MIT; every optional model/backend/data license still
needs independent review before actual service deployment.

## 13. Delivery integrity and local validation details

Run `python tools/verify_bundle.py` before edits. The manifest verifies file integrity, not
a signed publisher identity. This standalone repository has no overlay installer and
must not be applied as a patch to the consolidated robot harness.

`python tools/validate.py --out runs/validation-new --loopback` runs the local suite,
compilation, source/link checks, CLI demos, paced synthetic load and a real localhost
HTTP coordinator/SDK smoke. Ruff is required by default. In the delivery environment
it was unavailable; `--allow-missing-ruff` records that explicitly and is not a lint pass.
The smoke initially exposed a reversed helper argument in its own test script; that
was corrected before the successful run. It did not command hardware or call a model.

Dependency source lineage compares immutable source identities/timestamps, not merely
matching image hashes. An observation can legitimately be current in one job and historical
context in another; that role is job-local. IDs should be unique within a logical session
across tracker resets. A genuinely new capture needs a new ID even when pixels repeat.

Read `VALIDATION.md` for exact test/build scopes and `docs/STATUS.md` for deferred features.

### Recorded local outcome

The delivered new-repository suite passed **136 tests**. Compilation, source/link checks, synthetic
async demo, synthetic scheduler replay, paced mock load and the real localhost sidecar/SDK smoke
passed. A wheel built and its imports/doctor/demo/replay worked outside the checkout using existing
dependencies exposed to the test virtual environment. The release ZIP was extracted and its hashes
and 136 tests checked again. **Ruff was unavailable and was not run.** No GPU, Jetson, actual model
endpoint, real camera, native robot trial, full parent-repo integration or production deployment was
validated. `VALIDATION.md` distinguishes each of these scopes.
