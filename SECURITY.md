# Security and operations boundary

This is a trusted-application, single-tenant research runtime. It is not a production multi-tenant
cloud, safety controller, authorization system for robots, or untrusted plugin sandbox.

## Defaults

Network inference is disabled until explicitly enabled. Examples use synthetic workers. The sidecar
binds to loopback, requires a bearer token and disables API documentation/access logs. Off-loopback
HTTP endpoints are rejected: use HTTPS or an authenticated local tunnel. Endpoint URLs are configured
by the operator, never chosen by a model/request. Redirects and arbitrary remote image URLs are not
followed. Credentials are read only from configured environment-variable names.

Body, JSON depth, frame count, model output, queue, jobs, attempts and estimated-charge bounds exist.
These are research limits, not a defense against arbitrary denial of service. Add a hardened reverse
proxy, request timeouts, rate limits, identities, transport security, payload scrubbing and retention
policy before production. Do not expose the reference worker unprotected to a public network.

## Sensitive data

Operational events omit prompts/pixels/model text. The SQLite request/receipt journal and recorded
load plan DO contain source payloads and results. They are private evidence, not safe-to-publish
telemetry. Main database permissions are restricted, but encrypt disks/backups and set restrictive
parent-directory permissions. The runtime does not encrypt SQLite or implement tenant data deletion.
Do not commit `.env`, credential values, private images, licensed assets, or real runs.

The producer is trusted to declare all evidence it consumed. Type checks cannot detect an arbitrary
Python plugin reading undeclared files, nor prove a VLM interpretation is correct.

## Unknown backend work

HTTP cancellation/timeout is not confirmation that remote compute stopped. On ambiguous termination
the pool is quarantined, reservations remain held, and restart does not replay work. Inspect the actual
worker/server and confirm termination or restart before release. A restarted coordinator creates a new
clock epoch; clients must remap clocks and reopen/advance sessions.

```python
# Run offline after stopping the coordinator; Store's lock prevents concurrent writers.
from agmina_runtime.store import Store
s = Store("runs/campaign/ledger.sqlite", campaign="THE_SAME_CAMPAIGN",
          max_attempts=THE_EXISTING_CAP, max_microusd=THE_EXISTING_CAP_MICROUSD)
s.reconcile("local", "job-id", actual_microusd=ACTUAL_CHARGE,
            evidence="operator-billing-receipt-reference", now_ns=MONOTONIC_NOW)
s.release_pool("pool-id", "operator-worker-termination-receipt", MONOTONIC_NOW)
s.close()
```

Do not reconcile zero merely because a client saw an error. Unknown usage/cost remains unknown. Paid
rates are explicit configuration; prices and API/model support are never hard-coded as current facts.
A reservation is an estimated admission charge, not a guaranteed invoice cap. Use provider-side caps.
Local transport with no provider bill does not mean zero GPU rental/energy cost; those metrics are null.

`Store.extend_budget()` requires a nondecreasing cumulative ceiling and approval reference. It does
not reset attempts or unresolved holds. Update the runtime config to the identical new caps afterward.
A reference is an operator audit record, not automated verification of user authorization.

## Robot and workflow authority

A consumed result is not a valid robot action, emergency-stop signal, verified task result, or approval
to modify a system of record. The consumer must recheck after network delivery. Keep the native
execution gate and application-level authorization. Do not stream partial JSON to actuators.

Do not use this prototype to control weapons, autonomous driving, or safety-critical processes.
No real robot control has been tested by this delivery.
