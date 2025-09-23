
 """Tests for the input recorder's gamepad event emission."""
 
 from __future__ import annotations
 
 import sys
 import types
 
 
 def _ensure_pynput_stub() -> None:
     """Provide a minimal ``pynput`` stub if the real dependency is missing."""
 
     if "pynput" in sys.modules:
         return
 
     try:  # pragma: no cover - only exercised when the dependency exists
         import pynput  # type: ignore  # noqa: F401
     except ModuleNotFoundError:
         pynput_mod = types.ModuleType("pynput")
 
         class _Listener:  # pylint: disable=too-few-public-methods
             def __init__(self, *args, **kwargs):  # noqa: D401, ANN002, ANN003
                 self.args = args
                 self.kwargs = kwargs
 
             def start(self):  # noqa: D401
                 """No-op start method for the stub listener."""
 
             def stop(self):  # noqa: D401
                 """No-op stop method for the stub listener."""
 
         keyboard_mod = types.ModuleType("pynput.keyboard")
         keyboard_mod.Listener = _Listener
 
         mouse_mod = types.ModuleType("pynput.mouse")
         mouse_mod.Listener = _Listener
 
         pynput_mod.keyboard = keyboard_mod
         pynput_mod.mouse = mouse_mod
 
         sys.modules["pynput"] = pynput_mod
         sys.modules["pynput.keyboard"] = keyboard_mod
         sys.modules["pynput.mouse"] = mouse_mod
 
 
 _ensure_pynput_stub()
 
 from core.events import Event
 from data_collection.recorders.input_recorder import InputRecorder
 
 
 class _WriterStub:
     """Captures event payloads written by the recorder."""
 
     def __init__(self) -> None:
         self.records = []
 
     def write(self, payload):  # type: ignore[no-untyped-def]
         self.records.append(payload)
 
 
 def test_event_accepts_gamepad_kind():
     event = Event(kind="gamepad", session="sess", data={"index": 0, "connected": True})
 
     assert event.kind == "gamepad"
     assert event.data["index"] == 0
     assert event.data["connected"] is True
 
 
 def test_input_recorder_emits_gamepad_event():
     writer = _WriterStub()
     recorder = InputRecorder(session="sess", events_writer=writer)
 
     state = {
         "connected": True,
         "buttons": {"A": True},
         "lt": 0.25,
         "rt": 0.0,
     }
 
     recorder._emit_gamepad(1, state)
 
     assert len(writer.records) == 1
 
     event_dict = writer.records[0]
     assert event_dict["kind"] == "gamepad"
     assert event_dict["session"] == "sess"
 
     payload = event_dict["data"]
     assert payload["index"] == 1
     assert payload["connected"] is True
     assert payload["buttons"] == {"A": True}
     assert payload["lt"] == 0.25
