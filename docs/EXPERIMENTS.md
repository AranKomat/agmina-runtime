# Experiment sequence for the inference MVP

These IDs are **R0–R8**, separate from the physical harness's existing Phase 0–14 queue.
Nothing here authorizes model spending, native motion, changing simulator physics, or resetting
billing holds. No Jetson or solved BEHAVIOR task is required to start this sequence.

## R0 — reproduce the delivered foundation

```bash
python -m pip install -e '.[dev,server]'
python tools/validate.py --out runs/r0-001
```

Run the suite, doctor, async demo, deterministic replay, paced mock load, package import smoke and
Ruff. The delivery's own validation record distinguishes what was actually run from unavailable tools.
Check that the exact same input trace is used for FIFO/EDF/slack. Retain the nonpreemption negative
control: an already-running long background call can defeat every queue policy.

**Pass:** invariants hold, no network/model/GPU/actuator access, no stale result becomes consumable,
restarts preserve unknown reservations and block affected pools. This is software verification only.

## R1 — read-only integration with the two applications

First StreamBudget, then the physical harness. Pin the application commit and use retained evidence.
Keep the source application's logic unchanged and replace only one call boundary in a separate branch.

Check source hashes, image order/detail, prompts, output caps, task/episode IDs, cutoff/availability,
monotonic clock mapping and accounting owner. Compare generated request payloads against existing
ones before any paid call. Include old-task results, late responses, clock reset, invalid source
hashes, and pending/in-flight shutdown. Use the app's existing parsers and native execution gates.

**Pass:** source-bound packets make a round trip without changing application semantics or bypassing
an existing guard. No model-quality improvement can be claimed from request equivalence alone.

For the first no-network workflow smoke, install the two parent checkouts into an isolated
environment and run the opt-in tool below. It uses a schema-valid fixture backend, feeds the
delivered response into the actual StreamBudget and Physical Harness validators, and exercises
invalid-source and stale-epoch rejection. It does not run a parent watch scheduler, make a model
call, or authorize an action:

```bash
uv pip install --python .venv/bin/python \
  -e /path/to/streambudget -e /path/to/physical-agent-harness
PYTHONPATH=src .venv/bin/python tools/r1_read_only_smoke.py \
  --streambudget-root /path/to/streambudget \
  --physical-root /path/to/physical-agent-harness \
  --out runs/r1-workflow-001
```

## R2 — one actual endpoint, one workload

Select a model already known to produce useful outputs for that workload. Do not restart a broad
model bake-off. For video, the current GLM endpoint or an operator-owned compatible VLM is a reasonable
candidate based on the user's prior screens, not a newly established quality result here. For policy
inference, use one checkpoint with a known observation/action recipe in its native environment.

```bash
# Operator edits model ID/revision, serving URL, profile and budget first.
agmina probe --config configs/local-chat.template.json \
  --packet examples/vision_packet.json --model vision --count 3 \
  --out runs/r2-transport-001 --allow-network
```

This is a tiny transport test. Next use authorized retained real inputs and record exact device,
server/source versions, weights, precision, sampling, all preprocessing and any internal routing.
Separate cold load/compile from warm timing. Compare output/schema validity with the same backend
called directly, not with an unrelated model. A different request model name is rejected.

Measure first content separately from complete usable output. For policy tensors, record the native
codec/units/period and compare against the reference recipe. Do not infer quality from finite numbers.

**Pass:** identical intended requests, usable native outputs, complete accounting and measured timings.
It is acceptable to find that a hosted API is already sufficient; custom serving must earn its place.

## R3 — paced multi-session load without robot action

Use `agmina load`, first with fixtures and then actual endpoint calls. Input arrival must continue
while inference runs. Start with one stream, then 2/4/8 sessions only within a declared call budget.
Preserve task/observation identity; duplicate pixels at different times remain different evidence.

```bash
agmina load --config configs/local-chat.template.json \
  --plan examples/vision_load.json --out runs/r3-001 --allow-network
```

The included plan is a four-call generated-image fixture, not a camera workload. Replace it with a
frozen licensed/authorized workload plan for the actual study. Prepared-input replay excludes live
capture/decode; report those omissions. Use a held-out duration profile, not the actual future service
time as scheduler input. Measure baseline API/server batching settings and resident memory.

**Pass:** no queue growth beyond bounds, no late/cross-epoch consumption, no duplicate dispatch on
client retry, correct handling of missing usage/429/timeouts, and useful completions under the
specified offered load. Rejections and deadline misses stay in the denominator.

## R4 — controlled scheduling, placement and cancellation study

Hold requests, model, precision, source data, server batching, pool capacity and deadline semantics
fixed. Compare FIFO, EDF and least-slack. Do not weaken the baseline by disabling the serving engine's
ordinary batching. Do not call EDF a reproduction of Kairos.

Test unloaded, near-capacity, overloaded, bursty, and background-blocking cases. Add separately labeled
injected delay/loss via an isolated test proxy or deterministic backend wrapper. Distinguish this from
measuring a real Wi-Fi/cloud link. Include expired-before-dispatch and expired-in-flight cases and
coordinator restart while remote work is outstanding.

Primary systems outcomes: useful completed requests / all offered requests, by workload; complete
response and consumer observation-age distributions; queue blocking; timeout/quarantine/recovery;
resource occupancy and cost. Keep p50/p95/p99 sample counts and censored requests visible.

Isolate ablations: scheduler only; exact historical cache only; latest-only replacement only; placement
only; joint configuration. Changing observation sampling changes the workload and requires a separate
quality experiment. Do not claim speedups by dropping all background work.

**Pass:** replicated improvement at a declared load/quality constraint, not universal superiority.
A no-improvement result identifies which backend or application intervention is actually required.

## R5 — fixed-camera quality and cost with StreamBudget

This is the first plausible product demo without a robot. Use standing operational events and later
questions on held-out footage. Retain sufficient source frame rate for short events, or explicitly
restrict the event class. Do not test only the generated square.

Baselines: fixed-rate VLM; tuned detector/motion plus refresh; existing StreamBudget adaptive behavior.
Then add Agmina underneath with the same semantic policy to isolate serving effects. Finally test
application selection plus runtime scheduling jointly.

Measure event recall, false alerts/camera-hour, alert delivery latency, missed transient events,
question accuracy/evidence support, model calls/tokens, bytes, measured GPU time where available, and
cost/camera-hour. Use independent annotations invisible to the runtime. Set quality/latency constraints
before optimization. At least one held-out camera/view and negative segment must be included.

**Pass:** a cost/capacity gain while meeting predeclared quality and latency requirements. A model call
reduction alone is insufficient. StreamBudget's earlier prefix pilot did not establish this result.

## R6 — robot inference and closed-loop integration

Use a compatible, relatively tractable policy/simulator workload in addition to BEHAVIOR. The
existing BEHAVIOR effort remains the hard integration track; it must not define all serving benchmarks.
FluxVLA/LIBERO or another already-working policy setup can generate requests without porting an
unmatched embodiment. These are integration targets, not dependencies installed by this bundle.

First replay recorded policy inputs with no actions. Then, separately authorized, compare a direct
server path with Agmina under the identical native policy recipe. A stateless RPC must carry whatever
history the model requires; hidden stateful `.select_action()` must remain host-owned.

Keep local control and emergency behavior local. Validate the post-network consumer fence immediately
before native admission. Test epoch change during inference, stale catalog, clock uncertainty, target
movement, network stall and buffer exhaustion. Do not claim a buffer is a safety certificate.

Measure task/progress outcomes, simulated and wall times, robot idle/stall intervals, corrections,
complete prediction age and all action counts. Frozen open-loop trace replay cannot establish these
closed-loop outcomes. Report checkpoint training overlap and hold actuation budgets fixed.

**Pass:** the physical comparison's relevant native gates and outcome evidence—not a timer fixture.

## R7 — heterogeneous compute and embedded baseline

After R2–R4 work on one GPU, add one AMD or NVIDIA endpoint at a time. Freeze model and precision
where comparable; report changed kernels, sampling and output differences. Keep operator-owned
NVIDIA-only perception/robot libraries on NVIDIA rather than claiming they ran on MI300X.

Use the MI300X for experiments unavailable behind a generic API: custom dispatch, controlled
contention, exact batching/candidate experiments, measured tail latency, or model state/encoder work
in a separately qualified backend. This package does not implement those GPU internals.

Only claim edge/offload energy benefits after actual Jetson/device measurements with power mode,
clocks, temperature and complete sensor/control path recorded. Do not use A100/H200/MI300X latency as
an invented Jetson baseline. An embedded device is not needed for earlier coordinator experiments.

## R8 — design-partner validation and product boundary

Pick ONE initial buyer segment, despite retaining two technical reference applications. Obtain an
actual current trace and a permitted read-only integration. Ask whether the partner will pay for
measurable capacity, predictability, reduced interventions or integration—not whether they like the
architecture. Do not require them to replace ROS, their VLA, or their whole autonomy stack.

Deliver one repeatable configuration and a clear ownership boundary. A second partner should reuse
the same coordinator and protocol without a fork. If every engagement needs a new control stack,
stop calling it a reusable runtime and narrow the interface/use case.

## Evidence and stop rules for every run

Use a fresh directory; record code/config/model/hardware/data pins, input hashes, expected event
schedule, approval/call ceiling, cold/warm policy, primary metric, failure handling and cleanup. Retain
failed/late/rejected work and unknown spend. Do not automatically retry failed provider or native
calls. Set caps before running, not after viewing a promising result.

Prompts/source changes are a new condition. Scheduling traces are not semantic benchmarks. Hosted
wall time is not GPU time. Samples from one correlated clip are not independent task trials. Do not
multiply gains from different benchmarks. Freeze a strong baseline before choosing the winning
configuration. Keep claim labels separate: software pass, transport pass, trace simulation, real
endpoint performance, application quality, and physical task benefit.
