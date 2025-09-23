from __future__ import annotations

import signal
import threading
from typing import Optional

import typer

from core.events import Event, SessionMeta, event_dump
from data_collection.event_writer import JsonlWriter, ensure_dir
from config.paths import ensure_session_io, get_paths, session_events_path

# Prefer new package layout: data_collection/recorders/*.py.
# Legacy aliases are kept for older installations that might still ship the
# recorders as top-level modules.
try:  # pragma: no cover - import path compatibility
    from data_collection.recorders.screen_recorder import ScreenRecorder
except ModuleNotFoundError:  # pragma: no cover - legacy support
    from data_collection.recorders.screen_recorder import ScreenRecorder  # type: ignore

try:  # pragma: no cover - import path compatibility
    from data_collection.recorders.input_recorder import InputRecorder
except ModuleNotFoundError:  # pragma: no cover - legacy support
    from data_collection.recorders.input_recorder import InputRecorder  # type: ignore

try:  # Optional dependency – requires sounddevice
    from data_collection.recorders.audio_recorder import AudioRecorder
except ModuleNotFoundError:  # pragma: no cover - audio capture optional
    AudioRecorder = None  # type: ignore[assignment]


app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def main(
    name: str = typer.Option(..., "--name", "-n", help="Session name, e.g. dev_smoke"),
    fps: int = typer.Option(12, help="Target FPS for screen capture"),
    left: Optional[int] = typer.Option(None, help="Capture region left"),
    top: Optional[int] = typer.Option(None, help="Capture region top"),
    right: Optional[int] = typer.Option(None, help="Capture region right"),
    bottom: Optional[int] = typer.Option(None, help="Capture region bottom"),
    inputs: bool = typer.Option(True, help="Record keyboard/mouse inputs"),
    audio: bool = typer.Option(True, help="Record system audio when available"),
    audio_device: Optional[str] = typer.Option(
        None,
        "--audio-device",
        help="Audio device index or substring, e.g. '2-Realtek(R) Audio'",
    ),
    audio_chunk: float = typer.Option(1.0, help="Audio chunk duration in seconds"),
) -> None:
    """Entry point for the lightweight recording CLI."""

    # Resolve all directories via centralized config
    paths = get_paths()
    ensure_session_io(name)

    session_dir = paths.session_dir(name)
    events_path = session_events_path(name)

    # Ensure events file parent exists (double-safe)
    ensure_dir(session_dir)

    writer = JsonlWriter(events_path, flush_every=25)

    # Write a meta event capturing basic session info
    meta = SessionMeta(name=name)
    if hasattr(meta, "model_dump"):
        meta_payload = meta.model_dump()
    else:  # pragma: no cover - Pydantic v1 fallback
        meta_payload = meta.dict()
    writer.write(event_dump(Event(kind="meta", session=name, data=meta_payload)))

    region = None
    if all(v is not None for v in (left, top, right, bottom)):
        region = (left, top, right, bottom)  # type: ignore[arg-type]

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
            if audio_device is None:
                device_spec: Optional[object] = None
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

    def _stop(*_object: object) -> None:
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
