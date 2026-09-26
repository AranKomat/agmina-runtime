# Agmina Runtime Experiment Summary

**Date:** 2026-09-25  
**Repository:** `AranKomat/agmina-runtime`  
**Latest commit:** `12f172c` (`Declare experiment recording dependency`)

## Bottom Line

The local Agmina coordinator is validated, and the read-only application bridges have useful
integration evidence. The project has **not yet qualified** a real hosted-model benefit, held-out
model quality, live policy offload, robot task success, heterogeneous hardware, or partner value.

## Phase Status

| Phase | Status | What is established / what remains |
|---|---|---|
| R0 foundation | **Complete** | Local install, replay/load, sidecar, wheel/import, safety checks, Ruff, and `144 passed`. |
| R1 application bridges | **Partial** | Fresh StreamBudget and Physical Harness read-only bridges, the supported two-parent fault matrix, lineage preservation, and clock/generation fences pass. StreamBudget still lacks parent task/episode identity fields. |
| R2 real endpoint | **Partial** | No-network preflight and routing metadata checks pass. Hosted attempts did not produce a usable direct/Agmina pair or charge reconciliation. |
| R3 multi-session load | **Pending** | Needs a real pinned endpoint and paced 1/2/4/8-session campaign. |
| R4 scheduling | **Partial, synthetic only** | FIFO/EDF/least-slack replay completed. Real endpoint placement, cancellation, delay/loss, and capacity tests remain. |
| R5 quality/cost | **Partial, protocol and application screen complete** | The MMVU candidate and both fixed-camera prefixes pass zero-cost Agmina wiring, and the fixed-camera protocol is frozen; no real model quality result exists yet. |
| R6 policy/simulator loop | **Partial** | Five retained native policy boundaries pass exact no-action replay and local direct-vs-Agmina mock comparison. Live policy-server comparison and closed-loop simulator testing remain. |
| R7 heterogeneous compute | **Pending** | Needs a second real endpoint or device class after R2-R4 stabilize. |
| R8 partner validation | **Pending** | Needs authorized design-partner traces and repeatable value measurements. |

## Key Results

### R0 and R1

- The current local suite passes: **144 tests**; Ruff and bundle verification pass.
- R1 runs `r1-workflow-014`, `r1-fault-012`, and `r1-clock-008` preserve source hashes,
  image order, prompts, cutoff times, clock mappings, and accounting. The fault campaign also
  covers queued/in-flight shutdown, cancelled-watch responses, deadline containment, late physical
  responses, pending physical calls, and historical-only old-task delivery.
- Late physical results become errors; old-task results remain historical-only; shutdown ambiguity
  is reported; stale clock/epoch mappings are rejected.
- These are read-only integration and lineage results, not model-quality or robot results.
- The remaining identity limitation is upstream: StreamBudget does not populate task/episode
  identity in its current watch requests. Agmina does not infer it from watch IDs.

### R2 and R4

- `r2-preflight-002` validates the intended request body, fingerprint, reservation, cap, and
  provider routing configuration without network or paid calls.
- The hosted OpenRouter attempts were inconclusive: one response omitted the required model field,
  and a later relaxed attempt did not complete before timeout. Preserve and reconcile those attempts
  before retrying.
- The reconciled requested provider route order is **`together`, `baseten/fp8`, `fireworks`,
  `parasail/fp8`, `coreweave/nvfp4`**, with fallback disabled. This is routing configuration only;
  it does not prove that any route is available or served a request.
- A public metadata query returned HTTP 200 and listed all five route tags with status `0`; GLM 5.3
  Flash advertises text/image/video input and structured outputs. No inference was made, so this is
  still only routing-readiness evidence.
- `r4-synthetic-001` replayed 539 requests. FIFO protected mapping (`26/26` on time) but admitted
  only `2/335` policy requests on time; EDF admitted `108/335` policy requests but mapping fell to
  `7/26`. This is a workload tradeoff, not an endpoint benchmark.

### R5

- Candidate `runs/r5-heldout-candidate-001` contains six MMVU validation cases and 96 sampled
  frames, excludes all 40 cases from the earlier StreamBudget manifest, and keeps labels separate.
- `runs/r5-heldout-audit-003` verifies video/frame hashes and label IDs.
- `runs/r5-screen-mock-002` passes all six cases through the actual StreamBudget request/image
  conversion and Agmina ledger with zero paid calls and `labels_read: false`.
- `runs/r5-streamarena-mock-003` passes all eight tasks from the two pinned 600-second, 2 FPS
  fixed-camera prefixes through the same Agmina boundary. Eight causal frame windows were hashed
  and consumed; private labels were not opened, with zero paid calls and zero native actions.
- `runs/r5-policy-mock-003/JNpUsYTVM6k-fixed` replays the actual parent fixed policy over 1,200
  frames and journals 602 visual calls through Agmina; all 602 are consumed with zero bridge
  errors, paid calls, native actions, or label reads. This is policy/ledger integration evidence,
  not model quality or endpoint performance.
- `runs/r5-policy-mock-004/JNpUsYTVM6k-motion` completes the matched motion-policy replay with
  1,191/1,191 visual calls consumed and zero bridge errors. The corrected adaptive replay at
  `runs/r5-policy-mock-005/JNpUsYTVM6k-adaptive` also consumed 1,191/1,191 calls with zero bridge
  errors. It took 2,269.8 seconds on the CPU-only host and remains mock integration evidence,
  not a capacity or quality result; the earlier 1,000-cap run is retained as negative evidence.
- The real-campaign runner now records input provenance (manifest, source, task-spec, video, and
  selected-frame hashes). `tools/r5_evaluate_candidate.py` scores outputs only after inference,
  with labels outside runtime; its mock negative control correctly remains unqualified.
- `docs/R5_STREAMARENA_PROTOCOL.md` freezes the ask/watch taxonomy, evaluator-only label custody,
  negative-segment handling, causal cutoff rule, matched policy comparisons, and metrics for the
  next real campaign.
- This proves preparation and accounting only. The candidate is explicitly **not qualified** until
  a fixed protocol, independent label custody, real Agmina-backed inference, and independent scoring
  are completed.

### R6

- Five retained native policy boundaries were extracted and hash-checked.
- Native packet/action validation passes, including exact action-shape and finite-value checks.
- Direct and local mock-Agmina outputs are exactly equal for the five-boundary cohort.
- All replayed consumptions have `action_authorized=false`; no robot action occurred.
- No local NVIDIA GPU or live policy server is currently available on the Mac, so this is not live
  policy performance evidence.

## Recommended Next Order

1. Preserve independent label custody and use the frozen fixed-camera protocol without changing it
   after model outcomes are visible.
2. Re-run the local verification commands below and preserve a fresh run directory.
3. When an operator-approved resource is available, choose one real gate:
   - R5: a newly capped, pinned real endpoint on the six-case candidate, followed by independent
     scoring; or
   - R6: a live GPU policy server, comparing the identical five native packets directly and via
     Agmina with action admission disabled.
4. Only after the selected transport/quality gate passes, run separately authorized closed-loop
   simulator or robot experiments. R3, real R4, R7, and R8 remain downstream.

No additional architecture or policy-model claims should be made from the current evidence alone.

## Next Gates

1. Run a fresh no-network preflight against the reconciled R2 provider template.
2. Do not make further paid endpoint calls without a new explicit campaign cap and charge-reconciliation plan.
3. When a qualified GPU policy server is available, run the identical five-boundary cohort directly
   and through Agmina with action admission disabled.
4. If R6 transport passes, run a separately authorized closed-loop simulator trial.
5. For R5, run the six-case candidate through one pinned real model via Agmina and score it with
   independent labels.

## Non-Claims

Synthetic, mock, retained-replay, and open-loop results must not be described as hosted-model
quality, endpoint throughput, GPU performance, robot competence, benchmark success, or safety
certification. The current worktree is intentionally dirty; do not reset unrelated changes.

## Verification

```bash
./.venv/bin/python tools/verify_bundle.py
./.venv/bin/ruff check .
./.venv/bin/pytest -q
```
