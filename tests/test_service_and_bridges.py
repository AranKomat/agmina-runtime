import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest

from agmina_runtime.adapters.hosts import (
    ActionChunk,
    physical_observation,
    streambudget_job,
    streambudget_text_job,
)
from agmina_runtime.client import Client, validate_delivery
from agmina_runtime.clocks import ClockMap
from agmina_runtime.contracts import JobState, ResultKind
from agmina_runtime.server import create_app
from conftest import make_job


async def test_authenticated_service(runtime,clock):
    token="x"*32
    app=create_app(runtime,token)
    transport=httpx.ASGITransport(app=app,raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport,base_url="http://test") as anonymous:
        assert (await anonymous.get("/v1/clock")).status_code == 401
    client=Client("http://localhost",token,transport=transport)
    s=await client.open_session("s","t")
    assert (await client.clock())["clock_id"] == clock.id
    j=make_job(s,clock.now_ns())
    assert (await client.submit(j)).state == JobState.QUEUED
    await runtime.wait(j.id)
    assert (await client.result(j.id)).prediction_json is None
    result=await client.consume(j.id,"app")
    assert result.prediction_json is not None
    await client.close()
    await runtime.close()


async def test_service_invalid_payload_redacted(runtime):
    app=create_app(runtime,"x"*32)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,raise_app_exceptions=False),
            base_url="http://test",headers={"Authorization":"Bearer "+"x"*32}) as c:
        r=await c.post("/v1/jobs",json={"secret":"must-not-appear-in-error"})
        assert r.status_code == 422
        assert "must-not" not in r.text
        r=await c.post("/v1/jobs",content=b"a"*9_000_001)
        assert r.status_code == 413
    await runtime.close()


async def test_after_network_fence(runtime,session,clock):
    j=make_job(session,clock.now_ns())
    runtime.submit(j)
    await runtime.wait(j.id)
    r=runtime.consume(j.id,consumer_id="app")
    mapping=ClockMap(clock.id,"robot-local",1000,10,clock.now_ns()+10_000_000_000)
    args=dict(tenant=session.tenant,session_id=session.id,current_epoch=0,
              current_task_revision=session.task_revision,consumer_id="app",local_clock_id="robot-local",
              server_to_local=mapping,max_mapping_error_ns=10)
    check=validate_delivery(j,r,now_local_ns=clock.now_ns()+1000,**args)
    assert not check.action_authorized
    with pytest.raises(PermissionError):
        validate_delivery(j,r,now_local_ns=j.deadline_ns+1000,**args)
    args["current_epoch"]=1
    with pytest.raises(PermissionError):
        validate_delivery(j,r,now_local_ns=clock.now_ns()+1000,**args)
    await runtime.close()


async def test_delivery_wrong_reply(runtime,session,clock):
    j=make_job(session,clock.now_ns())
    runtime.submit(j)
    await runtime.wait(j.id)
    r=runtime.consume(j.id,consumer_id="app")
    with pytest.raises(PermissionError):
        validate_delivery(j,r.model_copy(update={"request_fingerprint":"0"*64}),tenant=session.tenant,
            session_id=session.id,current_epoch=0,current_task_revision=session.task_revision,consumer_id="app",
            now_local_ns=clock.now_ns(),local_clock_id=clock.id,
            server_to_local=ClockMap(clock.id,clock.id,0,0,clock.now_ns()+100),max_mapping_error_ns=0)
    await runtime.close()


def test_streambudget_shape_bridge(session,clock):
    image=SimpleNamespace(evidence_id="image",timestamp=1.,jpeg=b"pixels")
    req=SimpleNamespace(operation="perceive",system="system",text="question",images=[image],context={})
    m=ClockMap("video",clock.id,8_000_000_000,0,clock.now_ns()+100)
    j=streambudget_job(req,session=session,clock_map=m,now_ns=clock.now_ns(),snapshot_ns=clock.now_ns(),
         deadline_ns=clock.now_ns()+1_000_000_000,model="model",job_id="job",
         sequence_by_id={"image":1},available_by_id={"image":1.2})
    assert j.observations[0].capture_ns == 9_000_000_000
    assert j.observations[0].available_ns == 9_200_000_000
    assert j.result_kind == ResultKind.HISTORICAL
    with pytest.raises(ValueError):
        streambudget_job(req,session=session,clock_map=m,now_ns=clock.now_ns(),snapshot_ns=clock.now_ns(),
            deadline_ns=clock.now_ns()+1_000_000_000,model="model",job_id="job",sequence_by_id={},available_by_id={})


def test_streambudget_text_bridge_is_explicit_query(session, clock):
    req = SimpleNamespace(operation="plan", system="system", text="question", images=[], context={})
    job = streambudget_text_job(req, session=session, now_ns=clock.now_ns(),
                                snapshot_ns=clock.now_ns(), deadline_ns=clock.now_ns() + 1_000_000_000,
                                model="model", job_id="text-job")
    assert job.workload == "query" and job.observations == ()
    assert json.loads(job.payload_json)["messages"][1]["content"] == "question"
    with pytest.raises(ValueError, match="image inputs"):
        streambudget_text_job(SimpleNamespace(operation="plan", system="s", text="t",
                                              images=[SimpleNamespace()], context={}),
                              session=session, now_ns=clock.now_ns(), snapshot_ns=clock.now_ns(),
                              deadline_ns=clock.now_ns() + 1_000_000_000, model="model", job_id="bad")


def test_physical_frame_uses_wall_not_sim(clock):
    blob=b"pixels"
    sha=hashlib.sha256(blob).hexdigest()
    class Frame:
        basis=SimpleNamespace(captured_wall=2.,sim_time=999999.)
        available_wall=2.1
        asset_id="asset"
        camera="head"
        content_sha256=sha
        def verify_bytes(self,value):
            if hashlib.sha256(value).hexdigest()!=sha:
                raise PermissionError("bad bytes")
    m=ClockMap("native-run",clock.id,7_000_000_000,0,clock.now_ns()+1000)
    o=physical_observation(Frame(),blob,sequence=3,clock_map=m,clock_id=clock.id,now_ns=clock.now_ns())
    assert o.capture_ns==9_000_000_000 and o.source_time=="sim:999999.0"
    with pytest.raises(PermissionError):
        physical_observation(Frame(),b"wrong",sequence=3,clock_map=m,clock_id=clock.id,now_ns=clock.now_ns())


def test_action_codec_does_not_adapt_embodiment():
    a=ActionChunk(codec_revision="test",action_names=("joint","grip"),units=("radian","fraction"),
                  period_ns=33333333,normalized=False,actions=((1.,.5),))
    assert a.require_codec(revision="test",names=a.action_names,units=a.units,
                           period_ns=a.period_ns,normalized=False) == a
    with pytest.raises(PermissionError):
        a.require_codec(revision="other-robot",names=a.action_names,units=a.units,
                         period_ns=a.period_ns,normalized=False)
    with pytest.raises(ValueError):
        ActionChunk(codec_revision="test",action_names=("joint","grip"),units=("radian","fraction"),
                    period_ns=1,normalized=False,actions=((float("nan"),.5),))
