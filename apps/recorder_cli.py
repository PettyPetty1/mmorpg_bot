 from __future__ import annotations
 import threading
 import signal
 import sys
 from pathlib import Path
 from typing import Optional
 import typer
 
 from core.events import Event, SessionMeta
 from data_collection.event_writer import JsonlWriter, ensure_dir
 
 # Prefer new package layout: data_collection/recorders/*.py
 # Fall back to legacy locations if needed.
 try:
     from data_collection.recorders.screen_recorder import ScreenRecorder
 except ModuleNotFoundError:  # fallback if recorders/ isn't present
     from data_collection.recorders.screen_recorder import ScreenRecorder  # type: ignore
 
 try:
     from data_collection.recorders.input_recorder import InputRecorder
 except ModuleNotFoundError:  # fallback if recorders/ isn't present
     from data_collection.recorders.input_recorder import InputRecorder  # type: ignore
 
 try:
     from data_collection.recorders.audio_recorder import AudioRecorder
 except ModuleNotFoundError:  # optional dependency
     AudioRecorder = None  # type: ignore
 
 # Centralized paths (SDK/env/defaults)
 from config.paths import get_paths, session_events_path, ensure_session_io
 
 app = typer.Typer(add_completion=False, no_args_is_help=True)
 
 @app.command()
 def main(
     name: str = typer.Option(..., "--name", "-n", help="Session name, e.g. dev_smoke"),
     fps: int = typer.Option(12, help="Target FPS for screen capture"),
     left: int = typer.Option(None, help="Capture region left"),
     top: int = typer.Option(None, help="Capture region top"),
     right: int = typer.Option(None, help="Capture region right"),
     bottom: int = typer.Option(None, help="Capture region bottom"),
     inputs: bool = typer.Option(True, help="Record keyboard/mouse inputs"),
     audio: bool = typer.Option(True, help="Record system audio (WASAPI loopback when available)"),
     audio_device: Optional[str] = typer.Option(
         None,
         "--audio-device",
         help="Audio device index or substring, e.g. '2-Realtek(R) Audio'",
     ),
     audio_chunk: float = typer.Option(1.0, help="Audio chunk duration in seconds"),
 ):
     """
     Starts a simple recording session:
     - Writes events.jsonl (via config.paths.session_events_path)
     - Saves frames/ PNGs under the centralized session directory
     - (Optionally) streams input events
     """
     # Resolve all directories via centralized config
     paths = get_paths()              # honors SDK -> ENV -> platform defaults
     ensure_session_io(name)          # creates session dir + frames subdir
 
     session_dir = paths.session_dir(name)
     events_path = session_events_path(name)
 
     # Ensure events file parent exists (double-safe)
     ensure_dir(session_dir)
 
     writer = JsonlWriter(events_path, flush_every=25)
 
     # Write a meta event
     meta = SessionMeta(name=name)
     writer.write(Event(kind="meta", session=name, data=meta.dict()).dict())
 
     region = None
     if all(v is not None for v in (left, top, right, bottom)):
         region = (left, top, right, bottom)
 
     screen = ScreenRecorder(
         session=name,
         session_dir=session_dir,
         events_writer=writer,
         region=region,
         target_fps=fps,
     )
     input_rec = InputRecorder(session=name, events_writer=writer) if inputs else None
 
     audio_rec: Optional[AudioRecorder] = None
     if audio:
         if AudioRecorder is None:
             typer.echo("[conanbot] audio recorder unavailable (sounddevice missing)", err=True)
         else:
             device_spec: Optional[object]
             if audio_device is None:
                 device_spec = None
             else:
                 try:
                     device_spec = int(audio_device)
                 except ValueError:
                     device_spec = audio_device
             try:
                 audio_rec = AudioRecorder(
                     session=name,
                     session_dir=session_dir,
                     events_writer=writer,
                     device=device_spec,
                     chunk_duration=audio_chunk,
                 )
                 audio_rec.start()
             except Exception as exc:  # pragma: no cover - runtime feedback
                 typer.echo(f"[conanbot] failed to start audio recorder: {exc}", err=True)
                 audio_rec = None
 
     # Graceful shutdown
     stop_event = threading.Event()
 
     def _stop(*_):
         stop_event.set()
         screen.stop()
         if input_rec:
             input_rec.stop()
         if audio_rec:
             audio_rec.stop()
         writer.close()
 
     signal.signal(signal.SIGINT, _stop)
     signal.signal(signal.SIGTERM, _stop)
 
     # Start
     t_screen = threading.Thread(target=screen.run, daemon=True)
     t_screen.start()
     if input_rec:
         input_rec.start()
     if audio_rec:
         typer.echo("[conanbot] Audio recorder active")
 
     typer.echo(f"[conanbot] Recording session '{name}' → {session_dir}")
     typer.echo("Press Ctrl+C to stop.")
 
     try:
         while not stop_event.is_set():
             stop_event.wait(0.25)
     finally:
         _stop()
 
 if __name__ == "__main__":
     app()
