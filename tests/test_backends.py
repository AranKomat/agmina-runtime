import base64
import json

import httpx
import pytest

from agmina_runtime.backends import BackendFailure, HttpBackend, tensor_check, usage_from_chat, validate_chat
from agmina_runtime.config import Endpoint
from agmina_runtime.contracts import canonical
from conftest import make_job


def chat_ep(**updates):
    data = dict(id="e", model="model", pool="gpu", site="local", kind="chat",
                url="https://example.test/v1/chat/completions", model_name="test-model")
    data.update(updates)
    return Endpoint(**data)


def packet(session, clock):
    data = b"test image bytes"
    body = {"messages": [{"role": "user", "content": [
        {"type": "text", "text": "describe"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(data).decode()}}
    ]}]}
    return make_job(session, clock.now_ns(), payload_json=canonical(body))


async def test_nonstream_chat_contract(clock, session):
    seen = []
    async def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"model": "test-model", "choices": [
            {"message": {"content": '{"object":"box"}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 4}})
    backend = HttpBackend(clock, transport=httpx.MockTransport(handler))
    r = await backend.infer(packet(session, clock), chat_ep())
    assert json.loads(r.payload_json)["text"] == '{"object":"box"}'
    assert r.usage.input_tokens == 20 and r.first_content_ns is None
    assert seen[0]["max_tokens"] == 256
    assert "Authorization" not in canonical(seen)
    await backend.close()


async def test_stream_chat_complete(clock, session):
    events = [
        {"model":"test-model", "choices":[{"delta":{"content":"{"}, "finish_reason":None}]},
        {"model":"test-model", "choices":[{"delta":{"content":"\"x\":1}"}, "finish_reason":"stop"}]},
        {"model":"test-model", "choices":[], "usage":{"prompt_tokens":8,"completion_tokens":4,
            "prompt_tokens_details":{"cached_tokens":5}, "completion_tokens_details":{"reasoning_tokens":2}}},
    ]
    data = "".join("data: "+canonical(e)+"\n\n" for e in events) + "data: [DONE]\n\n"
    backend = HttpBackend(clock, transport=httpx.MockTransport(lambda req: httpx.Response(200, text=data)))
    r = await backend.infer(packet(session, clock), chat_ep(stream=True))
    assert json.loads(r.payload_json) == {"text": '{"x":1}'}
    assert r.first_content_ns == clock.now_ns()
    assert r.usage.cached_input_tokens == 5
    assert r.usage.reasoning_output_tokens == 2  # Already included in four output tokens.
    await backend.close()


async def test_stream_missing_response_model_is_terminal_and_explicitly_allowed(clock, session):
    events = [
        {"choices":[{"delta":{"content":"ok"}, "finish_reason":"stop"}]},
        {"choices":[], "usage":{"prompt_tokens":1,"completion_tokens":1}},
    ]
    data = "".join("data: "+canonical(e)+"\n\n" for e in events) + "data: [DONE]\n\n"

    strict_backend = HttpBackend(clock, transport=httpx.MockTransport(
        lambda req: httpx.Response(200, text=data)))
    with pytest.raises(BackendFailure) as exc:
        await strict_backend.infer(packet(session, clock), chat_ep(stream=True))
    assert exc.value.code == "stream_model_mismatch:<missing>"
    assert exc.value.termination_known
    await strict_backend.close()

    permissive_backend = HttpBackend(clock, transport=httpx.MockTransport(
        lambda req: httpx.Response(200, text=data)))
    result = await permissive_backend.infer(
        packet(session, clock), chat_ep(stream=True, response_model_required=False))
    assert json.loads(result.payload_json) == {"text": "ok"}
    await permissive_backend.close()


@pytest.mark.parametrize("finish,done", [("length", True), ("stop", False), (None, True)])
async def test_partial_stream_not_delivered(clock, session, finish, done):
    data = "data: "+canonical({"choices":[{"delta":{"content":"incomplete"},"finish_reason":finish}]})+"\n\n"
    if done:
        data += "data: [DONE]\n\n"
    backend = HttpBackend(clock, transport=httpx.MockTransport(lambda req: httpx.Response(200, text=data)))
    with pytest.raises(BackendFailure):
        await backend.infer(packet(session, clock), chat_ep(stream=True))
    await backend.close()


@pytest.mark.parametrize("status", [301, 302, 400, 401, 429, 500, 503])
async def test_no_retry_or_redirect(clock, session, status):
    count = []
    async def handler(req):
        count.append(1)
        return httpx.Response(status, headers={"Location":"https://leak.example/"}, text="secret failure")
    backend = HttpBackend(clock, transport=httpx.MockTransport(handler))
    with pytest.raises(BackendFailure) as exc:
        await backend.infer(packet(session, clock), chat_ep())
    assert "secret" not in str(exc.value)
    assert len(count) == 1
    await backend.close()


async def test_network_disabled(clock, session):
    backend = HttpBackend(clock)
    with pytest.raises(BackendFailure, match="network_not_authorized"):
        await backend.infer(packet(session, clock), chat_ep())
    await backend.close()


async def test_missing_credential_no_request(clock, session, monkeypatch):
    monkeypatch.delenv("SOME_CREDENTIAL", raising=False)
    backend = HttpBackend(clock, transport=httpx.MockTransport(lambda req: pytest.fail("must not dispatch")))
    with pytest.raises(BackendFailure, match="missing_endpoint_credential"):
        await backend.infer(packet(session, clock), chat_ep(credential_env="SOME_CREDENTIAL"))
    await backend.close()


async def test_response_model_mismatch(clock, session):
    backend = HttpBackend(clock, transport=httpx.MockTransport(lambda req: httpx.Response(200,
        json={"model":"wrong-model", "choices":[]})))
    with pytest.raises(BackendFailure, match="response_model_mismatch"):
        await backend.infer(packet(session, clock), chat_ep())
    await backend.close()


async def test_http_200_provider_error_is_not_model_mismatch(clock, session):
    backend = HttpBackend(clock, transport=httpx.MockTransport(lambda req: httpx.Response(200,
        json={"error": {"code": "provider_busy", "message": "not retained"}})))
    with pytest.raises(BackendFailure, match="provider_error:provider_busy"):
        await backend.infer(packet(session, clock), chat_ep())
    await backend.close()


async def test_missing_response_model_can_be_explicitly_allowed(clock, session):
    backend = HttpBackend(clock, transport=httpx.MockTransport(lambda req: httpx.Response(200,
        json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})))
    with pytest.raises(BackendFailure, match="response_model_mismatch"):
        await backend.infer(packet(session, clock), chat_ep())
    result = await backend.infer(packet(session, clock), chat_ep(response_model_required=False))
    assert json.loads(result.payload_json)["text"] == "ok"
    await backend.close()


async def test_response_byte_bound(clock, session):
    backend = HttpBackend(clock, transport=httpx.MockTransport(lambda req: httpx.Response(200, text="a"*1024)))
    with pytest.raises(BackendFailure, match="response_byte_bound"):
        await backend.infer(packet(session, clock), chat_ep(stream=True, max_response_bytes=256))
    await backend.close()


@pytest.mark.parametrize("url", ["https://image.example/pic.png", "file:///secret", "data:image/png;base64,?bad"])
def test_image_source_validation(clock, session, url):
    j = packet(session, clock)
    p = j.payload()
    p["messages"][0]["content"][1]["image_url"]["url"] = url
    with pytest.raises(ValueError):
        validate_chat(j.model_copy(update={"payload_json":canonical(p)}), chat_ep())


def test_undeclared_image(clock, session):
    j = packet(session, clock)
    bad = j.observations[0].model_copy(update={"sha256": "0"*64})
    with pytest.raises(ValueError):
        validate_chat(j.model_copy(update={"observations":(bad,)}), chat_ep())


def test_usage_pricing():
    e = chat_ep(externally_billed=True, reserve_microusd=100,
                input_per_million_microusd=1_000_000, cached_per_million_microusd=100_000,
                output_per_million_microusd=2_000_000)
    u = usage_from_chat({"prompt_tokens":100,"completion_tokens":10,
                        "prompt_tokens_details":{"cached_tokens":50},
                        "completion_tokens_details":{"reasoning_tokens":5}}, e)
    assert u.cost_microusd == 75
    assert usage_from_chat(None, e).cost_microusd is None


@pytest.mark.parametrize("changes", [
    {"data":[1]}, {"shape":[0]}, {"datatype":"BF16"}, {"data":[float('inf'),1]},
    {"data":[True,1]}, {"datatype":"UINT8", "data":[256,0]},
    {"datatype":"INT32", "data":[2**32,0]}, {"shape":[True,2]},
])
def test_bad_tensors(changes):
    t = {"name":"action","shape":[1,2],"datatype":"FP32","data":[1.,2.]}
    t.update(changes)
    with pytest.raises(ValueError):
        tensor_check(t)


async def test_triton_roundtrip(clock, session):
    t = {"name":"state","shape":[1,2],"datatype":"FP32","data":[1.,2.]}
    o = {**t, "name":"action"}
    ep = Endpoint(id="e",model="model",pool="gpu",site="local",kind="triton",
                  url="http://127.0.0.1:8000/v2/models/policy/versions/1/infer",
                  model_name="policy",model_version="1")
    seen = []
    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200,json={"model_name":"policy","model_version":"1","outputs":[o]})
    backend = HttpBackend(clock, transport=httpx.MockTransport(handler))
    j = make_job(session, clock.now_ns(), payload_json=canonical({"inputs":[t]}))
    result = await backend.infer(j,ep)
    assert json.loads(result.payload_json)["outputs"] == [o]
    assert seen == [{"inputs":[t]}]
    await backend.close()


async def test_worker_result_epoch_mismatch(clock, session):
    e = Endpoint(id="e",model="model",pool="gpu",site="local",kind="worker",url="http://localhost/infer")
    backend = HttpBackend(clock, transport=httpx.MockTransport(lambda req: httpx.Response(200,
        json={"job_id":"j1","epoch":999,"payload":{"a":1},"usage":{}})))
    with pytest.raises(BackendFailure,match="worker_result_binding"):
        await backend.infer(make_job(session,clock.now_ns()),e)
    await backend.close()


def test_fp32_overflow_rejected():
    with pytest.raises(ValueError):
        tensor_check({"name": "x", "shape": [1], "datatype": "FP32", "data": [1e39]})


async def test_invalid_local_payload_confirmed_not_sent(clock, session):
    calls = []
    backend = HttpBackend(clock, transport=httpx.MockTransport(lambda r: calls.append(r)))
    with pytest.raises(BackendFailure) as exc:
        await backend.infer(make_job(session, clock.now_ns(), payload_json='{"invalid":true}'), chat_ep())
    assert exc.value.not_sent and exc.value.termination_known and not calls
    await backend.close()
