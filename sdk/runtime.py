
from __future__ import annotations
from pathlib import Path
from .config import SDK_CONFIG
from .ids import new_ulid, now_monotonic_ns, now_utc_ns, ms_since
from .events import VideoFrame, AudioChunk, InputEvent
from .logging import JsonlWriter
class Session:
    def __init__(self, name: str | None = None):
        self.session_id = new_ulid()
        self.name = name or self.session_id
        self.start_ns = 0
        paths = SDK_CONFIG.paths
        self.session_dir = Path(paths.data_root) / "raw" / "sessions" / self.name
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.writer = JsonlWriter()
        self.writer.open(self.session_dir / "events.jsonl")
    def _base(self):
        return dict(session_id=self.session_id, wall_time_utc_ns=now_utc_ns(), ms_since_start=ms_since(self.start_ns))
    def start(self): self.start_ns = now_monotonic_ns()
    def emit_video(self, frame_idx:int,w:int,h:int,path:str|None=None):
        e = VideoFrame(event_id=new_ulid(), frame_idx=frame_idx, w=w, h=h, path=path, **self._base()); self.writer.write(e)
    def emit_audio(self, seq:int,samples:int,rate:int):
        e = AudioChunk(event_id=new_ulid(), seq=seq, samples=samples, rate=rate, **self._base()); self.writer.write(e)
    def emit_input(self, payload:dict):
        e = InputEvent(event_id=new_ulid(), payload=payload, **self._base()); self.writer.write(e)
    def stop(self): self.writer.close()
