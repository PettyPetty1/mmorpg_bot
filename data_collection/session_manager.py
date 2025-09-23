 
 from dataclasses import dataclass
 from datetime import datetime, timezone
 import json
 from config.paths import get_paths
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
         self.paths = get_paths()
         self.paths.ensure_all()
         self.cfg = cfg
         self.ts = datetime.now(timezone.utc).strftime(ISO)
         session_name = cfg.name or self.ts
         self.paths = get_paths()
         # ``get_paths`` ensures that the common directory tree exists, but we
         # still create the concrete session directory explicitly.
         self.session_name = cfg.name or self.ts
         self.session_dir = self.paths.session_dir(self.session_name)
         self.session_dir = self.paths.session_dir(session_name)
         self.session_dir.mkdir(parents=True, exist_ok=True)
         self.meta = self.session_dir / "session_meta.json"
         self.session = Session(session_name)
 
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
