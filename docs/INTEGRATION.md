# Integration without merging the applications

## Reviewed interfaces

The integration design was checked through GitHub reads at:

- `AranKomat/streambudget`: `076783012377d074b82efd7aaf296a8175b3a7f4`.
  `src/streambudget/backend.py`: `Request`, `ImageInput`, `Result`, `ModelPool.call`.
- `AranKomat/physical-agent-harness`: `cc03d4ed1ecb1664d9c1d04f6adc13786385f6d5`.
  `physical_harness/perception/contracts.py`: `FrameRef`, `DiscoveryRequest`.

The current workspace also contains a local StreamBudget checkout and a Physical Harness source
snapshot used by the R1 campaigns. StreamBudget reports commit
`076783012377d074b82efd7aaf296a8175b3a7f4` and a dirty working tree; the Physical Harness snapshot
has no `.git` metadata, so its revision is recorded as unavailable in fresh reports. These local
sources are evidence for the recorded smoke only; do not infer that they equal the GitHub reference
revisions above. Treat a newer upstream commit as a new integration target and inspect changed
interfaces before enabling an adapter.

## StreamBudget

Keep its application scheduler. It decides which watch/query deserves perception and which frames to
retain. Insert Agmina at the model-call boundary, initially for one perception role, not by moving
Watch, MemoryStore, agent tools or alert dispatch into this repo.

`adapters.hosts.streambudget_job()` accepts the inspected Request fields. It requires the source
availability/sequence map from the host evidence store plus an explicit source-to-coordinator clock
mapping. `ImageInput.timestamp` alone is not enough to reconstruct arrival time. The helper preserves
system/text/timestamped images; it does not append `request.context` as invented extra prompt content.
Compare the exact outgoing body with the existing `_body()` and set image detail/sampling identically
before any quality comparison.

The host sequence is:

```text
watch/query chooses evidence
→ retain source bytes and causal cutoff
→ reserve under the EXISTING parent experiment/campaign authorization
→ build and submit one Agmina job
→ await result, claim result, apply local post-network fence
→ pass result text to the existing StreamBudget parser
→ reconcile one actual provider attempt in parent accounting
→ watch/verifier decides whether to publish a semantic event
```

Agmina's durable admission ledger is an additional guard, not a new entitlement to spend. Do not
silently double-reserve forever or add the same provider cost twice in the final report: pick an
accounting owner and correlate attempt IDs. During the first isolated benchmark use a separately
approved new campaign, not the historical StreamBudget budget.

The returned Prediction contains `{"text": "..."}` for chat. Construct the host's Result with that
text, measured latency, request ID, and appropriately mapped usage. Keep normalized Agmina token
fields distinct from the host provider schema. Unknown charges remain unresolved in both views.

Provider reconciliation is an explicit offline operator step. `tools/reconcile_charges.py` accepts
only bounded JSON/JSONL rows with the exact Agmina `job_id`, a nonnegative integer
`actual_microusd`, and an `evidence_ref` identifying the provider export or receipt. It runs as a
dry-run unless `--apply` is supplied, validates the whole batch before writing, and rejects duplicate,
unknown, or already-settled jobs. A provider generation ID is useful evidence for future campaigns,
but it is not enough unless the export also maps it to the exact Agmina job. Never assign aggregate
account usage to one campaign or turn a missing invoice row into a zero-cost settlement.

No optional embedding/VSS/RTSP feature is recreated here. Existing live input and evidence storage
continue to belong to StreamBudget.

## Physical Agent Harness

Start with a **read-only discovery/shadow** bridge. `physical_observation()` converts a FrameRef after
checking the actual source bytes. It uses `basis.captured_wall` and `available_wall`; `basis.sim_time`
is preserved only as source metadata. Map monotonic origins explicitly.

Keep the corrected native SAM streaming worker and its state inside the host. Do not put that worker
behind interchangeable replicas. The first served policies should expose a documented stateless
prediction function, with complete observation/history/state supplied according to the checkpoint.
The native action queue, reset, preprocessing and normalization do not migrate automatically.

```text
native observations + current Basis
→ host chooses one inference request
→ Agmina admission/dispatch/result
→ post-network local fence against CURRENT task/execution epoch
→ native codec/identity/source checks
→ fresh catalog rebind / existing ActionExecutor review
→ actuator ownership, stop monitoring and independent task verification
```

The `ActionChunk` envelope checks named dimensions, units, normalization convention, period and finite
shape. It deliberately does not pad a DROID action to R1Pro, turn joint commands into EEF commands,
retime a learned policy, reset hidden state, or perform inverse kinematics.

For the inspected R1Pro loopback server, `adapters.native_policy` provides a narrower proposal-only
boundary. The host calls `HttpNativePolicyTransport.reset()` at episode setup, outside Agmina; each
Agmina job then carries the native stamp, instruction, 61-element proprio vector and the three native
camera arrays. The backend validates the returned stamp and finite 23-channel action rows without
resizing, padding, retiming or authorizing them. This qualifies the reset/infer RPC envelope locally;
it does not qualify a checkpoint, GPU latency, simulator behavior or live actuation.

The current native Phase 5–9 gates remain unchanged. A scheduler experiment is not motion permission.
Agmina has no method that drives a motor, writes WorldState geometry or marks a task complete.

`tools/r6_native_policy_compare.py` is the prepared campaign runner for the next R6 gate. It resets
the native server separately for the direct and routed paths, sends the same ordered packet cohort
through each path, records per-call complete-output latencies and the Agmina ledger trace, and
rejects any output mismatch. It requires explicit operator metadata for weights, preprocessing,
output schema, sampling, model revision and hardware/server details; the runner reports transport
equivalence only.

### R6 live-run recipe

On a qualified GPU host, start the already-pinned Behavior-Skill server in its own policy
environment. The server is loopback-only and does not authorize actions:

```bash
python -m physical_ai.behavior_skill_server \
  --source /workspace/physical-ai-lab \
  --checkpoint /workspace/behavior-skill-weights/pi05-pt50-skill \
  --manifest /workspace/behavior-skill-weights/manifest.json \
  --receipt /tmp/r6-policy.json --port 8011
```

After recording the exact checkpoint revision, preprocessing, hardware, precision, and server
revision, run the five prepared packets in order:

```bash
./.venv/bin/python tools/r6_native_policy_compare.py \
  --packet runs/r6-native-packet-001/packet.json \
  --packet runs/r6-native-packet-002/packet.json \
  --packet runs/r6-native-packet-003/packet.json \
  --packet runs/r6-native-packet-004/packet.json \
  --packet runs/r6-native-packet-005/packet.json \
  --out runs/r6-native-live-001 --model-name behavior-skill \
  --model-version PINNED_SERVER_REVISION --weights PINNED_CHECKPOINT_REVISION \
  --preprocessing PINNED_PREPROCESSING --output-schema PINNED_OUTPUT_SCHEMA \
  --sampling PINNED_SAMPLING --estimate-s SERVICE_P95_SECONDS \
  --allow-network
```

Keep action admission disabled. A successful run qualifies only the native transport comparison;
closed-loop motion still requires a separate authorization and independent outcome verification.

## Models and transport adapters

| Adapter | Implemented | Remaining qualification |
|---|---|---|
| Chat-compatible HTTP | Fixed endpoint, image-byte hashes, full SSE assembly, usage, first-content timing | Real provider/model compatibility, routes/revision, latency/quality |
| vLLM / SGLang | Use their chat-compatible serving path | Pinned device deployment; native video/encoder/KV experiments are separate |
| Triton V2 JSON | Finite typed flattened tensors, model name/version checks | Model IO config, codecs, device deployment, binary/shared-memory optimization |
| Generic stateless worker | Bound job/session epoch request and response envelope | Actual SAM image/grasp/VLA callable and its independent output validation |
| vla.cpp | No direct native-protocol implementation | Wrap its native ZeroMQ/protobuf or stateless predict path; preserve GGUF/native codec |
| FluxVLA | No direct native-protocol implementation | Wrap one pinned policy's actual prediction API; preserve checkpoint and temporal recipe |
| Microsoft / Isaac ROS | Integration architecture only | ROS/source bridge, offload deployment, sensor-time measurement |
| DeepStream / Holoscan | Integration architecture only | Reuse their ingest/decode/transport; emit source-bound inference jobs |

`examples/reference_worker.py` is a real FastAPI boundary with a synthetic compute function. It is not
a SAM or VLA implementation. Replace that function only in an isolated, pinned model environment,
then qualify its output and startup behavior. Do not install ROS/Isaac/cuRobo/ROCm dependencies into
the coordinator environment.

## Hardware plan

Use the current workstation for host/application work. Use one NVIDIA server or the available MI300X
for an operator-owned inference endpoint when custom dispatch and co-scheduling are the experiment.
The core does not depend on Jetson, AMD, NVIDIA, Kubernetes, or a cloud vendor. No claim of device
performance follows from the HTTP interface working.

First hold model/checkpoint and workload fixed on one accelerator. Later compare topology/device
changes separately. A 4090+NVIDIA-only SAM worker can coexist with an AMD semantic model server via
separate pools. Do not attempt an unqualified port of the entire robot stack merely to fill the AMD node.

Jetson adds a real embedded baseline later; lack of Jetson does not prevent coordinator/protocol/load
experiments, but prevents claiming embedded speed/power gains.
