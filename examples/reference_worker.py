"""Example stateless worker boundary. Uses a synthetic tensor function ONLY.

Replace compute() with one pinned model implementation in its separate GPU env.
This server does not download/load SAM/VLAs and does not execute any robot action.
"""
import asyncio
import hmac
import os

from fastapi import FastAPI, HTTPException, Request

from agmina_runtime.contracts import canonical, strict_json

app = FastAPI(docs_url=None, redoc_url=None)
lock = asyncio.Lock()


def compute(payload):
    # Deliberately not a robot policy. No semantic quality claims from this fixture.
    return {"fixture": True, "echo": payload}


@app.post("/infer")
async def infer(request: Request):
    token = os.environ.get("WORKER_TOKEN", "")
    if len(token) < 24 or not hmac.compare_digest(request.headers.get("authorization", ""), "Bearer " + token):
        raise HTTPException(401)
    data = strict_json((await request.body()).decode(), max_bytes=8_000_000)
    if set(data) != {"job_id", "session_id", "epoch", "task_revision", "operation", "evidence", "payload"}:
        raise HTTPException(422)
    async with lock:
        result = await asyncio.to_thread(compute, data["payload"])
    strict_json(canonical(result))
    return {"job_id": data["job_id"], "epoch": data["epoch"], "payload": result,
            "usage": {"cost_microusd": 0}}
