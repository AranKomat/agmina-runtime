# Agmina Runtime Experiment Handoff

**Date:** 2026-09-25  
**Repository:** `AranKomat/agmina-runtime`  
**Latest committed revision:** `12f172c`

## Bottom Line

The local Agmina coordinator and its read-only integration boundaries are in good shape. The
project has **not yet qualified** a real hosted-model advantage, held-out model quality, live
policy offload, robot task success, heterogeneous hardware, or design-partner value.

## Phase Status

| Phase | Status | Evidence / remaining work |
|---|---|---|
| R0 foundation | **Complete** | Local install, replay/load, sidecar, wheel/import, safety checks, Ruff, and the local test suite pass. No paid calls, GPU inference, simulator actions, or actuator actions were used. |
| R1 application bridges | **Partial** | StreamBudget and Physical Harness read-only bridges, retained lineage, fault handling, shutdown behavior, and clock/generation fences pass. StreamBudget still lacks parent task/episode identity fields. |
| R2 real endpoint | **Partial** | Request/provider preflight passes. Hosted OpenRouter attempts were inconclusive: one response omitted a required field and another did not complete. No usable direct/Agmina pair or charge reconciliation exists. |
| R3 paced load | **Pending** | Needs a pinned real endpoint and a 1/2/4/8-session campaign. |
| R4 scheduling | **Partial, synthetic only** | FIFO/EDF/least-slack replay and contention tests pass. Real endpoint placement, cancellation, delay, loss, and capacity tests remain. |
| R5 quality/cost | **Partial, full-workload transport screen complete** | Provenance audits, a disjoint six-case candidate, frozen fixed-camera protocol, and a full-workload mock runner with image and text-only Agmina jobs pass. No real-model quality result exists. |
| R6 policy/simulator loop | **Partial** | Five retained native policy boundaries pass no-action replay and local direct-vs-Agmina mock comparison. Live policy-server comparison and closed-loop testing remain. |
| R7 heterogeneous compute | **Pending** | Requires a stable baseline and a second real endpoint/device class. |
| R8 partner validation | **Pending** | Requires an authorized partner trace and repeatable value measurement. |

## Key Results

- **R0:** Local validation is reproducible. The suite has passed with 144 tests, alongside Ruff,
  compilation, demo/replay, synthetic load, sidecar, wheel, and outside-source-tree import checks.
- **R1:** Runs `r1-workflow-014`, `r1-fault-012`, `r1-retained-004`, and `r1-clock-008` preserve
  source hashes, image order, prompts, causal cutoffs, clock mappings, accounting, late-result
  handling, old-task historical-only delivery, shutdown ambiguity, and stale-epoch rejection.
- **R4:** On synthetic run `r4-synthetic-001`, FIFO protected mapping (`26/26` on time) but
  admitted only `2/335` policy requests on time; EDF admitted `108/335` policy requests while
  mapping fell to `7/26`. This is a workload tradeoff, not a universal scheduler result.
- **R5:** The six-case candidate contains 96 sampled frames, excludes the earlier 40-case set,
  and keeps labels outside runtime. Fixed-camera and policy screens consumed their requests
  through the actual StreamBudget/Agmina ledger with zero paid calls and zero label reads. The
  corrected adaptive mock replay consumed `1,191/1,191` calls with zero bridge errors. These are
  transport/provenance results, not model-quality or capacity results.
- **R5 full workload:** `runs/r5-streamarena-agmina-mock-003` consumed 127 Agmina jobs in a
  bounded replay: 126 image-bound perception calls and one zero-observation planner query. Cost,
  label reads, and native actions were all zero. This validates routing/accounting only.
- **R5 evaluation:** `tools/r5_streamarena_label_audit.py` creates a hash-only private-label audit,
  and `tools/r5_evaluate_streamarena.py` scores only after transport completion. The bounded
  negative control returned `scored_incomplete`, with 4 visible tasks, 0 exact answers, and no
  qualification claim.
- **R6:** Five retained native policy packets round-trip with exact action validation and equal
  direct/mock-Agmina outputs. All consumptions have `action_authorized=false`; no robot action
  occurred. There is no live policy server on the Mac and no local NVIDIA GPU.

## Immediate Next Steps

1. Run the same full workload through one pinned real model using the completed runner. Image jobs
   use the normal evidence-bound request; planner/memory calls use explicit text-only query jobs.
2. Obtain a fresh campaign cap before any real endpoint
   call. Keep the private R5 labels unread until independent evaluation.
3. When a compatible GPU policy server is available, compare the same five native packets directly
   and through Agmina with action admission disabled.
4. Only after one transport/quality gate passes, run separately authorized closed-loop simulator
   testing. R3, real R4, R7, and R8 are downstream.

## Important Caveats

- The worktree is intentionally dirty with current experiment-integration changes; do not reset
  or revert unrelated edits.
- Synthetic, mock, retained-replay, and open-loop results must not be reported as hosted-model
  quality, endpoint throughput, GPU performance, robot competence, benchmark success, or safety
  certification.
- Raw evidence is under `runs/`; the detailed checklist is `docs/EXPERIMENT_STATUS.md`.

## Verification

```bash
./.venv/bin/python tools/verify_bundle.py
./.venv/bin/ruff check .
./.venv/bin/pytest -q
```
