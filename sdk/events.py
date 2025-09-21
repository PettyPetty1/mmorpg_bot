
from __future__ import annotations
from pydantic import BaseModel
from typing import Literal, Optional
EventVersion = Literal["v1"]
class BaseEvent(BaseModel):
    v: EventVersion = "v1"
    event_id: str
    session_id: str
    wall_time_utc_ns: int
    ms_since_start: int
    type: str
class VideoFrame(BaseEvent):
    type: Literal["video.frame"] = "video.frame"
    frame_idx: int
    w: int
    h: int
    pixfmt: Literal["bgr8"] = "bgr8"
    path: Optional[str] = None
class AudioChunk(BaseEvent):
    type: Literal["audio.chunk"] = "audio.chunk"
    seq: int
    samples: int
    rate: int
class InputEvent(BaseEvent):
    type: Literal["input.event"] = "input.event"
    payload: dict
