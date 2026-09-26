"""Explicit stateless adapters: chat-compatible HTTP, Triton V2, typed worker.

No retries, provider substitution, model downloads, or actuator calls. Cancelling
HTTP is not proof that GPU compute stopped; the coordinator quarantines on ambiguity.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import math
import os
from typing import Protocol

import httpx

from .config import Endpoint
from .contracts import Job, Prediction, Usage, canonical, strict_json


class Backend(Protocol):
    async def infer(self, job: Job, endpoint: Endpoint) -> Prediction: ...


class BackendFailure(RuntimeError):
    def __init__(self, code, *, termination_known=False, not_sent=False):
        super().__init__(code)
        self.code, self.not_sent = code, not_sent
        self.termination_known = termination_known or not_sent


class MockBackend:
    """Deterministic fixture timing/response, NOT a vision or policy model."""
    def __init__(self, clock):
        self.clock, self.calls = clock, []

    async def infer(self, job, endpoint):
        self.calls.append(job.id)
        p = job.payload()
        delay = p.get("fixture_delay_s", .001)
        if isinstance(delay, bool) or not isinstance(delay, (int, float)) or not 0 <= delay <= 10:
            raise BackendFailure("invalid_fixture_delay", termination_known=True)
        await asyncio.sleep(delay)
        if p.get("fixture_unknown"):
            # Deterministic stand-in for a transport loss whose remote
            # termination cannot be confirmed. The runtime must quarantine.
            raise BackendFailure("injected_transport_loss")
        if p.get("fixture_error"):
            raise BackendFailure("injected_failure", termination_known=True)
        return Prediction(payload_json=canonical(p.get("fixture_output", {"fixture": True, "job": job.id})),
                          usage=Usage(cost_microusd=0), first_content_ns=self.clock.now_ns())


def validate_chat(job: Job, endpoint: Endpoint):
    body = job.payload()
    if set(body) - {"messages", "response_format"} or not isinstance(body.get("messages"), list):
        raise ValueError("Chat payload supports messages and response_format only; sampling is server configured")
    if not 1 <= len(body["messages"]) <= 128:
        raise ValueError("Bounded nonempty messages required")
    image_hashes = []
    for msg in body["messages"]:
        if not isinstance(msg, dict) or set(msg) != {"role", "content"} or msg["role"] not in {
            "system", "user", "assistant"
        }:
            raise ValueError("Invalid chat message")
        content = msg["content"]
        if isinstance(content, str):
            continue
        if not isinstance(content, list):
            raise ValueError("Invalid message content")
        for item in content:
            if not isinstance(item, dict):
                raise ValueError("Invalid content item")
            if item.get("type") == "text" and set(item) == {"type", "text"} and isinstance(item["text"], str):
                continue
            if item.get("type") != "image_url" or set(item) != {"type", "image_url"}:
                raise ValueError("Only text and inline image inputs supported")
            obj = item["image_url"]
            if not isinstance(obj, dict) or set(obj) - {"url", "detail"}:
                raise ValueError("Invalid image field")
            url = obj.get("url", "")
            if not isinstance(url, str) or not url.startswith(("data:image/jpeg;base64,", "data:image/png;base64,")):
                raise ValueError("Remote media URLs are forbidden; provide source-bound inline images")
            try:
                blob = base64.b64decode(url.split(",", 1)[1], validate=True)
            except Exception as exc:
                raise ValueError("Invalid image base64") from exc
            if not blob or len(blob) > 4_000_000:
                raise ValueError("Image byte bound")
            image_hashes.append(hashlib.sha256(blob).hexdigest())
    available = {o.sha256 for o in job.observations}
    if any(h not in available for h in image_hashes):
        raise ValueError("Inline image not bound to declared evidence")
    result = dict(body)
    result.update(strict_json(endpoint.extra_body_json, max_bytes=8192))
    result.update(model=endpoint.model_name, max_tokens=endpoint.max_output_tokens, stream=endpoint.stream)
    if endpoint.stream:
        result["stream_options"] = {"include_usage": True}
    return result


def tensor_check(tensor: dict):
    if not isinstance(tensor, dict) or set(tensor) != {"name", "shape", "datatype", "data"}:
        raise ValueError("Tensor requires name/shape/datatype/flat data")
    if not isinstance(tensor["name"], str) or not tensor["name"]:
        raise ValueError("Tensor name required")
    shape = tensor["shape"]
    if not isinstance(shape, list) or not 1 <= len(shape) <= 8 or any(type(n) is not int or n < 1 for n in shape):
        raise ValueError("Invalid tensor dimensions")
    size = math.prod(shape)
    if size > 1_000_000 or not isinstance(tensor["data"], list) or len(tensor["data"]) != size:
        raise ValueError("Tensor size mismatch/bound")
    dtype = tensor["datatype"]
    if dtype not in {"FP32", "FP64", "INT32", "INT64", "UINT8", "BOOL"}:
        raise ValueError("Unsupported JSON tensor dtype")
    for value in tensor["data"]:
        if dtype == "BOOL":
            if type(value) is not bool:
                raise ValueError("Boolean tensor required")
        elif dtype.startswith("FP"):
            if type(value) not in (int, float) or not math.isfinite(value) or (
                dtype == "FP32" and abs(value) > 3.4028234663852886e38
            ):
                raise ValueError("Finite numeric tensor required")
        else:
            lo, hi = {"UINT8": (0, 255), "INT32": (-2**31, 2**31-1), "INT64": (-2**63, 2**63-1)}[dtype]
            if type(value) is not int or not lo <= value <= hi:
                raise ValueError("Integer dtype/range mismatch")


def usage_from_chat(value, endpoint: Endpoint):
    if value is None:
        return Usage(cost_microusd=None if endpoint.externally_billed else 0)
    if not isinstance(value, dict):
        raise ValueError("Usage must be an object")
    prompt = value.get("prompt_tokens")
    completion = value.get("completion_tokens")
    details = value.get("prompt_tokens_details") or {}
    out_details = value.get("completion_tokens_details") or {}
    cached = details.get("cached_tokens")
    reasoning = out_details.get("reasoning_tokens")
    usage = Usage(input_tokens=prompt, output_tokens=completion, cached_input_tokens=cached,
                  reasoning_output_tokens=reasoning)
    cost = None
    if not endpoint.externally_billed:
        cost = 0  # Only provider charges; GPU rental/energy intentionally NOT represented as zero.
    elif (type(value.get("cost")) in (int, float) and math.isfinite(value["cost"])
          and value["cost"] >= 0):
        # Prefer the provider's reported charge when available. This is stronger than a
        # configured estimate, but does not settle attempts that timed out before a response.
        cost = int(round(value["cost"] * 1_000_000))
    elif prompt is not None and completion is not None and endpoint.input_per_million_microusd is not None and (
            endpoint.output_per_million_microusd is not None
    ):
        # Missing cached count: conservatively price total input at uncached rate.
        cache_n = cached or 0
        cache_rate = endpoint.cached_per_million_microusd
        if cache_rate is None:
            cache_rate = endpoint.input_per_million_microusd
        numerator = ((prompt-cache_n)*endpoint.input_per_million_microusd + cache_n*cache_rate
                     + completion*endpoint.output_per_million_microusd)
        cost = (numerator + 999999)//1_000_000
    return usage.model_copy(update={"cost_microusd": cost})


def provider_request_id(value):
    """Return only a bounded provider generation identifier for later reconciliation."""
    if not isinstance(value, dict):
        return None
    value = value.get("id")
    return value if isinstance(value, str) and 0 < len(value) <= 256 else None


class HttpBackend:
    def __init__(self, clock, *, allow_network=False, transport=None):
        self.clock, self.allow_network, self.transport = clock, allow_network, transport
        self.client = httpx.AsyncClient(transport=transport, follow_redirects=False, trust_env=False)

    async def close(self):
        await self.client.aclose()

    async def infer(self, job, endpoint):
        if not self.allow_network and self.transport is None:
            raise BackendFailure("network_not_authorized", not_sent=True)
        headers = {"Content-Type": "application/json", "X-Agmina-Request-ID": job.id}
        if endpoint.credential_env:
            secret = os.getenv(endpoint.credential_env)
            if not secret:
                raise BackendFailure("missing_endpoint_credential", not_sent=True)
            headers["Authorization"] = "Bearer " + secret
        try:
            body = job.payload()
            if endpoint.kind == "chat":
                body = validate_chat(job, endpoint)
            elif endpoint.kind == "triton":
                if set(body) != {"inputs"} or not isinstance(body["inputs"], list) or not body["inputs"]:
                    raise ValueError("Triton payload must contain nonempty inputs")
                for tensor in body["inputs"]:
                    tensor_check(tensor)
                if len({t["name"] for t in body["inputs"]}) != len(body["inputs"]):
                    raise ValueError("Duplicate input tensor names")
            elif endpoint.kind == "worker":
                body = {"job_id": job.id, "session_id": job.session_id, "epoch": job.epoch,
                        "task_revision": job.task_revision, "operation": job.operation,
                        "evidence": [o.model_dump(mode="json") for o in job.observations], "payload": body}
            else:
                raise ValueError("Unsupported HTTP adapter")
        except (ValueError, TypeError, OverflowError) as exc:
            raise BackendFailure("invalid_outbound_payload", not_sent=True) from exc
        try:
            async with self.client.stream("POST", endpoint.url, json=body, headers=headers,
                                          timeout=endpoint.timeout_s) as response:
                if response.status_code != 200:
                    raise BackendFailure("http_status_" + str(response.status_code))
                if endpoint.kind == "chat" and endpoint.stream:
                    return await self._stream_chat(response, endpoint)
                raw = bytearray()
                async for block in response.aiter_bytes():
                    raw.extend(block)
                    if len(raw) > endpoint.max_response_bytes:
                        raise BackendFailure("response_byte_bound")
                obj = strict_json(raw.decode("utf8"), max_bytes=endpoint.max_response_bytes)
                if endpoint.kind == "chat":
                    if isinstance(obj.get("error"), dict):
                        error_value = obj["error"].get("code") or obj["error"].get("type") or "unknown"
                        error_code = error_value if isinstance(error_value, str) else "invalid"
                        raise BackendFailure("provider_error:" + error_code[:128], termination_known=True)
                    response_model = obj.get("model")
                    if ((response_model is None and endpoint.response_model_required)
                            or (response_model is not None and response_model != endpoint.model_name)):
                        # Preserve the bounded identifier so an operator can correct a provider
                        # alias without weakening exact response binding or logging response text.
                        observed = response_model if isinstance(response_model, str) else "<missing>"
                        raise BackendFailure("response_model_mismatch:" + observed,
                                             termination_known=True)
                    choices = obj.get("choices", [])
                    if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
                        raise BackendFailure("incomplete_chat_answer", termination_known=True)
                    text = choices[0].get("message", {}).get("content")
                    result = {"text": text}
                    if not isinstance(text, str) or not text:
                        raise BackendFailure("missing_chat_content", termination_known=True)
                    return Prediction(payload_json=canonical(result), usage=usage_from_chat(obj.get("usage"), endpoint),
                                      provider_request_id=provider_request_id(obj))
                if endpoint.kind == "triton":
                    if obj.get("model_name") != endpoint.model_name or (
                        endpoint.model_version is not None and obj.get("model_version") != endpoint.model_version
                    ):
                        raise BackendFailure("tensor_model_version_mismatch", termination_known=True)
                    outputs = obj.get("outputs")
                    if not isinstance(outputs, list) or not outputs:
                        raise ValueError("No tensor output")
                    for tensor in outputs:
                        tensor_check(tensor)
                    if len({t["name"] for t in outputs}) != len(outputs):
                        raise ValueError("Duplicate output tensor names")
                    return Prediction(payload_json=canonical({"outputs": outputs}),
                                      usage=Usage(cost_microusd=None if endpoint.externally_billed else 0))
                if set(obj) != {"job_id", "epoch", "payload", "usage"} or (
                    obj["job_id"], obj["epoch"]
                ) != (job.id, job.epoch):
                    raise BackendFailure("worker_result_binding", termination_known=True)
                return Prediction(payload_json=canonical(obj["payload"]),
                                  usage=Usage.model_validate_json(canonical(obj["usage"])))
        except (httpx.HTTPError, UnicodeError) as exc:
            raise BackendFailure("transport_failure") from exc

    async def _stream_chat(self, response, endpoint):
        text, usage, first, finished, done, request_id = [], None, None, False, False, None
        size = 0
        buffer = ""

        def parse_line(line):
            nonlocal usage, first, finished, done, request_id
            if not line.startswith("data:"):
                return
            value = line[5:].strip()
            if value == "[DONE]":
                done = True
                return
            if done:
                raise ValueError("Content after DONE")
            obj = strict_json(value, max_bytes=endpoint.max_response_bytes)
            if request_id is None:
                request_id = provider_request_id(obj)
            if isinstance(obj.get("error"), dict):
                error_value = obj["error"].get("code") or obj["error"].get("type") or "unknown"
                error_code = error_value if isinstance(error_value, str) else "invalid"
                raise BackendFailure("provider_error:" + error_code[:128], termination_known=True)
            if (("model" not in obj and endpoint.response_model_required)
                    or ("model" in obj and obj["model"] != endpoint.model_name)):
                observed_value = obj.get("model")
                observed = observed_value if isinstance(observed_value, str) else "<missing>"
                raise BackendFailure("stream_model_mismatch:" + observed, termination_known=True)
            if obj.get("usage") is not None:
                usage = obj["usage"]
            choices = obj.get("choices", [])
            if len(choices) > 1:
                raise ValueError("Multiple completions not supported")
            for choice in choices:
                content = choice.get("delta", {}).get("content")
                if content:
                    if finished or not isinstance(content, str):
                        raise ValueError("Invalid streaming content")
                    if first is None:
                        first = self.clock.now_ns()
                    text.append(content)
                reason = choice.get("finish_reason")
                if reason is not None:
                    if reason != "stop":
                        raise BackendFailure("incomplete_chat_answer")
                    finished = True
        # Bytes are bounded before newline parsing; a huge single line cannot bypass the cap.
        import codecs
        decoder = codecs.getincrementaldecoder("utf8")()
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > endpoint.max_response_bytes:
                raise BackendFailure("response_byte_bound")
            buffer += decoder.decode(chunk)
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                parse_line(line.rstrip("\r"))
        buffer += decoder.decode(b"", final=True)
        if buffer.strip():
            parse_line(buffer.rstrip("\r"))
        if not done or not finished or not text:
            raise BackendFailure("incomplete_stream")
        return Prediction(payload_json=canonical({"text": "".join(text)}),
                          usage=usage_from_chat(usage, endpoint), first_content_ns=first,
                          provider_request_id=request_id)
