"""Core event models shared across the project."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

import time

import ulid
from pydantic import BaseModel, Field


def now_ts_ms() -> int:
    """Return the current timestamp in milliseconds."""

    return int(time.time() * 1000)


def new_event_id() -> str:
    """Generate a ULID based identifier for events."""

    return str(ulid.new())


class Event(BaseModel):
    """Canonical event model emitted by recorders and pipelines."""

    id: str = Field(default_factory=new_event_id)
    ts_ms: int = Field(default_factory=now_ts_ms)
    kind: Literal["frame", "input", "meta", "gamepad", "audio", "system"]
    session: str
    data: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"


class SessionMeta(BaseModel):
    """Metadata describing a recording session."""

    name: str
    created_ts_ms: int = Field(default_factory=now_ts_ms)
    game: Optional[str] = None
    notes: Optional[str] = None


def event_dump(event: Event) -> Dict[str, Any]:
    """Return a serialisable representation of ``event``.

    The project gradually migrated from Pydantic v1 to v2.  This helper hides
    the API differences so that call sites can unconditionally obtain a plain
    ``dict`` suitable for JSON serialisation.
    """

    if hasattr(event, "model_dump"):
        return event.model_dump()  # type: ignore[return-value]
    return event.dict()  # type: ignore[return-value]


__all__ = ["Event", "SessionMeta", "event_dump", "now_ts_ms", "new_event_id"]
