"""Single-writer, asyncio inference coordinator. This module cannot actuate a robot."""
from __future__ import annotations

import asyncio
from pathlib import Path

from .backends import BackendFailure, HttpBackend, MockBackend
from .cache import HistoricalCache
from .clocks import Clock
from .config import RuntimeConfig
from .contracts import Job, JobState, Prediction, Receipt, Session, Usage, fingerprint
from .scheduling import Candidate, choose_endpoint, rank
from .store import Store


class Runtime:
    def __init__(self, config: RuntimeConfig, database: str | Path, *, clock=None,
                 allow_network=False, backends=None, transport=None):
        config = RuntimeConfig.model_validate_json(config.model_dump_json())
        self.config, self.clock = config, clock or Clock()
        self.models = {m.alias: m for m in config.models}
        self.endpoints = {e.id: e for e in config.endpoints}
        self.pools = {p.id: p.slots for p in config.pools}
        self.store = Store(database, campaign=config.campaign, max_attempts=config.max_attempts,
                           max_microusd=config.max_microusd)
        try:
            self.store.bind_tenant(config.tenant)
            self.store.recover(config.tenant, self.clock.now_ns())
        except Exception:
            self.store.close()
            raise
        self.store.event(self.clock.now_ns(), "coordinator_started", clock_id=self.clock.id,
                         config_fingerprint=fingerprint(config), native_actions_enabled=False)
        self.cache = HistoricalCache(config.cache_entries, config.cache_bytes, config.cache_ttl_ns)
        self.pool_use, self.endpoint_use = {}, {}
        self.http = HttpBackend(self.clock, allow_network=allow_network, transport=transport)
        self.mock = MockBackend(self.clock)
        self.backends = backends or {}
        self.running: dict[str, asyncio.Task] = {}
        self._loop_task = None
        self.closed = False
        self.allow_network = allow_network or transport is not None

    def open_session(self, session_id: str, task_revision: str) -> Session:
        now = self.clock.now_ns()
        try:
            old = self.store.session(self.config.tenant, session_id)
        except KeyError:
            old = None
        if old and old.state == "active":
            raise PermissionError("Session already active; advance it explicitly")
        s = Session(tenant=self.config.tenant, id=session_id, epoch=0 if old is None else old.epoch + 1,
                    task_revision=task_revision, clock_id=self.clock.id, updated_ns=now)
        self.store.put_session(s)
        self.store.event(now, "session_opened", session_id=s.id, epoch=s.epoch)
        return s

    def advance_session(self, sid: str, *, expected_epoch: int, task_revision: str,
                        close=False) -> Session:
        old = self.store.session(self.config.tenant, sid)
        if old.epoch != expected_epoch or old.clock_id != self.clock.id or old.state != "active":
            raise PermissionError("Session compare-and-swap failed")
        s = Session(tenant=old.tenant, id=old.id, epoch=old.epoch+1, task_revision=task_revision,
                    clock_id=self.clock.id, updated_ns=self.clock.now_ns(), state="closed" if close else "active")
        self.store.put_session(s)
        self.store.event(self.clock.now_ns(), "session_advanced", session_id=s.id, epoch=s.epoch)
        self._expire()
        return s

    def heartbeat(self, sid: str, *, expected_epoch: int, buffer_until_ns: int | None):
        old = self.store.session(self.config.tenant, sid)
        now = self.clock.now_ns()
        if old.epoch != expected_epoch or old.clock_id != self.clock.id or old.state != "active":
            raise PermissionError("Stale heartbeat")
        if buffer_until_ns is not None and not now <= buffer_until_ns <= now + 60_000_000_000:
            raise ValueError("Advisory buffer time must be within 60 seconds")
        s = Session(**{**old.model_dump(), "updated_ns": now, "buffer_until_ns": buffer_until_ns})
        self.store.put_session(s)
        self.store.event(now, "buffer_observed", session_id=sid, epoch=expected_epoch,
                         buffer_until_ns=buffer_until_ns)
        return s

    def submit(self, job: Job) -> Receipt:
        job = Job.model_validate_json(job.model_dump_json())
        if self.closed or job.tenant != self.config.tenant:
            raise PermissionError("Closed runtime or foreign tenant")
        try:
            original, receipt = self.store.job(job.tenant, job.id)
        except KeyError:
            original = None
        if original is not None:
            if original.fingerprint != job.fingerprint:
                raise ValueError("Idempotency ID reused for different work")
            return receipt
        if job.model not in self.models:
            raise ValueError("Unregistered model contract")
        if len(self.store.jobs(job.tenant)) >= self.config.max_jobs:
            raise PermissionError("Journal job admission capacity reached; retain/archive this campaign")
        s = self.store.session(job.tenant, job.session_id)
        now = self.clock.now_ns()
        reason = job.invalid_reason(s, now, self.clock.id)
        for dep in job.dependencies:
            parent, _ = self.store.job(job.tenant, dep)
            if (parent.session_id, parent.epoch, parent.task_revision) != (
                job.session_id, job.epoch, job.task_revision
            ):
                raise PermissionError("Dependency crosses task/session generation")
            if not {o.source_fingerprint for o in parent.observations} <= {
                o.source_fingerprint for o in job.observations
            }:
                raise PermissionError("Dependency source lineage omitted")
        superseded = []
        if job.replace_key and reason is None:
            for prev, r in self.store.jobs(job.tenant, (JobState.QUEUED,)):
                if (prev.session_id, prev.epoch, prev.task_revision, prev.replace_key, prev.model,
                    prev.operation) == (job.session_id, job.epoch, job.task_revision, job.replace_key,
                                        job.model, job.operation):
                    # Do not replace a newer semantic snapshot with late old work.
                    if prev.snapshot_ns >= job.snapshot_ns:
                        reason = "superseded_by_newer_snapshot"
                    elif not any(prev.id in child.dependencies for child, _ in
                                 self.store.jobs(job.tenant, (JobState.QUEUED, JobState.RUNNING))):
                        superseded.append((prev, r))
        if len(self.store.jobs(job.tenant, (JobState.QUEUED,))) - len(superseded) >= self.config.max_queue:
            reason = reason or "queue_capacity"
        eps = [e for e in self.config.endpoints if e.model == job.model and e.site in job.allowed_sites]
        if not eps:
            reason = reason or "no_allowed_endpoint"
        if eps and not self.allow_network and all(e.kind != "mock" and e.id not in self.backends for e in eps):
            reason = reason or "network_not_authorized"
        receipt = Receipt(job_id=job.id, request_fingerprint=job.fingerprint,
                          state=JobState.REJECTED if reason else JobState.QUEUED,
                          reason=reason, submitted_ns=now)
        self.store.add_job(job, receipt)
        if not reason:
            for prev, old_receipt in superseded:
                self._set(prev, old_receipt, JobState.SUPERSEDED, "explicit_latest_only_replacement")
        self.store.event(now, "submitted", job_id=job.id, session_id=job.session_id,
                         model=job.model, workload=job.workload, state=receipt.state.value,
                         evidence_count=len(job.observations), request_fingerprint=job.fingerprint,
                         reason=reason)
        return receipt

    def _set(self, job, receipt, state, reason):
        r = receipt.model_copy(update={"state": state, "reason": reason})
        self.store.receipt(job.tenant, r)
        self.store.event(self.clock.now_ns(), "job_state", job_id=job.id, state=state.value, reason=reason)
        return r

    def _expire(self):
        now = self.clock.now_ns()
        for job, r in self.store.jobs(self.config.tenant, (JobState.QUEUED, JobState.RUNNING)):
            s = self.store.session(job.tenant, job.session_id)
            reason = job.invalid_reason(s, now, self.clock.id)
            if reason:
                self._set(job, r, JobState.EXPIRED if "expired" in reason else JobState.STALE, reason)
                # In-flight work retains its slot until completion or quarantined timeout.

    def tick(self):
        if self.closed:
            return
        self._expire()
        now = self.clock.now_ns()
        ready = []
        for job, r in self.store.jobs(self.config.tenant, (JobState.QUEUED,)):
            dep_states = [self.store.job(job.tenant, d)[1].state for d in job.dependencies]
            if any(x not in {JobState.QUEUED, JobState.RUNNING, JobState.SUCCEEDED, JobState.CONSUMED}
                   for x in dep_states):
                self._set(job, r, JobState.REJECTED, "dependency_failed")
                continue
            if any(x not in {JobState.SUCCEEDED, JobState.CONSUMED} for x in dep_states):
                continue
            s = self.store.session(job.tenant, job.session_id)
            eps = [e for e in self.config.endpoints if e.model == job.model]
            estimate = min(e.estimate_ns for e in eps if e.site in job.allowed_sites)
            c = Candidate(job.id, r.submitted_ns, job.latest_ns(s), estimate, job.priority)
            ready.append((rank(c, now, self.config.scheduler), job, r, s))
        for _, job, r, session in sorted(ready, key=lambda x: x[0]):
            now = self.clock.now_ns()
            session = self.store.session(job.tenant, job.session_id)
            reason = job.invalid_reason(session, now, self.clock.id)
            if reason:
                self._set(job, r, JobState.EXPIRED if "expired" in reason else JobState.STALE, reason)
                continue
            cache_key = self.cache.key(job, self.models[job.model].fingerprint)
            hit = self.cache.get(cache_key, now)
            if hit is not None:
                payload, computed_ns = hit
                done = r.model_copy(update={"state": JobState.SUCCEEDED, "prediction_json": payload,
                                           "completed_ns": now, "computed_ns": computed_ns,
                                           "cache_hit": True, "usage": Usage(cost_microusd=0)})
                self.store.receipt(job.tenant, done)
                self.store.event(now, "cache_hit", job_id=job.id, computed_ns=computed_ns)
                continue
            eps = [e for e in self.config.endpoints if e.model == job.model]
            endpoint = choose_endpoint(eps, now_ns=now, latest_ns=job.latest_ns(session),
                                       site_allowlist=job.allowed_sites, pool_slots=self.pools,
                                       pool_use=self.pool_use, endpoint_use=self.endpoint_use,
                                       quarantined=self.store.quarantined(), placement=self.config.placement)
            if endpoint is None:
                continue
            try:
                self.store.reserve(job, endpoint, now)
            except PermissionError:
                self._set(job, r, JobState.REJECTED, "attempt_or_cost_ceiling")
                continue
            running = r.model_copy(update={"state": JobState.RUNNING, "endpoint": endpoint.id,
                                           "started_ns": now})
            self.store.receipt(job.tenant, running)
            self.pool_use[endpoint.pool] = self.pool_use.get(endpoint.pool, 0) + 1
            self.endpoint_use[endpoint.id] = self.endpoint_use.get(endpoint.id, 0) + 1
            self.store.event(now, "dispatched", job_id=job.id, endpoint=endpoint.id, pool=endpoint.pool,
                             estimate_ns=endpoint.estimate_ns, latest_ns=job.latest_ns(session))
            task = asyncio.create_task(self._run(job, endpoint, cache_key))
            self.running[job.id] = task
            task.add_done_callback(lambda _, jid=job.id: self.running.pop(jid, None))

    async def _run(self, job, endpoint, cache_key):
        backend = self.backends.get(endpoint.id, self.mock if endpoint.kind == "mock" else self.http)
        try:
            current = self.store.session(job.tenant, job.session_id)
            reason = job.invalid_reason(current, self.clock.now_ns(), self.clock.id)
            if reason:
                self.store.settle(job, Usage(cost_microusd=0))
                _, old = self.store.job(job.tenant, job.id)
                self._set(job, old, JobState.EXPIRED if "expired" in reason else JobState.STALE, reason)
                self.store.event(self.clock.now_ns(), "not_sent_after_dispatch_check", job_id=job.id)
                return
            result = await asyncio.wait_for(backend.infer(job, endpoint), timeout=endpoint.timeout_s)
            if not isinstance(result, Prediction):
                raise BackendFailure("invalid_prediction_contract", termination_known=True)
            now = self.clock.now_ns()
            _, old = self.store.job(job.tenant, job.id)
            if result.first_content_ns is not None and not old.started_ns <= result.first_content_ns <= now:
                raise BackendFailure("invalid_first_content_clock", termination_known=True)
            self.store.settle(job, result.usage)
            s = self.store.session(job.tenant, job.session_id)
            reason = job.invalid_reason(s, now, self.clock.id)
            if old.state != JobState.RUNNING:
                state, reason = old.state, old.reason
            elif reason:
                state = JobState.EXPIRED if "expired" in reason else JobState.STALE
            else:
                state = JobState.SUCCEEDED
            done = old.model_copy(update={"state": state, "reason": reason, "completed_ns": now,
                                          "computed_ns": now, "prediction_json": result.payload_json,
                                          "usage": result.usage, "first_content_ns": result.first_content_ns,
                                          "provider_request_id": result.provider_request_id})
            self.store.receipt(job.tenant, done)
            if state == JobState.SUCCEEDED:
                self.cache.put(cache_key, result.payload_json, now)
            self.store.event(now, "completed", job_id=job.id, state=state.value,
                             queue_ns=old.started_ns-old.submitted_ns,
                             backend_roundtrip_ns=now-old.started_ns,
                             first_content_ns=result.first_content_ns,
                             deadline_met=state == JobState.SUCCEEDED,
                             cost_microusd=result.usage.cost_microusd)
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            known = isinstance(exc, BackendFailure) and exc.termination_known
            not_sent = isinstance(exc, BackendFailure) and exc.not_sent
            code = exc.code if isinstance(exc, BackendFailure) else type(exc).__name__
            self.store.settle(job, Usage(cost_microusd=0) if not_sent else None)
            if not_sent:
                self.store.event(self.clock.now_ns(), "backend_not_sent", job_id=job.id, reason=code)
            _, old = self.store.job(job.tenant, job.id)
            state = JobState.FAILED if known else JobState.UNKNOWN
            if old.state != JobState.RUNNING:
                state = old.state
            self._set(job, old.model_copy(update={"completed_ns": self.clock.now_ns()}), state, code)
            if not known:
                self.store.quarantine(endpoint.pool, "unconfirmed_backend_termination")
                self.store.event(self.clock.now_ns(), "pool_quarantined", pool=endpoint.pool, job_id=job.id)
        finally:
            self.pool_use[endpoint.pool] -= 1
            self.endpoint_use[endpoint.id] -= 1

    def cancel(self, job_id: str):
        job, r = self.store.job(self.config.tenant, job_id)
        if r.state in {JobState.QUEUED, JobState.RUNNING, JobState.SUCCEEDED}:
            return self._set(job, r, JobState.CANCELLED, "consumer_cancelled")
        return r

    def result(self, job_id: str) -> Receipt:
        return self.store.job(self.config.tenant, job_id)[1]

    def consume(self, job_id: str, *, consumer_id: str) -> Receipt:
        job, r = self.store.job(self.config.tenant, job_id)
        s = self.store.session(job.tenant, job.session_id)
        reason = job.invalid_reason(s, self.clock.now_ns(), self.clock.id)
        if reason:
            raise PermissionError("Consumption rejected: " + reason)
        if r.state not in {JobState.SUCCEEDED, JobState.CONSUMED}:
            raise PermissionError("No acceptable result")
        if r.consumed_by is not None:
            if r.consumed_by != consumer_id:
                raise PermissionError("Result already claimed by another consumer")
            return r
        # Construct rather than bypass validation for caller-controlled consumer ID.
        done = Receipt(**{**r.model_dump(), "state": JobState.CONSUMED, "consumed_by": consumer_id,
                          "consumed_ns": self.clock.now_ns()})
        self.store.receipt(job.tenant, done)
        self.store.event(self.clock.now_ns(), "consumed", job_id=job.id, consumer_id=consumer_id,
                         max_current_age_ns=max((self.clock.now_ns()-o.capture_ns+o.uncertainty_ns
                                                for o in job.observations if o.role == "current"), default=None),
                         action_authorized=False)
        return done

    def record_outcome(self, job_id: str, *, consumer_id: str, outcome: str, evidence_ref: str):
        r = self.result(job_id)
        if r.consumed_by != consumer_id or outcome not in {"accepted", "executed", "rejected", "unknown"}:
            raise PermissionError("Outcome requires the claiming consumer and declared outcome type")
        if not evidence_ref or len(evidence_ref) > 256:
            raise ValueError("External evidence reference required")
        self.store.event(self.clock.now_ns(), "consumer_reported_outcome", job_id=job_id,
                         outcome=outcome, evidence_ref=evidence_ref, independently_verified=False)

    async def wait(self, job_id, *, timeout_s=30.0):
        start = asyncio.get_running_loop().time()
        while True:
            self.tick()
            job, r = self.store.job(self.config.tenant, job_id)
            if r.state not in {JobState.QUEUED, JobState.RUNNING}:
                return r
            if r.state == JobState.QUEUED:
                eligible = [e for e in self.config.endpoints
                            if e.model == job.model and e.site in job.allowed_sites]
                if eligible and all(e.pool in self.store.quarantined() for e in eligible):
                    raise RuntimeError("Job blocked: all eligible endpoint pools are quarantined")
            if asyncio.get_running_loop().time()-start > timeout_s:
                raise TimeoutError("Client wait elapsed; work may still run, call cancel explicitly")
            await asyncio.sleep(.001)

    async def serve_loop(self):
        while not self.closed:
            self.tick()
            await asyncio.sleep(.002)

    async def close(self, *, drain_s=1.0):
        if self.closed:
            return
        self.closed = True
        for job, r in self.store.jobs(self.config.tenant, (JobState.QUEUED,)):
            self._set(job, r, JobState.CANCELLED, "coordinator_shutdown")
        tasks = list(self.running.values())
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=drain_s)
            for task in pending:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        await self.http.close()
        self.store.event(self.clock.now_ns(), "coordinator_stopped", unconfirmed_pools=list(self.store.quarantined()))
        self.store.close()
