"""Bounded exact-result cache ONLY for immutable historical queries.

Not temporal feature reuse, not a semantic state cache, not action caching.
Full evidence timestamps, session, epoch, task and pinned model contract enter key.
"""
from collections import OrderedDict

from .contracts import Job, ResultKind, fingerprint


class HistoricalCache:
    def __init__(self, entries: int, max_bytes: int, ttl_ns: int):
        self.entries, self.max_bytes, self.ttl_ns = entries, max_bytes, ttl_ns
        self.data = OrderedDict()
        self.bytes = 0

    def key(self, job: Job, contract_fingerprint: str):
        if not job.cacheable or job.result_kind != ResultKind.HISTORICAL:
            return None
        value = job.model_dump(mode="json")
        for k in ("id", "deadline_ns", "priority", "allowed_sites", "dependencies", "replace_key", "discardable"):
            value.pop(k, None)
        return fingerprint([contract_fingerprint, value])

    def get(self, key, now_ns):
        if key is None or key not in self.data:
            return None
        payload, computed_ns, size = self.data[key]
        if now_ns - computed_ns >= self.ttl_ns:
            self.data.pop(key)
            self.bytes -= size
            return None
        self.data.move_to_end(key)
        return payload, computed_ns

    def put(self, key, payload: str, computed_ns: int):
        if key is None or not self.entries:
            return
        size = len(payload.encode())
        if size > self.max_bytes:
            return
        if key in self.data:
            self.bytes -= self.data.pop(key)[2]
        while self.data and (len(self.data) >= self.entries or self.bytes + size > self.max_bytes):
            _, (_, _, removed) = self.data.popitem(last=False)
            self.bytes -= removed
        self.data[key] = (payload, computed_ns, size)
        self.bytes += size
