"""Authenticated single-tenant development sidecar, default loopback only.

No arbitrary endpoint registration, code loading, media fetching or robot actions.
TLS/proxy authentication, rate limits, tenancy and deployment hardening are external.
"""
from __future__ import annotations

import asyncio
import hmac
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .contracts import Job, strict_json
from .telemetry import summarize


class BoundedBody:
    """Bound bytes BEFORE downstream JSON parsing, including chunked request bodies."""
    def __init__(self, app, limit=9_000_000):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            if event["type"] != "http.request":
                continue
            size += len(event.get("body", b""))
            if size > self.limit:
                response = JSONResponse({"error": "request_body_limit"}, status_code=413)
                return await response(scope, receive, send)
            chunks.append(event.get("body", b""))
            if not event.get("more_body", False):
                break
        delivered = False
        async def replay_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()
        return await self.app(scope, replay_receive, send)


def create_app(runtime, token: str):
    if not isinstance(token, str) or len(token) < 24:
        raise ValueError("Supply a high-entropy bearer token of at least 24 characters")

    @asynccontextmanager
    async def lifespan(_):
        task = asyncio.create_task(runtime.serve_loop())
        yield
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await runtime.close()

    app = FastAPI(title="Agmina runtime research sidecar", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied, "Bearer " + token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

    @app.exception_handler(Exception)
    async def safe_error(request, exc):
        if isinstance(exc, (ValueError, ValidationError)):
            return JSONResponse({"error": "invalid_contract"}, status_code=422)
        if isinstance(exc, PermissionError):
            return JSONResponse({"error": "admission_denied"}, status_code=409)
        if isinstance(exc, KeyError):
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse({"error": "internal_error"}, status_code=500)

    # Known contract/admission errors must not be reraised by ServerErrorMiddleware
    # and printed with Pydantic input values into transport logs.
    for error_type in (ValueError, ValidationError, PermissionError, KeyError):
        app.add_exception_handler(error_type, safe_error)

    async def obj(request, fields):
        data = strict_json((await request.body()).decode(), max_bytes=8192)
        if set(data) != set(fields):
            raise ValueError("Unexpected API fields")
        return data

    @app.get("/v1/clock")
    async def clock():
        return {"clock_id": runtime.clock.id, "now_ns": runtime.clock.now_ns(),
                "tenant": runtime.config.tenant, "remote_clock_mapping_required": True}

    @app.post("/v1/sessions")
    async def session(request: Request):
        data = await obj(request, ("id", "task_revision"))
        return runtime.open_session(data["id"], data["task_revision"]).model_dump(mode="json")

    @app.post("/v1/sessions/advance")
    async def advance(request: Request):
        data = await obj(request, ("id", "expected_epoch", "task_revision", "close"))
        if type(data["expected_epoch"]) is not int or type(data["close"]) is not bool:
            raise ValueError("Invalid compare-and-swap arguments")
        return runtime.advance_session(data.pop("id"), **data).model_dump(mode="json")

    @app.post("/v1/sessions/heartbeat")
    async def heartbeat(request: Request):
        data = await obj(request, ("id", "expected_epoch", "buffer_until_ns"))
        if type(data["expected_epoch"]) is not int or (data["buffer_until_ns"] is not None and
                type(data["buffer_until_ns"]) is not int):
            raise ValueError("Invalid heartbeat")
        return runtime.heartbeat(data.pop("id"), **data).model_dump(mode="json")

    @app.post("/v1/jobs")
    async def submit(request: Request):
        raw = (await request.body()).decode()
        strict_json(raw, max_bytes=9_000_000)
        job = Job.model_validate_json(raw)
        return runtime.submit(job).model_dump(mode="json", exclude={"prediction_json"})

    @app.get("/v1/result")
    async def result(id: str):
        return runtime.result(id).model_dump(mode="json", exclude={"prediction_json"})

    @app.post("/v1/consume")
    async def consume(request: Request):
        data = await obj(request, ("job_id", "consumer_id"))
        return runtime.consume(data["job_id"], consumer_id=data["consumer_id"]).model_dump(mode="json")

    @app.post("/v1/cancel")
    async def cancel(request: Request):
        data = await obj(request, ("job_id",))
        return runtime.cancel(data["job_id"]).model_dump(mode="json", exclude={"prediction_json"})

    @app.get("/v1/metrics")
    async def metrics():
        return summarize(runtime)

    # Middleware added last is outermost; body cap also applies before authentication/JSON parsing.
    app.add_middleware(BoundedBody)
    return app
