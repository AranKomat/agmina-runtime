# Agmina Runtime: Experiment Progress Handoff

**Date:** 2026-09-25  
**Repository:** `AranKomat/agmina-runtime`  
**Latest committed revision:** `12f172c` (`Declare experiment recording dependency`)

## Executive Summary

The local Agmina coordinator and its safety/accounting invariants are in good shape. Fresh
read-only integration with StreamBudget and Physical Harness has passed against the current
parent revisions, in addition to the retained-fixture evidence. A
fresh disjoint six-case R5 candidate split is now prepared, and the two pinned fixed-camera
prefixes have passed a zero-cost Agmina application screen. No real model was run on either
candidate in this repository. The program has **not** yet qualified a real hosted-model benefit,
held-out StreamBudget quality, live policy offload, robot task success, heterogeneous hardware,
or design-partner value.

The offline R5 protocol, provenance capture, policy screens, and label-separated evaluator are now
prepared. The next meaningful gate is resource-dependent: either a capped real R5 endpoint run or
the same ordered native policy packet cohort directly against a real policy server and through
Agmina, with action admission disabled.

## Phase Status

| Phase | Status | What is established | What remains |
|---|---|---|---|
| R0 foundation | **Complete** | Local install, replay, demo, load, wheel/import, sidecar, Ruff, safety checks; current suite `144 passed`. | None for the local foundation. |
| R1 application bridges | **Partial** | StreamBudget and Physical Harness read-only bridges, retained lineage, the supported two-parent fault matrix, old-task handling, shutdown behavior, and clock/generation fences. | Missing parent task/episode identity fields in StreamBudget prevent parent-native old-task/source-identity coverage. |
| R2 real endpoint | **Partial** | No-network request/provider preflight and local loopback comparison. | Successful direct/Agmina pair, pinned serving metadata, timings, and charge reconciliation. |
| R3 multi-session load | **Pending** | No real endpoint load result yet. | Authorized paced 1/2/4/8-session run. |
| R4 scheduling | **Partial, synthetic only** | FIFO/EDF/least-slack replay and profile-error contention on a fixed synthetic trace. | Real endpoint placement, cancellation, delay, loss, and capacity study. |
| R5 quality/cost | **Partial, protocol and application screen complete** | Retained/provenance audits, a fresh disjoint six-case candidate split, a frozen fixed-camera protocol, and both prefixes through zero-cost Agmina wiring. | Real Agmina-backed model run, independent evaluation, and qualified quality/cost result. |
| R6 policy/simulator loop | **Partial** | Five-query retained no-action replay; native RPC validation; ordered five-boundary direct-vs-Agmina runner and local mock pass. | Live policy-server comparison, then separately authorized closed-loop testing. |
| R7 heterogeneous compute | **Pending** | No comparable second device/endpoint result. | Stable R2-R4 baseline plus disclosed model/precision/hardware comparison. |
| R8 partner validation | **Pending** | No partner pilot. | Authorized partner trace and repeatable value measurement. |

## Results With Evidence

### R0: Local foundation

- The local validation suite passes: `144 passed`.
- Ruff, compilation, repository/link checks, doctor, demo, replay, synthetic paced load, sidecar
  smoke, wheel build, and outside-source-tree import checks pass.
- These checks used zero paid model calls, GPU inference, simulator actions, or actuator actions.

### R1: Read-only application integration

The latest runs `r1-workflow-014`, `r1-fault-012`, and `r1-clock-008`, together with retained
lineage run `r1-retained-004`, show that Agmina can preserve source hashes, image order, prompts,
cutoff times, clock mappings, parent accounting, and generation fences. They also cover late
responses, old-task results as historical-only data, in-flight and queued shutdown ambiguity, and
stale clock/epoch rejection. The workflow report records StreamBudget's dirty Git revision and the
Physical Harness scaffold revision `852e5802f0808b459be7aae97dd4055486c57638`; StreamBudget is
pinned at `076783012377d074b82efd7aaf296a8175b3a7f4` and dirty.

The retained lineage comparison produced five admitted requests and two parent-visible alerts on
both the native mock and Agmina-routed paths, with equivalent routed payloads. This is integration
and lineage evidence, not model-quality evidence.

The remaining R1 identity gap is upstream: StreamBudget exposes a generic `Request.context`, but
its current watch runtime does not populate task/episode identity. Agmina therefore does not infer
identity from watch IDs or invent a generation value.

### R2: Hosted endpoint attempt

`r2-preflight-002` validates the intended request body, fingerprint, reservation, cap, and provider
preference order:

`together -> baseten/fp8 -> fireworks -> parasail/fp8 -> coreweave/nvfp4`

Fallbacks are disabled. This records routing configuration only; it does not prove that a listed
provider served the request.

A public OpenRouter metadata query returned HTTP 200 for `z-ai/glm-5.3-flash` and listed all five
configured route tags with status `0`; the model advertises text/image/video input and structured
outputs. No inference or paid call was made, so this remains routing-readiness evidence only.

The hosted OpenRouter attempts were not a pass. One response omitted the required response-model
field, and a later relaxed attempt did not produce a complete report before timeout. No usable
direct/Agmina pair or charge reconciliation exists. Do not blindly retry that route; use a fresh
operator-pinned campaign and cap.

### R4: Synthetic scheduler comparison

`r4-synthetic-001` replayed 539 requests across policy, semantic, and mapping workloads:

- FIFO protected mapping (`26/26` completed in time) but admitted only `2/335` policy requests in
  time.
- EDF admitted `108/335` policy requests in time, while mapping fell to `7/26`.
- Least-slack was intermediate but had the highest queue and completion-age p95 values.

This demonstrates a workload tradeoff in the coordinator. It is not an endpoint throughput,
semantic-quality, or universal scheduler-winner result.

### R5: Development quality/cost material

The retained-frame audit verifies six frame hashes and two video identities. The visual-QA report
verifies six packet hashes and 1,107 packet frames, but explicitly labels the data as post-hoc
development qualification rather than a held-out benchmark.

The development audit records 12 completed GLM/Gemini trials from 32 attempts and `$0.016686395`
reported spend. The results are useful for debugging, but there are no independent held-out labels
or qualified answer-quality, recall, false-alert, latency, or cost claims.

The parent StreamBudget checkout also contains a 40-case `benchmark-subset-v1`; its existing screen
used 123 model attempts, reported `$1.1422144168`, and ended with `all_passed=false`. All 40 cases
were evaluated three times across Gemini, Qwen, and GLM. Labels and outputs are already present, and
the screen did not run through Agmina, so it cannot serve as the R5 held-out qualification set.

A fresh disjoint candidate was prepared at `runs/r5-heldout-candidate-001`. It selects six MMVU
validation cases (`MMVU-validation_538`, `_106`, `_680`, `_390`, `_21`, and `_340`) while excluding
the 40 cases in the prior StreamBudget manifest (excluded-manifest SHA-256
`0ad3c393...ea9b2b5`). Each case has a downloaded source video and 16 uniformly sampled JPEG
frames. The runtime `manifest.json` contains no answers; evaluator labels are stored separately
under `evaluator/labels-private.json` with SHA-256
`899c9cd7...9e235fee`. Acquisition completed with `model_calls: 0` and the manifest outcome
`prepared_not_qualified`. The repository audit `runs/r5-heldout-audit-003` verified all six video
hashes, all 96 frame hashes, and the six-case label-ID match. This is data-preparation evidence,
not a held-out quality result; independent label custody, a fixed protocol, real Agmina inference,
and independent evaluation remain required. The zero-cost application wiring screen
`runs/r5-screen-mock-002` then consumed all six cases through the actual StreamBudget
`Request`/`ImageInput` path and Agmina ledger, with six synthetic attempts, zero paid calls, zero
native actions, and `labels_read: false`. This is transport/accounting evidence only, not model
quality evidence.

The fixed-camera screen `runs/r5-streamarena-mock-003` consumed all eight tasks from the two
pinned 600-second, 2 FPS prefixes (`JNpUsYTVM6k` and `9CQ6qmoOhlQ`) through the same Agmina
request/ledger boundary. It used eight source frames at or before each task cutoff, verified the
selected frame hashes, did not open `labels-private.jsonl`, and reached `consumed` for all eight
jobs with zero paid calls and zero native actions. This closes the zero-cost fixed-camera wiring
screen only; the mock output is not model-quality or benchmark evidence.

The policy-level screen `runs/r5-policy-mock-003/JNpUsYTVM6k-fixed` replayed the actual parent
fixed policy over all 1,200 frames and four tasks. It scheduled 602 visual calls; all 602 were
accepted, consumed, and journaled by Agmina with zero bridge errors, paid calls, native actions,
or label reads. Planner calls stayed on the parent deterministic fixture, so this validates the
visual serving boundary and policy selection integration only. The bridge now assigns stable
sequences to reused evidence IDs; the failed predecessor `runs/r5-policy-mock-001` is retained as
negative evidence for the prior cap and identity bugs.

The matched motion screen `runs/r5-policy-mock-004/JNpUsYTVM6k-motion` completed 1,191 visual
calls over the same 1,200-frame prefix with zero bridge errors. The corrected adaptive replay at
`runs/r5-policy-mock-005/JNpUsYTVM6k-adaptive` also consumed 1,191/1,191 calls with zero bridge
errors. It took 2,269.8 seconds on the CPU-only host and remains mock integration evidence, not a
capacity or quality result. The earlier 1,000-attempt run is retained as negative evidence for the
former cap and is not a valid quality or call-volume comparison.

The fixed-camera acceptance protocol is now frozen in `docs/R5_STREAMARENA_PROTOCOL.md`. It
defines the ask/watch taxonomy, evaluator-only label and negative-segment custody, causal cutoff
rule, matched policy comparisons, latency/quality/cost metrics, and charge-admission requirements.

### R6: Native policy transport preparation

The retained RoboLab recording contains five native policy queries. The no-action replay
`r6-recorded-001` verified the retained inputs and exact `32x8` FP32 action payloads. Every replay
records `action_authorized=false`; no inference or robot actuation occurred.

The current uncommitted work adds:

- `src/agmina_runtime/adapters/native_policy.py`: loopback-only native reset/infer adapter with
  R1Pro stamp, camera, proprioception, and finite 23-channel action validation.
- `tools/r6_extract_native_packet.py`: hash-checking extraction of retained native boundaries.
- `tools/r6_native_policy_compare.py`: ordered same-cohort direct-vs-Agmina runner with separate
  resets, timing, ledger traces, and structured failure reports.
- `tests/test_native_policy.py`: contract tests for packet/result validation and stale stamps.

Five retained boundaries (native sequences `0, 32, 64, 96, 128`) passed this runner against a local
mock RPC with exact direct/routed output equality. This proves orchestration and validation only.
It is not a live server, GPU, latency, policy-quality, or task-success result.

## Current Constraints

- No native policy server is currently running on the Mac (`127.0.0.1:8011` was unavailable at
  the last handoff).
- There is no local NVIDIA GPU on the Mac.
- The StreamBudget and Physical Harness parent checkouts may be dirty; their state must be recorded,
  not overwritten or reset.
- The `runs/` directories cited here are local evidence and are excluded from the delivered bundle;
  copy the relevant run directories separately if the external agent needs to inspect raw reports.
- Synthetic, mock, retained-replay, and open-loop evidence must not be reported as live model,
  hardware, robot, or benchmark competence.

## Next Actions

1. Preserve independent custody of `runs/r5-heldout-candidate-001/evaluator` and use the frozen
   `docs/R5_STREAMARENA_PROTOCOL.md` without changing it after model outcomes are visible.
2. Obtain fresh endpoint/campaign authorization and charge reconciliation before running the
   six-case R5 candidate through one pinned real model with `tools/r5_agmina_screen.py`; then use
   `tools/r5_evaluate_candidate.py` after runtime completion.
3. Independently score the resulting R5 outputs; do not expose labels to runtime and do not call
   the split qualified until the protocol and label custody requirements pass.
4. In parallel when a compatible GPU policy server is available, run the ordered five-boundary
   cohort directly and through Agmina using identical checkpoint, preprocessing, output schema,
   sampling, server revision, hardware, precision, and scheduler metadata. Keep action admission
   disabled.
5. If that transport comparison passes, run a separately authorized closed-loop trial while
   Physical Harness retains safety, verification, recovery, and action authority.
6. Run R3 and real R4 only after a real endpoint is pinned; reconcile every offered, rejected,
   expired, cancelled, late, failed, and unknown-charge attempt before interpreting results.

## Verification

From the repository root:

```bash
./.venv/bin/python tools/verify_bundle.py
./.venv/bin/ruff check .
./.venv/bin/pytest -q
```

The detailed checklist and run-by-run notes remain in
[`EXPERIMENT_STATUS.md`](EXPERIMENT_STATUS.md).
