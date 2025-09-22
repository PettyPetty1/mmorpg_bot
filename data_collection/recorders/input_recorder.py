from __future__ import annotations
import time
import threading
from typing import Optional, Dict

from pynput import keyboard, mouse
from core.events import Event
from ..event_writer import JsonlWriter

# --------- XInput (Windows) via ctypes ----------
import ctypes
from ctypes import wintypes

# Try to load a usable XInput DLL
_XINPUT_DLL_CANDIDATES = [
    "xinput1_4.dll",  # Win8+
    "xinput1_3.dll",  # common redist
    "xinput9_1_0.dll",
    "xinput1_2.dll",
    "xinput1_1.dll",
]
_xi = None
for name in _XINPUT_DLL_CANDIDATES:
    try:
        _xi = ctypes.WinDLL(name)
        break
    except Exception:
        _xi = None

# XInput structures
class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", wintypes.WORD),
        ("bLeftTrigger", wintypes.BYTE),
        ("bRightTrigger", wintypes.BYTE),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]

class XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", wintypes.DWORD),
        ("Gamepad", XINPUT_GAMEPAD),
    ]

if _xi:
    _xi.XInputGetState.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_STATE)]
    _xi.XInputGetState.restype = wintypes.DWORD

# Button map for readability
BUTTONS = {
    0x0001: "DPAD_UP",
    0x0002: "DPAD_DOWN",
    0x0004: "DPAD_LEFT",
    0x0008: "DPAD_RIGHT",
    0x0010: "START",
    0x0020: "BACK",
    0x0040: "LEFT_THUMB",
    0x0080: "RIGHT_THUMB",
    0x0100: "LEFT_SHOULDER",
    0x0200: "RIGHT_SHOULDER",
    0x1000: "A",
    0x2000: "B",
    0x4000: "X",
    0x8000: "Y",
}
DEADZONE_L = 655
DEADZONE_R = 655
TRIGGER_DEADZONE = 5
OUTER_RING_L = 32767 
OUTER_RING_R = 32767

def _axis_norm(v: int, dead: int, maxmag: int = 32767) -> float:
    if abs(v) < dead:
        return 0.0
    # normalize to [-1, 1]
    return max(-1.0, min(1.0, v / maxmag))


class InputRecorder:
    """
    Records keyboard, mouse, and (if available) XInput gamepads.
    Emits 'input' events for keyboard & mouse, and 'gamepad' events
    on *changes* to gamepad state (buttons/axes/triggers).
    """
    def __init__(self, session: str, events_writer: JsonlWriter, gamepad_poll_hz: int = 125):
        self.session = session
        self.events_writer = events_writer
        self._k_listener: Optional[keyboard.Listener] = None
        self._m_listener: Optional[mouse.Listener] = None

        self._gp_thread: Optional[threading.Thread] = None
        self._gp_running = False
        self._gp_period = 1.0 / float(gamepad_poll_hz)
        self._last_gp: Dict[int, Dict] = {}  # controller idx -> last snapshot
        self._haptics_notice_sent = False

    # ---- lifecycle ----

    def start(self):
        # keyboard & mouse
        self._k_listener = keyboard.Listener(on_press=self._on_k_press, on_release=self._on_k_release)
        self._m_listener = mouse.Listener(on_move=self._on_m_move, on_click=self._on_m_click, on_scroll=self._on_m_scroll)
        self._k_listener.start()
        self._m_listener.start()

        # gamepads
        if _xi is None:
            self._emit_meta({"gamepad": {"xinput_available": False}})
        else:
            self._emit_meta({"gamepad": {"xinput_available": True}})
            self._gp_running = True
            self._gp_thread = threading.Thread(target=self._poll_gamepads, daemon=True)
            self._gp_thread.start()
            # haptics note (only once)
            if not self._haptics_notice_sent:
                self._emit_meta({"haptics_unavailable": "XInput does not expose vibration state; requires DLL proxy to intercept XInputSetState"})
                self._haptics_notice_sent = True

    def stop(self):
        try:
            if self._k_listener:
                self._k_listener.stop()
        except Exception:
            pass
        try:
            if self._m_listener:
                self._m_listener.stop()
        except Exception:
            pass
        self._gp_running = False

    # ---- keyboard callbacks ----

    def _on_k_press(self, key):
        ev = Event(kind="input", session=self.session, data={"device": "keyboard", "action": "press", "key": str(key)})
        self.events_writer.write(ev.model_dump())

    def _on_k_release(self, key):
        ev = Event(kind="input", session=self.session, data={"device": "keyboard", "action": "release", "key": str(key)})
        self.events_writer.write(ev.model_dump())

    # ---- mouse callbacks ----

    def _on_m_move(self, x, y):
        ev = Event(kind="input", session=self.session, data={"device": "mouse", "action": "move", "x": x, "y": y})
        self.events_writer.write(ev.model_dump())

    def _on_m_click(self, x, y, button, pressed):
        ev = Event(kind="input", session=self.session, data={"device": "mouse", "action": "click", "x": x, "y": y, "button": str(button), "pressed": bool(pressed)})
        self.events_writer.write(ev.model_dump())

    def _on_m_scroll(self, x, y, dx, dy):
        ev = Event(kind="input", session=self.session, data={"device": "mouse", "action": "scroll", "x": x, "y": y, "dx": dx, "dy": dy})
        self.events_writer.write(ev.model_dump())

    # ---- gamepad polling ----

    def _poll_gamepads(self):
        while self._gp_running:
            for idx in range(4):  # XInput supports up to 4 controllers
                s = XINPUT_STATE()
                res = _xi.XInputGetState(idx, ctypes.byref(s)) if _xi else 1
                if res != 0:
                    # controller not connected
                    if idx in self._last_gp:
                        del self._last_gp[idx]
                        self._emit_gamepad(idx, {"connected": False})
                    continue

                gp = s.Gamepad
                state = {
                    "connected": True,
                    "buttons": {name: bool(gp.wButtons & mask) for mask, name in BUTTONS.items()},
                    "lt": 0.0 if gp.bLeftTrigger < TRIGGER_DEADZONE else gp.bLeftTrigger / 255.0,
                    "rt": 0.0 if gp.bRightTrigger < TRIGGER_DEADZONE else gp.bRightTrigger / 255.0,
                    "lx": _axis_norm(gp.sThumbLX, DEADZONE_L),
                    "ly": _axis_norm(gp.sThumbLY, DEADZONE_L),
                    "rx": _axis_norm(gp.sThumbRX, DEADZONE_R),
                    "ry": _axis_norm(gp.sThumbRY, DEADZONE_R),
                }

                # Emit only on change
                if state != self._last_gp.get(idx):
                    self._last_gp[idx] = state
                    self._emit_gamepad(idx, state)

            time.sleep(self._gp_period)

    # ---- emit helpers ----

    def _emit_gamepad(self, idx: int, state: Dict):
        ev = Event(kind="gamepad", session=self.session, data={"index": idx, **state})
        self.events_writer.write(ev.model_dump())

    def _emit_meta(self, payload: Dict):
        ev = Event(kind="meta", session=self.session, data=payload)
        self.events_writer.write(ev.model_dump())
