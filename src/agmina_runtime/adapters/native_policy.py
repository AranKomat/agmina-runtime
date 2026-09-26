"""Read-only bridge for a native reset/infer policy RPC.

The policy server remains host-owned and is reset outside Agmina. Each inference
packet carries its full native stamp and observation, so Agmina does not migrate
or invent hidden policy state. Returned actions are proposals only; this module
does not authorize or execute them.
"""
from __future__ import annotations

import base64
import json
import math
from typing import Protocol
from urllib.parse import urlparse

import httpx

from ..backends import BackendFailure
from ..config import Endpoint
from ..contracts import Job, Prediction, Usage, canonical, strict_json

POLICY_METHOD_RESET = "policy.reset"
POLICY_METHOD_INFER = "policy.infer"
POLICY_CAMERAS = ("head", "left_wrist", "right_wrist")
POLICY_PROPRIO_DIM = 61
POLICY_ACTION_DIM = 23
POLICY_ACTION_HORIZON = 32
MAX_IMAGE_BYTES = 20_000_000


def _stamp(value):
    if not isinstance(value, dict) or set(value) != {"session", "epoch", "sequence"}:
        raise ValueError("Native policy stamp must contain session/epoch/sequence")
    if not isinstance(value["session"], str) or not value["session"]:
        raise ValueError("Native policy session is required")
    if type(value["epoch"]) is not int or value["epoch"] < 0:
        raise ValueError("Native policy epoch must be a nonnegative integer")
    if type(value["sequence"]) is not int or value["sequence"] < 0:
        raise ValueError("Native policy sequence must be a nonnegative integer")
    return value


def _nested_uint8(value):
    """Return (shape, bytes) for a bounded rectangular nested uint8 list."""
    if not isinstance(value, list) or not value:
        raise ValueError("Native policy image must be a nonempty nested list")
    if isinstance(value[0], list):
        child = [_nested_uint8(item) for item in value]
        shape, raw = child[0]
        if any(item[0] != shape for item in child[1:]):
            raise ValueError("Native policy image must be rectangular")
        return (len(value), *shape), b"".join(item[1] for item in child)
    if any(type(item) is not int or not 0 <= item <= 255 for item in value):
        raise ValueError("Native policy image values must be uint8")
    return (len(value),), bytes(value)


def _image_envelope(value):
    if isinstance(value, list):
        shape, raw = _nested_uint8(value)
        if len(shape) != 3 or shape[-1] != 3 or len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("Native policy image must be bounded HxWx3 uint8")
        return {"__ndarray__": base64.b64encode(raw).decode("ascii"),
                "dtype": "uint8", "shape": list(shape)}
    if not isinstance(value, dict) or set(value) != {"__ndarray__", "dtype", "shape"}:
        raise ValueError("Native policy image must be a nested list or ndarray envelope")
    if value["dtype"] != "uint8" or not isinstance(value["__ndarray__"], str):
        raise ValueError("Native policy image envelope must declare uint8 data")
    shape = value["shape"]
    if (not isinstance(shape, list) or len(shape) != 3
            or any(type(item) is not int or item < 1 for item in shape) or shape[-1] != 3):
        raise ValueError("Native policy image envelope must declare HxWx3 shape")
    try:
        raw = base64.b64decode(value["__ndarray__"], validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Native policy image envelope has invalid base64") from exc
    if len(raw) != math.prod(shape) or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Native policy image envelope byte bound mismatch")
    return {"__ndarray__": value["__ndarray__"], "dtype": "uint8", "shape": shape}


def validate_native_packet(value):
    """Validate the JSON-compatible native R1Pro packet without changing it."""
    if not isinstance(value, dict) or set(value) != {"stamp", "instruction", "proprio", "rgb"}:
        raise ValueError("Native policy packet has an unexpected shape")
    _stamp(value["stamp"])
    if not isinstance(value["instruction"], str) or not value["instruction"].strip():
        raise ValueError("Native policy instruction is required")
    proprio = value["proprio"]
    if not isinstance(proprio, list) or len(proprio) != POLICY_PROPRIO_DIM:
        raise ValueError("Native policy requires the full 61-element proprio vector")
    if any(type(item) not in (int, float) or not math.isfinite(item) for item in proprio):
        raise ValueError("Native policy proprioception must be finite")
    rgb = value["rgb"]
    if not isinstance(rgb, dict) or set(rgb) != set(POLICY_CAMERAS):
        raise ValueError("Native policy camera set/order is not the audited R1Pro set")
    normalized = dict(value)
    normalized["rgb"] = {camera: _image_envelope(rgb[camera]) for camera in POLICY_CAMERAS}
    return json.loads(json.dumps(normalized, separators=(",", ":")))


def validate_native_result(value, expected_stamp):
    """Validate a native action proposal and bind it to the submitted stamp."""
    if not isinstance(value, dict) or set(value) != {"stamp", "actions"}:
        raise ValueError("Native policy result has an unexpected shape")
    if _stamp(value["stamp"]) != expected_stamp:
        raise ValueError("Native policy returned a stale or mismatched stamp")
    actions = value["actions"]
    if not isinstance(actions, list) or not 1 <= len(actions) <= 256:
        raise ValueError("Native policy action horizon is outside the bounded contract")
    if any(
        not isinstance(row, list)
        or len(row) != POLICY_ACTION_DIM
        or any(type(item) not in (int, float) or not math.isfinite(item) for item in row)
        for row in actions
    ):
        raise ValueError("Native policy action codec must be finite 23-channel rows")
    return value


class NativePolicyTransport(Protocol):
    async def reset(self, stamp: dict) -> dict: ...

    async def infer(self, packet: dict) -> dict: ...


class HttpNativePolicyTransport:
    """Minimal client for the loopback RPent HTTP RPC used by the policy server."""

    def __init__(self, url: str, *, timeout_s: float = 180.0, transport=None):
        parsed = urlparse(url)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("Native policy transport must remain loopback-only")
        if not 0 < timeout_s <= 300:
            raise ValueError("Native policy timeout is outside the bounded range")
        self.client = httpx.AsyncClient(
            base_url=url.rstrip("/"),
            transport=transport,
            follow_redirects=False,
            trust_env=False,
            timeout=timeout_s,
        )

    async def close(self):
        await self.client.aclose()

    async def _call(self, method: str, argument: dict):
        body = {"method": method, "args": [argument], "kwargs": {}, "session_id": ""}
        try:
            response = await self.client.post("/call", json=body)
            raw = response.content
        except httpx.HTTPError as exc:
            raise BackendFailure("native_policy_transport_failure") from exc
        if response.status_code != 200:
            raise BackendFailure(f"native_policy_http_status_{response.status_code}",
                                 termination_known=True)
        try:
            envelope = strict_json(raw.decode("utf8"), max_bytes=8_000_000)
        except (UnicodeError, ValueError) as exc:
            raise BackendFailure("native_policy_invalid_response", termination_known=True) from exc
        if envelope.get("ok") is not True:
            raise BackendFailure("native_policy_rpc_error", termination_known=True)
        return envelope.get("result")

    async def reset(self, stamp: dict):
        stamp = _stamp(stamp)
        result = await self._call(POLICY_METHOD_RESET, stamp)
        if not isinstance(result, dict) or result.get("stamp") != stamp:
            raise BackendFailure("native_policy_reset_mismatch", termination_known=True)
        return result

    async def infer(self, packet: dict):
        packet = validate_native_packet(packet)
        return await self._call(POLICY_METHOD_INFER, packet)


class NativePolicyBackend:
    """Agmina backend for one already-reset native policy server."""

    def __init__(self, transport: NativePolicyTransport, *, clock):
        self.transport, self.clock = transport, clock

    async def infer(self, job: Job, endpoint: Endpoint) -> Prediction:
        packet = validate_native_packet(job.payload())
        result = validate_native_result(await self.transport.infer(packet), packet["stamp"])
        return Prediction(
            payload_json=canonical(result),
            usage=Usage(cost_microusd=0),
            first_content_ns=self.clock.now_ns(),
        )
