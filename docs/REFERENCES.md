# Source review and design derivation

Reviewed 2026-09-24. The runtime is an original implementation, not a reproduction of a paper or a
fork of a vendor stack. No published speedups are attributed to this implementation.

## User repositories: actual interfaces read

1. StreamBudget at `076783012377d074b82efd7aaf296a8175b3a7f4`:
   - https://github.com/AranKomat/streambudget/blob/076783012377d074b82efd7aaf296a8175b3a7f4/src/streambudget/backend.py
   - https://github.com/AranKomat/streambudget/blob/076783012377d074b82efd7aaf296a8175b3a7f4/docs/FEATURE_STATUS.md
   Its request/image/result fields motivate the thin bridge. Watches, evidence, scheduling of
   semantic attention and prior runtime-pilot limitations remain owned by that application.

2. Physical Agent Harness at `cc03d4ed1ecb1664d9c1d04f6adc13786385f6d5`:
   - https://github.com/AranKomat/physical-agent-harness/blob/cc03d4ed1ecb1664d9c1d04f6adc13786385f6d5/physical_harness/perception/contracts.py
   Source-bound FrameRef and monotonic `wall` fields motivate the physical observation bridge.
   This delivery does not requalify native geometry, tracking, controls, or experiment permissions.

## Primary runtime documentation read in this build

3. NVIDIA Triton batching:
   https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/batcher.html
   Distinguishes stateless dynamic batching from stateful sequence batching and documents queue
   priorities/timeouts. We leave GPU batching to the backend; our queue orders requests above it.

4. NVIDIA Triton cancellation:
   https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/request_cancellation.html
   Backend cancellation support is explicit and not universal. This motivates conservative
   resource quarantine rather than pretending a client timeout frees a GPU or stops billing.

5. vLLM multimodal inputs:
   https://docs.vllm.ai/en/latest/features/multimodal_inputs/
   Multimodal encoding/cache behavior is backend-specific. Our generic chat adapter does not
   activate native video, encoder disaggregation, or cross-observation activation reuse.

6. Microsoft Research offloading overview:
   https://www.microsoft.com/en-us/research/blog/offloaded-inference-for-real-world-physical-ai-robotics/
   Motivation for measuring offload as a whole-loop systems question. The package does not copy
   Microsoft deployment code, reproduce their robot results, or require Azure/Kubernetes.

## Integration candidates from the project discussion; not live-validated here

- https://github.com/microsoft/physical-ai-toolchain — deployment/lifecycle integration target.
- https://nvidia-isaac-ros.github.io/ — robot data-plane/capability integration target.
- https://developer.nvidia.com/deepstream-sdk — video ingest/decode/analytics substrate.
- https://developer.nvidia.com/holoscan-sdk — sensor streaming substrate.
- https://github.com/VinRobotics/vla.cpp — native VLA backend/protocol wrapper candidate.
- https://github.com/FluxVLA/FluxVLA — policy and simulation workload candidate, not FLUX 3 Action.

Future references must be pinned when turned into executable adapters. The current code neither
claims these projects' quality nor treats their README numbers as local measurements.
