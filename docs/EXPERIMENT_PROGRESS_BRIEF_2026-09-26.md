# Agmina Runtime Experiment Brief

**Date:** 2026-09-26  
**Repository:** `AranKomat/agmina-runtime`  
**Scope:** concise handoff for the next research agent

## Bottom Line

The local coordinator and read-only integration boundaries are validated. The real GLM path is
usable for development, but R5 is not qualified: external charges are not reconciled and labels
are kept outside runtime. The full two-video replay completed with a transport failure on the
second video, so it is not a quality result.

## R0-R8 Status

| Stage | Status | Evidence / remaining work |
|---|---|---|
| R0 foundation | Complete | 148 tests, Ruff, compile/bundle/demo/replay and safety checks pass. |
| R1 application bridges | Partial | StreamBudget and Physical Harness read-only bridges, lineage, fault and clock fences pass; parent task/episode identity is still absent upstream. |
| R2 real endpoint | Partial | Direct vs Agmina GLM packet had identical request hash and usable outputs; provider/cost reconciliation remains open. |
| R3 paced load | Partial | Real 1/2/4/8-session cohort completed; 1/2 clean, 4/8 freshness-limited. |
| R4 scheduling | Partial, synthetic | Scheduler replay passes; real endpoint placement/cancellation study remains. |
| R5 quality/cost | Partial | Six-case real GLM screen passed development checks; full real workload not yet clean or qualified. |
| R6 policy transport | Partial | Native policy packet extraction and local mock direct/Agmina comparison pass; live policy and closed loop remain. |
| R7 heterogeneous compute | Pending | Requires a stable baseline and second endpoint/device class. |
| R8 partner validation | Pending | Requires an authorized partner trace and repeatable value measurement. |

## Key Experiments

- **Local foundation:** the current workspace passes `148` tests and Ruff. No native robot action or
  GPU policy inference was used by these Agmina experiments.
- **R2 direct vs Agmina:** one identical request body was sent through both paths. Request hashes
  matched; observed latency was about 2.40 s direct vs 1.25 s through Agmina. Separate outputs are
  expected because they were independent calls. This is transport evidence only.
- **R5 real six-case screen:** 6/6 calls were consumed, schema-valid, citation-valid, and correct
  under the independent development evaluator. Labels were not held out and charge holds remain
  unresolved, so it is not a benchmark claim.
- **Original full StreamArena real run:** GLM frequently returned extra keys or non-string fact
  values; StreamBudget rejected them. This produced many parent schema failures.
- **Strict prompt and schema canaries:** strict prompts removed failures in a 20-call canary. The
  JSON-schema perception endpoint also passed a 20-call canary with zero schema failures.
- **Latest bounded task canary:**
  `runs/r5-streamarena-glm-schema-task-20260926-001` replayed 530 frames of `JNpUsYTVM6k`, crossing
  the 240-second watch and 260-second ask tasks. It consumed 522 calls: 519 perception and 3
  planner. It recorded 514 completed parent jobs, 6 `ContractError` failures, 11 skipped
  observations, and one emitted alert. The ask abstained because the runtime packet contained no
  audio evidence for the horn. The run is `transport_incomplete` and `not_qualified`.
- **Contract repair canary:** after adding an explicit empty-watch rule, the bounded
  `runs/r5-streamarena-glm-schema-nowatch-20260926-001` run consumed 111/111 perception calls
  through source time 59.5 seconds with zero parent failures. It covers both known failure regions
  and confirms the semantic prompt repair, but is not a model-quality result.
- **R3 real paced capacity:** `runs/r3-streamarena-glm-cohort-20260926-002` completed all 4/4
  one-session and 8/8 two-session jobs. Four sessions completed 11/16 and eight sessions 11/32;
  the remainder expired at the 20-second freshness boundary. Completion p50/p95 were 1.775/4.660 s
  (1 session), 1.548/2.534 s (2), 1.552/6.322 s (4), and 2.821/5.024 s (8). This is a real
  endpoint capacity result for one shared slot, not semantic quality or GPU timing.
- **Full real schema-routed replay:** `runs/r5-streamarena-glm-schema-full-20260926-003` ran both
  600-second videos. Video `JNpUsYTVM6k` completed 1,191/1,191 offered jobs with no parent
  failures. Video `9CQ6qmoOhlQ` completed 885 jobs, skipped 255 observations, and recorded 62
  parent failures. The failures were two planner `TimeoutError`s, one perception `RuntimeError`
  at source time 560s, and recurring perception timeouts from about 560s through the end; earlier
  ask timeouts occurred at about 432s and 509s. The run made 2,091 admitted attempts, all remain
  `unknown` in the Agmina ledger, and the configured estimated admission hold is `$4.182`. This
  is transport/freshness evidence only; labels were unread and no evaluator was run.
- **Timeout diagnosis and repair:** the real failure at call `...000895` was recorded as an Agmina
  `transport_failure`, which correctly quarantined the only endpoint pool. Independently, the
  bridge runner retained StreamBudget's default 30-second parent deadline while the Agmina
  endpoint allowed 180 seconds. The runner now aligns the parent deadline and drain timeout with
  the configured Agmina timeout, and the coordinator bridge fails fast when all eligible pools are
  quarantined. A zero-cost two-video smoke after the change completed with zero parent failures.
  This fixes runner behavior; it does not turn the provider failure into a quality result.
- **Cost accounting repair:** the chat adapter now retains a non-negative provider-reported
  `usage.cost` as normalized micro-USD when present, while failed or cancelled remote attempts
  remain unknown until reconciled. It also retains a bounded provider generation ID in successful
  receipts and call reports when returned by the endpoint. The available account key exposes only
  aggregate usage; per-day activity requires a management key, and the historical full replay
  retained no provider IDs. Its 2,091 attempts therefore remain unreconciled rather than being
  assigned from aggregate account usage.
- **Reconciliation import:** the runtime now has a dry-run-default JSON/JSONL importer for exact
  job-level provider charges. It validates a complete batch before an atomic apply and rejects
  duplicate, unknown, or already-settled jobs. A copied two-attempt ledger fixture passed; the
  historical campaign remains untouched because no per-attempt provider export is available.
- **R4 matrix preparation:** a no-dispatch manifest now freezes the first real scheduler comparison
  over the retained 16-job/four-session `s4` cohort, holding endpoint, pool capacity, source data,
  deadlines, and provider routing constant across FIFO, EDF, and least-slack. It has not been run
  because the configured provider credential is absent.

## Current Runtime Contract

- GLM model: `z-ai/glm-5.3-flash`, `reasoning.effort=low`, `max_tokens=4096`.
- Preferred provider order: Together, Baseten, Fireworks, Parasail, CoreWeave.
- Provider fallbacks are disabled; each attempt is retained and reconciled separately.
- Runtime labels remain unread; the private label audit is hash-only.
- No native actions are authorized by these experiments.

## Next Work

1. Obtain a management-key activity export or provider generation report and use the validated
   importer to reconcile the 2,091 real GLM attempt holds before any quality or cost claim.
2. Reconcile the provider-side transport failure and remaining unknown attempt holds; no new
   paid full replay is justified until that is done.
3. Dispatch the prepared bounded R4 scheduler matrix once a provider credential is available, then
   run the fixed-rate, tuned-detector/motion-refresh, and
   StreamBudget adaptive baselines under the same held-out protocol.
4. Keep R6 live policy, R7, and R8 downstream of the R5 quality gate.

## Verification

```bash
.venv/bin/ruff check .
.venv/bin/pytest -q
.venv/bin/python tools/verify_bundle.py
git diff --check
```

Raw run artifacts are under `runs/`; this brief intentionally does not include private labels or
provider credentials.
