# Agmina Runtime Experiment Progress

**Date:** 2026-09-26  
**Repository:** `AranKomat/agmina-runtime`  
**Protocol:** R0-R8 in [`EXPERIMENTS.md`](EXPERIMENTS.md)

## Bottom Line

The local Agmina coordinator and its read-only integration boundaries are in good shape. We have
not yet qualified a real hosted-model benefit, held-out model quality, live policy offload, robot
task success, heterogeneous hardware, or partner value. Most results below are synthetic, mock, or
retained-replay evidence and must not be presented as benchmark or robot performance.

## Phase Status

| Phase | Status | Evidence / remaining gate |
|---|---|---|
| R0 foundation | **Complete** | Local validation, replay/load, sidecar, wheel/import, safety checks, Ruff, and the recorded `144 passed` suite. |
| R1 application bridges | **Partial** | StreamBudget and Physical Harness read-only bridges, lineage, fault handling, shutdown behavior, and clock/generation fences pass. StreamBudget still lacks explicit parent task/episode identity. |
| R2 real endpoint | **Partial** | One corrected GLM packet completed directly and through Agmina with identical request hashes and usable outputs; charge/provider-revision reconciliation remains. |
| R3 paced load | **Pending** | Needs a pinned real endpoint and a 1/2/4/8-session campaign. |
| R4 scheduling | **Partial, synthetic only** | FIFO/EDF/least-slack replay and contention tests pass. Real endpoint placement, cancellation, delay, loss, and capacity remain. |
| R5 quality/cost | **Partial** | Six-case real GLM/Agmina development screen completed with 6/6 independent answers and citations; labels and charges are not qualified/fully reconciled. |
| R6 policy/simulator loop | **Partial** | Five retained native policy boundaries pass no-action replay and local mock direct-vs-Agmina comparison. Live policy-server and closed-loop tests remain. |
| R7 heterogeneous compute | **Pending** | Requires a stable baseline and a second endpoint/device class. |
| R8 partner validation | **Pending** | Requires an authorized partner trace and repeatable value measurement. |

## Results

### R0/R1: local and bridge validation

- Recorded local validation: `144 passed`, Ruff, compilation, bundle verification, demo/replay,
  synthetic load, sidecar smoke, wheel build, and outside-source-tree import checks.
- `r1-workflow-014`, `r1-fault-012`, `r1-retained-004`, and `r1-clock-008` preserve source hashes,
  image order, prompts, causal cutoffs, clock mappings, accounting, late-result handling,
  historical-only old-task delivery, shutdown ambiguity, and stale-epoch rejection.
- The remaining R1 limitation is upstream: current StreamBudget watch requests do not populate
  task/episode identity. Agmina does not infer identity from watch IDs.
- These checks used zero paid calls, zero GPU inference, and zero native actions.

### R2/R4: endpoint and scheduler preparation

- `r2-preflight-002` validates the intended request body, fingerprint, reservation, cap, and
  configured GLM route order:
  `together -> baseten/fp8 -> fireworks -> parasail/fp8 -> coreweave/nvfp4`.
- Hosted OpenRouter attempts were not a pass: one response omitted the required model field, and
  a later relaxed attempt timed out before a complete report. Reconcile charge state before retrying.
- The corrected comparison `runs/r2-glm-direct-agmina-001` completed one direct and one Agmina
  call with the same request-body hash. Direct latency was 2.40 s and Agmina latency was 1.25 s;
  separate output hashes are expected because these were independent calls. Provider cost fields
  were unavailable, so this is transport evidence, not a reconciled cost or quality result.
- Synthetic replay `r4-synthetic-001` covered 539 requests. FIFO completed `26/26` mapping
  requests on time but only `2/335` policy requests; EDF completed `108/335` policy requests but
  only `7/26` mapping requests. This is a workload tradeoff, not a universal winner.

### R5: StreamBudget quality/cost preparation

- `runs/r5-heldout-candidate-001` contains six disjoint MMVU validation cases and 96 sampled
  frames, excluding the earlier 40-case set. Runtime has no answers; evaluator labels are separate.
- Hash/provenance audits and the independent evaluator are implemented. The mock negative control
  correctly reports `scored_incomplete` / `not_qualified` rather than inventing quality.
- Fixed-camera and policy replays route through the actual StreamBudget/Agmina ledger with zero
  paid calls, zero native actions, and labels unread. The corrected adaptive mock replay consumed
  `1,191/1,191` visual calls with zero bridge errors.
- Corrected full replay `runs/r5-streamarena-agmina-mock-009` covered both videos, all 2,400 frames,
  and all eight tasks. It recorded 2,138 unique Agmina jobs, all consumed, zero parent failures,
  zero bridge failures, zero cost, zero unknown holds, zero native actions, and labels unread.
- Independent evaluation `runs/r5-streamarena-eval-mock-009.json` completed all eight tasks (seven
  eligible), scored zero exact/strict answers from the synthetic fixture, and correctly retained
  `r5_qualification: not_qualified`.
- The fresh six-case real GLM screen is recorded in `runs/r5-real-glm-merged-001`. All six jobs
  were consumed, schema-valid, citation-valid, and correct under the independent evaluator. The
  corrected endpoint contract uses `max_tokens=4096` and `reasoning.effort=low`; observed completion
  latency was 3.08--4.16 seconds. This is development evidence only because the labels were not
  held out and six external attempts retain unknown charge holds pending reconciliation.

### Previous R5 Blocker And Resolution

The earlier full replay was not parent-clean. StreamBudget reports contained failed observation
jobs even though the Agmina ledger reported all submitted Agmina jobs successful. Diagnosis found
three runner issues: per-call clock-map rebasing changed reused evidence identity, job IDs reset
between videos in a shared ledger, and the mock campaign cap/window was too small for the full
workload. These are fixed in the current runner; `mock-009` is the parent-clean result.

- `JNpUsYTVM6k`: 1,191 jobs, 288 completed, **903 `ValueError` failures**.
- `9CQ6qmoOhlQ`: 947 jobs, 240 completed, **706 `ValueError` failures**.

The runner now retains bounded error type/message/phase fields and makes the top-level outcome
`transport_incomplete` whenever parent `job_failed` is nonzero. Earlier capped/failed runs remain
negative evidence and are not used for the clean result.

### R6: policy transport preparation

- Five retained native policy boundaries were extracted and hash-checked at sequences `0, 32, 64,
  96, 128`.
- Exact packet/action validation passes, and ordered direct-vs-Agmina comparison produced equal
  outputs against a local mock RPC. All consumptions have `action_authorized=false`; no robot
  action occurred.
- This is orchestration/validation evidence only. No live policy server, GPU timing, policy
  quality, or closed-loop task result exists yet.

## Next Actions

1. Reconcile the six real GLM attempts, then run the fixed-camera StreamArena workload and matched
   fixed-rate, motion-refresh, and adaptive baselines under the same declared model contract.
2. When a compatible GPU policy server is available, compare the same five native packets directly
   and through Agmina with action admission disabled.
3. Only after a transport/quality gate passes, run closed-loop simulator tests. R3, real R4, R7,
   and R8 remain downstream.

## Verification Reference

Last recorded local verification commands:

```bash
./.venv/bin/python tools/verify_bundle.py
./.venv/bin/ruff check .
./.venv/bin/pytest -q
```

Raw evidence is under `runs/`. The worktree is intentionally dirty with experiment integration
changes; do not reset or revert unrelated edits.
