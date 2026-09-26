# Agmina Experiment Handoff

**Repository:** `agmina-runtime`  
**Date:** 2026-09-25  
**Purpose:** concise handoff for continuing the R0-R8 experiment sequence.

## Bottom Line

The local coordinator foundation is validated. The application bridges and failure fences have
meaningful retained-fixture evidence. No phase has yet established a real hosted endpoint advantage,
StreamBudget held-out quality result, live policy offload result, robot task success, heterogeneous
hardware result, or design-partner value.

The immediate high-value gate is R6: compare an ordered native policy packet cohort directly with
the same cohort through Agmina, with no actuation. A campaign runner is prepared, but no native
policy server is currently running on the Mac (`127.0.0.1:8011` was unavailable at handoff time).

## Phase Status

| Phase | Status | Evidence and remaining gate |
|---|---|---|
| R0 | Complete | Local installation, replay, load, wheel/import, sidecar, Ruff, and safety checks pass. This is coordinator software evidence only. |
| R1 | Partial | StreamBudget and Physical Harness read-only bridges plus the supported two-parent fault matrix, retained lineage, and clock-reset fences pass. Missing parent task/episode identity fields remain. |
| R2 | Partial | No-network provider preflight passes. The first hosted OpenRouter attempts had a missing response-model field and a later incomplete/timeout result; no usable direct/Agmina pair or charge reconciliation exists. |
| R3 | Pending | Requires paced 1/2/4/8-session load against a real pinned endpoint. |
| R4 | Partial, synthetic only | FIFO/EDF/least-slack replay and profile-error contention pass on a fixed synthetic trace. Real endpoint placement/cancellation and jitter remain. |
| R5 | Partial, development only | Retained-frame and visual-QA provenance audits pass; existing GLM/Gemini material is post-hoc, not held out. No quality/cost claim is qualified. |
| R6 | Partial | Five-query native no-action replay passes exactly. Native reset/infer adapter and direct-vs-Agmina runner are locally tested, but no live server comparison or closed-loop task result exists. |
| R7 | Pending | Requires a second real endpoint/device class after R2-R4 are stable. |
| R8 | Pending | Requires authorized design-partner traces and a repeatable value measurement. |

## Important Results

- **R0:** the current local suite passes (`144 passed` after the new native-policy contract tests),
  Ruff passes, and bundle-manifest verification passes. These checks use no paid model calls, GPU
  inference, simulator action, or actuator.
- **R1:** `runs/r1-workflow-014`, `runs/r1-fault-012`, `runs/r1-retained-004`, and
  `runs/r1-clock-008` preserve source hashes, prompt/image order, time mappings, parent behavior,
  late-result handling, shutdown ambiguity, old-task historical-only delivery, and generation fences.
- **R2:** `runs/r2-preflight-002` validates the exact request shape, reservation, fingerprint, and
  provider preference. The configured OpenRouter route order is `together -> baseten/fp8 -> fireworks ->
  parasail/fp8 -> coreweave/nvfp4`, with provider fallbacks disabled. This is only routing configuration, not evidence of
  provider availability or quality. Use a fresh campaign cap before any paid retry.
- **R4:** `runs/r4-synthetic-001` offered 539 synthetic requests. FIFO protected mapping (26/26 in
  time) but admitted only 2/335 policy requests in time; EDF admitted 108/335 policy requests in
  time while mapping fell to 7/26. These are workload tradeoffs, not endpoint measurements.
- **R5:** `runs/r5-dev-audit-002` records 12 completed development trials, 32 attempts, and
  `$0.016686395` reported spend. The data is not an untouched held-out benchmark.
- **R6:** `runs/r6-recorded-001` round-trips five retained native policy queries with exact action
  payloads. The inputs are `540x640x3 UINT8`, `7`-element joints, `1`-element gripper, and
  `32x8 FP32` actions. All five consumptions record `action_authorized=false`; replay does not run
  inference or move a robot.

## Current R6 Work

Recent files:

- [`src/agmina_runtime/adapters/native_policy.py`](../src/agmina_runtime/adapters/native_policy.py)
  preserves host-owned reset and validates the native R1Pro packet/action contract. RGB inputs are
  normalized to RPent-compatible bounded `uint8` ndarray envelopes; no resizing, padding, retiming,
  or action authorization occurs.
- [`tools/r6_native_policy_compare.py`](../tools/r6_native_policy_compare.py) resets the policy
  separately for direct and routed paths, sends the same ordered packet cohort, records per-call
  complete-output timing and the Agmina ledger trace, and retains structured failure reports.
- [`tests/test_native_policy.py`](../tests/test_native_policy.py) covers packet/result validation,
  loopback RPC envelopes, reset/infer behavior, action dimensions, stale stamps, and loopback URL
  restrictions.

The retained Behavior-Skill archive contains the first trace's native camera assets inside
`full-results.tar.gz`; the trace has the exact session/epoch/sequence, instruction, three RGB asset
references, and 61-element proprio vector needed to prepare a comparison cohort. Two boundaries
have already been extracted and hash-checked. Do not treat these retained packets as live task
observations or task results.

## Next Actions

1. On an operator-started GPU policy server, run the prepared ordered packet cohort with pinned
   checkpoint, preserving image bytes and native stamps.
2. Record preprocessing, output schema, sampling, model revision, hardware, and scheduler-estimate
   metadata, then compare the exact direct/routed outputs and complete usable-output latency.
3. Keep action admission disabled for the transport comparison; only after it passes, run a
   separately authorized closed-loop trial with local safety and recovery authority.
4. For R2/R3/R4, obtain a fresh paid campaign cap and charge-reconciliation plan before using a
   hosted provider. Do not automatically retry the unresolved OpenRouter attempts.
5. For R5, use the already prepared disjoint candidate and frozen protocol for a newly authorized
   real-model run, then score it with the label-separated evaluator.

## Non-Claims

This repository currently does **not** prove GPT/VLM quality, policy competence, BEHAVIOR task success,
GPU speedup, endpoint cost advantage, safety certification, or general hardware portability. Synthetic
replay, mock RPC, retained action round-trips, and met deadlines must not be reported as those results.

## Verification Command

From the repository root:

```bash
./.venv/bin/python tools/verify_bundle.py
./.venv/bin/ruff check .
./.venv/bin/pytest -q
```
