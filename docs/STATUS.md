# Delivery status — 0.1.0

The word **stateful** describes the coordination/session/ledger layer. It does not claim
migration of a model's recurrent state, policy action queue, SAM tracking memory, or KV cache.

| MVP surface | Delivered | Local test | Still to qualify |
|---|---|---|---|
| Physical/video session protocol | Named monotonic clocks, task/epoch fences, typed evidence, advisory buffer horizon | Contract/property and actual loopback HTTP checks | Actual source/consumer clock calibration and robot feedback |
| Scheduling | Bounded FIFO/EDF/least-slack queues, immutable dependencies, pending latest-only opt-in | Deterministic replay and live asyncio mock load | Measured heterogeneous endpoint profiles, saturated GPU behavior, fairness |
| Placement | Fastest or cheapest feasible endpoint within an operator-declared equivalent-model contract | Multiple endpoint/pool mock tests | Actual equivalence, hardware/network/precision effects |
| Backends | Chat/vision-compatible HTTP + complete SSE assembly, Triton HTTP V2 tensors, typed stateless worker | Mock HTTP, finite tensors, response and credential checks | Real providers, vLLM/SGLang/Triton, actual model workers |
| Resources | Shared cooperative slots, explicit pool quarantine on unknown completion | Cancellation, timeout and process-recovery checks | Backend cancellation acknowledgement; GPU memory/SM isolation |
| Stateful compute reduction | Job-ID idempotency, exact historical-result cache, explicit latest-only pending replacement | Scope/TTL/source/epoch checks | Encoder/KV reuse, cross-job sample coalescing, native microbatching |
| Accounting | Durable reservations, unknown-charge holds, approved extension/reconciliation hooks | Crash/restart and admission tests | Provider invoice reconciliation and GPU energy/rental accounting |
| Telemetry | Queue/model round-trip/first-content/complete/consume clocks, offered/status denominators | Tests, async demo, paced load | Actual camera decode, network-tail and device traces |
| Application bridge | StreamBudget request-to-job mapping; Physical Harness FrameRef conversion; action codec envelope | Shape-level fixtures from reviewed interfaces | Optional adapters running inside both full parent checkouts |
| Packaging | Python library, CLI, authenticated research sidecar, examples, CI definition | Built wheel/imports/CLI and extracted-bundle test (see validation) | Remote CI, Docker, Python 3.11 and target devices |

There is **no actuator API**, no new world state or semantic memory, and no reasoner/model selector
replacing GPT. No automatic host-ledger migration. The source-of-truth applications retain their
existing permissions and verification. All numerical replay results are synthetic scheduling
examples, not ML quality, customer ROI or hardware-speedup measurements.

A caller timeout is not proof a remote model stopped. Cooperative slots cannot constrain unrelated
GPU processes. Static latency estimates are heuristics, not end-to-end real-time guarantees.

See [Validation](../VALIDATION.md), [experiment sequence](EXPERIMENTS.md),
and [integration instructions](INTEGRATION.md).
