"""Paced arrival driver for real endpoints or test doubles.

This is inference load replay. It does not model closed-loop policy quality or
claim live camera capture/decode time. Source clock advances during inference.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from pydantic import Field, model_validator

from .config import RuntimeConfig
from .contracts import Contract, Job, JobState, Name, Observation, ResultKind, Sha, canonical
from .runtime import Runtime
from .telemetry import summarize


class LoadItem(Contract):
    id: Name
    session: Name
    model: Name
    workload: str = Field(pattern=r"^(policy|semantic|segmentation|mapping|query)$")
    release_ms: int = Field(ge=0, le=3_600_000)
    deadline_after_ms: int = Field(gt=0, le=300000)
    profile_capture_lag_ms: int = Field(default=0, ge=0, le=300000)
    result_kind: ResultKind = ResultKind.HISTORICAL
    max_age_ms: int | None = Field(default=None, gt=0, le=300000)
    evidence_hashes: tuple[Sha, ...] = Field(min_length=1, max_length=32)
    payload_json: str
    @model_validator(mode="after")
    def current_bound(self):
        from .contracts import strict_json
        strict_json(self.payload_json)
        if self.result_kind != ResultKind.HISTORICAL and self.max_age_ms is None:
            raise ValueError("Current load jobs require an age limit")
        return self


class LoadPlan(Contract):
    provenance: str = Field(min_length=1, max_length=2048)
    synthetic_inputs: bool
    jobs: tuple[LoadItem, ...] = Field(min_length=1, max_length=2000)
    @model_validator(mode="after")
    def unique(self):
        if len({j.id for j in self.jobs}) != len(self.jobs):
            raise ValueError("Load IDs must be unique")
        return self


async def run_load(config: RuntimeConfig, plan: LoadPlan, out: Path, *, allow_network=False, backends=None):
    out.mkdir(parents=True, exist_ok=False)
    runtime = Runtime(config, out/"ledger.sqlite", allow_network=allow_network, backends=backends)
    loop = asyncio.create_task(runtime.serve_loop())
    collectors = []
    try:
        sessions = {sid:runtime.open_session(sid,"load-v1") for sid in {x.session for x in plan.jobs}}
        base = runtime.clock.now_ns()
        release_lags = []
        async def collect(jid, deadline):
            while True:
                r = runtime.result(jid)
                if r.state not in {JobState.QUEUED,JobState.RUNNING}:
                    if r.state == JobState.SUCCEEDED:
                        try:
                            runtime.consume(jid,consumer_id="load-reader")
                        except PermissionError:
                            runtime.store.event(runtime.clock.now_ns(),"load_consume_expired",job_id=jid)
                    return
                if runtime.clock.now_ns() >= deadline+1_000_000_000:
                    runtime.cancel(jid)
                    return
                await asyncio.sleep(.002)
        for item in sorted(plan.jobs,key=lambda i:(i.release_ms,i.id)):
            release = base+item.release_ms*1_000_000
            await asyncio.sleep(max(0,(release-runtime.clock.now_ns())/1e9))
            now=runtime.clock.now_ns()
            release_lags.append(now-release)
            session=sessions[item.session]
            capture=max(0,release-item.profile_capture_lag_ms*1_000_000)
            observations=tuple(Observation(id=f"{item.id}-o{k}",source=item.session,sequence=k,
                sha256=h,capture_ns=capture,available_ns=release,source_time="load-replay")
                for k,h in enumerate(item.evidence_hashes))
            job=Job(id=item.id,tenant=config.tenant,session_id=session.id,epoch=session.epoch,
                task_revision=session.task_revision,clock_id=session.clock_id,model=item.model,
                operation="paced_load",workload=item.workload,result_kind=item.result_kind,
                observations=observations,snapshot_ns=release,deadline_ns=release+item.deadline_after_ms*1_000_000,
                max_age_ns=item.max_age_ms*1_000_000 if item.max_age_ms else None,
                payload_json=item.payload_json)
            runtime.submit(job)
            collectors.append(asyncio.create_task(collect(job.id,job.deadline_ns)))
        await asyncio.gather(*collectors)
        # Finish known backend attempts before final cost report where possible.
        pending=list(runtime.running.values())
        if pending:
            await asyncio.wait(pending,timeout=max(e.timeout_s for e in config.endpoints)+.1)
        report=summarize(runtime)
        report.update(kind="paced_inference_load",synthetic_inputs=plan.synthetic_inputs,
                      provenance=plan.provenance,source_decode_included=False,
                      release_lag_max_ns=max(release_lags),source_clock_continues=True)
        with (out/"report.json").open("x") as f:
            json.dump(report,f,indent=2)
        with (out/"trace.jsonl").open("x") as f:
            for event in runtime.store.export_events():
                f.write(canonical(event)+"\n")
        with (out/"plan.json").open("x") as f:
            f.write(plan.model_dump_json(indent=2))
        with (out/"config.json").open("x") as f:
            f.write(config.model_dump_json(indent=2))
        return report
    finally:
        loop.cancel()
        for task in collectors:
            if not task.done():
                task.cancel()
        await asyncio.gather(loop,*collectors,return_exceptions=True)
        await runtime.close()
