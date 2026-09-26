import asyncio

import pytest

from agmina_runtime.config import Endpoint, Pool, RuntimeConfig
from agmina_runtime.contracts import JobState, ResultKind
from agmina_runtime.runtime import Runtime
from conftest import make_job


async def test_success_and_consumer_fence(runtime, session, clock):
    j = make_job(session, clock.now_ns())
    runtime.submit(j)
    assert (await runtime.wait(j.id)).state == JobState.SUCCEEDED
    r = runtime.consume(j.id, consumer_id="reader")
    assert runtime.consume(j.id, consumer_id="reader") == r
    with pytest.raises(PermissionError):
        runtime.consume(j.id, consumer_id="other")
    runtime.advance_session(session.id, expected_epoch=session.epoch, task_revision="task-v2")
    with pytest.raises(PermissionError):
        runtime.consume(j.id, consumer_id="reader")
    await runtime.close()


async def test_wait_fails_fast_when_all_eligible_pools_are_quarantined(runtime, session, clock):
    runtime.store.quarantine("gpu", "test_unconfirmed_backend_termination")
    job = make_job(session, clock.now_ns())
    assert runtime.submit(job).state == JobState.QUEUED
    with pytest.raises(RuntimeError, match="eligible endpoint pools are quarantined"):
        await runtime.wait(job.id, timeout_s=1)
    assert runtime.result(job.id).state == JobState.QUEUED
    await runtime.close()


async def test_fresh_on_complete_stale_on_consume(runtime, session, clock):
    j = make_job(session, clock.now_ns())
    runtime.submit(j)
    await runtime.wait(j.id)
    clock.advance_to(j.deadline_ns)
    with pytest.raises(PermissionError):
        runtime.consume(j.id, consumer_id="reader")
    await runtime.close()


async def test_idempotent(runtime, session, clock):
    j = make_job(session, clock.now_ns())
    runtime.submit(j)
    runtime.submit(j)
    await runtime.wait(j.id)
    runtime.submit(j)
    assert runtime.mock.calls == [j.id]
    with pytest.raises(ValueError):
        runtime.submit(j.model_copy(update={"payload_json": '{"changed":true}'}))
    await runtime.close()


def test_revalidate_constructed_models(runtime, session, clock):
    j = make_job(session, clock.now_ns()).model_copy(update={"priority": -10})
    with pytest.raises(ValueError):
        runtime.submit(j)


def test_future_and_foreign(runtime, session, clock):
    assert runtime.submit(make_job(session, clock.now_ns()+1)).state == JobState.REJECTED
    with pytest.raises(PermissionError):
        runtime.submit(make_job(session, clock.now_ns(), id="foreign", tenant="other"))


def test_source_id_cannot_mutate(runtime, session, clock):
    j = make_job(session, clock.now_ns())
    runtime.submit(j)
    changed = j.observations[0].model_copy(update={"sha256": "b"*64})
    with pytest.raises(ValueError):
        runtime.submit(make_job(session, clock.now_ns(), id="j2", observations=(changed,)))


def test_latest_replacement_only_when_valid(runtime, session, clock):
    a = make_job(session, clock.now_ns(), replace_key="latest", discardable=True)
    runtime.submit(a)
    future = make_job(session, clock.now_ns()+10, id="future", replace_key="latest", discardable=True)
    assert runtime.submit(future).state == JobState.REJECTED
    assert runtime.result(a.id).state == JobState.QUEUED
    clock.advance_to(clock.now_ns()+20)
    b = make_job(session, clock.now_ns(), id="b", replace_key="latest", discardable=True)
    runtime.submit(b)
    assert runtime.result(a.id).state == JobState.SUPERSEDED
    assert runtime.result(b.id).state == JobState.QUEUED


def test_invalid_observation_cannot_supersede(runtime, session, clock):
    a = make_job(session, clock.now_ns(), replace_key="latest", discardable=True)
    runtime.submit(a)
    clock.advance_to(clock.now_ns()+20)
    bad = a.observations[0].model_copy(update={"capture_ns": clock.now_ns(), "available_ns": clock.now_ns()})
    with pytest.raises(ValueError):
        runtime.submit(make_job(session, clock.now_ns(), id="bad", observations=(bad,),
                                replace_key="latest", discardable=True))
    assert runtime.result(a.id).state == JobState.QUEUED


async def test_cancellation_does_not_free_inflight_slot(runtime, session, clock):
    a = make_job(session, clock.now_ns(), payload_json='{"fixture_delay_s":0.05}')
    runtime.submit(a)
    runtime.tick()
    await asyncio.sleep(.002)
    runtime.cancel(a.id)
    b = make_job(session, clock.now_ns(), id="b")
    runtime.submit(b)
    runtime.tick()
    assert runtime.result(b.id).state == JobState.QUEUED
    assert runtime.pool_use["gpu"] == 1
    await asyncio.sleep(.06)
    await runtime.wait(b.id)
    assert runtime.result(a.id).state == JobState.CANCELLED
    assert runtime.store.budget()["attempts"] == 2
    await runtime.close()


async def test_running_expiration_keeps_receipt_and_usage(runtime, session, clock):
    a = make_job(session, clock.now_ns(), payload_json='{"fixture_delay_s":0.02}')
    runtime.submit(a)
    runtime.tick()
    await asyncio.sleep(.001)
    clock.advance_to(a.deadline_ns)
    runtime.tick()
    assert runtime.result(a.id).state == JobState.EXPIRED
    assert runtime.pool_use["gpu"] == 1
    await asyncio.sleep(.03)
    r = runtime.result(a.id)
    assert r.state == JobState.EXPIRED and r.usage.cost_microusd == 0
    assert runtime.store.budget()["attempts"] == 1
    await runtime.close()


async def test_epoch_advance_inflight(runtime, session, clock):
    a = make_job(session, clock.now_ns(), payload_json='{"fixture_delay_s":0.01}')
    runtime.submit(a)
    runtime.tick()
    runtime.advance_session(session.id, expected_epoch=0, task_revision="new")
    await asyncio.sleep(.02)
    assert runtime.result(a.id).state == JobState.STALE
    with pytest.raises(PermissionError):
        runtime.consume(a.id, consumer_id="x")
    await runtime.close()


def test_stale_heartbeat(runtime, session, clock):
    runtime.advance_session(session.id, expected_epoch=0, task_revision="new")
    with pytest.raises(PermissionError):
        runtime.heartbeat(session.id, expected_epoch=0, buffer_until_ns=clock.now_ns()+100)


async def test_buffer_deadline_is_not_extended(runtime, session, clock):
    runtime.heartbeat(session.id, expected_epoch=0, buffer_until_ns=clock.now_ns()+10_000_000)
    a = make_job(session, clock.now_ns(), workload="policy", result_kind=ResultKind.ACTION_PROPOSAL)
    runtime.submit(a)
    await runtime.wait(a.id)
    clock.advance_to(clock.now_ns()+10_000_000)
    with pytest.raises(PermissionError):
        runtime.consume(a.id, consumer_id="x")
    await runtime.close()


async def test_historical_exact_cache(runtime, session, clock):
    a = make_job(session, clock.now_ns(), result_kind=ResultKind.HISTORICAL, cacheable=True)
    runtime.submit(a)
    await runtime.wait(a.id)
    b = a.model_copy(update={"id": "b"})
    runtime.submit(b)
    assert (await runtime.wait(b.id)).cache_hit
    assert runtime.mock.calls == ["j1"]
    assert runtime.store.budget()["attempts"] == 1
    new = a.model_copy(update={"id": "c", "operation": "different-question"})
    runtime.submit(new)
    assert not (await runtime.wait(new.id)).cache_hit
    await runtime.close()


async def test_cache_does_not_cross_session(runtime, session, clock):
    a = make_job(session, clock.now_ns(), result_kind=ResultKind.HISTORICAL, cacheable=True)
    runtime.submit(a)
    await runtime.wait(a.id)
    s2 = runtime.open_session("other", "task-v1")
    b = a.model_copy(update={"id": "b", "session_id": s2.id})
    runtime.submit(b)
    assert not (await runtime.wait(b.id)).cache_hit
    await runtime.close()


async def test_dependency_order(runtime, session, clock):
    a = make_job(session, clock.now_ns(), payload_json='{"fixture_delay_s":0.01}')
    runtime.submit(a)
    b = make_job(session, clock.now_ns(), id="b", dependencies=(a.id,), observations=a.observations)
    runtime.submit(b)
    await runtime.wait(b.id)
    assert runtime.mock.calls == [a.id, b.id]
    await runtime.close()


def test_dependency_foreign_session_and_missing(runtime, session, clock):
    a = make_job(session, clock.now_ns())
    runtime.submit(a)
    other = runtime.open_session("other", "t")
    with pytest.raises(PermissionError):
        runtime.submit(make_job(other, clock.now_ns(), id="b", dependencies=(a.id,)))
    with pytest.raises(KeyError):
        runtime.submit(make_job(session, clock.now_ns(), id="c", dependencies=("missing",)))


async def test_failed_dependency_rejects(runtime, session, clock):
    a = make_job(session, clock.now_ns(), payload_json='{"fixture_error":true}')
    runtime.submit(a)
    b = make_job(session, clock.now_ns(), id="b", dependencies=(a.id,), observations=a.observations)
    runtime.submit(b)
    r = await runtime.wait(b.id)
    assert r.state == JobState.REJECTED and r.reason == "dependency_failed"
    assert runtime.mock.calls == [a.id]
    await runtime.close()


async def test_cheapest_feasible_and_allowlist(cfg, tmp_path, clock):
    eps = (Endpoint(id="local-expensive", model="model", pool="gpu", site="local", kind="mock",
                    service_p95_ns=1_000_000, reserve_microusd=2),
           Endpoint(id="cloud-cheap", model="model", pool="cloud", site="cloud", kind="mock",
                    service_p95_ns=5_000_000, reserve_microusd=1))
    cfg = RuntimeConfig(**{**cfg.model_dump(), "pools": (Pool(id="gpu"), Pool(id="cloud")),
                           "endpoints": eps, "max_microusd": 10, "placement": "cheapest_feasible"})
    r = Runtime(cfg, tmp_path/"placement.db", clock=clock)
    s = r.open_session("s", "task")
    a = make_job(s, clock.now_ns())
    r.submit(a)
    assert (await r.wait(a.id)).endpoint == "cloud-cheap"
    b = make_job(s, clock.now_ns(), id="b", allowed_sites=("local",))
    r.submit(b)
    assert (await r.wait(b.id)).endpoint == "local-expensive"
    await r.close()


async def test_same_pool_serializes_different_endpoints(cfg, tmp_path, clock):
    cfg = RuntimeConfig(**{**cfg.model_dump(), "endpoints": cfg.endpoints+(
        cfg.endpoints[0].model_copy(update={"id": "other"}),)})
    r = Runtime(cfg, tmp_path/"pool.db", clock=clock)
    s = r.open_session("s", "t")
    for i in range(2):
        r.submit(make_job(s, clock.now_ns(), id=f"j{i}", payload_json='{"fixture_delay_s":0.01}'))
    r.tick()
    assert sum(r.endpoint_use.values()) == 1
    await r.wait("j1")
    await r.close()


async def test_dispatch_intent_expired_before_backend(runtime,session,clock,monkeypatch):
    j=make_job(session,clock.now_ns())
    runtime.submit(j)
    original=runtime.store.reserve
    def delayed_reserve(*args,**kwargs):
        original(*args,**kwargs)
        clock.advance_to(j.deadline_ns)
    monkeypatch.setattr(runtime.store,"reserve",delayed_reserve)
    runtime.tick()
    await asyncio.sleep(.003)
    assert not runtime.mock.calls
    assert runtime.result(j.id).state==JobState.EXPIRED
    assert runtime.store.budget()["known_microusd"]==0
    assert not runtime.store.quarantined()
    await runtime.close()


async def test_same_evidence_can_become_context(runtime, session, clock):
    original = make_job(session, clock.now_ns())
    runtime.submit(original)
    await runtime.wait(original.id)
    old_context = original.observations[0].model_copy(update={"role": "context"})
    second = make_job(session, clock.now_ns(), id="context-query", result_kind=ResultKind.HISTORICAL,
                      observations=(old_context,), dependencies=(original.id,))
    runtime.submit(second)
    assert (await runtime.wait(second.id)).state == JobState.SUCCEEDED
    await runtime.close()


def test_dependency_cannot_replace_source_with_identical_pixels(runtime, session, clock):
    original = make_job(session, clock.now_ns())
    runtime.submit(original)
    other_source = original.observations[0].model_copy(update={"id": "different", "source": "other-camera"})
    with pytest.raises(PermissionError, match="lineage"):
        runtime.submit(make_job(session, clock.now_ns(), id="child", dependencies=(original.id,),
                                observations=(other_source,)))


async def test_telemetry_keeps_unknown_tokens_and_workload_separate(runtime, session, clock):
    from agmina_runtime.telemetry import summarize
    runtime.submit(make_job(session, clock.now_ns()))
    await runtime.wait("j1")
    report = summarize(runtime)
    assert report["tokens"]["missing_attempt_counts"]["input_tokens"] == 1
    assert report["tokens"]["known_totals"]["input_tokens"] == 0
    assert report["tokens"]["reasoning_is_subset_of_output"]
    assert report["timing_groups"]["workload:semantic"]["offered"] == 1
    assert report["timing_groups"]["endpoint:worker"]["roundtrip_ns"]["n"] == 1
    await runtime.close()
