+"""System audio recorder using :mod:`sounddevice`.
+
+The implementation favours Windows WASAPI loopback capture so that the
+game's speakers output (for example ``"2-Realtek(R) Audio"``) can be
+recorded without requiring virtual cables.  Audio samples are persisted as
+``.wav`` chunks alongside JSONL events describing the captured audio.
+
+Example usage::
+
+    recorder = AudioRecorder(session="demo", session_dir=Path("/tmp/demo"), events_writer=writer)
+    recorder.start()
+    ...  # do work
+    recorder.stop()
+
+The recorder is self-contained – it spins up an internal thread for chunk
+writing and emits structured events compatible with :mod:`core.events`.
+"""
+
+from __future__ import annotations
+
+import contextlib
+import queue
+import threading
+import wave
+from pathlib import Path
+from typing import Dict, List, Optional, Tuple, Union
+
+import numpy as np
+
+import sounddevice as sd
+
+from core.events import Event
+from ..event_writer import JsonlWriter, ensure_dir
+
+# Type alias for user supplied device identifiers
+DeviceSpec = Union[int, str, None]
+
+
+class AudioRecorder:
+    """Capture system audio into chunked ``.wav`` files and emit events.
+
+    Parameters
+    ----------
+    session:
+        Logical session identifier used for emitted events.
+    session_dir:
+        Directory where ``audio/`` will be created to store wave chunks.
+    events_writer:
+        Writer used for structured event emission.
+    device:
+        Optional device specifier (index or substring match).  Useful for
+        targeting Windows speaker outputs such as ``"2-Realtek(R) Audio"``.
+    samplerate:
+        Target sampling rate for capture.
+    channels:
+        Requested channel count.  If ``None`` we derive a sensible default
+        from the selected device capabilities.
+    blocksize:
+        Buffer size (in frames) requested from ``sounddevice``.
+    chunk_duration:
+        Duration in seconds for each emitted audio chunk.
+    dtype:
+        Sample dtype requested from the backend.
+    prefer_loopback:
+        When ``True`` (default) and the device exposes only output channels
+        on a WASAPI host API we enable loopback recording automatically.
+    """
+
+    def __init__(
+        self,
+        session: str,
+        session_dir: Path,
+        events_writer: JsonlWriter,
+        *,
+        device: DeviceSpec = None,
+        samplerate: int = 48_000,
+        channels: Optional[int] = None,
+        blocksize: int = 2048,
+        chunk_duration: float = 1.0,
+        dtype: str = "float32",
+        prefer_loopback: bool = True,
+    ) -> None:
+        self.session = session
+        self.session_dir = Path(session_dir)
+        self.events_writer = events_writer
+
+        self._device_spec = device
+        self._samplerate = samplerate
+        self._requested_channels = channels
+        self._blocksize = blocksize
+        self._chunk_duration = max(0.1, float(chunk_duration))
+        self._dtype = dtype
+        self._prefer_loopback = prefer_loopback
+
+        self._chunk_frames = max(1, int(round(self._samplerate * self._chunk_duration)))
+        self._audio_dir = self.session_dir / "audio"
+        ensure_dir(self._audio_dir)
+
+        self._queue: "queue.Queue[Optional[np.ndarray]]" = queue.Queue()
+        self._writer_thread: Optional[threading.Thread] = None
+        self._stream: Optional[sd.InputStream] = None
+        self._running = False
+
+        self._seq = 0
+        self._device_info: Optional[Dict] = None
+        self._hostapi_name: Optional[str] = None
+        self._channels = channels or 0
+
+        self._pending: List[np.ndarray] = []
+        self._pending_samples = 0
+        self._status_messages: "queue.Queue[str]" = queue.Queue()
+
+    # ------------------------------------------------------------------
+    # Public API
+    # ------------------------------------------------------------------
+    def start(self) -> None:
+        """Start audio capture."""
+
+        device_index, info, channels, extra = self._resolve_device()
+        self._device_info = info
+        self._channels = channels
+
+        if device_index is None:
+            # ``sounddevice`` interprets ``None`` as default input device.
+            sd.check_input_settings(
+                samplerate=self._samplerate,
+                channels=self._channels,
+                dtype=self._dtype,
+                extra_settings=extra,
+            )
+        else:
+            sd.check_input_settings(
+                device=device_index,
+                samplerate=self._samplerate,
+                channels=self._channels,
+                dtype=self._dtype,
+                extra_settings=extra,
+            )
+
+        self._running = True
+        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
+        self._writer_thread.start()
+
+        self._stream = self._create_stream(device_index, channels, extra)
+        self._stream.start()
+
+        self._emit_meta("started")
+
+    def stop(self) -> None:
+        """Stop capture and flush pending buffers."""
+
+        self._running = False
+        if self._stream is not None:
+            with contextlib.suppress(Exception):
+                self._stream.stop()
+                self._stream.close()
+        self._stream = None
+
+        # unblock writer thread and wait for completion
+        self._queue.put(None)
+        if self._writer_thread is not None:
+            self._writer_thread.join(timeout=5.0)
+        self._writer_thread = None
+        self._emit_meta("stopped")
+
+    # ------------------------------------------------------------------
+    # Implementation helpers
+    # ------------------------------------------------------------------
+    def _resolve_device(self) -> Tuple[Optional[int], Dict, int, Optional[object]]:
+        """Resolve user supplied device spec into ``sounddevice`` arguments."""
+
+        devices = sd.query_devices()
+        index: Optional[int] = None
+
+        if isinstance(self._device_spec, int):
+            index = self._device_spec
+        elif isinstance(self._device_spec, str):
+            lowered = self._device_spec.lower()
+            for i, dev in enumerate(devices):
+                if lowered in dev.get("name", "").lower():
+                    index = i
+                    break
+            if index is None:
+                raise RuntimeError(f"Audio device '{self._device_spec}' not found")
+        else:
+            try:
+                default_input = sd.default.device[0]
+            except Exception:
+                default_input = None
+            if default_input is not None and default_input >= 0:
+                index = default_input
+
+        if index is None:
+            if not devices:
+                raise RuntimeError("No audio devices available")
+            info = devices[0]
+            index = 0
+        else:
+            info = sd.query_devices(index)
+
+        hostapis = sd.query_hostapis()
+        hostapi_name = None
+        hostapi_index = info.get("hostapi") if isinstance(info, dict) else None
+        if hostapi_index is not None and 0 <= hostapi_index < len(hostapis):
+            hostapi_name = hostapis[hostapi_index].get("name")
+        self._hostapi_name = hostapi_name
+
+        max_input = int(info.get("max_input_channels", 0)) if isinstance(info, dict) else 0
+        max_output = int(info.get("max_output_channels", 0)) if isinstance(info, dict) else 0
+
+        extra = None
+        derived_channels = self._requested_channels or max_input or max_output or 1
+
+        if max_input == 0 and max_output > 0:
+            if self._prefer_loopback and hostapi_name and "wasapi" in hostapi_name.lower():
+                extra = sd.WasapiSettings(loopback=True)
+                derived_channels = min(derived_channels, max_output) or max_output or 1
+            else:
+                raise RuntimeError("Selected device does not expose input channels")
+        else:
+            if max_input > 0:
+                derived_channels = min(derived_channels, max_input)
+
+        derived_channels = max(1, int(derived_channels))
+
+        return index, info, derived_channels, extra
+
+    def _create_stream(self, device: Optional[int], channels: int, extra_settings: Optional[object]):
+        return sd.InputStream(
+            samplerate=self._samplerate,
+            blocksize=self._blocksize,
+            dtype=self._dtype,
+            device=device,
+            channels=channels,
+            callback=self._audio_callback,
+            extra_settings=extra_settings,
+        )
+
+    def _audio_callback(self, indata, frames, time_info, status) -> None:  # pragma: no cover - exercised indirectly
+        if status:
+            self._status_messages.put(str(status))
+        # copy to ensure lifetime beyond callback
+        self._queue.put(indata.copy())
+
+    def _writer_loop(self) -> None:
+        while True:
+            try:
+                block = self._queue.get(timeout=0.5)
+            except queue.Empty:
+                if not self._running:
+                    break
+                continue
+
+            if block is None:
+                break
+
+            self._pending.append(block)
+            self._pending_samples += len(block)
+
+            while self._pending_samples >= self._chunk_frames:
+                chunk = self._pop_samples(self._chunk_frames)
+                if chunk.size:
+                    self._write_chunk(chunk)
+
+        # Flush any remaining samples as a final chunk.
+        if self._pending_samples:
+            chunk = self._pop_samples(self._pending_samples)
+            if chunk.size:
+                self._write_chunk(chunk)
+
+        self._pending.clear()
+        self._pending_samples = 0
+
+    def _pop_samples(self, n_samples: int) -> np.ndarray:
+        needed = n_samples
+        parts: List[np.ndarray] = []
+        while needed > 0 and self._pending:
+            current = self._pending[0]
+            if len(current) <= needed:
+                parts.append(current)
+                needed -= len(current)
+                self._pending_samples -= len(current)
+                self._pending.pop(0)
+            else:
+                parts.append(current[:needed])
+                self._pending[0] = current[needed:]
+                self._pending_samples -= needed
+                needed = 0
+        if not parts:
+            return np.empty((0, self._channels), dtype=np.float32)
+        return np.concatenate(parts, axis=0)
+
+    def _drain_status(self) -> List[str]:
+        messages: List[str] = []
+        while True:
+            try:
+                messages.append(self._status_messages.get_nowait())
+            except queue.Empty:
+                break
+        return messages
+
+    def _write_chunk(self, chunk: np.ndarray) -> None:
+        fname = f"audio_{self._seq:06d}.wav"
+        fpath = self._audio_dir / fname
+
+        pcm = np.clip(chunk, -1.0, 1.0)
+        pcm = (pcm * 32767.0).astype(np.int16)
+
+        with wave.open(str(fpath), "wb") as wf:
+            wf.setnchannels(self._channels)
+            wf.setsampwidth(2)  # int16
+            wf.setframerate(self._samplerate)
+            wf.writeframes(pcm.tobytes())
+
+        event_payload = {
+            "seq": self._seq,
+            "path": fname,
+            "samples": int(chunk.shape[0]),
+            "rate": self._samplerate,
+            "channels": self._channels,
+        }
+        status_messages = self._drain_status()
+        if status_messages:
+            event_payload["status"] = status_messages
+
+        event = Event(kind="audio", session=self.session, data=event_payload)
+        self.events_writer.write(event.dict())
+
+        self._seq += 1
+
+    def _emit_meta(self, state: str) -> None:
+        info = self._device_info or {}
+        meta = {
+            "audio": {
+                "state": state,
+                "samplerate": self._samplerate,
+                "chunk_frames": self._chunk_frames,
+                "blocksize": self._blocksize,
+                "dtype": self._dtype,
+                "device": info.get("name"),
+                "channels": self._channels,
+                "hostapi": self._hostapi_name,
+            }
+        }
+        event = Event(kind="meta", session=self.session, data=meta)
+        self.events_writer.write(event.dict())
+
+    # Convenience for tests / callers ----------------------------------
+    @staticmethod
+    def list_devices() -> List[Dict]:
+        """Return the list of audio devices reported by ``sounddevice``."""
+
+        return sd.query_devices()
 
EOF
)
