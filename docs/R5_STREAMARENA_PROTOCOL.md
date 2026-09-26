# R5 Fixed-Camera StreamArena Protocol

**Status:** frozen for the next real-model campaign; no paid call is authorized by this file.

## Workload

- Use the two retained 600-second, 2 FPS prefixes `JNpUsYTVM6k` and `9CQ6qmoOhlQ` from the
  separately maintained StreamBudget checkout.
- Use all four source tasks per prefix: eight tasks total, including both ask and watch tasks.
- The event taxonomy is `ask` (retrospective answer) and `watch` (proactive event detection and
  notification). The evaluator also retains negative segments, including eligible no-event periods,
  and failed/missing notifications remain in the denominator.
- Keep the source dataset and private evaluator labels outside this public repository. Record
  source, task, preparation, and selected-frame hashes in every run.
- The private label file is the evaluator-only authority for answer references, event references,
  censoring, and negative segments; runtime never receives it.
- Runtime input contains only frames and task text available at or before the task cutoff. No
  answer, reference timestamp, future frame, oracle crop, transcript, or post-hoc label may enter
  a request.

## Agmina Boundary

- Convert every model request with `streambudget_job`.
- Preserve source-frame IDs, source timestamps, sequence numbers, JPEG hashes, cutoff, clock map,
  model alias, request fingerprint, deadline, and ledger events.
- Keep the application host responsible for task semantics, label custody, answer delivery, and
  independent outcome evaluation. Agmina remains the inference coordinator and accounting layer.
- The zero-cost `runs/r5-streamarena-mock-003` screen is wiring evidence only. Its eight-frame
  recent windows are not a substitute for the final model-selection policy.
- The policy-level `runs/r5-policy-mock-003/JNpUsYTVM6k-fixed` screen exercises the real parent
  fixed-policy scheduler with Agmina beneath visual calls. It is still a mock-response screen;
  real-model quality remains open. The matched motion screen is
  `runs/r5-policy-mock-004/JNpUsYTVM6k-motion`; the corrected adaptive screen is
  `runs/r5-policy-mock-005/JNpUsYTVM6k-adaptive`. The earlier adaptive run in the motion directory
  remains retained as negative evidence because its temporary attempt cap was reached.
- Candidate reports retain `input_provenance` with the candidate-manifest hash, source metadata,
  task-spec hashes, video hashes, selected-frame hashes, and request evidence IDs. Use
  `tools/r5_evaluate_candidate.py` only after inference with the retained audit report; it reads
  evaluator labels outside the runtime and emits a hash-bound scoring artifact, but never qualifies
  R5 by itself.
- For the fixed-camera StreamArena replay, create a hash-only label record with
  `tools/r5_streamarena_label_audit.py` before inference, then use
  `tools/r5_evaluate_streamarena.py` after a transport-completed run. The evaluator accepts an
  audited superset for bounded development screens, rejects unaudited runtime videos, and marks
  incomplete campaigns `not_qualified`.

## Comparisons And Metrics

Run matched policies with the same model contract and source workload:

1. fixed-rate observation;
2. motion-triggered observation with periodic refresh;
3. adaptive observation;
4. the same selection policy with Agmina beneath it, when isolating serving effects.

Retain every offered, rejected, expired, cancelled, late, failed, unknown, and completed attempt.
Report per policy and per task:

- semantic answer correctness, with independent evaluator labels;
- proactive-event recall and strict delivery timing where applicable;
- first-content and complete-usable-output latency;
- evidence IDs and cutoff compliance;
- observation count, image bytes, input/output tokens, model attempts, reported cost, and unknown
  charge holds;
- errors, drops, step limits, censoring, and returned provider route.

Do not combine semantic correctness with timing, and do not replace censored or failed cases.
Custom judging is a development metric, not an official benchmark score.

## Admission And Interpretation

- Before a real endpoint run, create a fresh operator-approved campaign cap, pin the endpoint/model,
  record the provider priority and response schema, and reconcile each attempt before retrying.
- No automatic retry, quota borrowing, provider substitution, or label-based sample replacement.
- A successful mock or replay proves only application, causality, and accounting behavior. R5 is
  qualified only after a real Agmina-backed run and independent evaluation satisfy the frozen
  protocol.
