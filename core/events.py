from __future__ import annotations
from typing import Literal, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import time
import ulid


def now_ts_ms() -> int:
    return int(time.time() * 1000)


def new_event_id() -> str:
    return str(ulid.new())


class Event(BaseModel):
    id: str = Field(default_factory=new_event_id)
    ts_ms: int = Field(default_factory=now_ts_ms)
    kind: Literal["frame", "input", "meta"]  # extend as needed
    session: str
    data: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"


class SessionMeta(BaseModel):
    name: str
    created_ts_ms: int = Field(default_factory=now_ts_ms)
    game: Optional[str] = None
    notes: Optional[str] = None
