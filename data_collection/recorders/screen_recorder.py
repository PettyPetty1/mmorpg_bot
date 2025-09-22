from __future__ import annotations
from pathlib import Path
from typing import Optional, Tuple
import time
import threading

# Capture backends
try:
    import dxcam  # fast; Windows DXGI
    _DX = True
except Exception:
    _DX = False
    from mss import mss

from PIL import Image
import numpy as np

# Hotkeys / window handle
from pynput import keyboard
import ctypes
from ctypes import wintypes

from core.events import Event
from ..event_writer import JsonlWriter, ensure_dir


# --------- Win32 helpers (window → screen region) ----------

user32 = ctypes.WinDLL("user32", use_last_error=True)

class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

def _get_cursor_pos() -> Tuple[int, int]:
    pt = POINT()
    if not user32.GetCursorPos(ctypes.byref(pt)):
        raise ctypes.WinError(ctypes.get_last_error())
    return pt.x, pt.y

def _window_from_point(x: int, y: int) -> int:
    hwnd = user32.WindowFromPoint(POINT(x, y))
    return hwnd

def _get_client_rect_on_screen(hwnd: int) -> Tuple[int, int, int, int]:
    # client rect (0,0)-(w,h) in client coords
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    # Map client (0,0) to screen
    pt = POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    left, top = pt.x, pt.y
    right, bottom = left + rect.right, top + rect.bottom
    return left, top, right, bottom


class ScreenRecorder:
    """
    Captures frames to disk and emits 'frame' events containing metadata.
    New features:
      - Global hotkey F9: lock capture region to the window under the mouse.
      - Frameless windows supported (client rect mapped to screen).
    """
    def __init__(
        self,
        session: str,
        session_dir: Path,
        events_writer: JsonlWriter,
        region: Optional[Tuple[int, int, int, int]] = None,  # (left, top, right, bottom)
        target_fps: int = 15,
    ):
        self.session = session
        self.session_dir = session_dir
        self.events_writer = events_writer
        self._frames_dir = session_dir / "frames"
        ensure_dir(self._frames_dir)

        self._target_fps = target_fps
        self._delay = 1.0 / max(1, target_fps)

        self._region_lock = threading.Lock()
        self._region: Optional[Tuple[int, int, int, int]] = region  # dynamic
        self._running = False
        self._idx = 0

        # Start backend
        if _DX:
            self._cam = dxcam.create(output_idx=0)
            # We always start; region is applied per grab (get_latest_frame crops when provided to start(),
            # but we want dynamic re-lock via F9, so we use full capture and crop ourselves if needed).
            self._cam.start(target_fps=target_fps)
        else:
            self._cam = mss()

        # Hotkey listener for window lock (F9)
        self._kb_listener = keyboard.Listener(on_press=self._on_key_press)
        self._kb_listener.start()

        # Announce initial region
        self._emit_meta_region()

    # ------------- Hotkey handling ------------------

    def _on_key_press(self, key):
        try:
            if key == keyboard.Key.f9:
                # Lock region to the window under the cursor
                x, y = _get_cursor_pos()
                hwnd = _window_from_point(x, y)
                if hwnd:
                    new_region = _get_client_rect_on_screen(hwnd)
                    with self._region_lock:
                        self._region = new_region
                    self._emit_meta_region()
        except Exception:
            # don't crash the recorder if hotkey fails
            pass

    def _emit_meta_region(self):
        with self._region_lock:
            r = self._region
        data = {"target_fps": self._target_fps}
        if r:
            l, t, rgt, btm = r
            data.update({"region": {"left": l, "top": t, "right": rgt, "bottom": btm}})
        else:
            data.update({"region": None})
        ev = Event(kind="meta", session=self.session, data=data)
        # Use model_dump for pydantic v2
        self.events_writer.write(ev.model_dump())

    # ------------- Capture helpers ------------------

    def _grab_fullscreen_dx(self) -> Image.Image:
        frame = self._cam.get_latest_frame()
        if frame is None:
            raise RuntimeError("dxcam returned no frame")
        # dxcam gives numpy array (H, W, 3) in BGR
        return Image.fromarray(frame[:, :, ::-1])  # -> RGB

    def _grab_region_mss(self, region: Optional[Tuple[int, int, int, int]]) -> Image.Image:
        mon = self._cam.monitors[1]
        if region:
            left, top, right, bottom = region
            bbox = {"left": left, "top": top, "width": right - left, "height": bottom - top}
        else:
            bbox = {"left": mon["left"], "top": mon["top"], "width": mon["width"], "height": mon["height"]}
        shot = self._cam.grab(bbox)
        return Image.frombytes("RGB", shot.size, shot.rgb)

    def _crop_if_needed(self, img: Image.Image) -> Image.Image:
        with self._region_lock:
            region = self._region
        if not region:
            return img
        left, top, right, bottom = region
        # Crop relative to screen origin; dxcam returns full screen
        # We need to be careful: if monitor is not at (0,0), dxcam still returns
        # a full image positioned at (0,0). For multi-monitor with negative coords,
        # consider offset handling later.
        w, h = img.size
        # Clamp
        left_c = max(0, min(w, left))
        top_c = max(0, min(h, top))
        right_c = max(left_c, min(w, right))
        bottom_c = max(top_c, min(h, bottom))
        return img.crop((left_c, top_c, right_c, bottom_c))

    # ------------- Main loop ------------------

    def run(self):
        self._running = True
        while self._running:
            t0 = time.time()
            try:
                if _DX:
                    img = self._grab_fullscreen_dx()
                    img = self._crop_if_needed(img)
                else:
                    with self._region_lock:
                        r = self._region
                    img = self._grab_region_mss(r)

                fname = f"frame_{self._idx:06d}.png"
                fpath = self._frames_dir / fname
                img.save(fpath, format="PNG")

                ev = Event(
                    kind="frame",
                    session=self.session,
                    data={"frame_idx": self._idx, "path": str(fpath.name)},
                )
                self.events_writer.write(ev.model_dump())

                self._idx += 1
            except Exception:
                # You may want to log this; avoid hard-crash to allow clean stop
                break

            dt = time.time() - t0
            if dt < self._delay:
                time.sleep(self._delay - dt)

    def stop(self):
        self._running = False
        # dxcam has .stop(); MSS does not
        if _DX and hasattr(self._cam, "stop"):
            try:
                self._cam.stop()
            except Exception:
                pass
        try:
            self._kb_listener.stop()
        except Exception:
            pass
