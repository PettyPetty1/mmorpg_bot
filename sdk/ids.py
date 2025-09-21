
from __future__ import annotations
import time, ulid
NS_PER_MS = 1_000_000
def now_monotonic_ns() -> int: return time.monotonic_ns()
def now_utc_ns() -> int: return time.time_ns()
def ms_since(start_ns: int) -> int: return (now_monotonic_ns() - start_ns) // NS_PER_MS
def new_ulid() -> str: return str(ulid.new())
