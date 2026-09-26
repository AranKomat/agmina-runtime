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
| R4 scheduling | Partial, bounded real observations | FIFO/EDF/least-slack ran on retained unloaded, overloaded, bursty, and provider-pinned proxy-fault conditions with accounting; one joint cache/latest-only control passed, while placement and broader replication remain. |
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
  deadlines, and provider routing constant across FIFO, EDF, and least-slack.
- **R4 bounded endpoint observation:** the matrix then ran once per scheduler. FIFO consumed 14/16,
  EDF 16/16, and least-slack 15/16. All charges were known (`2,555` micro-USD total), with no
  unknown holds or pool quarantine. A metadata-only audit of the retained generation IDs succeeded
  for all 45 dispatched jobs in the matrix: Together served `z-ai/glm-5.3-flash-20260826`. This
  remains transport/capacity evidence rather than a scheduler or quality conclusion.
- **R4 overloaded replication:** the same three schedulers ran on the retained 32-job/eight-session
  cohort. FIFO consumed 10/32, EDF 11/32, and least-slack 9/32, with `1,842` micro-USD known usage
  and no unknown holds or quarantine. The same audit covered all 30 dispatched jobs and found the
  same Together-served revision. This extends the real load curve but does not qualify placement,
  cache/latest-only, injected-loss, or broader scheduler effects.
- **R4 provider-generation audit:** `tools/r4_audit_generations.py` queried retained OpenRouter
  generation metadata only; it made zero model calls, and all 81/81 lookups succeeded across the
  scheduler matrices and real cache/latest probes. The audit establishes provider/revision identity
  for the retained attempts, not quality, semantic equivalence, or invoice reconciliation.
- **R4 bursty replication:** a fresh all-at-once 16-job matrix completed 16/16 under FIFO, EDF, and
  least-slack with zero unknown charges. EDF had the lowest median queue/completion latency
  (`10.18/12.21 s`), ahead of FIFO (`14.94/16.55 s`) and least-slack (`10.99/12.92 s`). This is
  a bounded burst-handling observation on one endpoint, not a universal scheduler ranking.
- **R4 real-link fault probes:** the corrected localhost proxy campaign injected a declared 1-second
  response delay and consumed 37/48 dispatched jobs; 11 expired and all `2,430` micro-USD were known.
  The served model revision was uniform, but provider identity mixed Together and Parasail. A
  separate dropped-response probe quarantined the pool and was reconciled from its retained provider
  generation receipt to `95` micro-USD. These are bounded transport/accounting observations, not a
  pinned scheduler or quality result. The preceding proxy implementation failure is retained
  separately with three unresolved estimated holds (`6,000` micro-USD) because it did not log the
  upstream generation IDs; those attempts are excluded from the corrected totals.
- **R4 provider pin control:** one direct request with `provider.only=["together"]` consumed for
  `48` micro-USD and, after a short metadata propagation delay, was confirmed as Together serving
  `z-ai/glm-5.3-flash-20260826`. This is a routing-control check, not a scheduler or quality result.
- **R4 provider-pinned delay replication:** the same 16-job bursty workload was forwarded through
  the one-second proxy with Together-only routing. FIFO consumed 15/16, EDF 14/16, and least-slack
  11/16; 40/48 dispatched attempts had complete metadata, all were Together at
  `z-ai/glm-5.3-flash-20260826`, and known usage was `2,271` micro-USD. This is pinned transport
  evidence, not a scheduler or quality conclusion.
- **R4 joint cache/latest-only ablation:** a five-job Together-only trace combined one exact-cache
  duplicate with a queued latest-only replacement. The joint condition consumed 4/5 offered jobs
  through 3 dispatches, with one cache hit and one supersession, for `149` micro-USD; the matched
  no-control baseline consumed 4/5 through 4 dispatches for `219` micro-USD. All seven generation
  records audited to Together at `z-ai/glm-5.3-flash-20260826`, with zero unknown charges. This is
  a bounded joint-control observation, not a general cost or quality claim.
- **R4 ablation plumbing:** the paced load plan now passes explicit cache/latest-only controls and
  optional stable evidence IDs into runtime jobs. Retained mock smoke `...-002` produced one cache
  hit and superseded one queued older latest-only request when a newer snapshot arrived; `...-001`
  retains the equal-snapshot negative control. Policy caching/discarding and unstable evidence
  identity reuse are rejected. This is software/fixture evidence only; the bounded real probe is
  recorded separately below.
- **R4 bounded real ablation:** the corrected cache condition consumed both same-evidence jobs with
  one exact historical cache hit and `55` micro-USD known usage, with zero unknown attempts or
  quarantine. The retained first cache run had `cache_bytes=0` and is a configuration negative
  control. The latest-only probe superseded its queued older request, but the newer replacement
  expired because the conservative 19-second endpoint estimate did not fit the remaining 20-second
  deadline after the blocker. This is an admission/deadline observation, not a quality result.
- **R4 latest-only deadline correction:** a separately labeled 60-second condition consumed the
  blocker and newer request, superseded the older queued request, and recorded `151` micro-USD of
  known usage with zero unknown attempts or quarantine. The zero-cost injected-delay/loss control
  consumed all delayed jobs and quarantined the mock pool after an unconfirmed loss. These are
  coordinator/accounting results, not quality or real-link results.
- **R4 matched latest-only baseline:** the same three-job trace with replacement disabled consumed
  all 3 jobs for `204` micro-USD, while latest-only consumed 2 and superseded 1 for `151` micro-USD.
  The observed difference is `53` micro-USD and one avoided request under this trace only; provider
  revision and semantic equivalence remain unqualified.

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
3. Repeat the dropped-response fault with Together-only routing, then qualify placement when a
   second real endpoint path is available. Replicate the joint/cache/latest-only controls on more
   than one trace before making a broader claim, then run the fixed-rate,
   tuned-detector/motion-refresh, and StreamBudget adaptive baselines under the same held-out protocol.
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
