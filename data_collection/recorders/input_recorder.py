"""Keyboard, mouse and gamepad event capture."""

from __future__ import annotations

import contextlib
import threading
import time
from typing import Any, Dict, List, Optional

from core.events import Event, event_dump

from ..event_writer import JsonlWriter

try:  # Optional dependency - not always available in CI containers
    from pynput import keyboard as _pynput_keyboard  # type: ignore
except Exception:  # pragma: no cover - defensive guard
    _pynput_keyboard = None  # type: ignore

try:  # Optional dependency - not always available in CI containers
    from pynput import mouse as _pynput_mouse  # type: ignore
except Exception:  # pragma: no cover - defensive guard
    _pynput_mouse = None  # type: ignore

try:  # Optional dependency for gamepad support
    import inputs as _inputs  # type: ignore
except Exception:  # pragma: no cover - defensive guard
    _inputs = None  # type: ignore


class InputRecorder:
    """Capture keyboard, mouse and (optionally) gamepad events.

    The implementation is intentionally defensive – every dependency is
    optional and the recorder degrades gracefully when a backend is
    unavailable.  Emitted events follow the shared :class:`~core.events.Event`
    schema with ``kind`` set to ``"input"`` for keyboard/mouse events and
    ``"gamepad"`` for controller telemetry.
    """

    def __init__(
        self,
        session: str,
        events_writer: JsonlWriter,
        *,
        capture_keyboard: bool = True,
        capture_mouse: bool = True,
        capture_gamepad: bool = True,
        mouse_move_interval: float = 0.05,
    ) -> None:
        self.session = session
        self.events_writer = events_writer

        self.capture_keyboard = capture_keyboard
        self.capture_mouse = capture_mouse
        self.capture_gamepad = capture_gamepad
        self._mouse_move_interval = max(0.0, mouse_move_interval)

        self._keyboard_listener: Optional[Any] = None
        self._mouse_listener: Optional[Any] = None
        self._gamepad_thread: Optional[threading.Thread] = None

        self._stop_event = threading.Event()
        self._running = False

        self._gamepad_devices: List[Dict[str, Any]] = []

        self._status_lock = threading.Lock()
        self._status_messages: List[str] = []

        self._last_mouse_move = 0.0

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start capturing events."""

        if self._running:
            self._record_status("start() called while recorder already running")
            self._emit_meta("started")
            return

        self._running = True
        self._stop_event.clear()
        self._gamepad_devices = []

        self._prepare_keyboard()
        self._prepare_mouse()
        self._prepare_gamepad()

        self._emit_meta("started")

    def stop(self) -> None:
        """Stop capturing events and release resources."""

        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._keyboard_listener is not None:
            with contextlib.suppress(Exception):
                self._keyboard_listener.stop()
            self._keyboard_listener = None

        if self._mouse_listener is not None:
            with contextlib.suppress(Exception):
                self._mouse_listener.stop()
            self._mouse_listener = None

        if self._gamepad_thread is not None:
            self._gamepad_thread.join(timeout=0.5)
            self._gamepad_thread = None

        self._emit_meta("stopped")

    # ------------------------------------------------------------------
    # Backend preparation helpers
    # ------------------------------------------------------------------
    def _prepare_keyboard(self) -> None:
        if not self.capture_keyboard:
            self._record_status("keyboard capture disabled by configuration")
            return

        if _pynput_keyboard is None:
            self._record_status("pynput.keyboard unavailable; keyboard events disabled")
            return

        self._keyboard_listener = _pynput_keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._keyboard_listener.start()

    def _prepare_mouse(self) -> None:
        if not self.capture_mouse:
            self._record_status("mouse capture disabled by configuration")
            return

        if _pynput_mouse is None:
            self._record_status("pynput.mouse unavailable; mouse events disabled")
            return

        self._mouse_listener = _pynput_mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click,
            on_scroll=self._on_mouse_scroll,
        )
        self._mouse_listener.start()

    def _prepare_gamepad(self) -> None:
        if not self.capture_gamepad:
            self._record_status("gamepad capture disabled by configuration")
            return

        if _inputs is None:
            self._record_status("inputs library unavailable; gamepad events disabled")
            return

        try:
            devices = list(_inputs.devices.gamepads)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - hardware dependent
            self._record_status(f"gamepad discovery failed: {exc}")
            return

        if not devices:
            self._record_status("no gamepad devices detected")
            return

        self._gamepad_devices = [
            {
                "index": idx,
                "name": str(
                    getattr(dev, "name", None)
                    or getattr(dev, "device", None)
                    or f"gamepad_{idx}"
                ),
            }
            for idx, dev in enumerate(devices)
        ]

        self._gamepad_thread = threading.Thread(
            target=self._gamepad_loop,
            args=(devices,),
            name="gamepad-recorder",
            daemon=True,
        )
        self._gamepad_thread.start()

    # ------------------------------------------------------------------
    # Keyboard callbacks
    # ------------------------------------------------------------------
    def _on_key_press(self, key) -> None:  # pragma: no cover - requires OS hooks
        self._emit_input_event(
            {
                "device": "keyboard",
                "event": "press",
                "key": self._format_key(key),
            }
        )

    def _on_key_release(self, key) -> None:  # pragma: no cover - requires OS hooks
        self._emit_input_event(
            {
                "device": "keyboard",
                "event": "release",
                "key": self._format_key(key),
            }
        )

    # ------------------------------------------------------------------
    # Mouse callbacks
    # ------------------------------------------------------------------
    def _on_mouse_move(self, x: float, y: float) -> None:  # pragma: no cover - requires OS hooks
        now = time.monotonic()
        if self._mouse_move_interval > 0.0 and (now - self._last_mouse_move) < self._mouse_move_interval:
            return
        self._last_mouse_move = now
        self._emit_input_event(
            {
                "device": "mouse",
                "event": "move",
                "position": {"x": x, "y": y},
            }
        )

    def _on_mouse_click(
        self, x: float, y: float, button, pressed: bool
    ) -> None:  # pragma: no cover - requires OS hooks
        self._emit_input_event(
            {
                "device": "mouse",
                "event": "press" if pressed else "release",
                "button": getattr(button, "name", str(button)),
                "position": {"x": x, "y": y},
            }
        )

    def _on_mouse_scroll(
        self, x: float, y: float, dx: float, dy: float
    ) -> None:  # pragma: no cover - requires OS hooks
        self._emit_input_event(
            {
                "device": "mouse",
                "event": "scroll",
                "position": {"x": x, "y": y},
                "delta": {"dx": dx, "dy": dy},
            }
        )

    # ------------------------------------------------------------------
    # Gamepad polling
    # ------------------------------------------------------------------
    def _gamepad_loop(self, devices) -> None:  # pragma: no cover - hardware dependent
        assert _inputs is not None

        device_map = {id(dev): idx for idx, dev in enumerate(devices)}

        while not self._stop_event.is_set():
            try:
                events = _inputs.get_gamepad()  # type: ignore[attr-defined]
            except Exception as exc:
                self._record_status(f"gamepad error: {exc}")
                break

            for event in events:
                if self._stop_event.is_set():
                    break
                if getattr(event, "ev_type", "") == "Sync":
                    continue

                idx = device_map.get(id(getattr(event, "device", None)), 0)
                payload: Dict[str, Any] = {
                    "device": "gamepad",
                    "index": idx,
                    "event": getattr(event, "ev_type", "").lower() or "unknown",
                    "code": getattr(event, "code", None),
                    "state": getattr(event, "state", None),
                }
                ts = getattr(event, "timestamp", None)
                if ts is not None:
                    payload["timestamp"] = ts

                self._emit_event("gamepad", payload)

        self._record_status("gamepad loop stopped")

    # ------------------------------------------------------------------
    # Event emission helpers
    # ------------------------------------------------------------------
    def _emit_input_event(self, payload: Dict[str, Any]) -> None:
        self._emit_event("input", payload)

    def _emit_event(self, kind: str, payload: Dict[str, Any]) -> None:
        statuses = self._consume_statuses()
        if statuses:
            payload = dict(payload)
            payload["status"] = statuses

        event = Event(kind=kind, session=self.session, data=payload)
        self.events_writer.write(event_dump(event))

    def _emit_meta(self, state: str) -> None:
        payload: Dict[str, Any] = {
            "inputs": {
                "state": state,
                "keyboard": self.capture_keyboard and _pynput_keyboard is not None,
                "mouse": self.capture_mouse and _pynput_mouse is not None,
                "gamepad": self.capture_gamepad and bool(self._gamepad_devices),
            }
        }

        if self._gamepad_devices:
            payload["inputs"]["gamepads"] = list(self._gamepad_devices)

        statuses = self._consume_statuses()
        if statuses:
            payload["inputs"]["status"] = statuses

        event = Event(kind="meta", session=self.session, data=payload)
        self.events_writer.write(event_dump(event))

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _format_key(self, key: Any) -> str:
        try:
            char = key.char  # type: ignore[attr-defined]
        except AttributeError:
            char = None
        if char:
            return char
        return str(key)

    def _record_status(self, message: str) -> None:
        with self._status_lock:
            self._status_messages.append(message)

    def _consume_statuses(self) -> List[str]:
        with self._status_lock:
            if not self._status_messages:
                return []
            messages = list(self._status_messages)
            self._status_messages.clear()
            return messages