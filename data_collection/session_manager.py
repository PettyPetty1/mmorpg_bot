"""Utilities for orchestrating recording sessions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from config.paths import get_paths
from sdk.runtime import Session

ISO = "%Y%m%dT%H%M%SZ"


@dataclass
class SessionConfig:
    """Configuration parameters for a recording session."""

    name: Optional[str] = None
    fps: int = 30
    audio: bool = True
    inputs: bool = True
    system_metrics: bool = True


class SessionManager:
    """Create session directories and proxy lifecycle calls to ``Session``."""

    def __init__(self, cfg: SessionConfig) -> None:
        self.cfg = cfg
        self.paths = get_paths()
        self.paths.ensure_all()

        self.created_ts = datetime.now(timezone.utc)
        self.session_name = cfg.name or self.created_ts.strftime(ISO)

        self.session_dir = self.paths.session_dir(self.session_name)
        self.session_dir.mkdir(parents=True, exist_ok=True)

        self.meta_path = self.session_dir / "session_meta.json"
        self.session = Session(self.session_name)

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------
    def start(self) -> None:
        self.session.start()
        self._write_meta("running")

    def stop(self) -> None:
        self.session.stop()
        self._write_meta("stopped")

    # ------------------------------------------------------------------
    # Metadata persistence
    # ------------------------------------------------------------------
    def _write_meta(self, status: str) -> None:
        payload: Dict[str, Any] = {
            "status": status,
            "cfg": self.cfg.__dict__,
            "session_dir": str(self.session_dir),
            "created_ts": self.created_ts.strftime(ISO),
        }
        with self.meta_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)


__all__ = ["SessionConfig", "SessionManager"]