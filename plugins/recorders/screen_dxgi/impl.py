
from __future__ import annotations
from typing import Optional, Tuple

# optional deps; safe import even if missing
try:
    import dxcam  # type: ignore
except Exception:
    dxcam = None

class ScreenCapDXGI:
    """DXGI-based screen capture (Windows). Implements ScreenRecorder contract.
    read() returns a numpy ndarray (BGR) or None if unavailable.
    """
    def __init__(self):
        self.fps = 30
        self.region = None
        self.camera = None

    def configure(self, region: Optional[dict], fps: int) -> None:
        self.region, self.fps = region, fps

    def start(self) -> None:
        if dxcam:
            self.camera = dxcam.create(output_idx=0)
        else:
            self.camera = None

    def read(self):
        if not self.camera:
            return None
        # region: dict with x,y,w,h -> translate to (left, top, right, bottom) if provided
        reg = None
        if self.region:
            x, y, w, h = self.region.get("x",0), self.region.get("y",0), self.region.get("w",0), self.region.get("h",0)
            reg = (x, y, x+w, y+h)
        frame = self.camera.grab(region=reg)
        return frame  # numpy array in BGRA; caller may convert/resize

    def stop(self) -> None:
        self.camera = None
