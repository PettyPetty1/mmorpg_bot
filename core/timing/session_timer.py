
from dataclasses import dataclass, field
from time import monotonic_ns

NS_PER_MS = 1_000_000

@dataclass
class SessionTimer:
    started_ns: int = 0
    stopped_ns: int = 0
    running: bool = False
    laps_ms: list[float] = field(default_factory=list)
    _last: int = 0

    def start(self):
        now = monotonic_ns()
        self.started_ns = now
        self._last = now
        self.running = True

    def lap(self) -> float:
        assert self.running
        now = monotonic_ns()
        d = (now - self._last) / NS_PER_MS
        self.laps_ms.append(d)
        self._last = now
        return d

    def stop(self) -> float:
        assert self.running
        self.stopped_ns = monotonic_ns()
        self.running = False
        return self.elapsed_ms

    @property
    def elapsed_ms(self) -> float:
        end = monotonic_ns() if self.running else self.stopped_ns
        return 0.0 if self.started_ns == 0 else (end - self.started_ns) / NS_PER_MS
