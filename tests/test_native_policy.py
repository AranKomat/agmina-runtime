import json

import httpx
import pytest

from agmina_runtime.adapters.native_policy import (
    POLICY_ACTION_DIM,
    POLICY_CAMERAS,
    POLICY_PROPRIO_DIM,
    HttpNativePolicyTransport,
    NativePolicyBackend,
    validate_native_packet,
    validate_native_result,
)
from agmina_runtime.config import Endpoint
from agmina_runtime.contracts import ResultKind, canonical
from conftest import make_job


def stamp(sequence=0):
    return {"session": "s", "epoch": 0, "sequence": sequence}


def packet(sequence=0):
    return {
        "stamp": stamp(sequence),
        "instruction": "move to the radio",
        "proprio": [float(i) for i in range(POLICY_PROPRIO_DIM)],
        "rgb": {camera: [[[0, 0, 0]]] for camera in POLICY_CAMERAS},
    }


async def native_response(request):
    body = json.loads(request.content)
    method = body["method"]
    argument = body["args"][0]
    if method == "policy.reset":
        return httpx.Response(200, json={"ok": True, "result": {"stamp": argument}})
    if method == "policy.infer":
        return httpx.Response(200, json={"ok": True, "result": {
            "stamp": argument["stamp"],
            "actions": [[0.0] * POLICY_ACTION_DIM],
        }})
    return httpx.Response(200, json={"ok": False, "error": "unknown"})


def endpoint():
    return Endpoint(id="native", model="policy", pool="local", site="local", kind="worker",
                    url="http://127.0.0.1:8011/infer")


def test_native_packet_and_result_are_strict():
    assert validate_native_packet(packet())["stamp"] == stamp()
    assert validate_native_result({"stamp": stamp(), "actions": [[0.0] * POLICY_ACTION_DIM]}, stamp())
    with pytest.raises(ValueError, match="61-element"):
        validate_native_packet({**packet(), "proprio": [0.0]})
    with pytest.raises(ValueError, match="mismatched stamp"):
        validate_native_result({"stamp": stamp(1), "actions": [[0.0] * POLICY_ACTION_DIM]}, stamp())
    with pytest.raises(ValueError, match="23-channel"):
        validate_native_result({"stamp": stamp(), "actions": [[0.0]]}, stamp())


def test_native_transport_rejects_non_loopback_prefixes():
    with pytest.raises(ValueError, match="loopback-only"):
        HttpNativePolicyTransport("http://127.0.0.1.evil")


@pytest.mark.asyncio
async def test_native_transport_preserves_reset_and_infer_rpc():
    client = HttpNativePolicyTransport("http://127.0.0.1:8011",
                                       transport=httpx.MockTransport(native_response))
    try:
        assert await client.reset(stamp()) == {"stamp": stamp()}
        result = await client.infer(packet())
        assert result["stamp"] == stamp()
        assert len(result["actions"][0]) == POLICY_ACTION_DIM
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_native_backend_returns_proposal_without_authorizing_action(clock, session):
    client = HttpNativePolicyTransport("http://127.0.0.1:8011",
                                       transport=httpx.MockTransport(native_response))
    backend = NativePolicyBackend(client, clock=clock)
    try:
        job = make_job(session, clock.now_ns(), workload="policy", result_kind=ResultKind.ACTION_PROPOSAL,
                       payload_json=canonical(packet()))
        prediction = await backend.infer(job, endpoint())
        assert json.loads(prediction.payload_json)["stamp"] == stamp()
        assert prediction.usage.cost_microusd == 0
    finally:
        await client.close()
