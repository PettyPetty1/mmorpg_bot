from __future__ import annotations
import json
from pathlib import Path
from typing import Optional, IO
from threading import Lock
from .safe_io import ensure_dir  # we'll inline this helper below if you prefer

class JsonlWriter:
    """
    Minimal, robust JSONL writer with periodic flush.
    Not thread-safe across processes, but thread-safe within a process.
    """
    def __init__(self, out_path: Path, flush_every: int = 50):
        ensure_dir(out_path.parent)
        self._f: IO[str] = out_path.open("a", encoding="utf-8")
        self._n = 0
        self._flush_every = flush_every
        self._lock = Lock()

    def write(self, obj) -> None:
        line = json.dumps(obj, ensure_ascii=False)
        with self._lock:
            self._f.write(line + "\n")
            self._n += 1
            if self._n % self._flush_every == 0:
                self._f.flush()

    def close(self):
        with self._lock:
            try:
                self._f.flush()
            finally:
                self._f.close()


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)
