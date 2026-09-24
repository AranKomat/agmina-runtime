# Agmina Runtime

**A small, stateful inference coordinator for continuous video and physical agents.**

This is a new standalone MVP foundation, not another robot harness, video agent, inference
engine, or operating system. It sits between an application and its existing model servers.
It does not command robots, recognize objects, create task plans, or establish task success.

```text
Physical Agent Harness                  StreamBudget
  identity / geometry / task logic        video watches / evidence / investigation
                 \                       /
                  \ source-bound jobs   /
                   Agmina Runtime
         sessions · epochs · deadlines · resource pools
         nonpreemptive scheduling · compatible placement
         charge reservations · delivery fences · traces
                   /        |         \
          chat-compatible  Triton V2   typed worker
           API / local      tensors    model wrapper
                   \        |         /
             operator-managed NVIDIA / AMD / cloud
```

## Run locally without a GPU or API key

Python 3.11+ on Linux/macOS. Single writer; the file lock uses `fcntl`.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,server]'
agmina doctor
agmina demo --out runs/demo-001
agmina replay --out runs/replay-001
agmina load --config configs/mock.json --plan examples/mock_load.json --out runs/load-001
python tools/validate.py --out runs/validation-001
```

Use fresh output directories. These commands use explicit timer/JSON fixtures—not SAM, a VLA,
or a vision model. They do not make paid calls, use a GPU, or send robot commands. The replay
labels all outputs as simulated. It never infers physical task success from met deadlines.

## What is implemented

* **Sessions and four freshness boundaries:** submission/dispatch, model completion, server-side
  consumption, and a post-network client fence. Epoch/task changes invalidate old results.
* **Three nonpreemptive schedulers:** FIFO, earliest-deadline, and least-slack. They share admission
  and validity rules. Compatible endpoint placement is fastest or cheapest-estimate-that-fits.
* **Resource pools:** a cooperative slot budget across model workers sharing the same accelerator.
  Default one slot. No claim of GPU memory isolation, SM partitioning or kernel preemption.
* **Durable SQLite accounting:** estimated reservations, attempt caps, unknown-charge holds,
  reconciliation and explicit extensions. Crashed in-flight work is never automatically retried.
* **Cancellation discipline:** a cancelled consumer cannot consume the answer, but in-flight work
  keeps its slot. Unknown termination quarantines the pool until an explicit operator check.
* **Exact historical-result reuse and explicit latest-only queued replacement:** bounded,
  opt-in, session/task/evidence scoped. Neither alters current poses, actions, or tracker state.
* **Working adapter code:** chat-compatible HTTP with complete SSE assembly and first-content
  timing; Triton V2 JSON tensors; a small stateless-worker contract. All are tested locally;
  real model endpoints and device support remain to be measured.
* **Integration builders:** source-preserving StreamBudget requests, physical-harness FrameRefs,
  strict action-codec envelopes. Host parsers, ledgers, geometry, and action admission stay external.
* **Causal scheduler replay and paced endpoint load:** one preserves deterministic arrival/service
  traces; the other advances the source clock while actual requests run.

## First real endpoint experiment

Edit `configs/local-chat.template.json`: exact server model name, revision/provenance, measured
profile, output budget and endpoint. It targets an operator-owned local server by default.
For a billed provider, configure explicit positive reservations, rates, credential environment
variable and a separately authorized campaign ceiling. Do not reuse another project's spent budget.

```bash
agmina probe --config configs/local-chat.template.json \
  --packet examples/vision_packet.json --model vision --count 3 \
  --out runs/local-vlm-001 --allow-network

agmina load --config configs/local-chat.template.json \
  --plan examples/vision_load.json --out runs/local-load-001 --allow-network
```

The image is an original synthetic square. This qualifies transport, accounting and timing only.
`probe` stops on the first failed attempt. `load` follows a predeclared arrival plan; a failed worker
can quarantine its pool, and remaining offered jobs are retained as rejected/expired rather than retried.

## Optional loopback sidecar

```bash
export AGMINA_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
agmina serve --config configs/mock.json --database runs/sidecar/ledger.sqlite --port 8766
```

The authenticated API exposes sessions, jobs, result consumption, cancellation and metrics.
Credentials are environment references, not source files. No arbitrary endpoint registration or
remote image fetching is exposed. Do not expose this research server directly to the Internet.

## Scope boundaries

**Runtime state is not neural hidden state.** This version rejects models declared stateful. Keep
live SAM tracking state and policy queues inside their existing host workers; use stateless predictions
with explicitly supplied history until sequence/reset protocols are separately qualified.

The application still decides **whether inference is needed**. StreamBudget owns watches/keyframes;
the physical harness owns semantic boundaries and action legality. Agmina does not replace those
policies with another generic planner. It owns **when/where eligible work runs and whether its result
can still be delivered**.

GPU batching, encoder/KV reuse, model distillation, stateful-worker migration, live RTSP decoding,
Jetson measurement, dynamic SM partitioning, and native task improvement are not implemented or
claimed. Triton/vLLM/SGLang may batch internally; Agmina does not call independent HTTP requests a
GPU batch.

## Read next

[Self-contained handoff](HANDOFF.md) · [Design and invariants](docs/DESIGN.md) ·
[Integration instructions](docs/INTEGRATION.md) · [Experiment sequence](docs/EXPERIMENTS.md) ·
[Validation record](VALIDATION.md) · [Security/operations](SECURITY.md) ·
[Primary references](docs/REFERENCES.md) · [Third-party boundaries](THIRD_PARTY.md)

Original code is MIT licensed. No weights, datasets, upstream source trees, private logs, or cloud
credentials are included. No change was made to either existing repository.

## Integrity and status

Before editing, run `python tools/verify_bundle.py` against the delivered manifest.
The [feature-status table](docs/STATUS.md) separates implemented coordination from
unqualified model/device integrations. Local validation can include a real localhost
HTTP smoke with `python tools/validate.py --out runs/validation-new --loopback`.
