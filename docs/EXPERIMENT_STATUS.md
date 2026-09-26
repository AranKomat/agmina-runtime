# Agmina Runtime Experiment Status

**Protocol:** R0-R8 in [EXPERIMENTS.md](EXPERIMENTS.md)  
**Repository:** `AranKomat/agmina-runtime`  
**Last updated:** 2026-09-26

This is the working checklist for the Agmina Runtime experiment program. The R-series definitions
and acceptance criteria remain in `docs/EXPERIMENTS.md`; this file records what has actually been
run. A synthetic or shape-level check must not be promoted to an endpoint, application-quality,
hardware, or physical-task result.

## Status At A Glance

| Stage | Status | Current evidence / next gate |
|---|---|---|
| R0 | **Complete** | Local software reproduction and validation passed; see `VALIDATION.md`. |
| R1 | **Partial: retained read-only integration** | Fresh two-parent fault matrix, retained lineage comparison, and clock-reset/generation fences pass; explicit parent task/episode identity fields remain absent in StreamBudget. |
| R2 | **Partial: real direct/Agmina transport pair** | One corrected GLM packet completed directly and through Agmina with identical request hashes and usable outputs; provider revision and charge reconciliation remain open. |
| R3 | **Partial: real 1/2/4/8-session load complete** | 1/2 sessions completed all offered jobs; 4/8 sessions hit the declared freshness boundary. Repeat with a declared capacity target only if needed. |
| R4 | **Partial: first real scheduler observation** | The first real FIFO/EDF/least-slack matrix completed with full accounting; provider revision, replication, and broader placement/cancellation conditions remain. |
| R5 | **Partial: real GLM replay transport incomplete** | Six-case development scoring passed, but the full two-video replay failed on one provider transport path; labels and charges remain unresolved, so this is not a qualified benchmark result. |
| R6 | **Partial: retained replay + native RPC contract** | A native RoboLab policy recording round-trips through Agmina, and the inspected reset/infer boundary now has a local proposal-only adapter test; live direct-vs-Agmina timing and closed-loop outcomes remain unqualified. |
| R7 | **Pending** | Compare one additional compute/site class with model and precision differences disclosed. |
| R8 | **Pending** | Run one design-partner pilot and repeat the same protocol with a second partner. |

## Checklist

### R0 — Reproduce The Foundation

- [x] Install the package and development/server dependencies in a supported environment.
- [x] Run the complete local test suite: 148 passed in the current workspace.
- [x] Run compilation, repository/link checks, doctor, demo, replay, and synthetic paced load.
- [x] Run Ruff and the authenticated localhost sidecar/SDK smoke.
- [x] Build and import the wheel outside the source tree.
- [x] Verify zero paid model calls and zero native robot actions.
- [x] Preserve the deterministic replay's blocking-background negative control.

**R0 conclusion:** the coordinator's local software invariants are reproduced. This says nothing
about model quality, GPU performance, StreamBudget quality, or robot competence.

### R1 — Read-Only Application Bridges

- [x] Pin the StreamBudget interface commit used for the smoke: `076783012377d074b82efd7aaf296a8175b3a7f4`.
- [x] Record the Physical Harness contract source revision used by the audited smoke:
  `852e5802f0808b459be7aae97dd4055486c57638` from the current clean local scaffold checkout.
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
- [x] Record the live parent source state for each smoke: StreamBudget is pinned to
  `076783012377d074b82efd7aaf296a8175b3a7f4` and dirty; the Physical Harness scaffold is pinned
  to `852e5802f0808b459be7aae97dd4055486c57638` and clean for the latest smoke.
- [x] Run the physical-harness bridge in discovery/shadow mode only.
- [x] Run the supported two-parent fault matrix: StreamBudget queued/in-flight shutdown, cancelled
  watch, deadline containment, and Physical Harness late-result rejection, pending/in-flight
  shutdown, and old-task historical-only delivery.
- [ ] Add explicit task/episode identity fields to the StreamBudget parent request contract (or
  record an upstream contract change) before claiming parent-native old-task and cross-path source
  identity coverage; Agmina session/generation fences are covered separately.
- [x] Run the actual parent fault smoke: StreamBudget in-flight shutdown, Physical Harness late
  response rejection, old-task historical-only delivery, and in-flight shutdown ambiguity.
- [x] Run a two-path clock-reset/generation-fence smoke covering stale consumption, target-clock
  mismatch, and expired mapping rejection.

**Gate:** source-bound requests round-trip without semantic or authority changes.

**Current evidence:** the latest workflow smoke `runs/r1-workflow-014`, fault campaign
`runs/r1-fault-012`, and clock campaign `runs/r1-clock-008` passed against StreamBudget commit
`076783012377d074b82efd7aaf296a8175b3a7f4` and Physical Harness scaffold commit
`852e5802f0808b459be7aae97dd4055486c57638`, with zero paid calls, zero GPU work, and zero native
actions. The fault campaign covers StreamBudget queued/in-flight shutdown, cancellation of a
watch while its response is in flight, deadline cancellation of a slow response, and no alerts
after those boundaries. It also confirms that Physical Harness archives a late result as an error,
cancels a pending call without invoking it, delivers an old-task result only as historical
inventory without waking the current executive, and reports that an in-flight callback cannot be
declared stopped until it exits. The retained request comparison `runs/r1-retained-004` verifies
source hashes, image order/detail, prompt, cutoff, clock mapping, and parent accounting; explicit
task/episode identity is absent from the StreamBudget request contract. The clock-reset campaign
`runs/r1-clock-008` rejects stale consumption and mapping mismatches for both adapters. Parent
checkout commit and dirty state are retained in the latest reports. R1 remains partial only for
the upstream StreamBudget identity-contract limitation and the resulting untestable parent-native
old-task/source-identity cross-product.

The source audit confirms this is not an Agmina field-loss bug: StreamBudget's `Request.context` is
generic fixture/prompt context, but the current watch runtime does not populate task or episode
identity and has no parent generation authority for the adapter to infer. Watch IDs are therefore
not treated as episode IDs, and Agmina does not synthesize identity from them.

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
  reservation, and request fingerprint: `runs/r2-preflight-002` (supersedes `r2-preflight-001`).
- [x] Complete one successful direct/Agmina pair with identical intended requests; see
  `runs/r2-glm-direct-agmina-001`.
- [ ] Record checkpoint/model revision, preprocessing, sampling, output schema, server revision,
  hardware, precision, routing, and declared budget before dispatch.
- [x] Run the same authorized packet directly and through Agmina; see
  `runs/r2-glm-direct-agmina-001`.
- [ ] Measure cold load/compile separately from warm first-content and complete-usable-output time.
- [ ] Pin the actually served provider revision and reconcile charge receipts/unknown-charge holds
  by attempt ID.

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

The no-network preflight `runs/r2-preflight-002` passed with zero network and paid calls. It
validated the exact outbound request body and fingerprint, the declared model contract, the `$0.25`
campaign ceiling, the `$0.05` endpoint reservation, and the requested provider route order
`together -> baseten/fp8 -> fireworks -> parasail/fp8 -> coreweave/nvfp4` with fallbacks disabled.
This is configuration and transport-readiness evidence only; it does not establish provider
availability, endpoint latency, model quality, or a charge receipt.

The corrected real comparison `runs/r2-glm-direct-agmina-001` completed one identical packet
directly and through Agmina. Both paths returned usable chat outputs; the request body hash was
identical (`844285...bcd923ad`), direct latency was 2.40 seconds, and Agmina latency was 1.25
seconds including about 1 ms of queue time. The separate response hashes differ because these were
independent model calls, which is expected and is not treated as a quality difference. The report
records `paid_calls: true`, but the endpoint did not return usable cost fields, so invoice
reconciliation and the exact served provider revision remain pending.

A public OpenRouter metadata query on 2026-09-25 returned HTTP 200 for `z-ai/glm-5.3-flash`.
The model advertises text/image/video input and structured outputs, and all five configured route
tags were present with provider status `0` at query time. This is metadata evidence only: it does
not prove that a paid request will be admitted, served by the selected route, or complete within
the declared deadline.

**Next endpoint candidate:** `configs/openrouter-glm.template.json` pins the requested provider
route order `together -> baseten/fp8 -> fireworks -> parasail/fp8 -> coreweave/nvfp4` with fallback
disabled. Before a new paid run, replace the model revision/profile placeholders, confirm the route
tags are supported by the account, and declare a fresh campaign cap. The route preference is not
evidence that any particular provider actually served a request.

### R3 — Paced Multi-Session Load

- [x] Prepare a retained, authorized workload plan with declared arrival times and deadlines:
  `runs/r3-streamarena-glm-cohort-20260926-002`.
- [x] Run one, two, four, and eight sessions within a predeclared cap; the 4- and 8-session
  cohorts missed the declared freshness target, so R3 remains partial.
- [x] Keep offered, rejected, expired, cancelled, late, and completed work in the denominator;
  the retained reports expose offered and terminal-state counts for every cohort.
- [x] Check duplicate dispatch, cross-epoch consumption, and queue-bound behavior in the retained
  Agmina reports; no duplicate dispatch or cross-epoch consumption was recorded.
- [x] Record endpoint response distributions in each cohort report.
- [ ] Record resident resource telemetry such as GPU time, memory, or energy.

**Gate:** useful completions remain within the declared freshness and capacity constraints.

### R4 — Scheduling, Placement, And Cancellation

- [x] Run deterministic FIFO/EDF/least-slack replay on a shared synthetic trace.
- [x] Exercise synthetic profile error, blocking background work, expiry, and pool recovery.
- [x] Freeze the first real-endpoint scheduler matrix and generate its no-dispatch manifest from the
  retained `s4` plan; see `docs/R4_ENDPOINT_PROTOCOL.md` and
  `tools/r4_prepare_endpoint_matrix.py`.
- [x] Run the first bounded real-endpoint scheduler matrix with the retained plan and evaluate all
  three conditions; see `runs/r4-endpoint-matrix-20260926-002` and
  `tools/r4_evaluate_endpoint_matrix.py`.
- [ ] Replicate and qualify on the real endpoint while holding model, precision, source data, server
  batching, pool capacity, and deadline semantics fixed, with the served provider revision pinned.
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

The first real endpoint matrix used the retained 16-job/four-session `s4` plan with one endpoint
slot and the same declared cap for FIFO, EDF, and least-slack. FIFO consumed 14/16 jobs, EDF 16/16,
and least-slack 15/16. All three reports had zero unknown attempts, zero held charges, and no pool
quarantine; provider-reported usage summed to 2,555 micro-USD. This is a bounded transport/capacity
observation only. The served provider revision was not pinned, and the cohort is too small to select
a scheduler or claim a general endpoint improvement.

The matched overloaded `s8` matrix used 32 offered jobs across eight sessions. FIFO consumed 10/32,
EDF 11/32, and least-slack 9/32; all three reports had complete accounting and no pool quarantine,
with 1,842 micro-USD of provider-reported usage in total. Together with the retained real R3
one/two-session cohorts and the s4 matrix, this gives a first load curve from unloaded through
overloaded conditions. It does not isolate injected loss, placement, cache/latest-only behavior, or
served-provider revision, so R4 remains partial.

### R5 — StreamBudget Quality And Cost

- [x] Audit the retained six-frame campaign's receipt, frame hashes, timestamps, and video identities.
- [x] Prepare and independently integrity-audit a fresh disjoint six-case candidate split without
  making model calls.
- [x] Run the candidate through the actual StreamBudget request and Agmina ledger boundary using
  the zero-cost mock backend; evaluator labels remain unread.
- [x] Run the two pinned fixed-camera StreamArena prefixes through the same request/Agmina ledger
  boundary in mock mode, enforcing source cutoffs; see `runs/r5-streamarena-mock-003`.
- [x] Exercise the actual StreamBudget fixed observation policy on a full 600-second prefix with
  visual calls journaled through Agmina's zero-cost mock bridge; see
  `runs/r5-policy-mock-003/JNpUsYTVM6k-fixed`.
- [x] Exercise the actual StreamBudget motion policy on the same full prefix; 1,191/1,191 visual
  calls were consumed through Agmina with zero bridge errors in
  `runs/r5-policy-mock-004/JNpUsYTVM6k-motion`.
- [x] Complete the adaptive policy screen with a sufficient zero-cost attempt cap; the corrected
  run `runs/r5-policy-mock-005/JNpUsYTVM6k-adaptive` consumed 1,191/1,191 visual calls with zero
  bridge errors, paid calls, native actions, or label reads.
- [x] Add `tools/r5_evaluate_candidate.py` for post-inference scoring with private labels kept
  outside runtime and bound to the retained audit hash; its six-case mock negative control remains
  explicitly `not_qualified`.
- [x] Freeze a fixed-camera workload, event taxonomy, held-out-label custody, negative-segment
  handling, and quality/latency constraints in `docs/R5_STREAMARENA_PROTOCOL.md`.
- [x] Add and bounded-smoke-test `tools/r5_streamarena_agmina.py`, routing image calls through
  evidence-bound jobs and planner/memory calls through explicit text-only query jobs; see
  `runs/r5-streamarena-agmina-mock-003`.
- [x] Add `tools/r5_streamarena_label_audit.py` and
  `tools/r5_evaluate_streamarena.py`; the evaluator requires a hash-only label audit, keeps
  references out of its output, and marks incomplete campaigns unqualified.
- [x] Complete the full two-video, 2,400-frame mock workload with a parent-failure gate and
  globally unique Agmina job IDs; see `runs/r5-streamarena-agmina-mock-009`.
- [x] Run six disjoint candidate cases through real Agmina-backed GLM inference and score them
  independently; see `runs/r5-real-glm-merged-001`.
- [ ] Run fixed-rate VLM, tuned detector/motion refresh, and existing StreamBudget adaptive baselines.
- [x] Run the same full workload through Agmina with one pinned real model and the declared cap;
  `runs/r5-streamarena-glm-schema-full-20260926-003` completed the first video cleanly but was
  `transport_incomplete` on the second (62 parent failures and 255 skipped observations).
- [x] Diagnose the full-replay timeout cascade and patch the bridge deadline/quarantine handling;
  confirm the repair with a zero-cost two-video smoke.
- [x] Add a dry-run-default, atomic provider-charge import path and validate it against a copied
  two-attempt ledger fixture; this makes future reconciliation operational but does not settle the
  historical campaign.
- [ ] Reconcile all 2,091 real attempts from the full replay before starting another paid full
  workload.
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
check, not answer-quality or held-out evidence. The fixed-camera workload and evaluation protocol
are now frozen in `docs/R5_STREAMARENA_PROTOCOL.md`.

The local StreamBudget checkout also contains a 40-case public `benchmark-subset-v1` with packet
and label hashes. Its existing screen receipt records 123 model attempts, `$1.1422144168` reported
spend, and `all_passed: false`; all 40 cases appear in the receipt exactly three times across
Gemini, Qwen, and GLM, so no untouched case remains in that subset. Because the labels and prior
outputs are already present, and the screen ran directly in StreamBudget rather than through Agmina,
this is development/reference material, not a qualified R5 held-out result. A future R5 campaign
needs the fixed-camera protocol and a new Agmina-backed real-model run.

A fresh disjoint candidate is now prepared at `runs/r5-heldout-candidate-001`. It contains six
MMVU validation cases (`538`, `106`, `680`, `390`, `21`, and `340`), excludes all 40 cases in the
prior StreamBudget manifest, and stores 16 uniformly sampled JPEG frames per case. The runtime
manifest omits answers; evaluator labels are held separately under `evaluator/labels-private.json`.
Acquisition completed with zero model calls and manifest outcome `prepared_not_qualified`. This
does not advance R5 to a quality result until evaluator custody, protocol, Agmina-backed inference,
and independent evaluation are all completed.

The repository auditor now understands this root-level candidate format. Its report
`runs/r5-heldout-audit-003` verified all six source-video hashes and all 96 sampled-frame hashes,
matched the six private label IDs, and retained the explicit `r5_qualification: not_qualified`
status. The labels are available for independent evaluation but are not considered held out until
custody and the evaluation protocol are separated from runtime inference.

The candidate screen `runs/r5-screen-mock-002` consumed all six cases through the actual
StreamBudget `Request`/`ImageInput` adapter and Agmina ledger. It recorded six synthetic attempts,
zero paid model calls, zero native actions, and `labels_read: false`. This validates application
and accounting wiring only; the mock output is not a model or quality result.

The first real candidate attempt exposed a configuration defect: the initial GLM template used a
256-token output cap and omitted the previously validated low-reasoning setting, so five calls
returned non-`stop` completions and exhausted a `$0.25` reservation cap without usable outputs.
The corrected config `configs/openrouter-glm-r5-candidate.template.json` restores the validated
`max_tokens=4096` and `reasoning.effort=low` contract. The resulting five-case run plus an isolated
case-340 run completed all six cases with six consumed jobs, valid JSON/citations, and six correct
answers under the independent evaluator. Observed completion latency was 3.08--4.16 seconds for
these six calls; input size was 4,201--5,364 tokens and output size 90--109 tokens. The merged
artifact is `runs/r5-real-glm-merged-001/evaluation.json`, with `1.0` schema, citation, answer,
and cited-answer rates. This remains `r5_qualification: not_qualified`: labels were available in
the development environment rather than held out, and all six external attempts retain unknown
charge holds until invoice reconciliation. The two component campaigns reserve 300,000 micro-USD
in aggregate; the rejected sixth attempt from `runs/r5-real-glm-002` is retained as a cap-boundary
negative control, not silently retried.

The finalized candidate runner now retains a candidate-manifest hash, source metadata, per-case
task-spec hashes, video hashes, and selected-frame hashes/evidence IDs in `input_provenance`.
`runs/r5-screen-mock-004` consumed all six cases with that provenance. The independent evaluator
`tools/r5_evaluate_candidate.py` read labels only after the runtime completed, verified the label
hash against `runs/r5-heldout-audit-003/report.json`, and correctly scored the fixture's
missing-text outputs as invalid; it produced no quality claim and kept
`r5_qualification: not_qualified`.

The fixed-camera screen `runs/r5-streamarena-mock-003` then consumed all eight tasks from the two
pinned 600-second, 2 FPS prefixes (`JNpUsYTVM6k` and `9CQ6qmoOhlQ`). Each task used eight source
frames at or before its cutoff; the runner verifies selected frame hashes, records source/task
hashes, and never opens `labels-private.jsonl`. All eight jobs reached `consumed`, with zero paid
model calls, zero native actions, and `causal_cutoff_enforced: true`. This closes the zero-cost
fixed-camera application/ledger screen, but it is still not a model-quality, latency, cost, or
official benchmark result. The remaining R5 gate is a pinned real-model run and independent
scoring under the frozen protocol.

The policy-level screen `runs/r5-policy-mock-003/JNpUsYTVM6k-fixed` replayed the actual parent
StreamBudget fixed policy over all 1,200 source frames and four tasks. It scheduled 602 visual
calls; all 602 were accepted, consumed, and journaled by Agmina, with zero bridge errors, paid
calls, native actions, or label reads. Planner calls remained on the parent deterministic fixture;
the visual serving boundary was the part routed through Agmina. An earlier attempt is retained at
`runs/r5-policy-mock-001` and exposed two harness issues: the mock attempt cap was too low, and
request-relative sequence numbers caused legitimate reused frame IDs to be rejected. The corrected
bridge uses a stable sequence per evidence ID and records bridge errors explicitly. This remains
integration evidence only, not model quality, endpoint latency, or benchmark success.

The matched motion screen `runs/r5-policy-mock-004/JNpUsYTVM6k-motion` completed the same 1,200
source-frame prefix with 1,191 visual calls, all consumed through Agmina without bridge errors.
The corrected adaptive screen `runs/r5-policy-mock-005/JNpUsYTVM6k-adaptive` also completed the
prefix with 1,191 visual calls consumed and zero bridge errors. Its parent replay made 1,197
synthetic model attempts and took 2,269.8 seconds of deterministic wall time on this CPU-only
host, so this is evidence of correctness/accounting rather than a capacity result. The earlier
1,000-attempt run remains retained as negative evidence for the former cap and must not be used
as a quality or call-volume comparison.

The full-workload runner `tools/r5_streamarena_agmina.py` replaces the parent StreamBudget model
pool and routes every call through Agmina. In the bounded smoke
`runs/r5-streamarena-agmina-mock-003`, 127 jobs were consumed: 126 evidence-bound perception
jobs and one zero-observation planner query. The Agmina ledger recorded zero cost and zero unknown
attempts; labels remained unread and no native actions occurred. The predecessor smoke
`runs/r5-streamarena-agmina-mock-002` intentionally hit a 20-attempt cap and is retained as
negative evidence for campaign-cap sizing. The successful smoke proves routing/accounting and
text-only contract behavior, not model quality, latency, or benchmark performance.

The follow-up smoke `runs/r5-streamarena-agmina-mock-004` includes per-video provenance and was
scored with `runs/r5-streamarena-label-audit-001.json`. The evaluator returned
`scored_incomplete`: four tasks were visible from one capped video, three were missing and the
synthetic answer abstained, with zero exact answers and zero timely events. This is the intended
negative control. The evaluator accepts a label-audit superset but rejects an unaudited runtime
video, and it never copies reference answers into the scoring artifact. A complete two-video run
is now available as `mock-009`; real-model quality interpretation remains pending.

The corrected complete replay `runs/r5-streamarena-agmina-mock-009` covered both videos and all
2,400 frames with `2,138` unique Agmina jobs (`2,134` perception and `4` planner calls). Every
Agmina call was consumed; both parent StreamBudget reports recorded zero `job_failed` events; the
campaign recorded zero cost, zero unknown holds, zero native actions, and `labels_read: false`.
The independent evaluator `runs/r5-streamarena-eval-mock-009.json` scored all eight tasks (seven
eligible) with zero exact/strict answers and retained `r5_qualification: not_qualified`, as
expected for the synthetic fixture. This closes the parent-clean zero-cost transport and evaluator
mechanics gate only; it is not a model-quality, latency, capacity, or benchmark result.

Three runner issues found during this replay were fixed and reproduced in bounded tests: source
clock mappings are now stable across overlapping evidence windows, job IDs are unique across
videos sharing one Agmina ledger, and the zero-cost fixture capacity/window covers the declared
full workload. The runner also records bounded bridge error messages and reports
`transport_incomplete` whenever parent `job_failed` is nonzero. Earlier capped/failed runs remain
retained as negative evidence and are not used for the clean result.

The bounded real schema-routed task canary `runs/r5-streamarena-glm-schema-task-20260926-001`
replayed 530 frames of `JNpUsYTVM6k`, crossing the 240-second watch and 260-second ask tasks.
It consumed 522 calls (519 perception, 3 planner), recorded 514 completed parent jobs, 6
`ContractError` failures, 11 skipped observations, and one emitted alert. The ask path abstained
because the runtime packet contained no audio evidence for the horn. It is therefore
`transport_incomplete` and `r5_qualification: not_qualified`. The schema endpoint reduced the
earlier output-contract failure rate substantially but did not eliminate it. The campaign held
`$1.044` in estimated admission at the configured reservation rate; all 522 attempts remain
unknown holds pending provider reconciliation. This was the pre-repair rationale for the later
full replay; it is retained as historical context rather than a current instruction.

The follow-up no-watch canary `runs/r5-streamarena-glm-schema-nowatch-20260926-001` exercised 120
frames through source time 59.5 seconds, including both previously failing regions. With the
empty-watch semantic prompt guard, all 111 perception calls were consumed with zero parent
failures, zero skipped-contract failures, and zero native actions. This repairs the identified
failure mode; it is still only transport evidence and does not qualify R5.

The subsequent full real replay `runs/r5-streamarena-glm-schema-full-20260926-003` used the
repaired schema-routed path on two 600-second videos. The first video completed 1,191 offered
jobs without parent failures. The second completed 885 jobs, skipped 255 observations, and
recorded 62 parent failures: two planner timeouts, one perception runtime error at source time
560s, and a sustained perception-timeout cascade through the end of the video. The campaign made
2,091 admitted attempts; every attempt remains an explicit `unknown` charge disposition pending
provider reconciliation, with `$4.182` held at the configured estimate. The report is
`transport_incomplete`, labels were unread, and no evaluator was run. Do not interpret this as a
quality result. Before another paid full replay, isolate the timeout cascade and reconcile the
attempts.

The timeout diagnosis identified two separate conditions. The first real failure was an Agmina
`transport_failure` on job `...000895`, which quarantined the only endpoint pool as designed. The
runner also left StreamBudget's default 30-second parent scheduler deadline in place even though
the Agmina endpoint timeout was 180 seconds. The runner now aligns both parent scheduler deadline
and drain timeout with the configured bridge timeout, and the coordinator wait path fails fast
when all eligible endpoint pools are quarantined. A zero-cost two-video smoke after the repair
completed with zero parent failures. This is a runner correctness repair, not a provider-quality
or benchmark result.

The chat adapter also now preserves a non-negative provider-reported `usage.cost` as normalized
micro-USD before falling back to configured token rates. This improves reconciliation for future
successful responses; it does not settle calls that timed out or otherwise ended with unknown
remote termination. It also retains a bounded provider generation ID in the receipt and Agmina
call report when the endpoint returns one, giving future reconciliation a stable provider-side
reference without retaining response text or credentials. A read-only account check confirmed that
the currently available OpenRouter key exposes aggregate usage only; the per-day activity endpoint
requires a management key. The historical full replay retained neither provider generation IDs nor
a management-key activity export, so its 2,091 attempts cannot be reconciled per attempt from the
current artifacts. Aggregate account usage is deliberately not substituted for campaign evidence.

`tools/reconcile_charges.py` now provides the missing operational import boundary. It requires exact
job IDs, nonnegative integer micro-USD charges, and explicit evidence references; preflights the full
batch without writing by default; and atomically rejects duplicate, unknown, or already-settled
entries. The copied-ledger regression fixture covers dry-run and apply behavior, including a valid
zero-dollar provider settlement. This is accounting-tool validation only. No historical attempt was
settled because the required per-attempt provider evidence is still unavailable.

### R3 — Real Paced Capacity Result

The retained-input cohort `runs/r3-streamarena-glm-cohort-20260926-002` used four hash-verified
frames per session, a 6-second per-session release period, 20-second deadlines, one shared
endpoint slot, and separate campaign caps. It did not read labels or include source decode time.

| Sessions | Offered | Consumed | Expired | Completion p50/p95 | Interpretation |
|---:|---:|---:|---:|---:|---|
| 1 | 4 | 4 | 0 | 1.775 / 4.660 s | Within the declared boundary. |
| 2 | 8 | 8 | 0 | 1.548 / 2.534 s | Within the declared boundary. |
| 4 | 16 | 11 | 5 | 1.552 / 6.322 s | Freshness boundary reached under burstier load. |
| 8 | 32 | 11 | 21 | 2.821 / 5.024 s | Overloaded for this one-slot configuration. |

The four cohorts consumed no native actions. Estimated admission holds were `$0.008`, `$0.016`,
`$0.022`, and `$0.022` respectively; provider invoices remain unknown. This is a real endpoint
transport/capacity result, not semantic quality, GPU-time, or camera decode performance. R3 is
partial rather than passed because the 4- and 8-session cohorts missed the freshness target.
The retained ledgers contain one dispatch per dispatched job and no cross-epoch consumptions:
4/4, 8/8, 11/11, and 11/11 unique dispatch IDs for the 1/2/4/8-session cohorts respectively.
GPU time, resident memory, and device energy remain unavailable and are not inferred from HTTP
wall time.

### R6 — Policy/Simulator Closed Loop

- [x] Select and document a retained native policy/simulator recipe and its observation/action codec.
- [x] Replay recorded policy inputs with no actions first: `runs/r6-recorded-001`.
- [x] Add and locally test the loopback native `policy.reset`/`policy.infer` adapter with exact
  R1Pro packet and action validation; no server, GPU or action call was made by this contract test.
- [x] Prepare `tools/r6_native_policy_compare.py` for an ordered same-packet-cohort
  direct-versus-Agmina run; it resets once per path and requires an operator-started loopback
  server plus explicit `--allow-network`.
- [x] Prepare `tools/r6_extract_native_packet.py` to verify and decode one retained Behavior-Skill
  trace boundary into the audited native RGB/proprio packet; output is explicitly offline-only.
- [x] Extract and hash-check retained boundaries `runs/r6-native-packet-001` through
  `runs/r6-native-packet-005` at native sequences `0, 32, 64, 96, 128`; the five-boundary cohort
  crossed the direct-vs-Agmina runner in `runs/r6-native-compare-003` against a local mock RPC
  with exact output equality.
- [ ] Compare direct server and Agmina paths under the identical recipe.
- [ ] Keep local control, emergency behavior, action admission, verification, and recovery in the
  application host.
- [ ] Exercise epoch changes, stale catalogs, clock uncertainty, target movement, network stalls,
  and buffer exhaustion.
- [ ] Record task/progress outcomes, prediction age, idle/stall intervals, corrections, and action
  counts; independently verify outcomes.

**Gate:** native gates and closed-loop outcome evidence pass. A timer fixture or open-loop replay is
not sufficient.

The retained RoboLab `BananaInBowlTask` recording contains five native policy queries from one
successful source episode. The no-action replay `runs/r6-recorded-001` verified each retained NPZ
hash, the `540x640x3` UINT8 image, `7`-element FP32 joint state, `1`-element FP32 gripper state,
and `32x8` FP32 joint-position action chunk; all five action payloads round-tripped exactly through
the Agmina action-proposal contract. The host consumed them only as shadow evidence and recorded
`action_authorized=false` for every query; the campaign used zero model, network, GPU, and native
action calls. The source receipt reports a successful episode and native timing, but that is source
evidence rather than a result of this replay.

The five-boundary mock transport comparison `runs/r6-native-compare-003` preserved one reset per
path, strictly increasing native sequences, exact direct/routed proposals, and five successful
Agmina ledger consumptions with `action_authorized=false`. It remains a local mock result and does
not measure a real policy server, GPU, or policy quality.

This does not qualify live offload: the retained receipt lacks an exact checkpoint/server revision,
capture timestamps, and the reset/sequence semantics required by its session-ID contract. The next
R6 gate is therefore a direct-versus-Agmina comparison using the same native policy recipe, now
using the isolated native RPC adapter, followed by a separately authorized closed-loop run with
local action admission and independent outcome verification. `runs/r6-native-packet-001` is only
retained offline data preparation; its mock-RPC pass is not a live endpoint result.

The last read-only availability probe of the previously supplied GPU host returned connection
refused, and no policy server process was available locally. No inference or CPU/GPU workload was
started. R6 therefore remains waiting on a reachable, operator-owned Behavior-Skill server with
the exact checkpoint/server/hardware metadata required by the prepared comparison runner.

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
