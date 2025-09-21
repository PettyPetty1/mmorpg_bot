
from __future__ import annotations
from pathlib import Path
class JsonlEventWriter:
    def __init__(self): self.f=None
    def open(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True); self.f = open(path, "a", encoding="utf-8")
    def write(self, event) -> None:
        self.f.write(event.model_dump_json()); self.f.write("\n"); self.f.flush()
    def close(self) -> None:
        if self.f: self.f.close(); self.f=None
