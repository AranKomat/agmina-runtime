import asyncio

import pytest

from agmina_runtime.clocks import ManualClock
from agmina_runtime.config import RuntimeConfig
from agmina_runtime.contracts import JobState, Prediction, Usage
from agmina_runtime.runtime import Runtime
from agmina_runtime.store import Store
from conftest import make_job


async def test_unknown_timeout_quarantines_pool(cfg, tmp_path, clock):
    class Hung:
        async def infer(self, *args):
            await asyncio.sleep(10)
    e = cfg.endpoints[0].model_copy(update={"timeout_s":.01})
    cfg = RuntimeConfig(**{**cfg.model_dump(),"endpoints":(e,)})
    r = Runtime(cfg,tmp_path/"db",clock=clock,backends={e.id:Hung()})
    s = r.open_session("s","t")
    r.submit(make_job(s,clock.now_ns()))
    assert (await r.wait("j1")).state == JobState.UNKNOWN
    assert r.store.quarantined() == {"gpu"}
    assert r.store.budget()["unknown_attempts"] == 1
    r.submit(make_job(s,clock.now_ns(),id="next"))
    r.tick()
    assert r.result("next").state == JobState.QUEUED
    with pytest.raises(ValueError):
        r.store.release_pool("gpu","",clock.now_ns())
    r.store.release_pool("gpu","operator-worker-restart-receipt",clock.now_ns())
    await r.close()


async def test_budget_overrun_freezes_new_dispatch(cfg, tmp_path, clock):
    class Expensive:
        async def infer(self,*args):
            return Prediction(payload_json='{"ok":true}',usage=Usage(cost_microusd=20))
    e = cfg.endpoints[0].model_copy(update={"reserve_microusd":5})
    cfg = RuntimeConfig(**{**cfg.model_dump(),"endpoints":(e,),"max_microusd":10})
    r = Runtime(cfg,tmp_path/"db",clock=clock,backends={e.id:Expensive()})
    s = r.open_session("s","t")
    r.submit(make_job(s,clock.now_ns()))
    await r.wait("j1")
    assert r.store.budget()["over_ceiling"]
    r.submit(make_job(s,clock.now_ns(),id="next"))
    assert (await r.wait("next")).state == JobState.REJECTED
    assert r.store.budget()["attempts"] == 1
    await r.close()


async def test_missing_usage_retains_reservation(cfg, tmp_path, clock):
    class Missing:
        async def infer(self,*args):
            return Prediction(payload_json='{"ok":true}')
    e = cfg.endpoints[0].model_copy(update={"reserve_microusd":6})
    cfg = RuntimeConfig(**{**cfg.model_dump(),"endpoints":(e,),"max_microusd":10})
    r = Runtime(cfg,tmp_path/"db",clock=clock,backends={e.id:Missing()})
    s = r.open_session("s","t")
    r.submit(make_job(s,clock.now_ns()))
    await r.wait("j1")
    assert r.store.budget()["held_microusd"] == 6
    r.submit(make_job(s,clock.now_ns(),id="next"))
    assert (await r.wait("next")).state == JobState.REJECTED
    r.store.reconcile(cfg.tenant,"j1",3,"billing-receipt-sha",clock.now_ns())
    assert r.store.budget()["held_microusd"] == 0
    assert r.store.budget()["known_microusd"] == 3
    with pytest.raises(ValueError):
        r.store.reconcile(cfg.tenant,"j1",0,"overwrite",clock.now_ns())
    await r.close()


def test_single_coordinator_lock(tmp_path):
    path = tmp_path/"db"
    s = Store(path,campaign="x",max_attempts=1,max_microusd=10)
    with pytest.raises(RuntimeError):
        Store(path,campaign="x",max_attempts=1,max_microusd=10)
    s.close()
    s2 = Store(path,campaign="x",max_attempts=1,max_microusd=10)
    s2.close()


def test_caps_cannot_silently_reset(tmp_path):
    path = tmp_path/"db"
    s = Store(path,campaign="x",max_attempts=1,max_microusd=10)
    s.close()
    with pytest.raises(ValueError):
        Store(path,campaign="new-campaign",max_attempts=100,max_microusd=100)


async def test_restart_does_not_reissue_work(cfg,tmp_path,clock):
    path=tmp_path/"db"
    r=Runtime(cfg,path,clock=clock)
    s=r.open_session("s","t")
    a=make_job(s,clock.now_ns())
    r.submit(a)
    # Simulate crash between persistent dispatch intent and backend completion.
    r.store.reserve(a,cfg.endpoints[0],clock.now_ns())
    receipt=r.result(a.id).model_copy(update={"state":JobState.RUNNING,"endpoint":"worker",
                                           "started_ns":clock.now_ns()})
    r.store.receipt(cfg.tenant,receipt)
    await r.http.close()
    r.store.close()
    r.closed=True
    new=Runtime(cfg,path,clock=ManualClock(clock.now_ns()+1,"new-clock"))
    assert new.result(a.id).state == JobState.UNKNOWN
    assert new.store.quarantined() == {"gpu"}
    assert new.store.budget()["attempts"] == 1
    assert new.open_session("s","t").epoch == 1
    with pytest.raises(PermissionError):
        new.consume(a.id,consumer_id="reader")
    assert not new.mock.calls
    await new.close()


async def test_restart_queued_cancelled(cfg,tmp_path,clock):
    path=tmp_path/"db"
    r=Runtime(cfg,path,clock=clock)
    s=r.open_session("s","t")
    r.submit(make_job(s,clock.now_ns()))
    await r.http.close()
    r.store.close()
    r.closed=True
    new=Runtime(cfg,path,clock=ManualClock(clock.now_ns()+1,"new-clock"))
    assert new.result("j1").state == JobState.CANCELLED
    assert new.store.budget()["attempts"] == 0
    await new.close()


async def test_attempt_cap(cfg,tmp_path,clock):
    cfg=RuntimeConfig(**{**cfg.model_dump(),"max_attempts":1})
    r=Runtime(cfg,tmp_path/"db",clock=clock)
    s=r.open_session("s","t")
    for i in range(2):
        r.submit(make_job(s,clock.now_ns(),id=f"j{i}"))
        await r.wait(f"j{i}")
    assert r.result("j1").state == JobState.REJECTED
    await r.close()


async def test_shutdown_unknown_is_retained(cfg,tmp_path,clock):
    r=Runtime(cfg,tmp_path/"db",clock=clock)
    s=r.open_session("s","t")
    r.submit(make_job(s,clock.now_ns(),payload_json='{"fixture_delay_s":1}'))
    r.tick()
    await asyncio.sleep(.001)
    await r.close(drain_s=.001)
    new=Runtime(cfg,tmp_path/"db",clock=ManualClock(clock.now_ns()+1,"new-clock"))
    assert new.result("j1").state == JobState.UNKNOWN
    assert "gpu" in new.store.quarantined()
    await new.close()


def test_budget_extension_preserves_usage(tmp_path):
    store=Store(tmp_path/"db",campaign="x",max_attempts=1,max_microusd=10)
    with pytest.raises(ValueError):
        store.extend_budget(max_attempts=2,max_microusd=20,approval_ref="",now_ns=1)
    store.extend_budget(max_attempts=2,max_microusd=20,approval_ref="operator-approval-ref",now_ns=1)
    assert store.budget()["max_attempts"]==2 and store.budget()["attempts"]==0
    store.close()
    reopened=Store(tmp_path/"db",campaign="x",max_attempts=2,max_microusd=20)
    assert len(reopened.export_events())==1
    reopened.close()


async def test_missing_credentials_release_quote_but_preserve_attempt(cfg, tmp_path, clock, monkeypatch):
    from agmina_runtime.config import Endpoint
    monkeypatch.delenv("MISSING_PAID_TOKEN", raising=False)
    ep = Endpoint(id="paid", model="model", pool="gpu", site="cloud", kind="chat",
                  url="https://example.test/v1/chat/completions", credential_env="MISSING_PAID_TOKEN",
                  externally_billed=True, reserve_microusd=10, service_p95_ns=1_000_000, margin_ns=0)
    config = RuntimeConfig(**{**cfg.model_dump(), "endpoints": (ep,), "max_microusd": 10})
    r = Runtime(config, tmp_path/"db", clock=clock, allow_network=True)
    s = r.open_session("s", "t")
    r.submit(make_job(s, clock.now_ns(), payload_json='{"messages":[{"role":"user","content":"x"}]}'))
    assert (await r.wait("j1")).state == JobState.FAILED
    assert not r.store.quarantined()
    assert r.store.budget()["held_microusd"] == 0
    assert r.store.budget()["attempts"] == 1
    await r.close()


@pytest.mark.parametrize("receipt_state", [JobState.QUEUED, JobState.CANCELLED, JobState.STALE])
async def test_crash_with_terminal_receipt_and_unconfirmed_compute(cfg, tmp_path, clock, receipt_state):
    r = Runtime(cfg, tmp_path/"db", clock=clock)
    session = r.open_session("s", "t")
    job = make_job(session, clock.now_ns())
    r.submit(job)
    r.store.reserve(job, cfg.endpoints[0], clock.now_ns())
    r.store.receipt(cfg.tenant, r.result(job.id).model_copy(update={"state":receipt_state}))
    await r.http.close()
    r.store.close()
    r.closed = True
    restarted = Runtime(cfg, tmp_path/"db", clock=ManualClock(clock.now_ns()+1, "next-clock"))
    assert restarted.store.quarantined() == {"gpu"}
    assert restarted.store.budget()["unknown_attempts"] == 1
    assert restarted.store.budget()["attempts"] == 1
    assert not restarted.mock.calls
    await restarted.close()


async def test_runtime_tenant_is_pinned_to_ledger(cfg, tmp_path, clock):
    r = Runtime(cfg, tmp_path/"db", clock=clock)
    await r.close()
    other = RuntimeConfig(**{**cfg.model_dump(), "tenant":"another"})
    with pytest.raises(PermissionError, match="tenant"):
        Runtime(other, tmp_path/"db", clock=clock)
