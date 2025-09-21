
from __future__ import annotations
from typing import Optional
class ScreenCap:
    def __init__(self): self.region=None; self.fps=30; self.started=False
    def configure(self, region: Optional[dict], fps: int) -> None: self.region, self.fps = region, fps
    def start(self) -> None: self.started=True
    def read(self): return None
    def stop(self) -> None: self.started=False
