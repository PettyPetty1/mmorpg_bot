
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
import json
from config.paths import ensure_dirs, DATA_ROOT
from sdk.runtime import Session

ISO = "%Y%m%dT%H%M%SZ"

@dataclass
class SessionConfig:
    name: str | None = None
    fps: int = 30
    audio: bool = True
    inputs: bool = True
    system_metrics: bool = True

class SessionManager:
    def __init__(self, cfg: SessionConfig):
        ensure_dirs()
        self.cfg = cfg
        self.ts = datetime.now(timezone.utc).strftime(ISO)
        self.session_dir = DATA_ROOT / "raw" / "sessions" / (cfg.name or self.ts)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.meta = self.session_dir / "session_meta.json"
        self.session = Session(self.session_dir.name)

    def start(self):
        self.session.start()
        self._write_meta("running")

    def stop(self):
        self.session.stop()
        self._write_meta("stopped")

    def _write_meta(self, status: str):
        meta = {
            "status": status,
            "cfg": self.cfg.__dict__,
            "session_dir": str(self.session_dir),
        }
        with open(self.meta, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
