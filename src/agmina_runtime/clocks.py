"""Explicit clock mappings; no subtraction of unrelated monotonic clocks."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass


class Clock:
    def __init__(self):
        self.id = "clock-" + uuid.uuid4().hex
    def now_ns(self) -> int:
        return time.monotonic_ns()


class ManualClock:
    def __init__(self, now_ns=0, clock_id="fixture-clock"):
        self.id, self.value = clock_id, now_ns
    def now_ns(self):
        return self.value
    def advance_to(self, value):
        if value < self.value:
            raise ValueError("Cannot move clock backwards")
        self.value = value


@dataclass(frozen=True)
class ClockMap:
    source: str
    target: str
    offset_ns: int
    error_ns: int
    valid_until_ns: int

    def __post_init__(self):
        if not self.source or not self.target or any(type(x) is not int for x in
            (self.offset_ns, self.error_ns, self.valid_until_ns)) or self.error_ns < 0 or self.valid_until_ns < 0:
            raise ValueError("Explicit finite clock mapping required")

    def map(self, source_ns: int, *, target_clock: str, now_ns: int) -> tuple[int, int]:
        if type(source_ns) is not int or source_ns < 0 or type(now_ns) is not int or now_ns < 0:
            raise ValueError("Integer nonnegative clocks required")
        if self.error_ns < 0 or target_clock != self.target or now_ns > self.valid_until_ns:
            raise ValueError("Clock mapping is absent, expired or for a different coordinator")
        mapped = source_ns + self.offset_ns
        if mapped < 0:
            raise ValueError("Invalid mapped timestamp")
        return mapped, self.error_ns
