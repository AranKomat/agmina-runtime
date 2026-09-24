import hashlib

import pytest

from agmina_runtime.clocks import ManualClock
from agmina_runtime.config import Endpoint, Pool, RuntimeConfig
from agmina_runtime.contracts import Job, ModelContract, Observation, ResultKind, canonical
from agmina_runtime.runtime import Runtime


@pytest.fixture
def cfg():
    return RuntimeConfig(pools=(Pool(id="gpu"),),
        models=(ModelContract(alias="model", weights="weight-sha", preprocessing="prep-1",
                              output_schema="json-1", sampling="deterministic-1"),),
        endpoints=(Endpoint(id="worker", model="model", pool="gpu", site="local", kind="mock",
                            service_p95_ns=1_000_000, margin_ns=0),), max_attempts=100)


@pytest.fixture
def clock():
    return ManualClock(10_000_000_000)


def make_job(session, now, **changes):
    raw = b"test image bytes"
    job_id = changes.pop("id", "j1")
    base = dict(id=job_id, tenant=session.tenant, session_id=session.id, epoch=session.epoch,
        task_revision=session.task_revision, clock_id=session.clock_id, model="model", operation="test",
        workload="semantic", result_kind=ResultKind.CURRENT,
        observations=(Observation(id="obs-"+job_id, source="cam", sequence=0, sha256=hashlib.sha256(raw).hexdigest(),
            capture_ns=now, available_ns=now),), snapshot_ns=now, deadline_ns=now+1_000_000_000,
        max_age_ns=1_000_000_000, payload_json=canonical({"fixture_delay_s": .001}))
    base.update(changes)
    return Job(**base)


@pytest.fixture
def runtime(tmp_path, cfg, clock):
    r = Runtime(cfg, tmp_path/"db.sqlite", clock=clock)
    yield r
    if not r.closed:
        # Tests with active HTTP/coroutines explicitly await close themselves.
        r.store.close()
        r.closed = True


@pytest.fixture
def session(runtime):
    return runtime.open_session("s", "task-v1")
